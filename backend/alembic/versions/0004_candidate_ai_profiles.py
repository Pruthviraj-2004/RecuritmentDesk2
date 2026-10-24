"""candidate ai profiles

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-21 14:58:31.814985
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('candidate_ai_profiles',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('candidate_id', sa.Uuid(), nullable=False),
    sa.Column('source_type', sa.String(length=30), nullable=False),
    sa.Column('source_label', sa.String(length=300), nullable=True),
    sa.Column('input_hash', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('model_name', sa.String(length=100), nullable=True),
    sa.Column('prompt_version', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('result', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('applied_fields', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_candidate_ai_candidate', 'candidate_ai_profiles', ['candidate_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_candidate_ai_candidate', table_name='candidate_ai_profiles')
    op.drop_table('candidate_ai_profiles')
