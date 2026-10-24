"""widen gmail attachment id and rfc message id columns

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _schema():
    return op.get_context().version_table_schema  # None unless DATABASE_SCHEMA is set (PostgreSQL)


def upgrade() -> None:
    with op.batch_alter_table("email_attachments", schema=_schema()) as b:
        b.alter_column("gmail_attachment_id", existing_type=sa.String(length=300), type_=sa.Text(), existing_nullable=True)
    with op.batch_alter_table("email_messages", schema=_schema()) as b:
        b.alter_column("rfc_message_id", existing_type=sa.String(length=300), type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("email_messages", schema=_schema()) as b:
        b.alter_column("rfc_message_id", existing_type=sa.Text(), type_=sa.String(length=300), existing_nullable=True)
    with op.batch_alter_table("email_attachments", schema=_schema()) as b:
        b.alter_column("gmail_attachment_id", existing_type=sa.Text(), type_=sa.String(length=300), existing_nullable=True)
