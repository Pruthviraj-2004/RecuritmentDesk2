import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import type {
  Account, AiProfileHistoryItem, AiProfileRecord, AiStatus, Candidate, CandidateMatch, CandidateNote, CandidateStats, ImportHistoryItem, RequirementMatch, Submission, AuditEntry, Delivery, Duplicate, DuplicateDetail, ExportColumn, ExportJob, HealthDetails, Job, JobsSummary,
  Notification, Overview, Page, RecruitmentAnalytics, RequirementDetail, RequirementInput, Requirement, Source, Version,
} from "@/types/api";

type Params = Record<string, string | number | boolean | null | undefined>;

// ---------------------------------------------------------------- accounts
export const useAccounts = () => useQuery({ queryKey: ["accounts"], queryFn: () => api.get<Account[]>("/email-accounts"), refetchInterval: 15_000 });

// ---------------------------------------------------------------- requirements
export const useRequirements = (params: Params) =>
  useQuery({ queryKey: ["requirements", params], queryFn: () => api.get<Page<Requirement>>("/requirements", params), placeholderData: keepPreviousData });
export const useRequirement = (id: string | undefined) =>
  useQuery({ queryKey: ["requirement", id], queryFn: () => api.get<RequirementDetail>(`/requirements/${id}`), enabled: !!id });
export const useRequirementSources = (id: string, enabled = true) => useQuery({ queryKey: ["requirement", id, "sources"], queryFn: () => api.get<Source[]>(`/requirements/${id}/sources`), enabled });
export const useRequirementVersions = (id: string, enabled = true) => useQuery({ queryKey: ["requirement", id, "versions"], queryFn: () => api.get<Version[]>(`/requirements/${id}/versions`), enabled });
export const useSimilar = (id: string, enabled: boolean) =>
  useQuery({ queryKey: ["requirement", id, "similar"], queryFn: () => api.get<{ score: number; reasons: string[]; conflicts: string[]; requirement: Requirement }[]>(`/requirements/${id}/similar`), enabled });

// ---------------------------------------------------------------- emails / duplicates / jobs / exports
export const useDuplicates = (params: Params) => useQuery({ queryKey: ["duplicates", params], queryFn: () => api.get<Page<Duplicate>>("/duplicates", params), placeholderData: keepPreviousData });
export const useDuplicate = (id: string | null) => useQuery({ queryKey: ["duplicate", id], queryFn: () => api.get<DuplicateDetail>(`/duplicates/${id}`), enabled: !!id });
export const useJobs = (params: Params) => useQuery({ queryKey: ["jobs", params], queryFn: () => api.get<Page<Job>>("/jobs", params), refetchInterval: 4_000, placeholderData: keepPreviousData });
export interface ProcessingIssue { id: string; subject: string | null; sender: string | null; received_at: string | null; status: string; error: string | null; account: string }
export const useProcessingIssues = () => useQuery({ queryKey: ["jobs-issues"], queryFn: () => api.get<ProcessingIssue[]>("/jobs/issues"), refetchInterval: 10_000 });
export const useJobsSummary = () => useQuery({ queryKey: ["jobs-summary"], queryFn: () => api.get<JobsSummary>("/jobs/summary"), refetchInterval: 6_000 });
export const useExports = (params: Params = {}) => useQuery({ queryKey: ["exports", params], queryFn: () => api.get<Page<ExportJob>>("/exports", params), refetchInterval: 5_000 });
export const useDeliveries = (params: Params = {}) => useQuery({ queryKey: ["deliveries", params], queryFn: () => api.get<Page<Delivery>>("/deliveries", params), refetchInterval: 5_000 });
export const useExportColumns = () => useQuery({ queryKey: ["export-columns"], queryFn: () => api.get<{ columns: ExportColumn[] }>("/exports/columns"), staleTime: Infinity });
export const useEmailTemplates = () => useQuery({ queryKey: ["email-templates"], queryFn: () => api.get<Record<string, { subject: string; body: string }>>("/exports/templates/email"), staleTime: Infinity });

// ---------------------------------------------------------------- analytics / ops
export const useOverview = (params: Params) => useQuery({ queryKey: ["overview", params], queryFn: () => api.get<Overview>("/analytics/overview", params), refetchInterval: 30_000, placeholderData: keepPreviousData });
export const useRecruitmentAnalytics = (params: Params) => useQuery({ queryKey: ["recruitment-analytics", params], queryFn: () => api.get<RecruitmentAnalytics>("/analytics/recruitment", params), placeholderData: keepPreviousData });
export const useAudit = (params: Params) => useQuery({ queryKey: ["audit", params], queryFn: () => api.get<Page<AuditEntry>>("/audit-logs", params), placeholderData: keepPreviousData });
export const useNotifications = () => useQuery({ queryKey: ["notifications"], queryFn: () => api.get<{ unread: number; items: Notification[] }>("/notifications"), refetchInterval: 30_000 });
export const useHealth = () => useQuery({ queryKey: ["health"], queryFn: () => api.get<HealthDetails>("/health/details"), refetchInterval: 30_000 });
export const useAiStatus = (check: boolean) => useQuery({ queryKey: ["ai-status", check], queryFn: () => api.get<AiStatus>("/settings-meta/ai", { check }), enabled: true });
export const useSettings = <T,>(section: string) => useQuery({ queryKey: ["settings", section], queryFn: () => api.get<T>(`/settings/${section}`) });

// ---------------------------------------------------------------- generic mutation helper with real success/error toasts
interface MutOpts<TVars, TData> {
  fn: (v: TVars) => Promise<TData>;
  invalidate?: QueryKey[];
  success?: string | null | ((d: TData, v: TVars) => string | null);
  onDone?: (d: TData, v: TVars) => void;
}
export function useAction<TVars = void, TData = unknown>({ fn, invalidate = [], success, onDone }: MutOpts<TVars, TData>) {
  const qc = useQueryClient();
  return useMutation<TData, Error, TVars>({
    mutationFn: fn,
    onSuccess: (d, v) => {
      invalidate.forEach((k) => qc.invalidateQueries({ queryKey: k }));
      const msg = typeof success === "function" ? success(d, v) : success;
      if (msg) toast.success(msg);
      onDone?.(d, v);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}

const REQ_KEYS: QueryKey[] = [["requirements"], ["requirement"], ["overview"], ["duplicates"], ["recruitment-analytics"]];
export const reqKeys = REQ_KEYS;

export function useRequirementAction(action: "approve" | "reject" | "archive" | "restore") {
  const labels = { approve: "approved", reject: "rejected", archive: "archived", restore: "restored" };
  return useAction<string, RequirementDetail>({ fn: (id) => api.post(`/requirements/${id}/${action}`), invalidate: REQ_KEYS, success: `Requirement ${labels[action]}` });
}
export function useUpdateRequirement(id: string) {
  return useAction<RequirementInput, RequirementDetail>({ fn: (b) => api.patch(`/requirements/${id}`, b), invalidate: [...REQ_KEYS, ["audit"]], success: "Requirement saved" });
}

// ---------------------------------------------------------------- candidates
export const useCandidates = (params: Params) => useQuery({ queryKey: ["candidates", params], queryFn: () => api.get<Page<Candidate>>("/candidates", params), placeholderData: keepPreviousData });
export const useCandidate = (id: string | undefined) => useQuery({ queryKey: ["candidate", id], queryFn: () => api.get<Candidate>(`/candidates/${id}`), enabled: !!id });
export const useCandidateStats = () => useQuery({ queryKey: ["candidate-stats"], queryFn: () => api.get<CandidateStats>("/candidates/stats") });
export const useCandidateNotes = (id: string) => useQuery({ queryKey: ["candidate", id, "notes"], queryFn: () => api.get<CandidateNote[]>(`/candidates/${id}/notes`) });
export const useCandidateSubmissions = (id: string) => useQuery({ queryKey: ["candidate", id, "submissions"], queryFn: () => api.get<Submission[]>(`/candidates/${id}/submissions`) });
export const useCandidateMatches = (id: string) => useQuery({ queryKey: ["candidate", id, "matches"], queryFn: () => api.get<RequirementMatch[]>(`/candidates/${id}/matching-requirements`) });
export const useRequirementMatches = (id: string, enabled = true) => useQuery({ queryKey: ["requirement", id, "matching-candidates"], queryFn: () => api.get<CandidateMatch[]>(`/requirements/${id}/matching-candidates`), enabled });
export const useRequirementSubmissions = (id: string, enabled = true) => useQuery({ queryKey: ["requirement", id, "submissions"], queryFn: () => api.get<Submission[]>(`/requirements/${id}/submissions`), enabled });
export const useImportHistory = (enabled = true) => useQuery({ queryKey: ["candidate-imports"], queryFn: () => api.get<ImportHistoryItem[]>("/candidates/imports"), enabled });
export const candidateKeys: QueryKey[] = [["candidates"], ["candidate"], ["candidate-stats"], ["candidate-imports"], ["overview"], ["requirement"]];

// ---------------------------------------------------------------- candidate AI profile
export const useAiProfile = (id: string, profileId?: string | null) => useQuery({
  queryKey: ["candidate", id, "ai-profile", profileId ?? "latest"],
  queryFn: async () => (profileId ? api.get<AiProfileRecord>(`/candidates/${id}/ai-profiles/${profileId}`) : (await api.get<{ profile: AiProfileRecord | null }>(`/candidates/${id}/ai-profile`)).profile),
});
export const useAiProfileHistory = (id: string) => useQuery({ queryKey: ["candidate", id, "ai-profiles"], queryFn: () => api.get<AiProfileHistoryItem[]>(`/candidates/${id}/ai-profiles`) });
