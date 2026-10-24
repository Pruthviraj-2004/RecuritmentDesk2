"""Detect mail that RecruitmentDesk (or you) generated from already-extracted requirements, so it is never extracted a second time.

Rules (all conservative; ordinary mail from your own other accounts is still processed):
  * recruitmentdesk_export - the message carries our X-RecruitmentDesk-Export header, or its Message-ID is one we generated for a delivery
  * own_digest_spreadsheet - sent BY one of your connected accounts and carrying a spreadsheet attachment (a manually sent digest/report)
  * own_sent_only          - exists only in the account's Sent folder (label SENT without INBOX): outgoing mail is never a requirement
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.email import EmailAccount
from app.models.ops import EmailDelivery

EXPORT_HEADER = "X-RecruitmentDesk-Export"
SPREADSHEET_EXT = (".xlsx", ".xlsm", ".xlsb", ".xls", ".csv", ".ods")
SPREADSHEET_MIME_HINTS = ("spreadsheetml", "ms-excel", "text/csv", "opendocument.spreadsheet")


def own_addresses(db: Session, org_id: uuid.UUID) -> set[str]:
    return {a.lower() for a in db.scalars(select(EmailAccount.email_address).where(EmailAccount.organization_id == org_id))}


def is_our_message_id(db: Session, org_id: uuid.UUID, rfc_message_id: str | None) -> bool:
    if not rfc_message_id:
        return False
    return db.scalar(select(EmailDelivery.id).where(EmailDelivery.organization_id == org_id, EmailDelivery.rfc_message_id == rfc_message_id.strip())) is not None


def has_spreadsheet(filenames: list[str], mime_types: list[str | None]) -> bool:
    return any(n.lower().endswith(SPREADSHEET_EXT) for n in filenames) or any(any(h in (m or "").lower() for h in SPREADSHEET_MIME_HINTS) for m in mime_types)


def own_mail_reason(db: Session, org_id: uuid.UUID, *, sender_email: str | None, own: set[str], filenames: list[str], mime_types: list[str | None],
                    labels: list[str], export_header: bool, rfc_message_id: str | None) -> str | None:
    if export_header or is_our_message_id(db, org_id, rfc_message_id):
        return "recruitmentdesk_export"
    if sender_email and sender_email.lower() in own and has_spreadsheet(filenames, mime_types):
        return "own_digest_spreadsheet"
    if "SENT" in (labels or []) and "INBOX" not in (labels or []):
        return "own_sent_only"
    return None
