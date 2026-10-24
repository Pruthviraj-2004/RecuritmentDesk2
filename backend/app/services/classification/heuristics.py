"""Deterministic email classification and field hints. Runs before (and independent of) any AI provider."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.enums import MessageClassification as C

EMAIL_RE = re.compile(r"[\w.+\-']+@[\w\-]+(?:\.[\w\-]+)+")
PHONE_RE = re.compile(r"(?<!\d)(\+?\d{1,3}[\s\-.]?)?(\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}|\d{5}[\s\-]?\d{5})(?!\d)")
EXP_RANGE_RE = re.compile(r"(\d{1,2})\s*(?:\+|to|-|–)\s*(\d{1,2})?\s*\+?\s*(?:years|yrs|yr)", re.I)
EXP_MIN_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:years|yrs|yr)", re.I)
REF_RE = re.compile(
    r"\b(?:job\s*(?:id|code|ref(?:erence)?|#)|req(?:uisition)?\s*(?:id|no|number|#)|ref(?:erence)?\s*(?:id|no|number|#)|position\s*id)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\-_/]{2,30})",
    re.I,
)

_JD_SIGNALS = [
    (r"\b(job description|jd|job requirement|requirement|opening|vacancy|position|role)\b", 1.0),
    (r"\b(we are (hiring|looking)|looking for|urgent requirement|hot requirement|immediate (joiner|requirement))\b", 1.5),
    (r"\b(required skills?|mandatory skills?|must have|good to have|skills required|key skills|responsibilities)\b", 1.5),
    (r"\b(\d+\+?\s*(years|yrs) (of )?experience|experience:|exp:)\b", 1.0),
    (r"\b(ctc|salary|rate|c2c|w2|1099|contract|permanent|full[- ]time|notice period)\b", 0.75),
    (r"\b(location|remote|hybrid|onsite|on-site)\b", 0.5),
    (r"\b(send (your )?(resume|profile|cv|updated resume)|share (the )?(profiles?|resumes?))\b", 1.5),
]
_CLOSURE = re.compile(r"\b(position (has been )?(filled|closed|on hold|cancelled|canceled)|requirement (is )?(closed|on hold|cancelled|canceled)|no longer (hiring|open|required)|please ignore this requirement)\b", re.I)
_INTERVIEW = re.compile(r"\b(interview (schedule|slot|invite|confirmation)|schedule (an )?interview|calendar invite|zoom link|teams meeting|reschedul)", re.I)
_CANDIDATE = re.compile(r"\b(candidate (profile|submission|resume)|attached (is )?(the )?(resume|cv)|please find (the )?(resume|profile)|submitting (the )?(profile|candidate))", re.I)
_UPDATE = re.compile(r"\b(updated?|revised|modified|corrected|change in|new budget|rate (revised|changed)|location (changed|updated))\b", re.I)
_NOISE_SENDERS = re.compile(r"(no-?reply|noreply|notifications?@|newsletter|mailer-daemon|marketing)", re.I)
_NOISE_SUBJECT = re.compile(r"\b(unsubscribe|newsletter|webinar|invoice|receipt|password reset|verify your|security alert|sale|% off)\b", re.I)


@dataclass
class Classification:
    category: C
    confidence: float
    signals: list[str] = field(default_factory=list)


def classify_email(subject: str | None, body: str | None, sender: str | None = None, has_attachments: bool = False) -> Classification:
    text = f"{subject or ''}\n{(body or '')[:6000]}"
    lower = text.lower()
    signals: list[str] = []

    if _CLOSURE.search(lower):
        return Classification(C.JOB_CLOSURE, 0.8, ["closure_phrase"])
    if _INTERVIEW.search(lower) and not re.search(r"required skills?|job description", lower):
        return Classification(C.INTERVIEW_SCHEDULING, 0.75, ["interview_phrase"])

    score = 0.0
    for pat, weight in _JD_SIGNALS:
        if re.search(pat, lower):
            score += weight
            signals.append(pat[:30])
    if has_attachments and re.search(r"\b(jd|job description)\b", lower):
        score += 1.0
        signals.append("jd_attachment")

    if _CANDIDATE.search(lower) and score < 3.5:
        return Classification(C.CANDIDATE_SUBMISSION, 0.7, ["candidate_phrase"])
    if (_NOISE_SENDERS.search(sender or "") or _NOISE_SUBJECT.search(subject or "")) and score < 3:
        return Classification(C.UNRELATED, 0.85, ["noise_sender_or_subject"])

    if score >= 3.5:
        cat = C.UPDATED_REQUIREMENT if _UPDATE.search(subject or "") else C.NEW_REQUIREMENT
        return Classification(cat, min(0.95, 0.5 + score / 10), signals)
    if score >= 2:
        return Classification(C.NEEDS_REVIEW, 0.5, signals)
    if score >= 1:
        return Classification(C.RECRUITER_FOLLOWUP, 0.45, signals)
    return Classification(C.UNRELATED, 0.7 if len(text) > 200 else 0.5, signals)


def extract_hints(text: str) -> dict:
    """Deterministic field hints used to cross-validate AI output and to prefill manual creation."""
    hints: dict = {}
    emails = list(dict.fromkeys(m.lower() for m in EMAIL_RE.findall(text or "")))
    if emails:
        hints["emails"] = emails
    phones = [m.group(0).strip() for m in PHONE_RE.finditer(text or "")]
    if phones:
        hints["phones"] = list(dict.fromkeys(phones))[:5]
    for m in REF_RE.finditer(text or ""):
        ref = m.group(1).strip("-_/")
        if any(ch.isdigit() for ch in ref):  # real ids contain a digit; avoids matching words like "requirement"
            hints["job_reference_id"] = ref
            break
    for em in EXP_RANGE_RE.finditer(text or ""):
        lo = float(em.group(1))
        hi = float(em.group(2)) if em.group(2) else None
        hints["minimum_experience"] = lo
        if hi and hi >= lo:
            hints["maximum_experience"] = hi
        break
    else:
        em2 = EXP_MIN_RE.search(text or "")
        if em2:
            hints["minimum_experience"] = float(em2.group(1))
    low = (text or "").lower()
    if re.search(r"\bhybrid\b", low):
        hints["work_mode"] = "hybrid"
    elif re.search(r"\bremote\b", low) and not re.search(r"\bnot remote\b|\bno remote\b", low):
        hints["work_mode"] = "remote"
    elif re.search(r"\bon-?site\b|\bonsite\b|work from office", low):
        hints["work_mode"] = "onsite"
    return hints
