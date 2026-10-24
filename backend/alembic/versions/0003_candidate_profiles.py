"""candidate profiles

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-20 23:53:56.472930
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('candidate_imports',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('filename', sa.String(length=300), nullable=False),
    sa.Column('on_duplicate', sa.String(length=10), nullable=False),
    sa.Column('total_rows', sa.Integer(), nullable=False),
    sa.Column('created_count', sa.Integer(), nullable=False),
    sa.Column('updated_count', sa.Integer(), nullable=False),
    sa.Column('skipped_count', sa.Integer(), nullable=False),
    sa.Column('failed_count', sa.Integer(), nullable=False),
    sa.Column('error_report', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_candidate_import_org', 'candidate_imports', ['organization_id', 'created_at'], unique=False)
    op.create_table('candidates',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('first_name', sa.String(length=120), nullable=False),
    sa.Column('last_name', sa.String(length=120), nullable=True),
    sa.Column('full_name', sa.String(length=250), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('email_normalized', sa.String(length=320), nullable=False),
    sa.Column('phone', sa.String(length=50), nullable=False),
    sa.Column('phone_normalized', sa.String(length=20), nullable=False),
    sa.Column('current_title', sa.String(length=200), nullable=True),
    sa.Column('current_company', sa.String(length=200), nullable=True),
    sa.Column('total_experience', sa.Float(), nullable=True),
    sa.Column('relevant_experience', sa.Float(), nullable=True),
    sa.Column('current_location', sa.String(length=200), nullable=True),
    sa.Column('preferred_locations', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('willing_to_relocate', sa.Boolean(), nullable=True),
    sa.Column('notice_period', sa.String(length=100), nullable=True),
    sa.Column('current_ctc', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('expected_ctc', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=8), nullable=True),
    sa.Column('education', sa.String(length=500), nullable=True),
    sa.Column('certifications', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('work_authorization', sa.String(length=100), nullable=True),
    sa.Column('linkedin_url', sa.String(length=500), nullable=True),
    sa.Column('resume_url', sa.String(length=500), nullable=True),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=60), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=True),
    sa.Column('tags', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('last_contacted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('import_id', sa.Uuid(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['import_id'], ['candidate_imports.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'email_normalized', name='uq_candidate_org_email')
    )
    op.create_index('ix_candidate_org_created', 'candidates', ['organization_id', 'created_at'], unique=False)
    op.create_index('ix_candidate_org_name', 'candidates', ['organization_id', 'full_name'], unique=False)
    op.create_index('ix_candidate_org_phone', 'candidates', ['organization_id', 'phone_normalized'], unique=False)
    op.create_index('ix_candidate_org_status', 'candidates', ['organization_id', 'status'], unique=False)
    op.create_table('candidate_notes',
    sa.Column('candidate_id', sa.Uuid(), nullable=False),
    sa.Column('author_user_id', sa.Uuid(), nullable=True),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_candidate_note_candidate', 'candidate_notes', ['candidate_id', 'created_at'], unique=False)
    op.create_table('candidate_skills',
    sa.Column('candidate_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('normalized', sa.String(length=120), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('candidate_id', 'normalized', name='uq_candidate_skill')
    )
    op.create_index('ix_candidate_skill_norm', 'candidate_skills', ['normalized'], unique=False)
    op.create_table('candidate_submissions',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('candidate_id', sa.Uuid(), nullable=False),
    sa.Column('requirement_id', sa.Uuid(), nullable=False),
    sa.Column('stage', sa.String(length=20), nullable=False),
    sa.Column('notes', sa.String(length=1000), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requirement_id'], ['job_requirements.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('candidate_id', 'requirement_id', name='uq_submission_candidate_requirement')
    )
    op.create_index('ix_submission_requirement', 'candidate_submissions', ['requirement_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_submission_requirement', table_name='candidate_submissions')
    op.drop_table('candidate_submissions')
    op.drop_index('ix_candidate_skill_norm', table_name='candidate_skills')
    op.drop_table('candidate_skills')
    op.drop_index('ix_candidate_note_candidate', table_name='candidate_notes')
    op.drop_table('candidate_notes')
    op.drop_index('ix_candidate_org_status', table_name='candidates')
    op.drop_index('ix_candidate_org_phone', table_name='candidates')
    op.drop_index('ix_candidate_org_name', table_name='candidates')
    op.drop_index('ix_candidate_org_created', table_name='candidates')
    op.drop_table('candidates')
    op.drop_index('ix_candidate_import_org', table_name='candidate_imports')
    op.drop_table('candidate_imports')
