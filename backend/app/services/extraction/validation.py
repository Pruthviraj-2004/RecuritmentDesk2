"""Deterministic validation of AI output against the source text. The AI is never trusted blindly."""
from __future__ import annotations

import re

from app.services.extraction.schema import ExtractedRequirement
from app.services.normalization.text import normalize_skill, normalize_unicode

_EMAIL = re.compile(r"[\w.+\-']+@[\w\-]+(?:\.[\w\-]+)+")


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9@.+#]+", " ", normalize_unicode(s).lower()).strip()


def _in_source(value: str | None, source_squashed: str) -> bool:
    return bool(value) and _squash(value) in source_squashed


def validate_against_source(req: ExtractedRequirement, source_text: str) -> tuple[ExtractedRequirement, list[str], float]:
    """Return (cleaned requirement, warnings, completeness-based confidence 0..1)."""
    warnings: list[str] = []
    src = _squash(source_text)
    data = req.model_copy(deep=True)

    for fld in ("job_title", "client_name", "job_reference_id"):
        val = getattr(data, fld)
        if val and not _in_source(val, src):
            warnings.append(f"{fld}_not_found_in_source")
    for fld in ("recruiter_email", "submission_email"):
        val = getattr(data, fld)
        if val:
            if not _EMAIL.fullmatch(val.strip()):
                warnings.append(f"{fld}_invalid_format")
                setattr(data, fld, None)
            elif val.strip().lower() not in source_text.lower():
                setattr(data, fld, None)  # an invented address is worse than a missing one; it is dropped, so there is nothing left to warn about
            else:
                setattr(data, fld, val.strip().lower())

    src_tokens = f" {src} "
    for fld in ("required_skills", "preferred_skills"):
        kept, dropped = [], []
        for sk in getattr(data, fld):
            variants = {_squash(sk), _squash(normalize_skill(sk))}
            (kept if any(v and f" {v} " in src_tokens or (v and v in src) for v in variants) else dropped).append(sk)
        setattr(data, fld, kept)
        if dropped:
            warnings.append(f"{fld}_unsupported_removed:{len(dropped)}")

    if data.minimum_experience is not None and data.maximum_experience is not None and data.maximum_experience < data.minimum_experience:
        warnings.append("experience_range_inverted")
        data.minimum_experience, data.maximum_experience = data.maximum_experience, data.minimum_experience
    if data.salary_min is not None and data.salary_max is not None and data.salary_max < data.salary_min:
        warnings.append("salary_range_inverted")
        data.salary_min, data.salary_max = data.salary_max, data.salary_min
    if (data.salary_min or data.salary_max) and not data.salary_currency:
        warnings.append("salary_currency_missing")
    if data.recruiter_phone and len(re.sub(r"\D", "", data.recruiter_phone)) < 7:
        warnings.append("recruiter_phone_invalid")
        data.recruiter_phone = None

    # drop evidence snippets that are not actually in the source
    data.evidence = {k: v for k, v in data.evidence.items() if v and _squash(v) in src}

    weights = {"job_title": 0.25, "client_name": 0.2, "required_skills": 0.2, "location": 0.1, "minimum_experience": 0.1, "recruiter_email": 0.1, "job_description": 0.05}
    got = 0.0
    for fld, w in weights.items():
        val = (data.city or data.country or data.state) if fld == "location" else getattr(data, fld)
        if val not in (None, [], ""):
            got += w
    penalty = min(0.4, 0.1 * len([w for w in warnings if "not_found" in w or "unsupported" in w]))
    return data, warnings, max(0.0, round(got - penalty, 3))
