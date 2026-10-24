import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Checkbox, Field, Input, Select } from "@/components/ui/form";
import { api } from "@/lib/api";
import { useAction, useExportColumns } from "@/services/hooks";
import type { ExportJob } from "@/types/api";

export type ExportScope = "selected" | "filtered" | "approved";

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  selectedIds: string[];
  filters: Record<string, string>;
  defaultScope?: ExportScope;
}

export function ExportDialog({ open, onOpenChange, selectedIds, filters, defaultScope }: Props) {
  const nav = useNavigate();
  const cols = useExportColumns();
  const [scope, setScope] = useState<ExportScope>(defaultScope ?? (selectedIds.length ? "selected" : "filtered"));
  const [filename, setFilename] = useState("");
  const [sheet, setSheet] = useState("Requirements");
  const [sort, setSort] = useState("received_at");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const [columns, setColumns] = useState<string[] | null>(null);
  const [includeSource, setIncludeSource] = useState(false);
  const [includeAudit, setIncludeAudit] = useState(false);
  const [includeMeta, setIncludeMeta] = useState(false);

  const available = cols.data?.columns.filter((c) => c.group === "core") ?? [];
  const chosen = columns ?? available.filter((c) => c.default).map((c) => c.key);

  const create = useAction<void, ExportJob>({
    fn: () => api.post<ExportJob>("/exports", {
      scope, filename: filename || null, selected_ids: scope === "selected" ? selectedIds : null,
      filters: scope === "selected" ? null : filters,
      options: { columns: chosen, sheet_name: sheet || null, sort, direction, include_source: includeSource, include_audit: includeAudit, include_metadata: includeMeta, include_summary: true },
    }),
    invalidate: [["exports"]],
    success: (e) => (e.status === "completed" ? `Export ready: ${e.record_count} requirements` : e.status === "failed" ? null : "Export started"),
    onDone: (e) => { if (e.status === "failed") toast.error(e.error_summary ?? "Export failed"); onOpenChange(false); nav(`/exports?export=${e.id}`); },
  });

  const noSelection = scope === "selected" && selectedIds.length === 0;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Export to Excel" description="One row per unique canonical requirement. Merged and duplicate records are never exported twice." size="md">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="What to export" className="sm:col-span-2">
            <Select value={scope} onChange={(e) => setScope(e.target.value as ExportScope)} aria-label="Export scope">
              <option value="selected" disabled={!selectedIds.length}>Selected requirements ({selectedIds.length})</option>
              <option value="filtered">Current filtered results</option>
              <option value="approved">All approved requirements</option>
            </Select>
          </Field>
          <Field label="File name" htmlFor="xf" hint="Optional; .xlsx is added automatically"><Input id="xf" value={filename} onChange={(e) => setFilename(e.target.value)} placeholder="recruitment-requirements" /></Field>
          <Field label="Worksheet name" htmlFor="xs"><Input id="xs" maxLength={31} value={sheet} onChange={(e) => setSheet(e.target.value)} /></Field>
          <Field label="Sort by"><Select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort by"><option value="received_at">Received date</option><option value="client_name">Client</option><option value="job_title">Job title</option><option value="last_updated_at">Last updated</option></Select></Field>
          <Field label="Order"><Select value={direction} onChange={(e) => setDirection(e.target.value as "asc" | "desc")} aria-label="Sort order"><option value="desc">Newest / Z–A first</option><option value="asc">Oldest / A–Z first</option></Select></Field>
        </div>
        <fieldset>
          <legend className="mb-1.5 text-xs font-medium text-muted-foreground">Columns</legend>
          <div className="grid max-h-40 grid-cols-2 gap-x-3 gap-y-1.5 overflow-y-auto rounded-md border p-3 text-sm sm:grid-cols-3">
            {available.map((c) => (
              <label key={c.key} className="flex items-center gap-2"><Checkbox checked={chosen.includes(c.key)} onChange={(e) => setColumns(e.target.checked ? [...chosen, c.key] : chosen.filter((k) => k !== c.key))} /> {c.header}</label>
            ))}
          </div>
        </fieldset>
        <div className="space-y-1.5 text-sm">
          <label className="flex items-center gap-2"><Checkbox checked={includeSource} onChange={(e) => setIncludeSource(e.target.checked)} /> Include source information (accounts, email count)</label>
          <label className="flex items-center gap-2"><Checkbox checked={includeAudit} onChange={(e) => setIncludeAudit(e.target.checked)} /> Include status and audit metadata</label>
          <label className="flex items-center gap-2"><Checkbox checked={includeMeta} onChange={(e) => setIncludeMeta(e.target.checked)} /> Add an “Export Info” sheet</label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button loading={create.isPending} disabled={noSelection || chosen.length === 0} onClick={() => create.mutate()}>Generate Excel file</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
