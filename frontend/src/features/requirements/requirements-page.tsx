import type { ColumnDef, RowSelectionState } from "@tanstack/react-table";
import { Archive, Check, ChevronDown, Copy, Eye, FileSpreadsheet, FileUp, MoreHorizontal, Pencil, Plus, RotateCcw, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/app/auth";
import { SkillChips } from "@/components/common/skill-chips";
import { EmptyState, ErrorState, LoadingRows, PageHeader, StatusBadge, useDebounced } from "@/components/common/common";
import { DataTable, Pagination, type SortState } from "@/components/data-table/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown";
import { Checkbox, Field, Input, Select } from "@/components/ui/form";
import { api } from "@/lib/api";
import { fmtDate, fmtExperience, fmtSalary } from "@/lib/utils";
import { ExportDialog } from "@/features/exports/export-dialog";
import { RequirementImportDialog } from "@/features/requirements/import-dialog";
import { RequirementForm } from "@/features/requirements/requirement-form";
import { reqKeys, useAccounts, useAction, useRequirementAction, useRequirements } from "@/services/hooks";
import type { Requirement } from "@/types/api";

const FILTER_KEYS = ["q", "date_from", "date_to", "account_id", "client", "job_title", "skill", "exp_min", "exp_max", "location", "work_mode", "salary_min", "salary_max",
  "recruiter", "review_status", "lifecycle_status", "source_type", "duplicate_status"] as const;
const MORE_KEYS = ["date_from", "date_to", "client", "job_title", "skill", "exp_min", "exp_max", "location", "salary_min", "salary_max", "recruiter", "source_type", "duplicate_status"];
const STORAGE_KEY = "rd-req-filters";

export function RequirementsPage() {
  const [sp, setSp] = useSearchParams();
  const nav = useNavigate();
  const { can } = useAuth();
  const accounts = useAccounts();
  const [selection, setSelection] = useState<RowSelectionState>({});
  const [showMore, setShowMore] = useState(() => MORE_KEYS.some((k) => sp.has(k)));
  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  // restore the last used filters when arriving without any (filter state survives navigation)
  useEffect(() => {
    if (![...sp.keys()].length) {
      try { const saved = sessionStorage.getItem(STORAGE_KEY); if (saved) setSp(new URLSearchParams(saved), { replace: true }); } catch { /* ignore */ }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { try { sessionStorage.setItem(STORAGE_KEY, sp.toString()); } catch { /* ignore */ } }, [sp]);

  const page = Number(sp.get("page") ?? 1) || 1;
  const pageSize = Number(sp.get("page_size") ?? 25) || 25;
  const sort: SortState = { sort: sp.get("sort") ?? "received_at", direction: (sp.get("direction") as "asc" | "desc") ?? "desc" };
  const filters = useMemo(() => Object.fromEntries(FILTER_KEYS.filter((k) => sp.get(k)).map((k) => [k, sp.get(k) as string])), [sp]);
  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(sp);
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    if (!("page" in patch)) next.delete("page");
    setSp(next);
    setSelection({});
  };
  const clearAll = () => { setSp(new URLSearchParams()); setSelection({}); };

  const [qText, setQText] = useState(sp.get("q") ?? "");
  const dq = useDebounced(qText);
  useEffect(() => { if ((sp.get("q") ?? "") !== dq) update({ q: dq || null }); }, [dq]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setQText(sp.get("q") ?? ""); }, [sp.get("q")]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data, isLoading, isFetching, error, refetch } = useRequirements({ ...filters, page, page_size: pageSize, sort: sort.sort, direction: sort.direction });
  const approve = useRequirementAction("approve");
  const reject = useRequirementAction("reject");
  const archive = useRequirementAction("archive");
  const restore = useRequirementAction("restore");
  const bulk = useAction<{ ids: string[]; action: string }, { succeeded: string[]; failed: { id: string; error: string }[] }>({
    fn: (b) => api.post("/requirements/bulk", b), invalidate: reqKeys,
    success: null,
    onDone: (r, v) => {
      if (r.failed.length === 0) toast.success(`${r.succeeded.length} requirement(s): ${v.action} done`);
      else toast.warning(`${r.succeeded.length} succeeded, ${r.failed.length} failed: ${r.failed[0].error}`);
      setSelection({});
    },
  });

  const selectedIds = Object.keys(selection).filter((k) => selection[k]);
  const writable = can("member");
  const activeFilterCount = Object.keys(filters).length;

  const columns = useMemo<ColumnDef<Requirement, unknown>[]>(() => [
    {
      id: "select", enableSorting: false,
      header: ({ table }) => <Checkbox aria-label="Select all rows on this page" checked={table.getIsAllRowsSelected()} onChange={table.getToggleAllRowsSelectedHandler()} />,
      cell: ({ row }) => <Checkbox aria-label={`Select ${row.original.job_title ?? "requirement"}`} checked={row.getIsSelected()} onChange={row.getToggleSelectedHandler()} />,
    },
    { id: "client", header: "Client", meta: { sortKey: "client_name" }, cell: ({ row }) => <span className="font-medium">{row.original.client_name ?? "—"}</span> },
    {
      id: "title", header: "Job title", meta: { sortKey: "job_title" }, cell: ({ row }) => (
        <div className="max-w-[260px]">
          <Link to={`/requirements/${row.original.id}`} className="font-medium text-primary hover:underline">{row.original.job_title ?? "(untitled)"}</Link>
          <div className="mt-0.5 flex flex-wrap gap-1">
            {row.original.has_pending_duplicate && <Badge variant="warning"><Copy className="size-3" /> Possible duplicate</Badge>}
            {row.original.validation_warnings.length > 0 && <Badge variant="muted" title={row.original.validation_warnings.join(", ")}>{row.original.validation_warnings.length} warning(s)</Badge>}
          </div>
        </div>
      ),
    },
    { id: "ref", header: "Job ID", cell: ({ row }) => <span className="tabular text-xs">{row.original.job_reference_id ?? "—"}</span> },
    { id: "skills", header: "Required skills", cell: ({ row }) => <SkillChips skills={row.original.required_skills} /> },
    { id: "exp", header: "Experience", meta: { sortKey: "minimum_experience" }, cell: ({ row }) => <span className="whitespace-nowrap">{fmtExperience(row.original.minimum_experience, row.original.maximum_experience)}</span> },
    { id: "location", header: "Location", meta: { sortKey: "location" }, cell: ({ row }) => row.original.location ?? "—" },
    { id: "mode", header: "Work mode", cell: ({ row }) => (row.original.work_mode === "unknown" ? "—" : <StatusBadge status={row.original.work_mode} />) },
    { id: "salary", header: "Salary", cell: ({ row }) => <span className="whitespace-nowrap text-xs">{fmtSalary(row.original)}</span> },
    { id: "recruiter", header: "Recruiter", cell: ({ row }) => <div className="max-w-[180px] truncate" title={row.original.recruiter_email ?? ""}>{row.original.recruiter_name ?? row.original.recruiter_email ?? "—"}</div> },
    { id: "source", header: "Source account", cell: ({ row }) => <div className="max-w-[170px] truncate text-xs" title={row.original.source_accounts.join(", ")}>{row.original.source_accounts.join(", ") || "Manual"}{row.original.source_count > 1 && ` · ${row.original.source_count} emails`}</div> },
    { id: "received", header: "Received", meta: { sortKey: "received_at" }, cell: ({ row }) => <span className="whitespace-nowrap">{fmtDate(row.original.received_at)}</span> },
    { id: "review", header: "Review", meta: { sortKey: "review_status" }, cell: ({ row }) => <StatusBadge status={row.original.review_status} /> },
    { id: "lifecycle", header: "Lifecycle", cell: ({ row }) => <StatusBadge status={row.original.lifecycle_status} /> },
    { id: "updated", header: "Updated", meta: { sortKey: "last_updated_at" }, cell: ({ row }) => <span className="whitespace-nowrap">{fmtDate(row.original.last_updated_at)}</span> },
    {
      id: "actions", header: () => <span className="sr-only">Actions</span>, cell: ({ row }) => {
        const r = row.original;
        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" className="h-8 w-8" aria-label={`Actions for ${r.job_title ?? "requirement"}`}><MoreHorizontal /></Button></DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem onSelect={() => nav(`/requirements/${r.id}`)}><Eye /> View details</DropdownMenuItem>
              <DropdownMenuItem disabled={!writable} onSelect={() => nav(`/requirements/${r.id}?edit=1`)}><Pencil /> Edit</DropdownMenuItem>
              <DropdownMenuItem disabled={!writable || r.review_status === "approved"} onSelect={() => approve.mutate(r.id)}><Check /> Approve</DropdownMenuItem>
              <DropdownMenuItem disabled={!writable || r.review_status === "rejected"} onSelect={() => reject.mutate(r.id)}><X /> Reject</DropdownMenuItem>
              {r.lifecycle_status === "archived"
                ? <DropdownMenuItem disabled={!writable} onSelect={() => restore.mutate(r.id)}><RotateCcw /> Restore</DropdownMenuItem>
                : <DropdownMenuItem disabled={!writable} onSelect={() => archive.mutate(r.id)}><Archive /> Archive</DropdownMenuItem>}
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => nav(`/requirements/${r.id}?tab=sources`)}><Search /> View source emails</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => nav(`/requirements/${r.id}?tab=versions`)}><RotateCcw /> Version history</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => nav(`/requirements/${r.id}?tab=similar`)}><Copy /> Find similar</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => { setSelection({ [r.id]: true }); setExportOpen(true); }}><FileSpreadsheet /> Export record</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
    },
  ], [nav, writable, approve, reject, archive, restore]);

  return (
    <>
      <PageHeader title="Recruitment Requirements" description="Canonical, de-duplicated job requirements extracted from all connected accounts."
        actions={<>
          <Button variant="outline" disabled={!writable} onClick={() => setImportOpen(true)}><FileUp /> Import</Button>
          <Button variant="outline" onClick={() => setExportOpen(true)}><FileSpreadsheet /> Export{selectedIds.length ? ` (${selectedIds.length})` : ""}</Button>
          <Button disabled={!writable} onClick={() => setCreateOpen(true)}><Plus /> New requirement</Button>
        </>} />

      <div className="mb-3 space-y-3 rounded-lg border bg-card p-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
            <Input aria-label="Search requirements" placeholder="Search title, client, job ID, skills, recruiter email, location, description…" className="pl-8" value={qText} onChange={(e) => setQText(e.target.value)} />
          </div>
          <Select aria-label="Review status" className="w-48" value={sp.get("review_status") ?? ""} onChange={(e) => update({ review_status: e.target.value || null })}>
            <option value="">All review states</option><option value="needs_review">Needs review</option><option value="approved">Approved</option><option value="rejected">Rejected</option>
          </Select>
          <Select aria-label="Lifecycle status" className="w-44" value={sp.get("lifecycle_status") ?? ""} onChange={(e) => update({ lifecycle_status: e.target.value || null })}>
            <option value="">Active & closed</option><option value="active">Active</option><option value="closed">Closed</option><option value="archived">Archived</option>
          </Select>
          <Select aria-label="Gmail account" className="w-48" value={sp.get("account_id") ?? ""} onChange={(e) => update({ account_id: e.target.value || null })}>
            <option value="">All accounts</option>{accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.email_address}</option>)}
          </Select>
          <Select aria-label="Work mode" className="w-44" value={sp.get("work_mode") ?? ""} onChange={(e) => update({ work_mode: e.target.value || null })}>
            <option value="">Any work mode</option><option value="remote">Remote</option><option value="hybrid">Hybrid</option><option value="onsite">On-site</option>
          </Select>
          <Button variant="outline" aria-expanded={showMore} onClick={() => setShowMore((s) => !s)}>More filters <ChevronDown className={showMore ? "rotate-180" : ""} /></Button>
          {activeFilterCount > 0 && <Button variant="ghost" onClick={clearAll}><X /> Clear all ({activeFilterCount})</Button>}
        </div>
        {showMore && (
          <div className="grid gap-3 border-t pt-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Received from"><Input type="date" value={sp.get("date_from")?.slice(0, 10) ?? ""} onChange={(e) => update({ date_from: e.target.value ? `${e.target.value}T00:00:00Z` : null })} /></Field>
            <Field label="Received to"><Input type="date" value={sp.get("date_to")?.slice(0, 10) ?? ""} onChange={(e) => update({ date_to: e.target.value ? `${e.target.value}T23:59:59Z` : null })} /></Field>
            {([["client", "Client"], ["job_title", "Job title"], ["skill", "Required skill"], ["location", "Location"], ["recruiter", "Recruiter (name/email)"]] as const).map(([k, label]) => (
              <Field key={k} label={label}><Input value={sp.get(k) ?? ""} onChange={(e) => update({ [k]: e.target.value || null })} /></Field>
            ))}
            <Field label="Min experience (yrs)"><Input type="number" min={0} value={sp.get("exp_min") ?? ""} onChange={(e) => update({ exp_min: e.target.value || null })} /></Field>
            <Field label="Max experience (yrs)"><Input type="number" min={0} value={sp.get("exp_max") ?? ""} onChange={(e) => update({ exp_max: e.target.value || null })} /></Field>
            <Field label="Salary at least"><Input type="number" min={0} value={sp.get("salary_min") ?? ""} onChange={(e) => update({ salary_min: e.target.value || null })} /></Field>
            <Field label="Salary at most"><Input type="number" min={0} value={sp.get("salary_max") ?? ""} onChange={(e) => update({ salary_max: e.target.value || null })} /></Field>
            <Field label="Source type"><Select value={sp.get("source_type") ?? ""} onChange={(e) => update({ source_type: e.target.value || null })}><option value="">Any</option><option value="email_body">Email body</option><option value="attachment">Attachment</option><option value="manual">Manual</option><option value="duplicate_copy">Cross-account copy</option></Select></Field>
            <Field label="Duplicate status"><Select value={sp.get("duplicate_status") ?? ""} onChange={(e) => update({ duplicate_status: e.target.value || null })}><option value="">Any</option><option value="pending">Possible duplicate</option><option value="none">No pending duplicate</option></Select></Field>
          </div>
        )}
      </div>

      {selectedIds.length > 0 && (
        <div role="region" aria-label="Bulk actions" className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-primary/30 bg-accent/60 px-3 py-2 text-sm">
          <span className="font-medium">{selectedIds.length} selected</span>
          <Button size="sm" variant="outline" disabled={!writable} loading={bulk.isPending && bulk.variables?.action === "approve"} onClick={() => bulk.mutate({ ids: selectedIds, action: "approve" })}><Check /> Approve</Button>
          <Button size="sm" variant="outline" disabled={!writable} loading={bulk.isPending && bulk.variables?.action === "reject"} onClick={() => bulk.mutate({ ids: selectedIds, action: "reject" })}><X /> Reject</Button>
          <Button size="sm" variant="outline" disabled={!writable} loading={bulk.isPending && bulk.variables?.action === "archive"} onClick={() => bulk.mutate({ ids: selectedIds, action: "archive" })}><Archive /> Archive</Button>
          <Button size="sm" variant="outline" disabled={!writable} loading={bulk.isPending && bulk.variables?.action === "restore"} onClick={() => bulk.mutate({ ids: selectedIds, action: "restore" })}><RotateCcw /> Restore</Button>
          <Button size="sm" onClick={() => setExportOpen(true)}><FileSpreadsheet /> Export selected</Button>
          <Button size="sm" variant="ghost" onClick={() => setSelection({})}>Clear selection</Button>
          <span className="ml-auto text-xs text-muted-foreground">Merging is only done through Duplicate Review.</span>
        </div>
      )}

      {error && !data ? <ErrorState error={error} onRetry={() => refetch()} /> : isLoading ? <LoadingRows /> : !data?.items.length ? (
        <EmptyState icon={Search} title={activeFilterCount ? "No requirements match these filters" : "No requirements yet"}
          description={activeFilterCount ? "Try removing a filter or searching for something else." : "Sync a Gmail account to extract requirements, or create one manually."}
          action={activeFilterCount ? <Button variant="outline" onClick={clearAll}>Clear all filters</Button> : <Button onClick={() => nav("/accounts")}>Go to Connected Accounts</Button>} />
      ) : (
        <>
          <DataTable caption="Recruitment requirements" columns={columns} data={data.items} getRowId={(r) => r.id} rowSelection={selection} onRowSelectionChange={setSelection} loading={isFetching}
            sort={sort} onSortChange={(s) => update({ sort: s.sort, direction: s.direction })} />
          <Pagination page={page} pageSize={pageSize} total={data.total} onPage={(p) => update({ page: String(p) })} onPageSize={(s) => update({ page_size: String(s) })} />
        </>
      )}

      {importOpen && <RequirementImportDialog open onOpenChange={setImportOpen} />}
      {exportOpen && <ExportDialog open onOpenChange={setExportOpen} selectedIds={selectedIds} filters={filters} />}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent title="New requirement" description="Create a requirement manually. Source emails can be linked afterwards." size="lg">
          <RequirementForm mode="create" onDone={(id) => { setCreateOpen(false); nav(`/requirements/${id}`); }} onCancel={() => setCreateOpen(false)} />
        </DialogContent>
      </Dialog>
    </>
  );
}
