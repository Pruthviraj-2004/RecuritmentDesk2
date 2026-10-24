"""Per-message processing: attachments -> classification -> AI extraction -> validation -> dedup -> persistence.

Idempotent: re-running for the same message never creates duplicate requirements (see ingest_extracted).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger, redact
from app.db.types import utcnow
from app.integrations.gmail_client import GmailAuthError, GmailError, GmailTransient
from app.integrations.storage import StorageError, get_storage
from app.models.email import EmailAccount, EmailAttachment, EmailMessage
from app.models.enums import (
    REQUIREMENT_CLASSES,
    AttachmentStatus,
    ConnectionStatus,
    MessageClassification as C,
    MessageStatus as S,
)
from app.models.ops import ExtractionRun
from app.models.requirements import JobRequirement, RequirementSource
from app.services.app_settings import get_section
from app.services.audit import service as audit
from app.services.classification.heuristics import classify_email, extract_hints
from app.services.extraction.providers import PROMPT_VERSION, AIConfigError, AIError, get_provider
from app.services.extraction.validation import validate_against_source
from app.services.gmail.accounts import gateway_for
from app.services.gmail.attachments import parse_attachment
from app.services.gmail.mime import parse_gmail_message
from app.services.normalization.text import strip_quoted_replies
from app.services.requirements.service import ingest_extracted, link_source

log = get_logger(__name__)


class TransientProcessingError(Exception):
    """Retryable (AI/Gmail temporary failure)."""


def _load_attachment_texts(db: Session, msg: EmailMessage, acct: EmailAccount, process: bool, retain_files: bool) -> list[tuple[str, str]]:
    s = get_settings()
    texts: list[tuple[str, str]] = []
    gw = None
    storage = None
    for att in msg.attachments:
        if att.extraction_status == AttachmentStatus.EXTRACTED and att.extracted_text_reference:
            try:
                texts.append((att.filename, get_storage().read(att.extracted_text_reference).decode("utf-8", "replace")))
                continue
            except StorageError:
                att.extraction_status = AttachmentStatus.PENDING
        if att.extraction_status in (AttachmentStatus.QUARANTINED, AttachmentStatus.UNSUPPORTED, AttachmentStatus.TOO_LARGE):
            continue
        if not process:
            att.extraction_status = AttachmentStatus.SKIPPED
            continue
        if att.size_bytes and att.size_bytes > s.max_attachment_bytes:
            att.extraction_status, att.error_summary = AttachmentStatus.TOO_LARGE, "Attachment exceeds size limit"
            continue
        if not att.gmail_attachment_id:
            att.extraction_status, att.error_summary = AttachmentStatus.UNSUPPORTED, "Inline content is not processed"
            continue
        try:
            gw = gw or gateway_for(db, acct)
            data = gw.get_attachment(msg.gmail_message_id, att.gmail_attachment_id)
        except GmailAuthError:
            raise
        except GmailTransient as e:
            raise TransientProcessingError(str(e)) from e
        except GmailError as e:
            att.extraction_status, att.error_summary = AttachmentStatus.FAILED, redact(str(e))[:300]
            continue
        parsed = parse_attachment(att.filename, att.content_type, data, s.max_attachment_bytes)
        att.extraction_status = parsed.status
        att.error_summary = parsed.error
        import hashlib

        att.content_hash = hashlib.sha256(data).hexdigest()
        if parsed.text:
            storage = storage or get_storage()
            att.extracted_text_reference = storage.save("attachment-text", parsed.text.encode("utf-8"), ".txt")
            texts.append((att.filename, parsed.text))
        if retain_files and parsed.status == AttachmentStatus.EXTRACTED:
            storage = storage or get_storage()
            att.storage_reference = storage.save("attachments", data)
    return texts


def _ensure_body(db: Session, msg: EmailMessage, acct: EmailAccount) -> str:
    if msg.body_text or not msg.body_purged:
        return msg.body_text or ""
    try:
        raw = gateway_for(db, acct).get_message(msg.gmail_message_id)
    except GmailAuthError:
        raise
    except GmailTransient as e:
        raise TransientProcessingError(str(e)) from e
    msg.body_text = parse_gmail_message(raw, get_settings().max_email_body_chars).body_text
    msg.body_purged = False
    return msg.body_text


def process_message(db: Session, message_id: uuid.UUID, *, user_id: uuid.UUID | None = None, force: bool = False) -> str:
    """Process one message; returns the final processing_status."""
    msg = db.get(EmailMessage, message_id)
    if msg is None:
        return "missing"
    if msg.processing_status == S.IGNORED and not force:
        return msg.processing_status
    org_id = msg.organization_id
    acct = db.get(EmailAccount, msg.email_account_id)
    gmail_cfg = get_section(db, org_id, "gmail")
    ai_cfg = get_section(db, org_id, "ai")
    dedup_cfg = get_section(db, org_id, "dedup")

    msg.processing_status = S.PROCESSING
    msg.processing_attempts += 1
    msg.error_summary = None
    db.flush()

    try:
        # Cross-account copy of an already processed message: link sources, do not extract again.
        if msg.duplicate_of_message_id and not force:
            orig = db.get(EmailMessage, msg.duplicate_of_message_id)
            if orig and orig.processing_status in (S.PROCESSED, S.NEEDS_REVIEW):
                reqs = list(db.scalars(select(JobRequirement).join(RequirementSource, RequirementSource.job_requirement_id == JobRequirement.id)
                                       .where(RequirementSource.email_message_id == orig.id)))
                for r in reqs:
                    link_source(db, r, msg.id, "duplicate_copy", {"original_message_id": str(orig.id), "account_id": str(acct.id)})
                msg.classification, msg.classification_confidence = orig.classification, orig.classification_confidence
                msg.processing_status = S.DUPLICATE
                msg.processed_at = utcnow()
                db.flush()
                return msg.processing_status

        body = _ensure_body(db, msg, acct)
        has_att = bool(msg.attachments)
        att_texts = _load_attachment_texts(db, msg, acct, gmail_cfg.process_attachments, gmail_cfg.retain_attachment_files) if has_att else []
        clean_body = strip_quoted_replies(body)
        combined = "\n".join([msg.subject or "", clean_body] + [t for _, t in att_texts])

        cls = classify_email(msg.subject, combined, msg.sender, has_att)
        msg.classification, msg.classification_confidence = cls.category.value, cls.confidence
        if cls.category == C.UNRELATED and cls.confidence >= 0.7 and not force:
            msg.processing_status = S.NO_REQUIREMENT
            msg.processed_at = utcnow()
            msg.body_text, msg.body_purged = None, True  # unrelated mail is not retained
            db.flush()
            return msg.processing_status

        try:
            provider = get_provider()
        except AIConfigError as e:
            provider = None
            cfg_error = str(e)
        else:
            cfg_error = "AI provider is not configured"
        if provider is None:
            db.add(ExtractionRun(email_message_id=msg.id, provider=get_settings().ai_provider, prompt_version=PROMPT_VERSION, status="skipped",
                                 error_code="ai_not_configured", error_message=cfg_error, completed_at=utcnow()))
            msg.processing_status = S.AWAITING_AI
            msg.error_summary = cfg_error
            db.flush()
            return msg.processing_status

        run = ExtractionRun(email_message_id=msg.id, provider=provider.name, model_name=provider.model, prompt_version=PROMPT_VERSION, status="running")
        db.add(run)
        db.flush()
        try:
            result = provider.extract(subject=msg.subject or "", sender=msg.sender or "", body=clean_body, attachments=att_texts,
                                      received_at=msg.received_at.isoformat() if msg.received_at else None)
        except AIError as e:
            run.status, run.error_code, run.error_message, run.completed_at = "failed", e.code, redact(str(e))[:500], utcnow()
            if e.permanent:
                msg.processing_status = S.FAILED
                msg.error_summary = redact(str(e))[:500]
                audit.notify(db, org_id=org_id, kind="extraction_failed", severity="error", title="AI extraction is failing",
                             body=f"{e.code}: {e}", link="/settings")
                db.flush()
                return msg.processing_status
            db.flush()
            raise TransientProcessingError(str(e)) from e

        run.status, run.completed_at = "succeeded", utcnow()
        run.extracted_data = result.model_dump()
        category = C(result.classification) if result.classification in C._value2member_map_ else C.NEEDS_REVIEW
        msg.classification, msg.classification_confidence = category.value, result.classification_confidence

        if category not in REQUIREMENT_CLASSES and category != C.JOB_CLOSURE:
            msg.processing_status = S.NEEDS_REVIEW if category == C.NEEDS_REVIEW else S.NO_REQUIREMENT
            if not result.requirements:
                msg.processed_at = utcnow()
                db.flush()
                return msg.processing_status

        body_hints = extract_hints(clean_body)
        conflict_warning = []
        for name, t in att_texts:
            ah = extract_hints(t)
            for k in ("job_reference_id", "minimum_experience"):
                if k in ah and k in body_hints and str(ah[k]).lower() != str(body_hints[k]).lower():
                    conflict_warning.append(f"body_attachment_conflict:{k}")

        outcomes = []
        low_conf = False
        for ex in result.requirements:
            cleaned, warnings, conf = validate_against_source(ex, combined)
            warnings += conflict_warning
            if conf < ai_cfg.review_confidence_threshold:
                warnings.append("low_confidence")
                low_conf = True
            out = ingest_extracted(db, org_id, msg, cleaned, warnings=warnings, confidence=conf, model=provider.model,
                                   classification=category.value, source_type="email_body", dedup=dedup_cfg,
                                   needs_review_threshold=ai_cfg.review_confidence_threshold, user_id=user_id)
            outcomes.append(out)
            if out.requirement is not None and att_texts:
                link_source(db, out.requirement, msg.id, "attachment", {"files": [n for n, _ in att_texts][:10]})
            if out.action == "created":
                audit.record(db, org_id=org_id, user_id=None, action="requirement.extracted", entity_type="requirement", entity_id=out.requirement.id,
                             metadata={"title": out.requirement.job_title, "account": acct.email_address})
            elif out.action in ("created_probable",):
                audit.record(db, org_id=org_id, user_id=None, action="duplicate.detected", entity_type="requirement", entity_id=out.requirement.id,
                             metadata={"score": out.candidate.matching_score if out.candidate else None})
                audit.notify(db, org_id=org_id, kind="duplicate_review", title="Possible duplicate requirement", body=out.requirement.job_title,
                             link="/duplicates")
            elif out.action == "attached_exact":
                audit.record(db, org_id=org_id, user_id=None, action="duplicate.attached", entity_type="requirement", entity_id=out.requirement.id,
                             metadata={"message_id": str(msg.id)})
        run.confidence_metadata = {"requirements": len(outcomes), "actions": [o.action for o in outcomes], "warnings_count": sum(1 for _ in conflict_warning)}

        if outcomes and any(o.requirement for o in outcomes):
            msg.processing_status = S.NEEDS_REVIEW if low_conf else S.PROCESSED
        else:
            msg.processing_status = S.NO_REQUIREMENT
        msg.processed_at = utcnow()
        db.flush()
        return msg.processing_status

    except GmailAuthError as e:
        msg.processing_status, msg.error_summary = S.FAILED, "Gmail authorization expired; reauthorize the account"
        acct.connection_status, acct.last_error = ConnectionStatus.EXPIRED, str(e)[:500]
        db.flush()
        return msg.processing_status
    except TransientProcessingError as e:
        msg.processing_status, msg.error_summary = S.FAILED, f"Temporary error: {redact(str(e))[:300]}"
        db.flush()
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("process_message_failed", extra={"message_id": str(message_id)})
        msg.processing_status, msg.error_summary = S.FAILED, f"Unexpected error: {type(e).__name__}"
        db.flush()
        return msg.processing_status
