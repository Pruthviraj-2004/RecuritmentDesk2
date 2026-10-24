"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-17 01:12:55.759398
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('organizations',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('slug', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('users',
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('display_name', sa.String(length=200), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('external_auth_ref', sa.String(length=255), nullable=True),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('app_settings',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('section', sa.String(length=40), nullable=False),
    sa.Column('value', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'section', name='uq_setting_org_section')
    )
    op.create_table('audit_logs',
    sa.Column('organization_id', sa.Uuid(), nullable=True),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('entity_type', sa.String(length=50), nullable=True),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('metadata', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_entity', 'audit_logs', ['entity_type', 'entity_id'], unique=False)
    op.create_index('ix_audit_org_created', 'audit_logs', ['organization_id', 'created_at'], unique=False)
    op.create_table('email_accounts',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('connected_by_user_id', sa.Uuid(), nullable=True),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('provider_account_id', sa.String(length=128), nullable=True),
    sa.Column('email_address', sa.String(length=320), nullable=False),
    sa.Column('display_name', sa.String(length=200), nullable=True),
    sa.Column('encrypted_access_token', sa.Text(), nullable=True),
    sa.Column('encrypted_refresh_token', sa.Text(), nullable=True),
    sa.Column('token_expiry', sa.DateTime(timezone=True), nullable=True),
    sa.Column('scopes', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('connection_status', sa.String(length=32), nullable=False),
    sa.Column('sync_enabled', sa.Boolean(), nullable=False),
    sa.Column('import_days', sa.Integer(), nullable=False),
    sa.Column('extra_query', sa.String(length=500), nullable=True),
    sa.Column('is_default_sender', sa.Boolean(), nullable=False),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.String(length=500), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['connected_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'provider', 'email_address', name='uq_account_org_provider_email'),
    sa.UniqueConstraint('provider', 'provider_account_id', 'organization_id', name='uq_account_provider_identity')
    )
    op.create_index(op.f('ix_email_accounts_organization_id'), 'email_accounts', ['organization_id'], unique=False)
    op.create_table('job_requirements',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('client_name', sa.String(length=300), nullable=True),
    sa.Column('client_normalized', sa.String(length=300), nullable=True),
    sa.Column('job_title', sa.String(length=300), nullable=True),
    sa.Column('title_normalized', sa.String(length=300), nullable=True),
    sa.Column('job_reference_id', sa.String(length=100), nullable=True),
    sa.Column('job_description', sa.Text(), nullable=True),
    sa.Column('department', sa.String(length=200), nullable=True),
    sa.Column('seniority', sa.String(length=50), nullable=True),
    sa.Column('minimum_experience', sa.Float(), nullable=True),
    sa.Column('maximum_experience', sa.Float(), nullable=True),
    sa.Column('education', sa.String(length=500), nullable=True),
    sa.Column('certifications', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('domain_experience', sa.String(length=500), nullable=True),
    sa.Column('salary_min', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('salary_max', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('salary_currency', sa.String(length=8), nullable=True),
    sa.Column('salary_period', sa.String(length=20), nullable=True),
    sa.Column('employment_type', sa.String(length=50), nullable=True),
    sa.Column('notice_period', sa.String(length=100), nullable=True),
    sa.Column('location', sa.String(length=300), nullable=True),
    sa.Column('city', sa.String(length=120), nullable=True),
    sa.Column('state', sa.String(length=120), nullable=True),
    sa.Column('country', sa.String(length=120), nullable=True),
    sa.Column('location_normalized', sa.String(length=300), nullable=True),
    sa.Column('work_mode', sa.String(length=16), nullable=False),
    sa.Column('relocation', sa.String(length=200), nullable=True),
    sa.Column('travel', sa.String(length=200), nullable=True),
    sa.Column('recruiter_name', sa.String(length=200), nullable=True),
    sa.Column('recruiter_email', sa.String(length=320), nullable=True),
    sa.Column('recruiter_phone', sa.String(length=50), nullable=True),
    sa.Column('client_contact', sa.String(length=500), nullable=True),
    sa.Column('submission_email', sa.String(length=320), nullable=True),
    sa.Column('submission_instructions', sa.Text(), nullable=True),
    sa.Column('required_documents', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('number_of_openings', sa.Integer(), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('lifecycle_status', sa.String(length=16), nullable=False),
    sa.Column('review_status', sa.String(length=16), nullable=False),
    sa.Column('canonical_fingerprint', sa.String(length=64), nullable=True),
    sa.Column('merged_into_id', sa.Uuid(), nullable=True),
    sa.Column('extraction_confidence', sa.Float(), nullable=True),
    sa.Column('extraction_model', sa.String(length=100), nullable=True),
    sa.Column('validation_warnings', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['merged_into_id'], ['job_requirements.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_req_org_client_norm', 'job_requirements', ['organization_id', 'client_normalized'], unique=False)
    op.create_index('ix_req_org_fingerprint', 'job_requirements', ['organization_id', 'canonical_fingerprint'], unique=False)
    op.create_index('ix_req_org_lifecycle', 'job_requirements', ['organization_id', 'lifecycle_status'], unique=False)
    op.create_index('ix_req_org_received', 'job_requirements', ['organization_id', 'received_at'], unique=False)
    op.create_index('ix_req_org_refid', 'job_requirements', ['organization_id', 'job_reference_id'], unique=False)
    op.create_index('ix_req_org_review', 'job_requirements', ['organization_id', 'review_status'], unique=False)
    op.create_index('ix_req_org_title_norm', 'job_requirements', ['organization_id', 'title_normalized'], unique=False)
    op.create_table('notifications',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('severity', sa.String(length=10), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.String(length=500), nullable=True),
    sa.Column('link', sa.String(length=200), nullable=True),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_notif_org_created', 'notifications', ['organization_id', 'created_at'], unique=False)
    op.create_table('oauth_states',
    sa.Column('state_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('code_verifier', sa.String(length=200), nullable=False),
    sa.Column('purpose', sa.String(length=32), nullable=False),
    sa.Column('enable_send', sa.Boolean(), nullable=False),
    sa.Column('reauthorize_account_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('state_hash')
    )
    op.create_table('organization_memberships',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'user_id', name='uq_membership_org_user')
    )
    op.create_index(op.f('ix_organization_memberships_user_id'), 'organization_memberships', ['user_id'], unique=False)
    op.create_table('user_sessions',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('csrf_token', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('user_agent', sa.String(length=300), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index('ix_sessions_user', 'user_sessions', ['user_id'], unique=False)
    op.create_table('duplicate_candidates',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('requirement_id_a', sa.Uuid(), nullable=False),
    sa.Column('requirement_id_b', sa.Uuid(), nullable=False),
    sa.Column('matching_score', sa.Float(), nullable=False),
    sa.Column('matching_reasons', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('conflicting_fields', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('review_status', sa.String(length=16), nullable=False),
    sa.Column('resolved_by', sa.Uuid(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requirement_id_a'], ['job_requirements.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requirement_id_b'], ['job_requirements.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('requirement_id_a', 'requirement_id_b', name='uq_duplicate_pair')
    )
    op.create_index('ix_dup_org_status', 'duplicate_candidates', ['organization_id', 'review_status'], unique=False)
    op.create_table('email_messages',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('email_account_id', sa.Uuid(), nullable=False),
    sa.Column('gmail_message_id', sa.String(length=64), nullable=False),
    sa.Column('gmail_thread_id', sa.String(length=64), nullable=True),
    sa.Column('rfc_message_id', sa.String(length=300), nullable=True),
    sa.Column('sender', sa.String(length=500), nullable=True),
    sa.Column('sender_email', sa.String(length=320), nullable=True),
    sa.Column('recipients', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('subject', sa.String(length=1000), nullable=True),
    sa.Column('snippet', sa.String(length=500), nullable=True),
    sa.Column('body_text', sa.Text(), nullable=True),
    sa.Column('body_purged', sa.Boolean(), nullable=False),
    sa.Column('labels', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('normalized_content_hash', sa.String(length=64), nullable=True),
    sa.Column('duplicate_of_message_id', sa.Uuid(), nullable=True),
    sa.Column('classification', sa.String(length=40), nullable=True),
    sa.Column('classification_confidence', sa.Float(), nullable=True),
    sa.Column('processing_status', sa.String(length=32), nullable=False),
    sa.Column('processing_attempts', sa.Integer(), nullable=False),
    sa.Column('error_summary', sa.String(length=500), nullable=True),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source_metadata', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['duplicate_of_message_id'], ['email_messages.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['email_account_id'], ['email_accounts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email_account_id', 'gmail_message_id', name='uq_message_account_gmail_id')
    )
    op.create_index('ix_messages_org_hash', 'email_messages', ['organization_id', 'normalized_content_hash'], unique=False)
    op.create_index('ix_messages_org_received', 'email_messages', ['organization_id', 'received_at'], unique=False)
    op.create_index('ix_messages_org_status', 'email_messages', ['organization_id', 'processing_status'], unique=False)
    op.create_index('ix_messages_thread', 'email_messages', ['email_account_id', 'gmail_thread_id'], unique=False)
    op.create_table('email_sync_states',
    sa.Column('email_account_id', sa.Uuid(), nullable=False),
    sa.Column('last_successful_sync_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('gmail_history_id', sa.String(length=32), nullable=True),
    sa.Column('cursor_metadata', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('error_summary', sa.String(length=500), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['email_account_id'], ['email_accounts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email_account_id')
    )
    op.create_table('processing_jobs',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('email_account_id', sa.Uuid(), nullable=True),
    sa.Column('job_type', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('progress', sa.Float(), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('checkpoint', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('stats', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('error_summary', sa.String(length=500), nullable=True),
    sa.Column('requested_by', sa.Uuid(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['email_account_id'], ['email_accounts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_jobs_org_created', 'processing_jobs', ['organization_id', 'created_at'], unique=False)
    op.create_index('ix_jobs_org_status', 'processing_jobs', ['organization_id', 'status'], unique=False)
    op.create_table('requirement_skills',
    sa.Column('job_requirement_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('normalized', sa.String(length=120), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['job_requirement_id'], ['job_requirements.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_requirement_id', 'normalized', 'kind', name='uq_skill_per_requirement')
    )
    op.create_index('ix_skill_normalized', 'requirement_skills', ['normalized'], unique=False)
    op.create_table('requirement_versions',
    sa.Column('job_requirement_id', sa.Uuid(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('previous_values', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('new_values', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('change_source', sa.String(length=40), nullable=False),
    sa.Column('changed_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['job_requirement_id'], ['job_requirements.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_requirement_id', 'version_number', name='uq_version_number')
    )
    op.create_index(op.f('ix_requirement_versions_job_requirement_id'), 'requirement_versions', ['job_requirement_id'], unique=False)
    op.create_table('email_attachments',
    sa.Column('email_message_id', sa.Uuid(), nullable=False),
    sa.Column('gmail_attachment_id', sa.String(length=300), nullable=True),
    sa.Column('filename', sa.String(length=500), nullable=False),
    sa.Column('content_type', sa.String(length=200), nullable=True),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('storage_reference', sa.String(length=500), nullable=True),
    sa.Column('extraction_status', sa.String(length=32), nullable=False),
    sa.Column('extracted_text_reference', sa.String(length=500), nullable=True),
    sa.Column('error_summary', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['email_message_id'], ['email_messages.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_attachments_message', 'email_attachments', ['email_message_id'], unique=False)
    op.create_table('export_jobs',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('requested_by', sa.Uuid(), nullable=True),
    sa.Column('filename', sa.String(length=200), nullable=False),
    sa.Column('options', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('filters', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('selected_record_ids', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('file_reference', sa.String(length=500), nullable=True),
    sa.Column('file_size_bytes', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('error_summary', sa.String(length=500), nullable=True),
    sa.Column('record_count', sa.Integer(), nullable=True),
    sa.Column('processing_job_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['processing_job_id'], ['processing_jobs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_export_org_created', 'export_jobs', ['organization_id', 'created_at'], unique=False)
    op.create_table('extraction_runs',
    sa.Column('email_message_id', sa.Uuid(), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('model_name', sa.String(length=100), nullable=True),
    sa.Column('prompt_version', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('extracted_data', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('confidence_metadata', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('error_code', sa.String(length=50), nullable=True),
    sa.Column('error_message', sa.String(length=500), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['email_message_id'], ['email_messages.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_extraction_message', 'extraction_runs', ['email_message_id'], unique=False)
    op.create_table('requirement_sources',
    sa.Column('job_requirement_id', sa.Uuid(), nullable=False),
    sa.Column('email_message_id', sa.Uuid(), nullable=True),
    sa.Column('source_type', sa.String(length=32), nullable=False),
    sa.Column('evidence_metadata', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('linked_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['email_message_id'], ['email_messages.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['job_requirement_id'], ['job_requirements.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_requirement_id', 'email_message_id', 'source_type', name='uq_source_req_msg_type')
    )
    op.create_index('ix_source_message', 'requirement_sources', ['email_message_id'], unique=False)
    op.create_table('email_deliveries',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('export_job_id', sa.Uuid(), nullable=False),
    sa.Column('sender_account_id', sa.Uuid(), nullable=True),
    sa.Column('recipient_addresses', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('cc_addresses', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('subject', sa.String(length=500), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('rfc_message_id', sa.String(length=300), nullable=True),
    sa.Column('provider_message_id', sa.String(length=100), nullable=True),
    sa.Column('error_summary', sa.String(length=500), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('idempotency_key', sa.String(length=100), nullable=True),
    sa.Column('requested_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['export_job_id'], ['export_jobs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sender_account_id'], ['email_accounts.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'idempotency_key', name='uq_delivery_idempotency')
    )
    op.create_index('ix_delivery_org_created', 'email_deliveries', ['organization_id', 'created_at'], unique=False)

    # PostgreSQL only: trigram indexes speed up ILIKE search over requirements.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        schema = op.get_context().version_table_schema or "public"
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        for name, col in (("ix_req_title_trgm", "job_title"), ("ix_req_client_trgm", "client_name"), ("ix_req_location_trgm", "location")):
            op.execute(f'CREATE INDEX IF NOT EXISTS {name} ON "{schema}".job_requirements USING gin ({col} gin_trgm_ops)')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        schema = op.get_context().version_table_schema or "public"
        for name in ("ix_req_title_trgm", "ix_req_client_trgm", "ix_req_location_trgm"):
            op.execute(f'DROP INDEX IF EXISTS "{schema}".{name}')

    op.drop_index('ix_delivery_org_created', table_name='email_deliveries')
    op.drop_table('email_deliveries')
    op.drop_index('ix_source_message', table_name='requirement_sources')
    op.drop_table('requirement_sources')
    op.drop_index('ix_extraction_message', table_name='extraction_runs')
    op.drop_table('extraction_runs')
    op.drop_index('ix_export_org_created', table_name='export_jobs')
    op.drop_table('export_jobs')
    op.drop_index('ix_attachments_message', table_name='email_attachments')
    op.drop_table('email_attachments')
    op.drop_index(op.f('ix_requirement_versions_job_requirement_id'), table_name='requirement_versions')
    op.drop_table('requirement_versions')
    op.drop_index('ix_skill_normalized', table_name='requirement_skills')
    op.drop_table('requirement_skills')
    op.drop_index('ix_jobs_org_status', table_name='processing_jobs')
    op.drop_index('ix_jobs_org_created', table_name='processing_jobs')
    op.drop_table('processing_jobs')
    op.drop_table('email_sync_states')
    op.drop_index('ix_messages_thread', table_name='email_messages')
    op.drop_index('ix_messages_org_status', table_name='email_messages')
    op.drop_index('ix_messages_org_received', table_name='email_messages')
    op.drop_index('ix_messages_org_hash', table_name='email_messages')
    op.drop_table('email_messages')
    op.drop_index('ix_dup_org_status', table_name='duplicate_candidates')
    op.drop_table('duplicate_candidates')
    op.drop_index('ix_sessions_user', table_name='user_sessions')
    op.drop_table('user_sessions')
    op.drop_index(op.f('ix_organization_memberships_user_id'), table_name='organization_memberships')
    op.drop_table('organization_memberships')
    op.drop_table('oauth_states')
    op.drop_index('ix_notif_org_created', table_name='notifications')
    op.drop_table('notifications')
    op.drop_index('ix_req_org_title_norm', table_name='job_requirements')
    op.drop_index('ix_req_org_review', table_name='job_requirements')
    op.drop_index('ix_req_org_refid', table_name='job_requirements')
    op.drop_index('ix_req_org_received', table_name='job_requirements')
    op.drop_index('ix_req_org_lifecycle', table_name='job_requirements')
    op.drop_index('ix_req_org_fingerprint', table_name='job_requirements')
    op.drop_index('ix_req_org_client_norm', table_name='job_requirements')
    op.drop_table('job_requirements')
    op.drop_index(op.f('ix_email_accounts_organization_id'), table_name='email_accounts')
    op.drop_table('email_accounts')
    op.drop_index('ix_audit_org_created', table_name='audit_logs')
    op.drop_index('ix_audit_entity', table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_table('app_settings')
    op.drop_table('users')
    op.drop_table('organizations')
