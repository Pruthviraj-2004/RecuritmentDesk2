import { useState } from "react";
import { Activity, AlertTriangle, RefreshCw } from "lucide-react";
import { useAuth } from "@/app/auth";
import { EmptyState, ErrorState, KeyValue, LoadingRows, PageHeader, StatusBadge } from "@/components/common/common";
import { Pagination } from "@/components/data-table/data-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Select } from "@/components/ui/form";
import { useReauthorize, useSyncAll } from "@/hooks/use-gmail";
import { api } from "@/lib/api";
import { fmtDateTime, fmtRelative, titleCase } from "@/lib/utils";
import { useAction, useJobs, useJobsSummary, useProcessingIssues } from "@/services/hooks";
import type { Job } from "@/types/api";

const KEYS = [["jobs"], ["jobs-summary"], ["accounts"]];
const dur = (s: number | null) => (s == null ? "—" : s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`);

function JobDetail({ job, onClose }: { job: Job; onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={`${titleCase(job.job_type)} job`} description={job.account_email ?? undefined} size="md">
        <dl className="grid gap-3 sm:grid-cols-2">
          <KeyValue label="Status"><StatusBadge status={job.status} /></KeyValue><KeyValue label="Attempts">{job.attempts} / {job.max_attempts}</KeyValue>
          <KeyValue label="Started">{fmtDateTime(job.started_at)}</KeyValue><KeyValue label="Duration">{dur(job.duration_seconds)}</KeyValue>
          <KeyValue label="Mode">{String(job.checkpoint?.mode ?? "—")}</KeyValue><KeyValue label="Pages fetched">{String(job.checkpoint?.pages ?? "—")}</KeyValue>
        </dl>
        {Array.isArray(job.checkpoint?.error_samples) && (job.checkpoint.error_samples as string[]).length > 0 && (
          <div><p className="mb-1 text-xs font-medium text-muted-foreground">Error samples (no email content is recorded)</p>
            <ul className="space-y-1 rounded-md border bg-muted/40 p-2 font-mono text-xs">{(job.checkpoint.error_samples as string[]).map((s) => <li key={s} className="break-all">{s}</li>)}</ul></div>
        )}
        {job.error_summary && <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm">{job.error_summary}</div>}
        <div><p className="mb-1 text-xs font-medium text-muted-foreground">Counters</p>
          {Object.keys(job.stats).length === 0 ? <p className="text-sm text-muted-foreground">No counters recorded yet.</p> : (
            <table className="w-full text-sm"><tbody>{Object.entries(job.stats).map(([k, v]) => <tr key={k} className="border-t"><td className="py-1">{titleCase(k)}</td><td className="tabular py-1 text-right">{v}</td></tr>)}</tbody></table>)}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function IssuesCard() {
  const q = useProcessingIssues();
  if (!q.data?.length) return null;
  return (
    <Card className="mb-5"><CardHeader><CardTitle>Processing issues ({q.data.length})</CardTitle></CardHeader><CardContent>
      <ul className="divide-y text-sm">{q.data.map((i) => (
        <li key={i.id} className="flex flex-wrap items-start justify-between gap-2 py-2.5">
          <div className="min-w-0"><p className="truncate font-medium">{i.subject ?? "(no subject)"}</p><p className="truncate text-xs text-muted-foreground">{i.account} · {fmtDateTime(i.received_at)}</p>
            {i.error && <p className="mt-0.5 text-xs text-destructive">{i.error}</p>}</div>
          <StatusBadge status={i.status} />
        </li>))}</ul>
      <p className="mt-2 text-xs text-muted-foreground">Use “Retry all” above after fixing the cause (for example the AI provider settings). Only email metadata is shown here.</p>
    </CardContent></Card>
  );
}

export function SyncJobsPage() {
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<Job | null>(null);
  const { can } = useAuth();
  const jobs = useJobs({ status: status || undefined, page, page_size: 15 });
  const summary = useJobsSummary();
  const syncAll = useSyncAll();
  const reauth = useReauthorize();
  const cancel = useAction<string, Job>({ fn: (id) => api.post(`/jobs/${id}/cancel`), invalidate: KEYS, success: "Cancellation requested; the job stops at its next checkpoint" });
  const retry = useAction<string, Job>({ fn: (id) => api.post(`/jobs/${id}/retry`), invalidate: KEYS, success: "Retry started" });
  const retryEmails = useAction<void, { queued: number }>({ fn: () => api.post("/emails/retry-failed"), invalidate: [...KEYS, ["jobs-issues"]], success: (d) => `${d.queued} message(s) re-queued for extraction` });
  const s = summary.data;
  const lastRun = (accountId: string) => jobs.data?.items.find((j) => j.email_account_id === accountId);

  return (
    <>
      <PageHeader title="Synchronization Jobs" description="Operational view of Gmail synchronization and AI extraction. Jobs resume from their last checkpoint after a restart."
        actions={<Button disabled={!can("member")} loading={syncAll.isPending} onClick={() => syncAll.mutate()}><RefreshCw /> Sync all accounts</Button>} />
      <section aria-label="Processing summary" className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[["Extraction pending", s?.extraction_pending], ["Extraction failed", s?.extraction_failed], ["Processed", (s?.messages.processed ?? 0) + (s?.messages.duplicate ?? 0)], ["Waiting for AI", s?.messages.awaiting_ai ?? 0]].map(([label, v]) => (
          <Card key={String(label)}><CardContent className="p-4"><p className="text-xs text-muted-foreground">{label}</p><p className="tabular mt-1 text-2xl font-semibold">{v ?? "…"}</p></CardContent></Card>))}
      </section>
      {((s?.extraction_failed ?? 0) > 0 || (s?.messages.awaiting_ai ?? 0) > 0) && (
        <div className="mb-5 flex flex-wrap items-center gap-3 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">
          <AlertTriangle className="size-4 text-warning" /><span>{s?.extraction_failed ?? 0} failed and {s?.messages.awaiting_ai ?? 0} awaiting AI.</span>
          <Button size="sm" variant="outline" className="ml-auto" disabled={!can("member")} loading={retryEmails.isPending} onClick={() => retryEmails.mutate()}>Retry all</Button>
        </div>
      )}
      <IssuesCard />
      <Card className="mb-5"><CardHeader><CardTitle>Accounts</CardTitle></CardHeader><CardContent>
        {!s?.accounts.length ? <p className="text-sm text-muted-foreground">No accounts connected.</p> : (
          <ul className="divide-y">{s.accounts.map((a) => {
            const j = lastRun(a.id);
            return (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                <div className="min-w-0"><p className="truncate font-medium">{a.email}</p><p className="text-xs text-muted-foreground">Last successful sync: {fmtRelative(a.last_synced_at)}{j ? ` · fetched ${j.stats.fetched ?? 0}, stored ${j.stats.stored ?? 0}` : ""}</p></div>
                <div className="flex items-center gap-2"><StatusBadge status={a.status} />
                  {(a.status === "expired" || a.status === "disconnected") && <Button size="sm" variant="outline" disabled={!can("admin")} loading={reauth.isPending} onClick={() => reauth.mutate({ id: a.id, enable_send: true })}>Reauthorize</Button>}</div>
                {a.last_error && <p className="w-full text-xs text-destructive">{a.last_error}</p>}
              </li>);
          })}</ul>)}
      </CardContent></Card>

      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-sm font-semibold">Job history</h2>
        <Select aria-label="Filter jobs" className="ml-auto w-44" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">All jobs</option><option value="active">Active</option><option value="completed">Completed</option><option value="failed">Failed</option><option value="cancelled">Cancelled</option></Select>
      </div>
      {jobs.error && !jobs.data ? <ErrorState error={jobs.error} onRetry={() => jobs.refetch()} /> : jobs.isLoading ? <LoadingRows /> : !jobs.data?.items.length ? <EmptyState icon={Activity} title="No jobs yet" description="Start a sync from Connected Accounts or use “Sync all accounts”." /> : (
        <>
          <div className="overflow-x-auto rounded-lg border bg-card">
            <table className="w-full min-w-[820px] text-sm">
              <thead className="border-b bg-muted/50 text-left text-xs text-muted-foreground"><tr>{["Type", "Account", "Status", "Progress", "Started", "Duration", "Attempts", "Stored / fetched", "Error", ""].map((h) => <th key={h} className="px-3 py-2.5">{h}</th>)}</tr></thead>
              <tbody>{jobs.data.items.map((j) => (
                <tr key={j.id} className="border-b last:border-0 align-top">
                  <td className="px-3 py-2.5">{titleCase(j.job_type)}</td><td className="max-w-[160px] truncate px-3 py-2.5 text-xs">{j.account_email ?? "—"}</td><td className="px-3 py-2.5"><StatusBadge status={j.status} /></td>
                  <td className="px-3 py-2.5 tabular">{j.progress != null ? `${Math.round(j.progress * 100)}%` : j.status === "running" ? `${j.stats.fetched ?? 0} msgs…` : "—"}</td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-xs">{fmtDateTime(j.started_at ?? j.created_at)}</td><td className="px-3 py-2.5 tabular">{dur(j.duration_seconds)}</td>
                  <td className="px-3 py-2.5 tabular">{j.attempts}/{j.max_attempts}</td><td className="px-3 py-2.5 tabular">{j.stats.stored ?? 0} / {j.stats.fetched ?? 0}</td>
                  <td className="max-w-[220px] px-3 py-2.5 text-xs text-destructive"><span className="line-clamp-2" title={j.error_summary ?? ""}>{j.error_summary}</span></td>
                  <td className="whitespace-nowrap px-3 py-2.5"><div className="flex gap-1.5">
                    <Button size="sm" variant="ghost" onClick={() => setDetail(j)}>Details</Button>
                    {(j.status === "queued" || j.status === "running") && <Button size="sm" variant="outline" disabled={!can("member")} loading={cancel.isPending && cancel.variables === j.id} onClick={() => cancel.mutate(j.id)}>Cancel</Button>}
                    {j.job_type === "sync" && ["failed", "cancelled", "completed_with_errors"].includes(j.status) && <Button size="sm" variant="outline" disabled={!can("member")} loading={retry.isPending && retry.variables === j.id} onClick={() => retry.mutate(j.id)}>Retry</Button>}
                  </div></td>
                </tr>))}</tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={15} total={jobs.data.total} onPage={setPage} />
        </>
      )}
      {detail && <JobDetail job={detail} onClose={() => setDetail(null)} />}
    </>
  );
}
