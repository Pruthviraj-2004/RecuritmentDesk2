from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import Ctx, member, viewer
from app.services.gmail.links import gmail_url
from app.api.v1.endpoints.requirements import build_outputs
from app.models.email import EmailAccount, EmailMessage
from app.models.enums import DuplicateStatus
from app.models.requirements import DuplicateCandidate, RequirementSource
from app.schemas.api import DuplicateDetail, DuplicateOut, MergeIn, Page, SourceOut
from app.services.audit import service as audit
from app.services.requirements import service as svc

router = APIRouter(prefix="/duplicates", tags=["duplicates"])


def _out(ctx: Ctx, cands: list[DuplicateCandidate], model=DuplicateOut):
    reqs = []
    for c in cands:
        reqs += [svc.get_requirement(ctx.db, ctx.org_id, c.requirement_id_a), svc.get_requirement(ctx.db, ctx.org_id, c.requirement_id_b)]
    outs = build_outputs(ctx.db, reqs)
    result = []
    for i, c in enumerate(cands):
        result.append(model(id=c.id, matching_score=c.matching_score, matching_reasons=c.matching_reasons, conflicting_fields=c.conflicting_fields,
                            review_status=c.review_status, created_at=c.created_at, resolved_at=c.resolved_at, requirement_a=outs[2 * i], requirement_b=outs[2 * i + 1]))
    return result


def _sources(ctx: Ctx, rid: uuid.UUID) -> list[SourceOut]:
    rows = ctx.db.execute(select(RequirementSource, EmailMessage, EmailAccount.email_address)
                          .join(EmailMessage, EmailMessage.id == RequirementSource.email_message_id, isouter=True)
                          .join(EmailAccount, EmailAccount.id == EmailMessage.email_account_id, isouter=True)
                          .where(RequirementSource.job_requirement_id == rid).order_by(RequirementSource.linked_at)).all()
    return [SourceOut(id=s.id, source_type=s.source_type, linked_at=s.linked_at, email_message_id=s.email_message_id, account_email=email,
                      sender=m.sender if m else None, subject=m.subject if m else None, received_at=m.received_at if m else None,
                      gmail_url=gmail_url(email, m.gmail_message_id) if m else None, evidence=s.evidence_metadata or {}) for s, m, email in rows]


@router.get("", response_model=Page[DuplicateOut])
def list_duplicates(ctx: Ctx = viewer, status: str = Query("pending"), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    stmt = select(DuplicateCandidate).where(DuplicateCandidate.organization_id == ctx.org_id)
    if status != "all":
        stmt = stmt.where(DuplicateCandidate.review_status == status)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(ctx.db.scalars(stmt.order_by(DuplicateCandidate.matching_score.desc(), DuplicateCandidate.created_at.desc()).limit(page_size).offset((page - 1) * page_size)))
    return Page(items=_out(ctx, rows), total=total, page=page, page_size=page_size)


@router.get("/{duplicate_id}", response_model=DuplicateDetail)
def get_one(duplicate_id: uuid.UUID, ctx: Ctx = viewer):
    c = svc.get_candidate(ctx.db, ctx.org_id, duplicate_id)
    d = _out(ctx, [c], DuplicateDetail)[0]
    d.sources_a, d.sources_b = _sources(ctx, c.requirement_id_a), _sources(ctx, c.requirement_id_b)
    return d


@router.post("/{duplicate_id}/merge", response_model=DuplicateOut)
def merge(duplicate_id: uuid.UUID, body: MergeIn, ctx: Ctx = member):
    c = svc.get_candidate(ctx.db, ctx.org_id, duplicate_id)
    survivor = svc.merge_requirements(ctx.db, ctx.org_id, c, body.survivor_id, ctx.user_id)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="duplicate.merged", entity_type="duplicate", entity_id=c.id, metadata={"survivor": str(survivor.id)})
    ctx.db.commit()
    return _out(ctx, [c])[0]


def _resolve(status: DuplicateStatus, action: str):
    def endpoint(duplicate_id: uuid.UUID, ctx: Ctx = member):
        c = svc.get_candidate(ctx.db, ctx.org_id, duplicate_id)
        svc.resolve_candidate(ctx.db, c, status, ctx.user_id)
        audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action=f"duplicate.{action}", entity_type="duplicate", entity_id=c.id)
        ctx.db.commit()
        return _out(ctx, [c])[0]

    endpoint.__name__ = f"duplicate_{action}"
    return endpoint


for _s, _a, _p in ((DuplicateStatus.KEPT_BOTH, "keep_both", "keep-both"), (DuplicateStatus.RELATED, "mark_related", "mark-related"),
                   (DuplicateStatus.DISMISSED, "dismiss", "dismiss")):
    router.add_api_route(f"/{{duplicate_id}}/{_p}", _resolve(_s, _a), methods=["POST"], response_model=DuplicateOut)


@router.post("/{duplicate_id}/reopen", response_model=DuplicateOut)
def reopen(duplicate_id: uuid.UUID, ctx: Ctx = member):
    c = svc.get_candidate(ctx.db, ctx.org_id, duplicate_id)
    svc.reopen_candidate(ctx.db, c)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="duplicate.reopened", entity_type="duplicate", entity_id=c.id)
    ctx.db.commit()
    return _out(ctx, [c])[0]
