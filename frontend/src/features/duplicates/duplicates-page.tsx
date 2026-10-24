import { Copy, ExternalLink, GitMerge } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useAuth } from "@/app/auth";
import { ConfirmDialog, EmptyState, ErrorState, LoadingRows, PageHeader, StatusBadge } from "@/components/common/common";
import { Pagination } from "@/components/data-table/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Select } from "@/components/ui/form";
import { api } from "@/lib/api";
import { cn, fmtDate, fmtExperience, fmtSalary, pct, titleCase } from "@/lib/utils";
import { useAction, useDuplicate, useDuplicates } from "@/services/hooks";
import type { DuplicateDetail, Requirement, Source } from "@/types/api";

const KEYS = [["duplicates"], ["duplicate"], ["requirements"], ["requirement"], ["overview"]];

type Row = { label: string; field: string; get: (r: Requirement) => string };
const ROWS: Row[] = [
  { label: "Client", field: "client", get: (r) => r.client_name ?? "—" },
  { label: "Title", field: "job_title", get: (r) => r.job_title ?? "—" },
  { label: "Job ID", field: "job_reference_id", get: (r) => r.job_reference_id ?? "—" },
  { label: "Experience", field: "experience", get: (r) => fmtExperience(r.minimum_experience, r.maximum_experience) },
  { label: "Required skills", field: "required_skills", get: (r) => r.required_skills.join(", ") || "—" },
  { label: "Location", field: "location", get: (r) => r.location ?? "—" },
  { label: "Work mode", field: "work_mode", get: (r) => (r.work_mode === "unknown" ? "—" : titleCase(r.work_mode)) },
  { label: "Salary", field: "salary_min", get: (r) => fmtSalary(r) },
  { label: "Recruiter", field: "recruiter", get: (r) => r.recruiter_name ?? r.recruiter_email ?? "—" },
  { label: "First received", field: "", get: (r) => fmtDate(r.received_at) },
  { label: "Last updated", field: "", get: (r) => fmtDate(r.last_updated_at) },
];

function SourceList({ sources }: { sources: Source[] }) {
  if (!sources.length) return <span className="text-muted-foreground">No linked emails</span>;
  return <ul className="space-y-1">{sources.map((s) => (
    <li key={s.id} className="text-xs"><span className="font-medium">{s.subject ?? "(manual)"}</span><br /><span className="text-muted-foreground">{s.account_email ?? "—"} · {fmtDate(s.received_at)}</span>
      {s.gmail_url && <> · <a className="text-primary hover:underline" href={s.gmail_url} target="_blank" rel="noopener noreferrer">Gmail <ExternalLink className="inline size-3" /></a></>}</li>))}</ul>;
}

function Compare({ id, onClose }: { id: string | null; onClose: () => void }) {
  const q = useDuplicate(id);
  const { can } = useAuth();
  const [confirm, setConfirm] = useState<"a" | "b" | null>(null);
  const d: DuplicateDetail | undefined = q.data;
  const done = () => { setConfirm(null); onClose(); };
  const merge = useAction<string, unknown>({ fn: (survivor) => api.post(`/duplicates/${id}/merge`, { survivor_id: survivor }), invalidate: KEYS, success: "Merged. Sources and history from both records were preserved", onDone: done });
  const resolve = (path: string, msg: string) => useAction<void, unknown>({ fn: () => api.post(`/duplicates/${id}/${path}`), invalidate: KEYS, success: msg, onDone: onClose }); // eslint-disable-line react-hooks/rules-of-hooks
  const keep = resolve("keep-both", "Kept both requirements");
  const related = resolve("mark-related", "Marked as related");
  const dismiss = resolve("dismiss", "Duplicate candidate dismissed");
  const reopen = resolve("reopen", "Decision reopened");
  const conflicts = new Set(d?.conflicting_fields ?? []);
  const pending = d?.review_status === "pending";
  const w = can("member");
  const survivorId = confirm === "a" ? d?.requirement_a.id : d?.requirement_b.id;

  return (
    <Dialog open={!!id} onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="xl" title="Compare possible duplicate" description="Review both records side by side. A merge keeps every source email and the full history of both records.">
        {q.isLoading ? <LoadingRows rows={6} /> : q.error || !d ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="warning">{pct(d.matching_score)} match</Badge><StatusBadge status={d.review_status} />
              {d.matching_reasons.map((r) => <Badge key={r} variant="secondary">{r}</Badge>)}
            </div>
            {d.conflicting_fields.length > 0 && <p className="text-sm"><span className="font-medium">Conflicting fields:</span> {d.conflicting_fields.map(titleCase).join(", ")}</p>}
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="bg-muted/50 text-left text-xs"><tr><th className="w-32 px-3 py-2" /><th className="px-3 py-2">Record A <StatusBadge status={d.requirement_a.review_status} /></th><th className="px-3 py-2">Record B <StatusBadge status={d.requirement_b.review_status} /></th></tr></thead>
                <tbody>
                  {ROWS.map((r) => {
                    const a = r.get(d.requirement_a), b = r.get(d.requirement_b);
                    const diff = a !== b;
                    return <tr key={r.label} className={cn("border-t align-top", diff && r.field && "bg-warning/10")}><th scope="row" className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">{r.label}{conflicts.has(r.field) && <span className="ml-1 text-warning" title="Conflict">●</span>}</th><td className="break-words px-3 py-2">{a}</td><td className="break-words px-3 py-2">{b}</td></tr>;
                  })}
                  <tr className="border-t align-top"><th scope="row" className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Source emails</th><td className="px-3 py-2"><SourceList sources={d.sources_a} /></td><td className="px-3 py-2"><SourceList sources={d.sources_b} /></td></tr>
                  <tr className="border-t"><th scope="row" className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Open</th>
                    <td className="px-3 py-2"><Link className="text-primary hover:underline" to={`/requirements/${d.requirement_a.id}`}>Record A</Link></td><td className="px-3 py-2"><Link className="text-primary hover:underline" to={`/requirements/${d.requirement_b.id}`}>Record B</Link></td></tr>
                </tbody>
              </table>
            </div>
            {pending ? (
              <div className="flex flex-wrap gap-2">
                <Button disabled={!w} onClick={() => setConfirm("a")}><GitMerge /> Merge B into A (keep A)</Button>
                <Button disabled={!w} variant="outline" onClick={() => setConfirm("b")}><GitMerge /> Merge A into B (keep B)</Button>
                <Button disabled={!w} variant="outline" loading={keep.isPending} onClick={() => keep.mutate()}>Keep both</Button>
                <Button disabled={!w} variant="outline" loading={related.isPending} onClick={() => related.mutate()}>Mark as related</Button>
                <Button disabled={!w} variant="ghost" loading={dismiss.isPending} onClick={() => dismiss.mutate()}>Dismiss</Button>
              </div>
            ) : d.review_status === "merged" ? <p className="text-sm text-muted-foreground">This duplicate was merged and cannot be reopened. History is available on the surviving requirement.</p>
              : <Button variant="outline" disabled={!w} loading={reopen.isPending} onClick={() => reopen.mutate()}>Reopen decision</Button>}
          </div>
        )}
        <ConfirmDialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)} title="Merge these requirements?" confirmLabel="Merge" loading={merge.isPending}
          description="The other record is marked as merged and removed from working lists. Its source emails, skills and version history are moved to the surviving record; nothing is deleted. Merges cannot be undone."
          onConfirm={() => survivorId && merge.mutate(survivorId)} />
      </DialogContent>
    </Dialog>
  );
}

export function DuplicatesPage() {
  const [sp, setSp] = useSearchParams();
  const status = sp.get("status") ?? "pending";
  const page = Number(sp.get("page") ?? 1) || 1;
  const open = sp.get("open");
  const { data, isLoading, error, refetch } = useDuplicates({ status, page, page_size: 15 });
  const set = (patch: Record<string, string | null>) => { const n = new URLSearchParams(sp); Object.entries(patch).forEach(([k, v]) => (v ? n.set(k, v) : n.delete(k))); setSp(n); };
  return (
    <>
      <PageHeader title="Duplicate Review" description="Probable duplicates are never merged automatically. Decide what to do with each pair."
        actions={<Select aria-label="Status filter" className="w-44" value={status} onChange={(e) => set({ status: e.target.value, page: null })}>
          <option value="pending">Pending review</option><option value="merged">Merged</option><option value="kept_both">Kept both</option><option value="related">Related</option><option value="dismissed">Dismissed</option><option value="all">All</option></Select>} />
      {error && !data ? <ErrorState error={error} onRetry={() => refetch()} /> : isLoading ? <LoadingRows /> : !data?.items.length ? (
        <EmptyState icon={Copy} title={status === "pending" ? "No duplicates waiting for review" : "Nothing here"} description="When two requirements look alike but cannot be matched with certainty, they appear here for you to decide." />
      ) : (
        <>
          <div className="space-y-2">
            {data.items.map((d) => (
              <Card key={d.id} className="transition-colors hover:border-primary/40"><CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div className="grid min-w-0 flex-1 gap-1 sm:grid-cols-2 sm:gap-4">
                  {[d.requirement_a, d.requirement_b].map((r) => <div key={r.id} className="min-w-0"><p className="truncate text-sm font-medium">{r.job_title ?? "(untitled)"}</p><p className="truncate text-xs text-muted-foreground">{r.client_name ?? "—"} · {r.location ?? "—"} · {r.source_accounts.join(", ") || "manual"}</p></div>)}
                </div>
                <div className="flex items-center gap-2"><Badge variant={d.review_status === "pending" ? "warning" : "muted"}>{pct(d.matching_score)} match</Badge><StatusBadge status={d.review_status} />
                  <Button size="sm" onClick={() => set({ open: d.id })}>{d.review_status === "pending" ? "Review" : "View"}</Button></div>
              </CardContent></Card>
            ))}
          </div>
          <Pagination page={page} pageSize={15} total={data.total} onPage={(p) => set({ page: String(p) })} />
        </>
      )}
      <Compare id={open} onClose={() => set({ open: null })} />
    </>
  );
}
