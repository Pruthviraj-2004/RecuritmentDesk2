// Types mirroring backend/app/schemas/api.py (FastAPI OpenAPI: /api/openapi.json)
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }

export interface User { id: string; email: string; display_name: string }
export type Role = "owner" | "admin" | "member" | "viewer";
export interface Me { user: User; organization: { id: string; name: string; slug: string }; role: Role; csrf_token: string }

export type ConnectionStatus = "connected" | "syncing" | "disconnected" | "expired" | "error";
export interface Account {
  id: string; email_address: string; masked_email: string; display_name: string | null; provider: string; connection_status: ConnectionStatus;
  sync_enabled: boolean; import_days: number; extra_query: string | null; is_default_sender: boolean; scopes: string[]; can_send: boolean; can_read: boolean;
  last_synced_at: string | null; last_error: string | null; created_at: string;
  stats: { messages?: number; processed?: number; failed?: number; pending?: number; requirements?: number };
}

export type ReviewStatus = "needs_review" | "approved" | "rejected";
export type LifecycleStatus = "active" | "closed" | "archived" | "merged";
export type WorkMode = "remote" | "hybrid" | "onsite" | "unknown";

export interface Requirement {
  id: string; client_name: string | null; job_title: string | null; job_reference_id: string | null; job_description?: string | null;
  required_skills: string[]; preferred_skills: string[]; minimum_experience: number | null; maximum_experience: number | null;
  salary_min: number | null; salary_max: number | null; salary_currency: string | null; salary_period: string | null; employment_type: string | null;
  location: string | null; work_mode: WorkMode; recruiter_name: string | null; recruiter_email: string | null; number_of_openings: number | null;
  received_at: string | null; last_updated_at: string | null; lifecycle_status: LifecycleStatus; review_status: ReviewStatus;
  extraction_confidence: number | null; validation_warnings: string[]; version_number: number; merged_into_id: string | null;
  source_accounts: string[]; source_count: number; has_pending_duplicate: boolean;
}
export interface RequirementDetail extends Requirement {
  department: string | null; seniority: string | null; education: string | null; domain_experience: string | null; notice_period: string | null;
  city: string | null; state: string | null; country: string | null; relocation: string | null; travel: string | null; recruiter_phone: string | null;
  client_contact: string | null; submission_email: string | null; submission_instructions: string | null; certifications: string[];
  required_documents: string[]; extraction_model: string | null; created_at: string; updated_at: string;
}
/** Editable fields accepted by POST/PATCH /requirements */
export interface RequirementInput {
  client_name?: string | null; job_title?: string | null; job_reference_id?: string | null; job_description?: string | null; department?: string | null;
  seniority?: string | null; minimum_experience?: number | null; maximum_experience?: number | null; education?: string | null;
  domain_experience?: string | null; salary_min?: number | null; salary_max?: number | null; salary_currency?: string | null;
  salary_period?: "hour" | "day" | "month" | "year" | null; employment_type?: string | null; notice_period?: string | null; location?: string | null;
  city?: string | null; state?: string | null; country?: string | null; work_mode?: WorkMode | null; relocation?: string | null; travel?: string | null;
  recruiter_name?: string | null; recruiter_email?: string | null; recruiter_phone?: string | null; client_contact?: string | null;
  submission_email?: string | null; submission_instructions?: string | null; number_of_openings?: number | null; certifications?: string[];
  required_documents?: string[]; required_skills?: string[]; preferred_skills?: string[];
}

export interface Source {
  id: string; source_type: string; linked_at: string; email_message_id: string | null; account_email: string | null; sender: string | null;
  subject: string | null; received_at: string | null; gmail_url: string | null; evidence: Record<string, unknown>;
}
export interface Version { id: string; version_number: number; previous_values: Record<string, unknown>; new_values: Record<string, unknown>; change_source: string; changed_by: string | null; created_at: string }

export type DuplicateStatus = "pending" | "merged" | "kept_both" | "related" | "dismissed";
export interface Duplicate {
  id: string; matching_score: number; matching_reasons: string[]; conflicting_fields: string[]; review_status: DuplicateStatus; created_at: string;
  resolved_at: string | null; requirement_a: Requirement; requirement_b: Requirement;
}
export interface DuplicateDetail extends Duplicate { sources_a: Source[]; sources_b: Source[] }

export interface Job {
  id: string; job_type: string; status: string; progress: number | null; attempts: number; max_attempts: number; email_account_id: string | null;
  account_email: string | null; stats: Record<string, number>; checkpoint: Record<string, unknown>; error_summary: string | null;
  started_at: string | null; completed_at: string | null; created_at: string; duration_seconds: number | null;
}
export interface JobsSummary {
  messages: Record<string, number>; extraction_pending: number; extraction_failed: number;
  accounts: { id: string; email: string; status: string; last_synced_at: string | null; last_error: string | null }[];
}

export interface ExportJob {
  id: string; filename: string; status: "queued" | "running" | "completed" | "failed" | "expired"; record_count: number | null; file_size_bytes: number | null;
  error_summary: string | null; created_at: string; completed_at: string | null; expires_at: string | null; options: Record<string, unknown>;
  filters: Record<string, unknown>; requested_by: string | null;
}
export interface ExportColumn { key: string; header: string; group: string; default: boolean }
export interface Delivery {
  id: string; export_job_id: string; sender_account_id: string | null; sender_email: string | null; recipient_addresses: string[]; cc_addresses: string[];
  subject: string; status: "queued" | "sending" | "accepted_by_gmail" | "failed" | "uncertain"; status_label: string; provider_message_id: string | null;
  error_summary: string | null; attempts: number; created_at: string; sent_at: string | null;
}

export interface AuditEntry { id: string; user_id: string | null; user_email: string | null; action: string; entity_type: string | null; entity_id: string | null; metadata: Record<string, unknown>; created_at: string }
export interface Notification { id: string; kind: string; severity: string; title: string; body: string | null; link: string | null; read_at: string | null; created_at: string }

export interface NamedCount { name: string; count: number }
export interface Overview {
  range: { from: string; to: string };
  kpis: {
    total_unique_requirements: number; awaiting_review: number; approved: number; received_today: number; received_this_week: number; duplicates_pending: number;
    emails_processed: number; extraction_failed_or_pending: number; connected_accounts: number; accounts_needing_attention: number;
    last_successful_sync: string | null; pending_deliveries: number; candidates: number;
  };
  received_over_time: { date: string; count: number }[]; weekly_activity: { week: string; count: number }[]; monthly_activity: { month: string; count: number }[];
  by_status: NamedCount[]; by_location: NamedCount[]; by_client: NamedCount[]; top_skills: NamedCount[]; by_source_account: NamedCount[];
  email_processing: { succeeded: number; failed: number; pending: number };
}
export interface RecruitmentAnalytics {
  range: { from: string; to: string }; total_requirements: number; by_client: NamedCount[]; by_location: NamedCount[]; by_work_mode: NamedCount[];
  by_experience: NamedCount[]; by_skill: NamedCount[];
  duplicate_rate: { value: number | null; duplicate_candidates: number; cross_account_copies: number };
  extraction_success_rate: { value: number | null; runs: number }; manual_correction_rate: { value: number | null; corrected: number; extracted: number };
  average_job_duration_seconds: number | null; failed_jobs_by_type: NamedCount[]; account_activity: NamedCount[];
}

export interface HealthDetails {
  version: string; database: { status: string; detail?: string }; redis: { status: string; detail?: string }; worker: { status: string; detail?: string };
  ai: { status: string; provider: string }; gmail: { status: string; detail?: string | null };
}
export interface AiStatus { provider: string; model: string | null; configured: boolean; base_url_host: string | null; message: string | null; health?: { status: string; detail: string | null } }

// ---------------------------------------------------------------- candidates
export type CandidateStatus = "new" | "screening" | "shortlisted" | "interviewing" | "offered" | "hired" | "rejected" | "on_hold" | "not_interested";
export const CANDIDATE_STATUSES: CandidateStatus[] = ["new", "screening", "shortlisted", "interviewing", "offered", "hired", "rejected", "on_hold", "not_interested"];
export type PipelineStage = "shortlisted" | "submitted" | "interview" | "offered" | "joined" | "rejected" | "withdrawn";
export const PIPELINE_STAGES: PipelineStage[] = ["shortlisted", "submitted", "interview", "offered", "joined", "rejected", "withdrawn"];

export interface Candidate {
  id: string; first_name: string; last_name: string | null; full_name: string; email: string; phone: string; current_title: string | null; current_company: string | null;
  total_experience: number | null; relevant_experience: number | null; current_location: string | null; preferred_locations: string[]; willing_to_relocate: boolean | null;
  notice_period: string | null; current_ctc: number | null; expected_ctc: number | null; currency: string | null; education: string | null; certifications: string[];
  work_authorization: string | null; linkedin_url: string | null; resume_url: string | null; summary: string | null; source: string; status: CandidateStatus; rating: number | null;
  tags: string[]; skills: string[]; is_archived: boolean; last_contacted_at: string | null; created_at: string; updated_at: string; pipeline_count: number;
}
/** Fields accepted by POST/PATCH /candidates. Name, email and phone are mandatory on create. */
export interface CandidateInput {
  first_name?: string; last_name?: string | null; email?: string; phone?: string; current_title?: string | null; current_company?: string | null; total_experience?: number | null;
  relevant_experience?: number | null; current_location?: string | null; preferred_locations?: string[]; willing_to_relocate?: boolean | null; notice_period?: string | null;
  current_ctc?: number | null; expected_ctc?: number | null; currency?: string | null; education?: string | null; certifications?: string[]; work_authorization?: string | null;
  linkedin_url?: string | null; resume_url?: string | null; summary?: string | null; source?: string | null; status?: CandidateStatus; rating?: number | null; tags?: string[];
  skills?: string[]; initial_note?: string | null;
}
export interface CandidateStats { total: number; new_this_week: number; in_pipeline: number; by_status: Record<string, number> }
export interface ImportRowInfo { row: number; name: string; email: string | null; action: string; errors: string[]; warnings: string[]; matched_name: string | null }
export interface ImportPreview {
  total_rows: number; counts: { create: number; update: number; skip_duplicate: number; skip_in_file: number; error: number }; recognised_columns: string[]; ignored_columns: string[];
  problems: ImportRowInfo[]; sample: ImportRowInfo[]; truncated: boolean;
}
export interface ImportResult { id: string; filename: string; total_rows: number; created: number; updated: number; skipped: number; failed: number; problems: { row: number; name: string; action: string; problems: string[] }[] }
export interface ImportHistoryItem extends ImportResult { created_at: string; on_duplicate: string }
export interface CandidateNote { id: string; kind: "note" | "status" | "system"; body: string; author: string | null; created_at: string }
export interface Submission {
  id: string; stage: PipelineStage; notes: string | null; created_at: string; updated_at: string; candidate_id: string; candidate_name: string; candidate_title: string | null;
  requirement_id: string; requirement_title: string | null; requirement_client: string | null;
}
export interface MatchInfo { score: number; matched_skills: string[]; missing_skills: string[]; reasons: string[]; stage: PipelineStage | null; ai_profile_used?: boolean; ai_only_matches?: string[] }
export interface CandidateMatch extends MatchInfo { candidate: Candidate }
export interface RequirementMatch extends MatchInfo {
  requirement: { id: string; job_title: string | null; client_name: string | null; location: string | null; work_mode: string; minimum_experience: number | null; maximum_experience: number | null; required_skills: string[] };
}

// ---------------------------------------------------------------- candidate AI profile
export interface AiPosition { company: string; title: string | null; start: string | null; end: string | null; location: string | null; description: string | null; skills_used: string[] }
export interface AiProfileData {
  headline: string | null; ai_summary: string | null; current_title: string | null; current_company: string | null; location: string | null; seniority: string | null; industries: string[];
  skills: string[]; top_skills: string[]; positions: AiPosition[]; education: { school: string; degree: string | null; field: string | null; start_year: number | null; end_year: number | null }[];
  certifications: string[]; projects: { name: string; description: string | null; technologies: string[]; url: string | null }[]; languages: string[]; honors: string[]; links: string[];
  contact_email: string | null; contact_phone: string | null; career_highlights: string[]; screening_questions: string[];
}
export interface AiAnalytics {
  total_experience_years: number | null; employers: number; roles: number; average_tenure_months: number | null; longest_tenure: { company: string; months: number } | null;
  recent_companies: string[]; employers_last_5_years: number | null; short_stints: { company: string; months: number }[]; gaps: { after: string; before: string; months: number }[];
  currently_employed: boolean; undated_roles: number;
}
export interface AiProfileRecord {
  id: string; created_at: string; source_type: string; source_label: string | null; provider: string; model: string | null; prompt_version: string; applied_fields: string[]; applied_at: string | null;
  result: { profile: AiProfileData; analytics: AiAnalytics; verify: string[]; warnings: string[] };
}
export interface AiProfileHistoryItem { id: string; created_at: string; source_type: string; source_label: string | null; model: string | null; headline: string | null; applied_fields: string[] }

export interface ApiErrorBody { error: { code: string; message: string; details?: unknown; request_id?: string } }
