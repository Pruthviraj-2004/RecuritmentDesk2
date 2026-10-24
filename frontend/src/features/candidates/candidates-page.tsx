import type { ColumnDef, RowSelectionState } from "@tanstack/react-table";
import { Archive, Download, Eye, FileUp, Mail, MoreHorizontal, Phone, Plus, RotateCcw, Search, Tag, UserCheck, Users, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/app/auth";
import { SkillChips } from "@/components/common/skill-chips";
import { EmptyState, ErrorState, LoadingRows, PageHeader, StatusBadge, useDebounced } from "@/components/common/common";
import { DataTable, Pagination, type SortState } from "@/components/data-table/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown";
import { Checkbox, Input, Select } from "@/components/ui/form";
import { CandidateForm } from "@/features/candidates/candidate-form";
import { ImportDialog } from "@/features/candidates/import-dialog";
import { api, errorMessage } from "@/lib/api";
import { downloadPost } from "@/lib/download";
import { fmtDate, fmtRelative, titleCase } from "@/lib/utils";
import { candidateKeys, useAction, useCandidates, useCandidateStats } from "@/services/hooks";
import { CANDIDATE_STATUSES, type Candidate } from "@/types/api";

const FILTER_KEYS = ["q", "status", "skill", "location", "exp_min", "exp_max", "notice", "tag", "rating_min", "source", "archived"] as const;

export const Stars = ({ n }: { n: number | null }) => (n ? <span aria-label={`${n} out of 5`} className="whitespace-nowrap text-warning" title={`${n}/5`}>{"★".repeat(n)}<span className="text-muted-foreground/40">{"★".repeat(5 - n)}</span></span> : <span className="text-muted-foreground">—</span>);

export function CandidatesPage() {
  const [sp, setSp] = useSearchParams();
  const nav = useNavigate();
  const { can } = useAuth();
  const writable = can("member");
  const [selection, setSelection] = useState<RowSelectionState>({});
  const [addOpen, setAddOpen] = useState(sp.get("add") === "1");
  const [importOpen, setImportOpen] = useState(sp.get("import") === "1");
  const [showMore, setShowMore] = useState(() => ["skill", "location", "exp_min", "exp_max", "notice", "tag", "rating_min", "source"].some((k) => sp.has(k)));
  const [tagValue, setTagValue] = useState("");

  const page = Number(sp.get("page") ?? 1) || 1;
  const pageSize = Number(sp.get("page_size") ?? 25) || 25;
  const sort: SortState = { sort: sp.get("sort") ?? "created_at", direction: (sp.get("direction") as "asc" | "desc") ?? "desc" };
  const filters = useMemo(() => Object.fromEntries(FILTER_KEYS.filter((k) => sp.get(k)).map((k) => [k, sp.get(k) as string])), [sp]);
  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(sp);
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    if (!("page" in patch)) next.delete("page");
    setSp(next);
    setSelection({});
  };
  const [qText, setQText] = useState(sp.get("q") ?? "");
  const dq = useDebounced(qText);
  useEffect(() => { if ((sp.get("q") ?? "") !== dq) update({ q: dq || null }); }, [dq]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data, isLoading, isFetching, error, refetch } = useCandidates({ ...filters, page, page_size: pageSize, sort: sort.sort, direction: sort.direction });
  const stats = useCandidateStats();
  const filterCount = Object.keys(filters).length;
  const selectedIds = Object.keys(selection).filter((k) => selection[k]);

  const bulk = useAction<{ action: string; value?: string }, { succeeded: string[]; failed: unknown[] }>({
    fn: (b) => api.post("/candidates/bulk", { ids: selectedIds, ...b }), invalidate: candidateKeys,
    success: (r, v) => `${r.succeeded.length} candidate(s): ${titleCase(v.action)} done${r.failed.length ? `, ${r.failed.length} failed` : ""}`, onDone: () => setSelection({}),
  });
  const archiveOne = useAction<string, unknown>({ fn: (id) => api.del(`/candidates/${id}`), invalidate: candidateKeys, success: "Candidate archived" });
  const restoreOne = useAction<string, unknown>({ fn: (id) => api.post(`/candidates/${id}/restore`), invalidate: candidateKeys, success: "Candidate restored" });
  const exportFile = async (ids?: string[]) => {
    try { await downloadPost("/candidates/export", ids?.length ? { ids } : { filters }, "candidates.xlsx"); toast.success("Excel file downloaded"); } catch (e) { toast.error(errorMessage(e)); }
  };

  const columns = useMemo<ColumnDef<Candidate, unknown>[]>(() => [
    {
      id: "select", header: ({ table }) => <Checkbox aria-label="Select all rows on this page" checked={table.getIsAllRowsSelected()} onChange={table.getToggleAllRowsSelectedHandler()} />,
      cell: ({ row }) => <Checkbox aria-label={`Select ${row.original.full_name}`} checked={row.getIsSelected()} onChange={row.getToggleSelectedHandler()} />,
    },
    {
      id: "name", header: "Candidate", meta: { sortKey: "full_name" }, cell: ({ row }) => (
        <div className="min-w-[190px]">
          <Link to={`/candidates/${row.original.id}`} className="font-medium text-primary hover:underline">{row.original.full_name}</Link>
          <div className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground"><Mail className="size-3 shrink-0" /><span className="truncate">{row.original.email}</span></div>
          <div className="flex items-center gap-1 text-xs text-muted-foreground"><Phone className="size-3 shrink-0" />{row.original.phone}</div>
        </div>
      ),
    },
    { id: "role", header: "Current role", cell: ({ row }) => <div className="max-w-[200px]"><p className="truncate">{row.original.current_title ?? "—"}</p><p className="truncate text-xs text-muted-foreground">{row.original.current_company ?? ""}</p></div> },
    { id: "skills", header: "Skills", cell: ({ row }) => <SkillChips skills={row.original.skills} width={240} /> },
    { id: "exp", header: "Exp", meta: { sortKey: "total_experience" }, cell: ({ row }) => (row.original.total_experience != null ? <span className="whitespace-nowrap">{row.original.total_experience} yrs</span> : "—") },
    { id: "loc", header: "Location", cell: ({ row }) => row.original.current_location ?? "—" },
    { id: "notice", header: "Notice", cell: ({ row }) => <span className="whitespace-nowrap">{row.original.notice_period ?? "—"}</span> },
    { id: "ectc", header: "Expected CTC", meta: { sortKey: "expected_ctc" }, cell: ({ row }) => (row.original.expected_ctc != null ? <span className="whitespace-nowrap tabular">{row.original.currency ?? ""} {row.original.expected_ctc.toLocaleString("en-IN")}</span> : "—") },
    { id: "status", header: "Status", meta: { sortKey: "status" }, cell: ({ row }) => <StatusBadge status={row.original.status} /> },
    { id: "rating", header: "Rating", meta: { sortKey: "rating" }, cell: ({ row }) => <Stars n={row.original.rating} /> },
    { id: "tags", header: "Tags", cell: ({ row }) => <div className="flex max-w-[150px] flex-wrap gap-1">{row.original.tags.slice(0, 3).map((t) => <Badge key={t} variant="muted">{t}</Badge>)}{row.original.tags.length > 3 && <Badge variant="muted">+{row.original.tags.length - 3}</Badge>}</div> },
    { id: "pipe", header: "Jobs", cell: ({ row }) => (row.original.pipeline_count ? <Badge variant="default">{row.original.pipeline_count} in pipeline</Badge> : <span className="text-muted-foreground">—</span>) },
    { id: "added", header: "Added", meta: { sortKey: "created_at" }, cell: ({ row }) => <span className="whitespace-nowrap text-xs" title={`Last contacted: ${row.original.last_contacted_at ? fmtRelative(row.original.last_contacted_at) : "never"}`}>{fmtDate(row.original.created_at)}</span> },
    {
      id: "actions", header: () => <span className="sr-only">Actions</span>, cell: ({ row }) => {
        const c = row.original;
        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" className="h-8 w-8" aria-label={`Actions for ${c.full_name}`}><MoreHorizontal /></Button></DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem onSelect={() => nav(`/candidates/${c.id}`)}><Eye /> View profile</DropdownMenuItem>
              <DropdownMenuItem disabled={!writable} onSelect={() => nav(`/candidates/${c.id}?edit=1`)}>Edit</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => nav(`/candidates/${c.id}?tab=matches`)}><UserCheck /> Matching jobs</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => exportFile([c.id])}><Download /> Export profile</DropdownMenuItem>
              <DropdownMenuSeparator />
              {c.is_archived ? <DropdownMenuItem disabled={!writable} onSelect={() => restoreOne.mutate(c.id)}><RotateCcw /> Restore</DropdownMenuItem>
                : <DropdownMenuItem disabled={!writable} onSelect={() => archiveOne.mutate(c.id)}><Archive /> Archive</DropdownMenuItem>}
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
    },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [nav, writable, filters]);

  const s = stats.data;
  return (
    <>
      <PageHeader title="Candidate Profiles" description="Your talent database. Add candidates one at a time or import a file, then match them to your requirements."
        actions={<>
          <Button variant="outline" onClick={() => exportFile(selectedIds)}><Download /> Export{selectedIds.length ? ` (${selectedIds.length})` : ""}</Button>
          <Button variant="outline" disabled={!writable} onClick={() => setImportOpen(true)}><FileUp /> Import file</Button>
          <Button disabled={!writable} onClick={() => setAddOpen(true)}><Plus /> Add candidate</Button>
        </>} />

      <section aria-label="Candidate summary" className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-5">
        {[["Total candidates", s?.total, undefined], ["Added this week", s?.new_this_week, undefined], ["In a pipeline", s?.in_pipeline, undefined], ["Shortlisted", s?.by_status.shortlisted ?? 0, "shortlisted"], ["Interviewing", s?.by_status.interviewing ?? 0, "interviewing"]].map(([label, value, status]) => (
          <button key={String(label)} type="button" onClick={() => status && update({ status: String(status) })} className="text-left" disabled={!status}>
            <Card className="h-full hover:-translate-y-0.5"><CardContent className="p-4"><p className="text-xs text-muted-foreground">{label}</p><p className="tabular mt-1 text-2xl font-semibold" data-testid={`cstat-${label}`}>{value ?? "…"}</p></CardContent></Card>
          </button>
        ))}
      </section>

      <div className="mb-3 space-y-3 rounded-lg border bg-card p-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
            <Input aria-label="Search candidates" placeholder="Search name, email, phone, title, company, skills, tags…" className="pl-8" value={qText} onChange={(e) => setQText(e.target.value)} />
          </div>
          <Select aria-label="Status" className="w-48" value={sp.get("status") ?? ""} onChange={(e) => update({ status: e.target.value || null })}>
            <option value="">All statuses</option>{CANDIDATE_STATUSES.map((st) => <option key={st} value={st}>{titleCase(st)}</option>)}
          </Select>
          <label className="flex items-center gap-2 text-sm"><Checkbox checked={sp.get("archived") === "true"} onChange={(e) => update({ archived: e.target.checked ? "true" : null })} /> Show archived</label>
          <Button variant="outline" aria-expanded={showMore} onClick={() => setShowMore((v) => !v)}>More filters</Button>
          {filterCount > 0 && <Button variant="ghost" onClick={() => { setQText(""); setSp(new URLSearchParams()); setSelection({}); }}><X /> Clear all ({filterCount})</Button>}
        </div>
        {showMore && (
          <div className="grid gap-3 border-t pt-3 sm:grid-cols-2 lg:grid-cols-4">
            {([["skill", "Skill"], ["location", "Location"], ["notice", "Notice period"], ["tag", "Tag"], ["source", "Source"]] as const).map(([k, label]) => (
              <label key={k} className="space-y-1.5 text-xs font-medium text-muted-foreground">{label}<Input value={sp.get(k) ?? ""} onChange={(e) => update({ [k]: e.target.value || null })} className="text-foreground" /></label>
            ))}
            <label className="space-y-1.5 text-xs font-medium text-muted-foreground">Min experience (yrs)<Input type="number" min={0} value={sp.get("exp_min") ?? ""} onChange={(e) => update({ exp_min: e.target.value || null })} className="text-foreground" /></label>
            <label className="space-y-1.5 text-xs font-medium text-muted-foreground">Max experience (yrs)<Input type="number" min={0} value={sp.get("exp_max") ?? ""} onChange={(e) => update({ exp_max: e.target.value || null })} className="text-foreground" /></label>
            <label className="space-y-1.5 text-xs font-medium text-muted-foreground">Minimum rating<Select value={sp.get("rating_min") ?? ""} onChange={(e) => update({ rating_min: e.target.value || null })} className="text-foreground"><option value="">Any</option>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{"★".repeat(n)} and up</option>)}</Select></label>
          </div>
        )}
      </div>

      {selectedIds.length > 0 && (
        <div role="region" aria-label="Bulk actions" className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-primary/30 bg-accent/60 px-3 py-2 text-sm">
          <span className="font-medium">{selectedIds.length} selected</span>
          <Select aria-label="Set status for selected" className="h-8 w-44" value="" disabled={!writable} onChange={(e) => e.target.value && bulk.mutate({ action: "set_status", value: e.target.value })}>
            <option value="">Set status…</option>{CANDIDATE_STATUSES.map((st) => <option key={st} value={st}>{titleCase(st)}</option>)}
          </Select>
          <Input aria-label="Tag to add" placeholder="Tag" className="h-8 w-32" value={tagValue} onChange={(e) => setTagValue(e.target.value)} />
          <Button size="sm" variant="outline" disabled={!writable || !tagValue.trim()} onClick={() => { bulk.mutate({ action: "add_tag", value: tagValue.trim() }); setTagValue(""); }}><Tag /> Add tag</Button>
          <Button size="sm" variant="outline" disabled={!writable} onClick={() => bulk.mutate({ action: "mark_contacted" })}>Mark contacted</Button>
          <Button size="sm" variant="outline" disabled={!writable} onClick={() => bulk.mutate({ action: sp.get("archived") === "true" ? "restore" : "archive" })}>{sp.get("archived") === "true" ? <><RotateCcw /> Restore</> : <><Archive /> Archive</>}</Button>
          <Button size="sm" onClick={() => exportFile(selectedIds)}><Download /> Export selected</Button>
          <Button size="sm" variant="ghost" onClick={() => setSelection({})}>Clear selection</Button>
        </div>
      )}

      {error && !data ? <ErrorState error={error} onRetry={() => refetch()} /> : isLoading ? <LoadingRows /> : !data?.items.length ? (
        <EmptyState icon={Users} title={filterCount ? "No candidates match these filters" : "No candidates yet"}
          description={filterCount ? "Try removing a filter or searching for something else." : "Add a candidate manually, or import a CSV / Excel file using the standard template."}
          action={filterCount ? <Button variant="outline" onClick={() => { setQText(""); setSp(new URLSearchParams()); }}>Clear all filters</Button> : writable ? <div className="flex gap-2"><Button onClick={() => setAddOpen(true)}><Plus /> Add candidate</Button><Button variant="outline" onClick={() => setImportOpen(true)}><FileUp /> Import file</Button></div> : undefined} />
      ) : (
        <>
          <DataTable caption="Candidates" columns={columns} data={data.items} getRowId={(r) => r.id} rowSelection={selection} onRowSelectionChange={setSelection} loading={isFetching}
            sort={sort} onSortChange={(st) => update({ sort: st.sort, direction: st.direction })} />
          <Pagination page={page} pageSize={pageSize} total={data.total} onPage={(p) => update({ page: String(p) })} onPageSize={(n) => update({ page_size: String(n) })} />
        </>
      )}

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent title="Add candidate" description="Name, email and phone are required. Add the rest now or later." size="lg">
          <CandidateForm mode="create" onDone={(id) => { setAddOpen(false); nav(`/candidates/${id}`); }} onCancel={() => setAddOpen(false)} />
        </DialogContent>
      </Dialog>
      {importOpen && <ImportDialog open onOpenChange={setImportOpen} />}
    </>
  );
}
