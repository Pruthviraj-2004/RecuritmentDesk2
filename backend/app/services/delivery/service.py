"""Sending exports through Gmail. Never automatic, never blindly retried after an ambiguous failure."""
from __future__ import annotations

import uuid
from email.message import EmailMessage as MimeMessage
from email.utils import formatdate, make_msgid

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailure
from app.core.logging import get_logger, redact
from app.db.types import utcnow
from app.integrations.gmail_client import (
    GmailAmbiguousSend,
    GmailAuthError,
    GmailError,
    GmailRateLimited,
    GmailTransient,
)
from app.models.email import EmailAccount
from app.models.enums import ConnectionStatus, DeliveryStatus
from app.models.ops import EmailDelivery, ExportJob
from app.services.audit import service as audit
from app.services.exports.runner import XLSX_MIME, read_export_file
from app.services.gmail.accounts import gateway_for

log = get_logger(__name__)
MAX_RECIPIENTS = 20

TEMPLATES = {
    "summary": ("Recruitment Requirements Summary", "Hello,\n\nPlease find attached the summary of current recruitment requirements ({count} positions).\n\nRegards"),
    "weekly": ("Weekly Hiring Requirements", "Hello,\n\nAttached are this week's hiring requirements ({count} positions).\n\nRegards"),
    "client_wise": ("Client-wise Requirement Report", "Hello,\n\nPlease find attached the client-wise requirement report ({count} positions).\n\nRegards"),
    "custom": ("Recruitment Report", "Hello,\n\nPlease find the attached recruitment report.\n\nRegards"),
}


def validate_recipients(addresses: list[str], field: str = "recipients") -> list[str]:
    out: list[str] = []
    for a in addresses:
        a = (a or "").strip()
        if not a:
            continue
        if any(ch in a for ch in "\r\n,;<>"):
            raise ValidationFailure(f"Invalid address in {field}: {a[:60]!r}")
        try:
            out.append(validate_email(a, check_deliverability=False).normalized.lower())
        except EmailNotValidError as e:
            raise ValidationFailure(f"Invalid address in {field}: {a[:60]!r} ({e})") from e
    out = list(dict.fromkeys(out))
    if len(out) > MAX_RECIPIENTS:
        raise ValidationFailure(f"At most {MAX_RECIPIENTS} addresses allowed in {field}")
    return out


def clean_header(value: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def build_mime(*, sender: str, to: list[str], cc: list[str], subject: str, body: str, filename: str, xlsx: bytes) -> tuple[MimeMessage, str]:
    msg = MimeMessage()
    msg["X-RecruitmentDesk-Export"] = "1"  # lets any connected mailbox recognise (and skip) our own exports when they arrive
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = clean_header(subject)
    msg["Date"] = formatdate(localtime=False)
    rfc_id = make_msgid(domain=sender.split("@")[-1])
    msg["Message-ID"] = rfc_id
    msg.set_content(body or "")
    maintype, subtype = XLSX_MIME.split("/")
    msg.add_attachment(xlsx, maintype=maintype, subtype=subtype, filename=filename)
    return msg, rfc_id


def create_delivery(db: Session, *, org_id: uuid.UUID, user_id: uuid.UUID, export_id: uuid.UUID, sender_account_id: uuid.UUID, to: list[str],
                    cc: list[str], subject: str, body: str, confirmed: bool, idempotency_key: str | None) -> tuple[EmailDelivery, bool]:
    """Validate and persist a delivery request. Returns (delivery, created). Does not send."""
    if not confirmed:
        raise ValidationFailure("Sending requires explicit confirmation", code="confirmation_required")
    if idempotency_key:
        existing = db.scalar(select(EmailDelivery).where(EmailDelivery.organization_id == org_id, EmailDelivery.idempotency_key == idempotency_key))
        if existing:
            return existing, False
    to_list, cc_list = validate_recipients(to, "recipients"), validate_recipients(cc or [], "cc")
    if not to_list:
        raise ValidationFailure("At least one recipient is required")
    subject = clean_header(subject)
    if not subject:
        raise ValidationFailure("Subject is required")
    exp, data = read_export_file(db, org_id, export_id)
    limit = get_settings().max_delivery_attachment_mb * 1024 * 1024
    if len(data) > limit:
        raise ValidationFailure(f"Attachment is {len(data) / 1048576:.1f} MB; the limit is {get_settings().max_delivery_attachment_mb} MB", code="attachment_too_large")
    acct = db.scalar(select(EmailAccount).where(EmailAccount.id == sender_account_id, EmailAccount.organization_id == org_id))
    if not acct:
        raise NotFoundError("Sender account not found")
    if acct.connection_status in (ConnectionStatus.DISCONNECTED, ConnectionStatus.EXPIRED):
        raise ConflictError("Sender account must be reauthorized", code="account_needs_reauth")
    if not acct.can_send:
        raise ConflictError("This account was connected without send permission; reauthorize it with send access", code="missing_send_scope")
    d = EmailDelivery(organization_id=org_id, export_job_id=exp.id, sender_account_id=acct.id, recipient_addresses=to_list, cc_addresses=cc_list,
                      subject=subject, body=body or "", status=DeliveryStatus.QUEUED, requested_by=user_id, idempotency_key=idempotency_key)
    db.add(d)
    db.flush()
    audit.record(db, org_id=org_id, user_id=user_id, action="delivery.requested", entity_type="delivery", entity_id=d.id,
                 metadata={"recipients": len(to_list) + len(cc_list), "export_id": str(exp.id), "sender": acct.email_address})
    return d, True


def send_delivery(db: Session, delivery_id: uuid.UUID) -> EmailDelivery:
    d = db.get(EmailDelivery, delivery_id)
    if d is None:
        raise NotFoundError("Delivery not found")
    if d.status in (DeliveryStatus.ACCEPTED, DeliveryStatus.SENDING):
        return d  # idempotent: never double send
    if d.status == DeliveryStatus.UNCERTAIN and not d.rfc_message_id:
        raise ConflictError("Uncertain delivery has no tracking id")
    acct = db.get(EmailAccount, d.sender_account_id) if d.sender_account_id else None
    exp = db.get(ExportJob, d.export_job_id)
    d.status, d.attempts, d.error_summary = DeliveryStatus.SENDING, d.attempts + 1, None
    db.commit()
    try:
        if acct is None:
            raise GmailError("Sender account no longer exists")
        _, data = read_export_file(db, d.organization_id, d.export_job_id)
        gw = gateway_for(db, acct)
        if d.rfc_message_id:
            # a previous attempt may have been accepted: check Gmail's Sent mail before submitting again
            found = gw.find_sent_by_rfc_id(d.rfc_message_id)
            if found:
                return _accepted(db, d, found, acct)
        mime, rfc_id = build_mime(sender=acct.email_address, to=d.recipient_addresses, cc=d.cc_addresses, subject=d.subject, body=d.body,
                                  filename=exp.filename, xlsx=data)
        d.rfc_message_id = rfc_id
        db.commit()  # persist the tracking id BEFORE the network call
        try:
            resp = gw.send_raw(mime.as_bytes())
        except GmailAmbiguousSend:
            found = None
            try:
                found = gw.find_sent_by_rfc_id(rfc_id)
            except GmailError:
                pass
            if found:
                return _accepted(db, d, found, acct)
            d.status = DeliveryStatus.UNCERTAIN
            d.error_summary = "Network error while sending; Gmail may or may not have accepted the message. Check the Sent folder before retrying."
            audit.notify(db, org_id=d.organization_id, kind="send_failed", severity="warning", title="Email delivery outcome uncertain",
                         body=d.subject, link="/exports")
            db.commit()
            return d
        return _accepted(db, d, resp.get("id"), acct)
    except GmailAuthError as e:
        d.status, d.error_summary = DeliveryStatus.FAILED, "Gmail authorization failed; reauthorize the sending account"
        if acct:
            acct.connection_status, acct.last_error = ConnectionStatus.EXPIRED, redact(str(e))[:300]
    except (GmailRateLimited, GmailTransient) as e:
        d.status, d.error_summary = DeliveryStatus.FAILED, f"Temporary Gmail error ({redact(str(e))[:200]}); the message was not sent. You can retry."
    except (GmailError, ValidationFailure, NotFoundError, PermissionError, Exception) as e:  # noqa: BLE001
        d.status, d.error_summary = DeliveryStatus.FAILED, redact(str(e))[:400] or type(e).__name__
        if not isinstance(e, (GmailError, ValidationFailure, NotFoundError)):
            log.exception("delivery_failed", extra={"delivery_id": str(delivery_id)})
    audit.record(db, org_id=d.organization_id, user_id=d.requested_by, action="delivery.failed", entity_type="delivery", entity_id=d.id,
                 metadata={"error": d.error_summary})
    audit.notify(db, org_id=d.organization_id, kind="send_failed", severity="error", title="Email could not be sent", body=d.error_summary, link="/exports")
    db.commit()
    return d


def _accepted(db: Session, d: EmailDelivery, provider_id: str | None, acct: EmailAccount) -> EmailDelivery:
    d.status, d.provider_message_id, d.sent_at, d.error_summary = DeliveryStatus.ACCEPTED, provider_id, utcnow(), None
    audit.record(db, org_id=d.organization_id, user_id=d.requested_by, action="delivery.accepted", entity_type="delivery", entity_id=d.id,
                 metadata={"sender": acct.email_address, "recipients": len(d.recipient_addresses) + len(d.cc_addresses)})
    db.commit()
    return d
