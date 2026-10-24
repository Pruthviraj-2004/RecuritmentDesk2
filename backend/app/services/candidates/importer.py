"""Candidate file import: standard CSV/XLSX template, tolerant header matching, row validation, duplicate handling, dry-run preview.

The uploaded file is treated as untrusted: size/row/column limits, type sniffed from bytes, macro workbooks refused, formula cells read as values only,
and the stored error report never contains raw file content beyond the offending cell's field name and a short reason.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Any

from email_validator import EmailNotValidError, validate_email
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationFailure
from app.models.candidates import CANDIDATE_STATUSES, Candidate, CandidateImport
from app.services.candidates import service as svc
from app.services.normalization.text import normalize_email_address

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
MAX_COLUMNS = 60
MAX_ERROR_REPORT = 200


@dataclass(frozen=True)
class Spec:
    field: str  # internal field (or "full_name" which is split)
    header: str  # standard template header
    kind: str  # text | email | phone | float | bool | list | url | status | rating | notes
    example: str
    help: str
    aliases: tuple[str, ...] = ()


SPECS: list[Spec] = [
    Spec("first_name", "first_name", "text", "Asha", "Required (or use a single full_name column)", ("firstname", "given_name", "first")),
    Spec("last_name", "last_name", "text", "Verma", "Optional", ("lastname", "surname", "family_name", "last")),
    Spec("full_name", "full_name", "text", "", "Optional alternative to first_name + last_name; split on the first space", ("name", "candidate_name", "candidate", "full_name", "fullname")),
    Spec("email", "email", "email", "asha.verma@example.com", "Required; used to detect duplicates", ("email_id", "email_address", "e_mail", "mail", "emailid")),
    Spec("phone", "phone", "phone", "+91 98765 43210", "Required; 7-15 digits; used to detect duplicates", ("mobile", "mobile_number", "phone_number", "contact", "contact_number", "mobile_no", "phone_no", "contact_no")),
    Spec("current_title", "current_title", "text", "Senior Python Developer", "Current designation", ("designation", "title", "job_title", "current_designation", "role", "current_role")),
    Spec("current_company", "current_company", "text", "Acme Technologies", "Current employer", ("company", "current_employer", "employer", "organization", "organisation", "current_organization")),
    Spec("total_experience", "total_experience_years", "float", "6.5", "Years, 0-60", ("total_experience", "experience", "total_exp", "exp", "years_of_experience", "yoe", "experience_years")),
    Spec("relevant_experience", "relevant_experience_years", "float", "4", "Years, 0-60", ("relevant_experience", "relevant_exp", "relevant_years")),
    Spec("skills", "skills", "list", "Python; Django; AWS", "Separate with comma, semicolon or |", ("skill_set", "key_skills", "primary_skills", "technologies", "skillset", "tech_stack", "skill")),
    Spec("current_location", "current_location", "text", "Bengaluru", "City / location", ("location", "city", "current_city")),
    Spec("preferred_locations", "preferred_locations", "list", "Pune; Hyderabad", "Separate with comma, semicolon or |", ("preferred_location", "preferred_city", "preferred_cities", "preferred_loc")),
    Spec("willing_to_relocate", "willing_to_relocate", "bool", "yes", "yes / no", ("relocate", "open_to_relocation", "relocation")),
    Spec("notice_period", "notice_period", "text", "30 days", "Free text, e.g. 30 days / Immediate", ("notice", "np", "notice_period_days")),
    Spec("current_ctc", "current_ctc", "float", "1800000", "Number", ("ctc", "current_salary", "current_package", "ctc_lpa", "current_compensation")),
    Spec("expected_ctc", "expected_ctc", "float", "2400000", "Number", ("ectc", "expected_salary", "expected_package", "expected_ctc_lpa", "expected_compensation")),
    Spec("currency", "currency", "text", "INR", "3-letter code", ("curr",)),
    Spec("education", "education", "text", "B.Tech Computer Science", "Highest qualification", ("qualification", "highest_qualification", "degree")),
    Spec("certifications", "certifications", "list", "AWS SAA; PMP", "Separate with comma, semicolon or |", ("certification", "certs")),
    Spec("work_authorization", "work_authorization", "text", "Indian citizen", "Visa / work permit status", ("visa", "visa_status", "work_permit", "authorization")),
    Spec("linkedin_url", "linkedin_url", "url", "https://www.linkedin.com/in/asha-verma", "Must be a web address", ("linkedin", "linkedin_profile", "linkedin_link")),
    Spec("resume_url", "resume_url", "url", "https://drive.example.com/asha-cv", "Link to the resume (the file itself is not uploaded)", ("resume", "cv_link", "cv_url", "resume_link", "cv")),
    Spec("summary", "summary", "text", "Backend engineer with 6 years in fintech", "Profile summary", ("profile_summary", "about", "headline")),
    Spec("status", "status", "status", "new", "One of: " + ", ".join(CANDIDATE_STATUSES), ("stage", "candidate_status")),
    Spec("rating", "rating", "rating", "4", "1 to 5", ("score",)),
    Spec("tags", "tags", "list", "referral; priority", "Separate with comma, semicolon or |", ("labels", "tag")),
    Spec("source", "source", "text", "LinkedIn", "Where you found the candidate (default: import)", ("source_of_hire", "sourced_from")),
    Spec("notes", "notes", "notes", "Spoke on 12 Oct, interested", "Saved as the first note on the profile", ("remarks", "comments", "note", "comment")),
]
STANDARD_HEADERS = [s.header for s in SPECS if s.field != "full_name"]
_HEADER_MAP: dict[str, Spec] = {}
for _s in SPECS:
    for _k in {_s.header, _s.field, *_s.aliases}:
        _HEADER_MAP[_k] = _s


def norm_header(h: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(h or "").strip().lower()).strip("_")


# ---------------------------------------------------------------- template
def build_template(fmt: str, examples_rows: bool = True) -> tuple[bytes, str, str]:
    """Returns (bytes, filename, media type). With examples_rows=True two example rows show the expected formats; False gives headers only."""
    examples = [[s.example for s in SPECS if s.field != "full_name"],
                ["Rahul", "Mehta", "rahul.mehta@example.com", "9123456780", "Data Engineer", "Globex", "3", "3", "Python, Spark, SQL", "Pune", "Mumbai", "no", "Immediate", "900000", "1300000", "INR",
                 "MCA", "", "Indian citizen", "", "", "", "screening", "3", "", "Campaign", ""]]
    if not examples_rows:
        examples = []
    suffix = "" if examples_rows else "-blank"
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(STANDARD_HEADERS)
        w.writerows(examples)
        return ("﻿" + buf.getvalue()).encode("utf-8"), f"candidate-import-template{suffix}.csv", "text/csv"
    wb = Workbook()
    ws = wb.active
    ws.title = "Candidates"
    ws.append(STANDARD_HEADERS)
    for row in examples:
        ws.append(row)
    fill = PatternFill("solid", start_color="C2410C")
    for i, h in enumerate(STANDARD_HEADERS, 1):
        c = ws.cell(row=1, column=i)
        c.font, c.fill, c.alignment = Font(bold=True, color="FFFFFF"), fill, Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = max(16, len(h) + 4)
    ws.freeze_panes = "A2"
    info = wb.create_sheet("Instructions")
    info.append(["Column", "Required", "Format / allowed values", "Example"])
    for c in info[1]:
        c.font = Font(bold=True)
    for s in SPECS:
        if s.field == "full_name":
            continue
        info.append([s.header, "Yes" if s.field in ("first_name", "email", "phone") else "No (optional)", s.help, s.example])
    info.append([])
    info.append(["Name (first_name or full_name), email and phone are required for every candidate; all other columns are optional. Replace the two example rows with your candidates (keep the header row). Extra columns are ignored."])
    info.append(["Duplicates are detected by email and phone number. Choose to skip them or update the existing profile when you upload."])
    for col, w in zip("ABCD", (26, 28, 60, 40)):
        info.column_dimensions[col].width = w
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), f"candidate-import-template{suffix}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------- reading
def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def read_rows(filename: str, data: bytes) -> tuple[list[str], list[list[str]]]:
    """Return (raw headers, data rows). Raises ValidationFailure for unusable files."""
    if not data:
        raise ValidationFailure("The file is empty")
    if len(data) > MAX_BYTES:
        raise ValidationFailure(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB")
    name = (filename or "").lower()
    if name.endswith((".xlsm", ".xlsb", ".xls")):
        raise ValidationFailure("Please save the file as .xlsx or .csv (macro-enabled and legacy Excel formats are not accepted)")
    is_zip = data[:4] == b"PK\x03\x04"
    if name.endswith(".xlsx") or is_zip:
        return _read_xlsx(data)
    if name.endswith((".csv", ".txt", ".tsv")) or b"\x00" not in data[:2048]:
        return _read_csv(data)
    raise ValidationFailure("Unsupported file type. Upload a .csv or .xlsx file")


def _read_xlsx(data: bytes) -> tuple[list[str], list[list[str]]]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if "xl/workbook.xml" not in names:
                raise ValidationFailure("This zip file is not an Excel workbook")
            if any(n.lower().endswith("vbaproject.bin") for n in names):
                raise ValidationFailure("Workbooks with macros are not accepted")
            if sum(i.file_size for i in zf.infolist()) > 80 * 1024 * 1024:
                raise ValidationFailure("The workbook expands beyond allowed limits")
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except ValidationFailure:
        raise
    except Exception as e:  # noqa: BLE001
        raise ValidationFailure("The Excel file could not be read; is it a valid .xlsx file?") from e
    ws = wb["Candidates"] if "Candidates" in wb.sheetnames else wb.worksheets[0]
    rows: list[list[str]] = []
    for r in ws.iter_rows(values_only=True):
        cells = [_cell(c) for c in r[:MAX_COLUMNS]]
        if any(cells):
            rows.append(cells)
        if len(rows) > MAX_ROWS + 1:
            raise ValidationFailure(f"Too many rows: at most {MAX_ROWS} candidates per file")
    wb.close()
    if not rows:
        raise ValidationFailure("The file has no data")
    return rows[0], rows[1:]


def _read_csv(data: bytes) -> tuple[list[str], list[list[str]]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows: list[list[str]] = []
    for r in csv.reader(io.StringIO(text), dialect):
        cells = [c.strip() for c in r[:MAX_COLUMNS]]
        if any(cells):
            rows.append(cells)
        if len(rows) > MAX_ROWS + 1:
            raise ValidationFailure(f"Too many rows: at most {MAX_ROWS} candidates per file")
    if not rows:
        raise ValidationFailure("The file has no data")
    return rows[0], rows[1:]


def map_headers(raw: list[str]) -> tuple[dict[int, Spec], list[str], list[str]]:
    """Return ({column index: spec}, unrecognised headers, problems). Column order and unknown extra columns do not matter."""
    mapping: dict[int, Spec] = {}
    seen: set[str] = set()
    unknown: list[str] = []
    for i, h in enumerate(raw):
        spec = _HEADER_MAP.get(norm_header(h))
        if spec is None:
            if str(h).strip():
                unknown.append(str(h)[:60])
            continue
        if spec.field in seen:
            continue  # first matching column wins
        seen.add(spec.field)
        mapping[i] = spec
    problems = []
    fields = {s.field for s in mapping.values()}
    if not ({"first_name", "full_name"} & fields):
        problems.append("No name column found. Add first_name (and last_name) or a name/full_name column.")
    for needed, label in (("email", "email"), ("phone", "phone")):
        if needed not in fields:
            problems.append(f"No {label} column found. Name, email and phone are all required.")
    return mapping, unknown, problems


# ---------------------------------------------------------------- row parsing
_TRUE, _FALSE = {"yes", "y", "true", "1", "open", "willing"}, {"no", "n", "false", "0", "not willing"}
_STATUS_SYN = {"in_progress": "screening", "interview": "interviewing", "interviewed": "interviewing", "selected": "shortlisted", "joined": "hired", "dropped": "not_interested", "hold": "on_hold"}


def _split(v: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,;|\n]", v) if p.strip()]


def _number(v: str) -> float | None:
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", v)
    return float(m.group(0).replace(",", "")) if m else None


@dataclass
class RowResult:
    row: int
    name: str
    email: str | None
    action: str = "create"  # create | update | skip_duplicate | skip_in_file | error
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    values: dict = field(default_factory=dict)
    note: str | None = None
    matched_id: uuid.UUID | None = None
    matched_name: str | None = None

    def public(self) -> dict:
        return {"row": self.row, "name": self.name, "email": self.email, "action": self.action, "errors": self.errors, "warnings": self.warnings,
                "matched_name": self.matched_name}


def parse_row(row_no: int, cells: list[str], mapping: dict[int, Spec]) -> RowResult:
    raw: dict[str, str] = {}
    for idx, spec in mapping.items():
        if idx < len(cells) and cells[idx].strip():
            raw[spec.field] = cells[idx].strip()
    res = RowResult(row=row_no, name="", email=None)
    vals: dict[str, Any] = {}
    errs, warns = res.errors, res.warnings
    for spec in mapping.values():
        v = raw.get(spec.field)
        if v is None or spec.field == "full_name":
            continue
        try:
            if spec.kind == "text":
                vals[spec.field] = v[: svc.MAX_LEN.get(spec.field, 2000)]
            elif spec.kind == "email":
                try:
                    vals["email"] = validate_email(v, check_deliverability=False).normalized.lower()
                except EmailNotValidError:
                    errs.append("email is not a valid address")
            elif spec.kind == "phone":
                if svc.normalize_phone(v):
                    vals["phone"] = v[:50]
                else:
                    errs.append("phone needs 7-15 digits")
            elif spec.kind == "float":
                n = _number(v)
                if n is None:
                    errs.append(f"{spec.header} must be a number")
                elif spec.field.endswith("experience") and not (0 <= n <= 60):
                    errs.append(f"{spec.header} must be between 0 and 60")
                elif n < 0:
                    errs.append(f"{spec.header} cannot be negative")
                else:
                    vals[spec.field] = n
            elif spec.kind == "bool":
                lv = v.lower()
                if lv in _TRUE:
                    vals[spec.field] = True
                elif lv in _FALSE:
                    vals[spec.field] = False
                else:
                    warns.append(f"{spec.header}: '{v[:20]}' not understood (use yes/no); ignored")
            elif spec.kind == "list":
                vals[spec.field] = _split(v)
            elif spec.kind == "url":
                u = v
                if not re.match(r"^https?://", u, re.I) and re.match(r"^(www\.|[\w-]+\.[a-z]{2,}/)", u, re.I):
                    u = "https://" + u
                if re.match(r"^https?://\S+$", u, re.I):
                    vals[spec.field] = u[:500]
                else:
                    errs.append(f"{spec.header} must be a web address starting with http(s)://")
            elif spec.kind == "status":
                s = re.sub(r"[^a-z]+", "_", v.lower()).strip("_")
                s = _STATUS_SYN.get(s, s)
                if s in CANDIDATE_STATUSES:
                    vals["status"] = s
                else:
                    warns.append(f"status '{v[:20]}' is not recognised; set to 'new'")
            elif spec.kind == "rating":
                n = _number(v)
                if n is not None and 1 <= n <= 5 and float(n).is_integer():
                    vals["rating"] = int(n)
                else:
                    errs.append("rating must be a whole number from 1 to 5")
            elif spec.kind == "notes":
                res.note = v[:5000]
        except Exception:  # noqa: BLE001 - never let one odd cell abort the file
            errs.append(f"{spec.header} could not be read")
    first, last = vals.get("first_name"), vals.get("last_name")
    if not first and raw.get("full_name"):
        parts = raw["full_name"].split(None, 1)
        first, last = parts[0][:120], (parts[1][:120] if len(parts) > 1 else last)
        vals["first_name"], vals["last_name"] = first, last
    if not first:
        errs.append("name is missing")
    if "email" not in vals and not any("email" in e for e in errs):
        errs.append("email is required")
    if "phone" not in vals and not any("phone" in e for e in errs):
        errs.append("phone is required")
    vals.setdefault("source", "import")
    res.values = vals
    res.name = " ".join(p for p in (first, last) if p)
    res.email = vals.get("email")
    if errs:
        res.action = "error"
    return res


# ---------------------------------------------------------------- analysis & commit
@dataclass
class Analysis:
    total: int
    rows: list[RowResult]
    unknown_headers: list[str]
    recognised: list[str]

    def counts(self) -> dict:
        c = {"create": 0, "update": 0, "skip_duplicate": 0, "skip_in_file": 0, "error": 0}
        for r in self.rows:
            c[r.action] += 1
        return c


def analyse(db: Session, org_id: uuid.UUID, filename: str, data: bytes, on_duplicate: str) -> Analysis:
    if on_duplicate not in ("skip", "update"):
        raise ValidationFailure("on_duplicate must be 'skip' or 'update'")
    raw_headers, data_rows = read_rows(filename, data)
    mapping, unknown, problems = map_headers(raw_headers)
    if problems:
        raise ValidationFailure(" ".join(problems) + " Download the template to see the expected columns.", code="invalid_template")
    results = [parse_row(i + 2, cells, mapping) for i, cells in enumerate(data_rows)]
    emails = {normalize_email_address(r.email) for r in results if r.email}
    phones = {svc.normalize_phone(r.values.get("phone")) for r in results if r.values.get("phone")} - {None}
    by_email: dict[str, Candidate] = {}
    by_phone: dict[str, Candidate] = {}
    if emails or phones:
        conds = []
        if emails:
            conds.append(Candidate.email_normalized.in_(emails))
        if phones:
            conds.append(Candidate.phone_normalized.in_(phones))
        from sqlalchemy import or_

        for c in db.scalars(select(Candidate).where(Candidate.organization_id == org_id, or_(*conds))):
            if c.email_normalized:
                by_email[c.email_normalized] = c
            if c.phone_normalized:
                by_phone[c.phone_normalized] = c
    seen_email: dict[str, int] = {}
    seen_phone: dict[str, int] = {}
    for r in results:
        if r.action == "error":
            continue
        e = normalize_email_address(r.email) if r.email else None
        p = svc.normalize_phone(r.values.get("phone")) if r.values.get("phone") else None
        first = (e and seen_email.get(e)) or (p and seen_phone.get(p))
        if first:
            r.action = "skip_in_file"
            r.warnings.append(f"Same email/phone as row {first} in this file; skipped")
            continue
        if e:
            seen_email[e] = r.row
        if p:
            seen_phone[p] = r.row
        match = (e and by_email.get(e)) or (p and by_phone.get(p))
        if match:
            r.matched_id, r.matched_name = match.id, match.full_name
            r.action = "update" if on_duplicate == "update" else "skip_duplicate"
    return Analysis(total=len(results), rows=results, unknown_headers=unknown, recognised=sorted({s.header for s in mapping.values()}))


def commit(db: Session, org_id: uuid.UUID, user_id: uuid.UUID, filename: str, analysis: Analysis, on_duplicate: str) -> CandidateImport:
    imp = CandidateImport(organization_id=org_id, filename=filename[:300], on_duplicate=on_duplicate, total_rows=analysis.total, created_by=user_id, error_report=[])
    db.add(imp)
    db.flush()
    report: list[dict] = []
    for r in analysis.rows:
        if r.action in ("error", "skip_in_file", "skip_duplicate"):
            if r.action == "error":
                imp.failed_count += 1
            else:
                imp.skipped_count += 1
            if len(report) < MAX_ERROR_REPORT:
                report.append({"row": r.row, "name": r.name, "action": r.action, "problems": r.errors + r.warnings})
            continue
        try:
            with db.begin_nested():
                if r.action == "update" and r.matched_id:
                    cand = svc.get_candidate(db, org_id, r.matched_id)
                    # identity fields (name, email, phone) are never changed by an update: they are how the profile was matched
                    svc.apply_fields(cand, {k: v for k, v in r.values.items() if k not in ("source", "email", "phone", "first_name", "last_name")}, merge=True)
                    cand.updated_by = user_id
                    imp.updated_count += 1
                else:
                    cand = svc.create_candidate(db, org_id, r.values, user_id=user_id, check_duplicates=False, import_id=imp.id)
                    imp.created_count += 1
                if r.note:
                    svc.add_note(db, cand, r.note, user_id=user_id)
        except Exception as e:  # noqa: BLE001 - one bad row must not abort the batch
            imp.failed_count += 1
            if r.action == "update":
                imp.updated_count -= 1
            else:
                imp.created_count -= 1
            if len(report) < MAX_ERROR_REPORT:
                report.append({"row": r.row, "name": r.name, "action": "error", "problems": [f"could not be saved ({type(e).__name__})"]})
    imp.error_report = report
    db.flush()
    return imp
