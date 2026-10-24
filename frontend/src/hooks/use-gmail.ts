import { api } from "@/lib/api";
import { useAction } from "@/services/hooks";

interface SyncResult { started?: { account: string; job_id: string; already_running: boolean }[]; skipped?: { account: string; reason: string }[]; job_id?: string; already_running?: boolean }

const SYNC_KEYS = [["jobs"], ["jobs-summary"], ["accounts"], ["emails"]];

/** Starts Google's real OAuth consent flow: the backend returns Google's authorization URL and the browser navigates to it. */
export function useConnectGmail() {
  return useAction<{ enable_send?: boolean; login_hint?: string } | void, { authorization_url: string }>({
    fn: (b) => api.post("/email-accounts/connect", { enable_send: true, ...(b ?? {}) }),
    onDone: (d) => { window.location.assign(d.authorization_url); },
  });
}
export function useReauthorize() {
  return useAction<{ id: string; enable_send: boolean }, { authorization_url: string }>({
    fn: ({ id, enable_send }) => api.post(`/email-accounts/${id}/reauthorize`, { enable_send }),
    onDone: (d) => { window.location.assign(d.authorization_url); },
  });
}
export function useSyncAll() {
  return useAction<void, SyncResult>({
    fn: () => api.post("/email-accounts/sync-all"), invalidate: SYNC_KEYS,
    success: (d) => {
      const n = d.started?.filter((s) => !s.already_running).length ?? 0;
      const skipped = d.skipped?.length ?? 0;
      if (n === 0 && !(d.started?.length)) return skipped ? `No accounts could be synced (${skipped} skipped)` : "No connected accounts to sync";
      return `Sync started for ${n} account${n === 1 ? "" : "s"}${skipped ? `, ${skipped} skipped` : ""}`;
    },
  });
}
export function useSyncAccount() {
  return useAction<{ id: string; mode?: "auto" | "full"; import_days?: number }, SyncResult>({
    fn: ({ id, ...body }) => api.post(`/email-accounts/${id}/sync`, body), invalidate: SYNC_KEYS,
    success: (d) => (d.already_running ? "A sync is already running for this account" : "Sync started"),
  });
}
