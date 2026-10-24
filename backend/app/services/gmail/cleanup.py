"""One-off cleanup for requirements that were extracted from RecruitmentDesk's own exports / digests before they were recognised."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.models.email import EmailAccount, EmailMessage
from app.models.enums import DuplicateStatus, LifecycleStatus, ReviewStatus
from app.models.requirements import DuplicateCandidate, JobRequirement, RequirementSource
from app.services.gmail.own_mail import own_addresses, own_mail_reason


@dataclass
class CleanupReport:
    messages: int = 0
    sources_removed: int = 0
    requirements_archived: int = 0
    candidates_dismissed: int = 0
    details: list[str] = field(default_factory=list)


def cleanup_own_exports(db: Session, *, apply: bool) -> CleanupReport:
    """Find stored messages that are our own exports/digests, detach them from requirements and archive requirements that existed ONLY because of them.

    Requirements that were approved, edited by a person, or that have another real source are never archived; only the bad source link is removed.
    """
    rep = CleanupReport()
    for org_id in {o for o in db.scalars(select(EmailAccount.organization_id))}:
        own = own_addresses(db, org_id)
        bad: list[EmailMessage] = []
        for m in db.scalars(select(EmailMessage).where(EmailMessage.organization_id == org_id)):
            labels = list(m.labels or [])
            reason = own_mail_reason(db, org_id, sender_email=m.sender_email, own=own, filenames=[a.filename for a in m.attachments],
                                     mime_types=[a.content_type for a in m.attachments], labels=labels, export_header=False, rfc_message_id=m.rfc_message_id)
            if reason:
                bad.append(m)
        bad_ids = {m.id for m in bad}
        rep.messages += len(bad)
        for m in bad:
            rep.details.append(f"{m.subject or '(no subject)'} <- {m.sender_email}")
        affected = {rid for (rid,) in db.execute(select(RequirementSource.job_requirement_id).where(RequirementSource.email_message_id.in_(bad_ids)))} if bad_ids else set()
        for rid in affected:
            req = db.get(JobRequirement, rid)
            others = db.scalar(select(func.count()).select_from(RequirementSource).where(RequirementSource.job_requirement_id == rid,
                                                                                       RequirementSource.email_message_id.not_in(bad_ids))) or 0
            untouched = req.version_number <= 1 and req.review_status == ReviewStatus.NEEDS_REVIEW and req.lifecycle_status == LifecycleStatus.ACTIVE
            if others == 0 and untouched:
                rep.requirements_archived += 1
                if apply:
                    req.lifecycle_status, req.review_status = LifecycleStatus.ARCHIVED, ReviewStatus.REJECTED
                    req.validation_warnings = sorted(set((req.validation_warnings or []) + ["created_from_own_export"]))
                    for c in db.scalars(select(DuplicateCandidate).where(DuplicateCandidate.review_status == DuplicateStatus.PENDING,
                                                                         (DuplicateCandidate.requirement_id_a == rid) | (DuplicateCandidate.requirement_id_b == rid))):
                        c.review_status, c.resolved_at = DuplicateStatus.DISMISSED, utcnow()
                        rep.candidates_dismissed += 1
        if bad_ids:
            n = db.scalar(select(func.count()).select_from(RequirementSource).where(RequirementSource.email_message_id.in_(bad_ids))) or 0
            rep.sources_removed += n
            if apply:
                db.execute(delete(RequirementSource).where(RequirementSource.email_message_id.in_(bad_ids)))
                db.execute(delete(EmailMessage).where(EmailMessage.id.in_(bad_ids)))
    if not apply:
        db.rollback()
    return rep


def delete_flagged_copies(db: Session, *, apply: bool) -> list[str]:
    """Permanently delete requirements that cleanup_own_exports flagged (`created_from_own_export`), have no remaining source email and were
    never approved by a person. Returns a description of each affected record."""
    out: list[str] = []
    for req in db.scalars(select(JobRequirement)):
        if "created_from_own_export" not in (req.validation_warnings or []) or req.review_status == ReviewStatus.APPROVED:
            continue
        n = db.scalar(select(func.count()).select_from(RequirementSource).where(RequirementSource.job_requirement_id == req.id)) or 0
        if n:
            continue
        out.append(f"{req.client_name or '-'} / {req.job_title or '(untitled)'} [{req.lifecycle_status}]")
        if apply:
            db.delete(req)  # skills/versions/duplicate candidates cascade
    if not apply:
        db.rollback()
    return out
