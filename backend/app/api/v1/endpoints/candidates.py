from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, File, Form, Query, Response, UploadFile
from sqlalchemy import Text, cast, exists, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import Ctx, member, viewer
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailure
from app.db.types import utcnow
from app.models.auth import User
from app.models.candidates import (
    CANDIDATE_STATUSES,
    Candidate,
    CandidateImport,
    CandidateNote,
    CandidateSkill,
    CandidateSubmission,
)
from app.models.requirements import JobRequirement
from app.schemas.candidates import (
    BulkIn,
    CandidateCreate,
    CandidateOut,
    CandidatePatch,
    ApplyIn,
    ExportIn,
    MatchOut,
    NoteIn,
    NoteOut,
    SubmissionIn,
    SubmissionOut,
    SubmissionPatch,
)
from app.schemas.api import Page
from app.services.audit import service as audit
from app.core.security import rate_limiter
from app.models.candidate_ai import CandidateAIProfile
from app.services.candidates import ai_profile as ai
from app.services.candidates import importer, matching
from app.services.gmail.attachments import parse_attachment
from app.services.candidates import service as svc
from app.services.candidates.export import build_workbook
from app.services.normalization.text import normalize_skill

router = APIRouter(tags=["candidates"])
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------- helpers
def to_out(c: Candidate, pipeline: int = 0) -> CandidateOut:
    return CandidateOut(
        id=c.id, first_name=c.first_name, last_name=c.last_name, full_name=c.full_name, email=c.email, phone=c.phone, current_title=c.current_title,
        current_company=c.current_company, total_experience=c.total_experience, relevant_experience=c.relevant_experience, current_location=c.current_location,
        preferred_locations=c.preferred_locations or [], willing_to_relocate=c.willing_to_relocate, notice_period=c.notice_period,
        current_ctc=float(c.current_ctc) if c.current_ctc is not None else None, expected_ctc=float(c.expected_ctc) if c.expected_ctc is not None else None,
        currency=c.currency, education=c.education, certifications=c.certifications or [], work_authorization=c.work_authorization, linkedin_url=c.linkedin_url,
        resume_url=c.resume_url, summary=c.summary, source=c.source, status=c.status, rating=c.rating, tags=c.tags or [], skills=c.skill_names, is_archived=c.is_archived,
        last_contacted_at=c.last_contacted_at, created_at=c.created_at, updated_at=c.updated_at, pipeline_count=pipeline)


def _pipeline_counts(ctx: Ctx, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    return dict(ctx.db.execute(select(CandidateSubmission.candidate_id, func.count()).where(CandidateSubmission.candidate_id.in_(ids)).group_by(CandidateSubmission.candidate_id)).all())


def _escape(v: str) -> str:
    return v.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def apply_filters(stmt, org_id: uuid.UUID, f: dict):
    C = Candidate
    stmt = stmt.where(C.organization_id == org_id)
    stmt = stmt.where(C.is_archived.is_(bool(f.get("archived"))))
    if f.get("status"):
        stmt = stmt.where(C.status == f["status"])
    if f.get("source"):
        stmt = stmt.where(C.source == f["source"])
    if f.get("location"):
        like = f"%{_escape(f['location'])}%"
        stmt = stmt.where(or_(C.current_location.ilike(like, escape="\\"), cast(C.preferred_locations, Text).ilike(like, escape="\\")))
    if f.get("exp_min") is not None:
        stmt = stmt.where(C.total_experience >= float(f["exp_min"]))
    if f.get("exp_max") is not None:
        stmt = stmt.where(C.total_experience <= float(f["exp_max"]))
    if f.get("rating_min") is not None:
        stmt = stmt.where(C.rating >= int(f["rating_min"]))
    if f.get("notice"):
        stmt = stmt.where(C.notice_period.ilike(f"%{_escape(f['notice'])}%", escape="\\"))
    if f.get("tag"):
        stmt = stmt.where(cast(C.tags, Text).ilike(f'%"{_escape(f["tag"])}"%', escape="\\"))
    if f.get("skill"):
        norm = normalize_skill(f["skill"])
        stmt = stmt.where(exists().where(CandidateSkill.candidate_id == C.id, CandidateSkill.normalized == norm))
    if f.get("q"):
        like = f"%{_escape(f['q'].strip())}%"
        conds = [col.ilike(like, escape="\\") for col in (C.full_name, C.email, C.phone, C.current_title, C.current_company, C.current_location)]
        conds.append(cast(C.tags, Text).ilike(like, escape="\\"))
        conds.append(exists().where(CandidateSkill.candidate_id == C.id, CandidateSkill.normalized.ilike(f"%{_escape(normalize_skill(f['q']))}%", escape="\\")))
        stmt = stmt.where(or_(*conds))
    return stmt


SORTS = {"created_at": Candidate.created_at, "updated_at": Candidate.updated_at, "full_name": Candidate.full_name, "total_experience": Candidate.total_experience,
         "expected_ctc": Candidate.expected_ctc, "status": Candidate.status, "rating": Candidate.rating}


# ---------------------------------------------------------------- static routes (declared before /{candidate_id})
@router.get("/candidates/stats")
def stats(ctx: Ctx = viewer):
    C = Candidate
    base = (C.organization_id == ctx.org_id, C.is_archived.is_(False))
    total = ctx.db.scalar(select(func.count()).select_from(C).where(*base)) or 0
    by_status = dict(ctx.db.execute(select(C.status, func.count()).where(*base).group_by(C.status)).all())
    week = ctx.db.scalar(select(func.count()).select_from(C).where(*base, C.created_at >= utcnow() - timedelta(days=7))) or 0
    in_pipeline = ctx.db.scalar(select(func.count(func.distinct(CandidateSubmission.candidate_id))).where(CandidateSubmission.organization_id == ctx.org_id)) or 0
    return {"total": total, "new_this_week": week, "in_pipeline": in_pipeline, "by_status": by_status}


@router.get("/candidates/import/template")
def import_template(ctx: Ctx = viewer, format: str = Query("xlsx", pattern="^(csv|xlsx)$"), examples: bool = True):
    data, name, mime = importer.build_template(format, examples)
    return Response(content=data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


def _read_upload(file: UploadFile) -> bytes:
    data = file.file.read(importer.MAX_BYTES + 1)
    if len(data) > importer.MAX_BYTES:
        raise ValidationFailure(f"File is larger than {importer.MAX_BYTES // (1024 * 1024)} MB")
    return data


@router.post("/candidates/import/preview")
def import_preview(file: UploadFile = File(...), on_duplicate: str = Form("skip"), ctx: Ctx = member):
    """Dry run: validates every row and reports what would happen. Nothing is saved."""
    a = importer.analyse(ctx.db, ctx.org_id, file.filename or "upload", _read_upload(file), on_duplicate)
    problems = [r.public() for r in a.rows if r.action != "create"]
    return {"total_rows": a.total, "counts": a.counts(), "recognised_columns": a.recognised, "ignored_columns": a.unknown_headers,
            "problems": problems[:100], "sample": [r.public() for r in a.rows if r.action == "create"][:10], "truncated": len(problems) > 100}


@router.post("/candidates/import", status_code=201)
def import_commit(file: UploadFile = File(...), on_duplicate: str = Form("skip"), ctx: Ctx = member):
    name = file.filename or "upload"
    a = importer.analyse(ctx.db, ctx.org_id, name, _read_upload(file), on_duplicate)
    if a.counts()["create"] + a.counts()["update"] == 0:
        raise ValidationFailure("There is nothing to import: every row was invalid or a duplicate. Run the check to see why.", code="nothing_to_import")
    imp = importer.commit(ctx.db, ctx.org_id, ctx.user_id, name, a, on_duplicate)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="candidates.imported", entity_type="candidate_import", entity_id=imp.id,
                 metadata={"file": name[:100], "created": imp.created_count, "updated": imp.updated_count, "skipped": imp.skipped_count, "failed": imp.failed_count})
    ctx.db.commit()
    return {"id": str(imp.id), "filename": imp.filename, "total_rows": imp.total_rows, "created": imp.created_count, "updated": imp.updated_count,
            "skipped": imp.skipped_count, "failed": imp.failed_count, "problems": imp.error_report}


@router.get("/candidates/imports")
def import_history(ctx: Ctx = viewer, limit: int = Query(10, ge=1, le=50)):
    rows = ctx.db.scalars(select(CandidateImport).where(CandidateImport.organization_id == ctx.org_id).order_by(CandidateImport.created_at.desc()).limit(limit))
    return [{"id": str(i.id), "filename": i.filename, "created_at": i.created_at, "total_rows": i.total_rows, "created": i.created_count, "updated": i.updated_count,
             "skipped": i.skipped_count, "failed": i.failed_count, "on_duplicate": i.on_duplicate, "problems": i.error_report} for i in rows]


@router.post("/candidates/export")
def export(body: ExportIn, ctx: Ctx = viewer):
    stmt = select(Candidate).options(selectinload(Candidate.skills))
    if body.ids:
        stmt = stmt.where(Candidate.organization_id == ctx.org_id, Candidate.id.in_(body.ids))
    else:
        stmt = apply_filters(stmt, ctx.org_id, body.filters or {})
    rows = list(ctx.db.scalars(stmt.order_by(Candidate.full_name).limit(5001)))
    if not rows:
        raise ValidationFailure("No candidates match this export")
    if len(rows) > 5000:
        raise ValidationFailure("Export is limited to 5000 candidates; narrow the filters")
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="candidates.exported", metadata={"count": len(rows)})
    ctx.db.commit()
    return Response(content=build_workbook(rows), media_type=XLSX_MIME, headers={
        "Content-Disposition": f'attachment; filename="candidates-{utcnow():%Y-%m-%d}.xlsx"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/candidates/bulk")
def bulk(body: BulkIn, ctx: Ctx = member):
    if body.action == "set_status" and body.value not in CANDIDATE_STATUSES:
        raise ValidationFailure(f"value must be one of {CANDIDATE_STATUSES}")
    if body.action in ("add_tag", "remove_tag") and not (body.value or "").strip():
        raise ValidationFailure("A tag is required")
    ok: list[uuid.UUID] = []
    failed: list[dict] = []
    for cid in dict.fromkeys(body.ids):
        try:
            c = svc.get_candidate(ctx.db, ctx.org_id, cid)
            if body.action == "set_status":
                svc.update_candidate(ctx.db, c, {"status": body.value}, user_id=ctx.user_id)
            elif body.action == "add_tag":
                c.tags = svc.clean_list((c.tags or []) + [body.value])
            elif body.action == "remove_tag":
                c.tags = [t for t in (c.tags or []) if t.lower() != body.value.strip().lower()]
            elif body.action == "archive":
                c.is_archived = True
            elif body.action == "restore":
                c.is_archived = False
            elif body.action == "mark_contacted":
                svc.touch_contacted(c)
            c.updated_by = ctx.user_id
            ok.append(cid)
        except NotFoundError:
            failed.append({"id": str(cid), "error": "Candidate not found"})
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action=f"candidates.bulk_{body.action}", metadata={"count": len(ok), "value": body.value})
    ctx.db.commit()
    return {"succeeded": ok, "failed": failed}


# ---------------------------------------------------------------- list / create
@router.get("/candidates", response_model=Page[CandidateOut])
def list_candidates(ctx: Ctx = viewer, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200), q: str | None = Query(None, max_length=200), status: str | None = None,
                    skill: str | None = None, location: str | None = None, exp_min: float | None = None, exp_max: float | None = None, notice: str | None = None,
                    source: str | None = None, tag: str | None = None, rating_min: int | None = Query(None, ge=1, le=5), archived: bool = False,
                    sort: str = "created_at", direction: str = Query("desc", pattern="^(asc|desc)$")):
    f = {"q": q, "status": status, "skill": skill, "location": location, "exp_min": exp_min, "exp_max": exp_max, "notice": notice, "source": source, "tag": tag,
         "rating_min": rating_min, "archived": archived}
    base = apply_filters(select(Candidate), ctx.org_id, f)
    total = ctx.db.scalar(select(func.count()).select_from(base.subquery())) or 0
    col = SORTS.get(sort, Candidate.created_at)
    order = (col.asc() if direction == "asc" else col.desc()).nullslast()
    rows = list(ctx.db.scalars(base.options(selectinload(Candidate.skills)).order_by(order, Candidate.id).limit(page_size).offset((page - 1) * page_size)))
    counts = _pipeline_counts(ctx, [r.id for r in rows])
    return Page(items=[to_out(r, counts.get(r.id, 0)) for r in rows], total=total, page=page, page_size=page_size)


@router.post("/candidates", response_model=CandidateOut, status_code=201)
def create(body: CandidateCreate, ctx: Ctx = member):
    values = body.model_dump(exclude_unset=True, exclude={"initial_note"})
    c = svc.create_candidate(ctx.db, ctx.org_id, values, user_id=ctx.user_id)
    if body.initial_note:
        svc.add_note(ctx.db, c, body.initial_note, user_id=ctx.user_id)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="candidate.created", entity_type="candidate", entity_id=c.id, metadata={"name": c.full_name})
    ctx.db.commit()
    return to_out(svc.get_candidate(ctx.db, ctx.org_id, c.id))


# ---------------------------------------------------------------- one candidate
@router.get("/candidates/{candidate_id}", response_model=CandidateOut)
def get_one(candidate_id: uuid.UUID, ctx: Ctx = viewer):
    c = svc.get_candidate(ctx.db, ctx.org_id, candidate_id)
    return to_out(c, _pipeline_counts(ctx, [c.id]).get(c.id, 0))


@router.patch("/candidates/{candidate_id}", response_model=CandidateOut)
def patch(candidate_id: uuid.UUID, body: CandidatePatch, ctx: Ctx = member):
    c = svc.get_candidate(ctx.db, ctx.org_id, candidate_id)
    data = body.model_dump(exclude_unset=True)
    svc.update_candidate(ctx.db, c, data, user_id=ctx.user_id)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="candidate.updated", entity_type="candidate", entity_id=c.id, metadata={"fields": sorted(data)})
    ctx.db.commit()
    c = svc.get_candidate(ctx.db, ctx.org_id, candidate_id)
    return to_out(c, _pipeline_counts(ctx, [c.id]).get(c.id, 0))


@router.delete("/candidates/{candidate_id}")
def archive(candidate_id: uuid.UUID, ctx: Ctx = member):
    """Archives (soft delete) so notes and pipeline history are never lost by accident."""
    c = svc.get_candidate(ctx.db, ctx.org_id, candidate_id)
    c.is_archived = True
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="candidate.archived", entity_type="candidate", entity_id=c.id)
    ctx.db.commit()
    return {"archived": True}


@router.post("/candidates/{candidate_id}/restore", response_model=CandidateOut)
def restore(candidate_id: uuid.UUID, ctx: Ctx = member):
    c = svc.get_candidate(ctx.db, ctx.org_id, candidate_id)
    c.is_archived = False
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="candidate.restored", entity_type="candidate", entity_id=c.id)
    ctx.db.commit()
    return to_out(svc.get_candidate(ctx.db, ctx.org_id, candidate_id))


@router.get("/candidates/{candidate_id}/notes", response_model=list[NoteOut])
def notes(candidate_id: uuid.UUID, ctx: Ctx = viewer):
    svc.get_candidate(ctx.db, ctx.org_id, candidate_id)
    rows = ctx.db.execute(select(CandidateNote, User.display_name).join(User, User.id == CandidateNote.author_user_id, isouter=True)
                          .where(CandidateNote.candidate_id == candidate_id).order_by(CandidateNote.created_at.desc())).all()
    return [NoteOut(id=n.id, kind=n.kind, body=n.body, author=name, created_at=n.created_at) for n, name in rows]


@router.post("/candidates/{candidate_id}/notes", response_model=NoteOut, status_code=201)
def add_note(candidate_id: uuid.UUID, body: NoteIn, ctx: Ctx = member):
    c = svc.get_candidate(ctx.db, ctx.org_id, candidate_id)
    n = svc.add_note(ctx.db, c, body.body, user_id=ctx.user_id)
    svc.touch_contacted(c)
    ctx.db.commit()
    return NoteOut(id=n.id, kind=n.kind, body=n.body, author=ctx.user.display_name, created_at=n.created_at)


# ---------------------------------------------------------------- pipeline & matching
def _sub_out(s: CandidateSubmission, req: JobRequirement | None = None) -> SubmissionOut:
    return SubmissionOut(id=s.id, stage=s.stage, notes=s.notes, created_at=s.created_at, updated_at=s.updated_at, candidate_id=s.candidate_id, candidate_name=s.candidate.full_name,
                         candidate_title=s.candidate.current_title, requirement_id=s.requirement_id, requirement_title=req.job_title if req else None,
                         requirement_client=req.client_name if req else None)


def _get_sub(ctx: Ctx, sid: uuid.UUID) -> CandidateSubmission:
    s = ctx.db.scalar(select(CandidateSubmission).options(selectinload(CandidateSubmission.candidate)).where(CandidateSubmission.id == sid, CandidateSubmission.organization_id == ctx.org_id))
    if not s:
        raise NotFoundError("Pipeline entry not found")
    return s


@router.get("/candidates/{candidate_id}/submissions", response_model=list[SubmissionOut])
def candidate_submissions(candidate_id: uuid.UUID, ctx: Ctx = viewer):
    svc.get_candidate(ctx.db, ctx.org_id, candidate_id)
    rows = ctx.db.execute(select(CandidateSubmission, JobRequirement).options(selectinload(CandidateSubmission.candidate))
                          .join(JobRequirement, JobRequirement.id == CandidateSubmission.requirement_id).where(CandidateSubmission.candidate_id == candidate_id)
                          .order_by(CandidateSubmission.updated_at.desc())).all()
    return [_sub_out(s, r) for s, r in rows]


@router.post("/candidates/{candidate_id}/submissions", response_model=SubmissionOut, status_code=201)
def add_submission(candidate_id: uuid.UUID, body: SubmissionIn, ctx: Ctx = member):
    c = svc.get_candidate(ctx.db, ctx.org_id, candidate_id)
    req = ctx.db.scalar(select(JobRequirement).where(JobRequirement.id == body.requirement_id, JobRequirement.organization_id == ctx.org_id))
    if not req:
        raise NotFoundError("Requirement not found")
    if ctx.db.scalar(select(CandidateSubmission.id).where(CandidateSubmission.candidate_id == c.id, CandidateSubmission.requirement_id == req.id)):
        raise ConflictError(f"{c.full_name} is already in the pipeline for this requirement", code="already_in_pipeline")
    s = CandidateSubmission(organization_id=ctx.org_id, candidate_id=c.id, requirement_id=req.id, stage=body.stage, notes=body.notes, created_by=ctx.user_id)
    s.candidate = c
    ctx.db.add(s)
    ctx.db.flush()
    svc.add_note(ctx.db, c, f"Added to pipeline for {req.job_title or 'a requirement'} ({req.client_name or 'unknown client'}) as {body.stage}", user_id=ctx.user_id, kind="system")
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="candidate.submitted", entity_type="candidate", entity_id=c.id, metadata={"requirement": str(req.id), "stage": body.stage})
    ctx.db.commit()
    return _sub_out(s, req)


@router.patch("/candidates/submissions/{submission_id}", response_model=SubmissionOut)
def patch_submission(submission_id: uuid.UUID, body: SubmissionPatch, ctx: Ctx = member):
    s = _get_sub(ctx, submission_id)
    data = body.model_dump(exclude_unset=True)
    if "stage" in data and data["stage"] and data["stage"] != s.stage:
        svc.add_note(ctx.db, s.candidate, f"Pipeline stage changed from {s.stage} to {data['stage']}", user_id=ctx.user_id, kind="system")
        s.stage = data["stage"]
    if "notes" in data:
        s.notes = data["notes"]
    req = ctx.db.get(JobRequirement, s.requirement_id)
    ctx.db.commit()
    return _sub_out(s, req)


@router.delete("/candidates/submissions/{submission_id}")
def remove_submission(submission_id: uuid.UUID, ctx: Ctx = member):
    s = _get_sub(ctx, submission_id)
    ctx.db.delete(s)
    ctx.db.commit()
    return {"removed": True}


@router.get("/candidates/{candidate_id}/matching-requirements")
def candidate_matches(candidate_id: uuid.UUID, ctx: Ctx = viewer, limit: int = Query(15, ge=1, le=50)):
    c = svc.get_candidate(ctx.db, ctx.org_id, candidate_id)
    return [{"requirement": {"id": str(r.id), "job_title": r.job_title, "client_name": r.client_name, "location": r.location, "work_mode": r.work_mode,
                             "minimum_experience": r.minimum_experience, "maximum_experience": r.maximum_experience, "required_skills": r.required_skills},
             **MatchOut(score=m.score, matched_skills=m.matched_skills, missing_skills=m.missing_skills, reasons=m.reasons, stage=stage, ai_profile_used=m.ai_profile_used, ai_only_matches=m.ai_only_matches).model_dump()}
            for r, m, stage in matching.matching_requirements(ctx.db, ctx.org_id, c, limit)]


@router.get("/requirements/{requirement_id}/matching-candidates")
def requirement_matches(requirement_id: uuid.UUID, ctx: Ctx = viewer, limit: int = Query(20, ge=1, le=50)):
    req = ctx.db.scalar(select(JobRequirement).options(selectinload(JobRequirement.skills)).where(JobRequirement.id == requirement_id, JobRequirement.organization_id == ctx.org_id))
    if not req:
        raise NotFoundError("Requirement not found")
    return [{"candidate": to_out(c).model_dump(mode="json"), **MatchOut(score=m.score, matched_skills=m.matched_skills, missing_skills=m.missing_skills, reasons=m.reasons, stage=stage, ai_profile_used=m.ai_profile_used, ai_only_matches=m.ai_only_matches).model_dump()}
            for c, m, stage in matching.matching_candidates(ctx.db, ctx.org_id, req, limit)]


@router.get("/requirements/{requirement_id}/submissions", response_model=list[SubmissionOut])
def requirement_submissions(requirement_id: uuid.UUID, ctx: Ctx = viewer):
    req = ctx.db.scalar(select(JobRequirement).where(JobRequirement.id == requirement_id, JobRequirement.organization_id == ctx.org_id))
    if not req:
        raise NotFoundError("Requirement not found")
    rows = ctx.db.scalars(select(CandidateSubmission).options(selectinload(CandidateSubmission.candidate)).where(CandidateSubmission.requirement_id == requirement_id)
                          .order_by(CandidateSubmission.updated_at.desc()))
    return [_sub_out(s, req) for s in rows]


# ---------------------------------------------------------------- AI profile (runs only when the user asks)
def _ai_out(r: CandidateAIProfile) -> dict:
    return {"id": str(r.id), "created_at": r.created_at, "source_type": r.source_type, "source_label": r.source_label, "provider": r.provider, "model": r.model_name,
            "prompt_version": r.prompt_version, "applied_fields": r.applied_fields or [], "applied_at": r.applied_at, "result": r.result}


@router.post("/candidates/{candidate_id}/ai-profile", status_code=201)
def ai_profile_run(candidate_id: uuid.UUID, text: str | None = Form(None, max_length=200_000), source: str = Form("linkedin_text"), file: UploadFile | None = File(None), ctx: Ctx = member):
    """Extract a structured profile from text the user provides (pasted LinkedIn text, LinkedIn 'Save to PDF', or a resume file).

    The server never fetches LinkedIn URLs (LinkedIn forbids automated access). The source text is not stored.
    """
    if source not in ("linkedin_text", "resume_text"):
        raise ValidationFailure("source must be linkedin_text or resume_text")
    cand = svc.get_candidate(ctx.db, ctx.org_id, candidate_id)
    rate_limiter.check(f"ai-profile:{ctx.user_id}", 15, 3600)
    source_type, label, body = source, None, (text or "")
    if file is not None and file.filename:
        data = file.file.read(importer.MAX_BYTES + 1)
        parsed = parse_attachment(file.filename, file.content_type, data, importer.MAX_BYTES)
        if parsed.status != "extracted" or not parsed.text:
            raise ValidationFailure(f"The file could not be read ({parsed.error or parsed.status}). Use a text-based PDF, DOCX or TXT file.", code="unreadable_file")
        source_type, label, body = "file", file.filename, parsed.text
    elif not body.strip():
        raise ValidationFailure("Paste the profile text or upload a file")
    res = ai.run(ctx.db, ctx.org_id, cand, ctx.user_id, body, source_type, label or ("LinkedIn text" if source == "linkedin_text" else "Resume text"))
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="candidate.ai_profile", entity_type="candidate", entity_id=cand.id, metadata={"source": source_type, "model": res.record.model_name})
    ctx.db.commit()
    return _ai_out(res.record)


@router.get("/candidates/{candidate_id}/ai-profiles")
def ai_profile_history(candidate_id: uuid.UUID, ctx: Ctx = viewer):
    svc.get_candidate(ctx.db, ctx.org_id, candidate_id)
    rows = ctx.db.scalars(select(CandidateAIProfile).where(CandidateAIProfile.candidate_id == candidate_id).order_by(CandidateAIProfile.created_at.desc()).limit(20))
    return [{"id": str(r.id), "created_at": r.created_at, "source_type": r.source_type, "source_label": r.source_label, "model": r.model_name,
             "headline": (r.result.get("profile") or {}).get("headline"), "applied_fields": r.applied_fields or []} for r in rows]


@router.get("/candidates/{candidate_id}/ai-profile")
def ai_profile_latest(candidate_id: uuid.UUID, ctx: Ctx = viewer):
    svc.get_candidate(ctx.db, ctx.org_id, candidate_id)
    r = ctx.db.scalar(select(CandidateAIProfile).where(CandidateAIProfile.candidate_id == candidate_id).order_by(CandidateAIProfile.created_at.desc()).limit(1))
    return {"profile": _ai_out(r) if r else None}


@router.get("/candidates/{candidate_id}/ai-profiles/{profile_id}")
def ai_profile_one(candidate_id: uuid.UUID, profile_id: uuid.UUID, ctx: Ctx = viewer):
    return _ai_out(ai.get_record(ctx.db, ctx.org_id, candidate_id, profile_id))


@router.post("/candidates/{candidate_id}/ai-profiles/{profile_id}/apply")
def ai_profile_apply(candidate_id: uuid.UUID, profile_id: uuid.UUID, body: ApplyIn, ctx: Ctx = member):
    cand = svc.get_candidate(ctx.db, ctx.org_id, candidate_id)
    rec = ai.get_record(ctx.db, ctx.org_id, candidate_id, profile_id)
    applied = ai.apply_to_candidate(ctx.db, cand, rec, body.fields, ctx.user_id)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="candidate.ai_profile_applied", entity_type="candidate", entity_id=cand.id, metadata={"fields": applied})
    ctx.db.commit()
    return {"applied": applied, "candidate": to_out(svc.get_candidate(ctx.db, ctx.org_id, candidate_id)).model_dump(mode="json")}


@router.delete("/candidates/{candidate_id}/ai-profiles/{profile_id}")
def ai_profile_delete(candidate_id: uuid.UUID, profile_id: uuid.UUID, ctx: Ctx = member):
    rec = ai.get_record(ctx.db, ctx.org_id, candidate_id, profile_id)
    ctx.db.delete(rec)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="candidate.ai_profile_deleted", entity_type="candidate", entity_id=candidate_id)
    ctx.db.commit()
    return {"deleted": True}

