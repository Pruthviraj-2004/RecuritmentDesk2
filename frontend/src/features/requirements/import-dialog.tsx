import { CheckCircle2, Download, FileSpreadsheet, FileUp, TriangleAlert } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Checkbox, Field, Select } from "@/components/ui/form";
import { downloadUrl, upload } from "@/lib/api";
import { fmtBytes } from "@/lib/utils";
import { reqKeys, useAction } from "@/services/hooks";

interface Row { row: number; title: string; client: string | null; action: string; errors: string[]; warnings: string[]; matched: string | null }
interface Preview {
  total_rows: number; counts: { create: number; update: number; skip_duplicate: number; skip_in_file: number; error: number };
  recognised_columns: string[]; ignored_columns: string[]; problems: Row[]; sample: Row[]; truncated: boolean;
}
interface Result { filename: string; total_rows: number; created: number; updated: number; skipped: number; failed: number; problems: { row: number; title: string; action: string; problems: string[] }[] }

const ACCEPT = ".csv,.xlsx,.txt";

function form(file: File, onDuplicate: string, approve: boolean) {
  const f = new FormData();
  f.append("file", file);
  f.append("on_duplicate", onDuplicate);
  f.append("mark_approved", String(approve));
  return f;
}

/** Import a set of requirements from an Excel or CSV file, after downloading the standard template. */
export function RequirementImportDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [onDuplicate, setOnDuplicate] = useState<"skip" | "update">("skip");
  const [approve, setApprove] = useState(true);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [drag, setDrag] = useState(false);

  const reset = () => { setPreview(null); setResult(null); };
  const pick = (f: File | null) => { setFile(f); reset(); };
  const check = useAction<void, Preview>({ fn: () => upload<Preview>("/requirements/import/preview", form(file!, onDuplicate, approve)), onDone: setPreview });
  const run = useAction<void, Result>({
    fn: () => upload<Result>("/requirements/import", form(file!, onDuplicate, approve)), invalidate: [...reqKeys, ["overview"]],
    success: (r) => `Imported ${r.created} new and ${r.updated} updated requirement(s)`, onDone: (r) => { setResult(r); setPreview(null); },
  });
  const onDrop = (e: DragEvent) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) pick(f); };
  const importable = preview ? preview.counts.create + preview.counts.update : 0;

  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) pick(null); }}>
      <DialogContent title="Import requirements" description="Upload a CSV or Excel file of jobs. Only the job title is required; every other column is optional." size="lg">
        <section className="space-y-2">
          <h3 className="text-sm font-semibold">1. Download the sample file</h3>
          <p className="text-xs text-muted-foreground">Keep these column names (common alternatives such as “Client”, “Skills” or “Job ID” are understood too). The Excel version has an Instructions sheet.</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => window.location.assign(downloadUrl("/requirements/import/template?format=xlsx"))}><Download /> Excel sample (.xlsx)</Button>
            <Button variant="outline" size="sm" onClick={() => window.location.assign(downloadUrl("/requirements/import/template?format=csv"))}><Download /> CSV sample (.csv)</Button>
            <Button variant="ghost" size="sm" onClick={() => window.location.assign(downloadUrl("/requirements/import/template?format=xlsx&examples=false"))}>Blank Excel (no example rows)</Button>
          </div>
        </section>

        <section className="space-y-2">
          <h3 className="text-sm font-semibold">2. Choose your file</h3>
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={onDrop}
            className={`flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors ${drag ? "border-primary bg-accent/50" : "border-input"}`}
          >
            <FileUp className="size-6 text-muted-foreground" />
            {file ? <p className="text-sm font-medium"><FileSpreadsheet className="mr-1 inline size-4" />{file.name} <span className="font-normal text-muted-foreground">({fmtBytes(file.size)})</span></p>
              : <p className="text-sm text-muted-foreground">Drag a .csv or .xlsx file here (max 5 MB, 5,000 rows)</p>}
            <input ref={input} id="requirement-file" data-testid="requirement-file" type="file" accept={ACCEPT} className="sr-only" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
            <Button variant="outline" size="sm" onClick={() => input.current?.click()}>{file ? "Choose a different file" : "Browse files"}</Button>
          </div>
          <Field label="If the job already exists (same client + job ID, or client + title + location)" htmlFor="req-on-dup">
            <Select id="req-on-dup" value={onDuplicate} onChange={(e) => { setOnDuplicate(e.target.value as "skip" | "update"); reset(); }}>
              <option value="skip">Skip it (keep the existing requirement as is)</option>
              <option value="update">Update it with the non-empty cells in my file</option>
            </Select>
          </Field>
          <label className="flex items-center gap-2 text-sm"><Checkbox checked={approve} onChange={(e) => { setApprove(e.target.checked); reset(); }} /> Mark new requirements as approved (otherwise they wait in “needs review”)</label>
        </section>

        {preview && (
          <section className="space-y-3" aria-label="File check results">
            <h3 className="text-sm font-semibold">3. Check results (nothing saved yet)</h3>
            <div className="flex flex-wrap gap-2 text-sm">
              <Badge variant="success">{preview.counts.create} to add</Badge>
              {preview.counts.update > 0 && <Badge variant="default">{preview.counts.update} to update</Badge>}
              {preview.counts.skip_duplicate > 0 && <Badge variant="warning">{preview.counts.skip_duplicate} already exist (skipped)</Badge>}
              {preview.counts.skip_in_file > 0 && <Badge variant="warning">{preview.counts.skip_in_file} repeated in file (skipped)</Badge>}
              {preview.counts.error > 0 && <Badge variant="destructive">{preview.counts.error} with errors</Badge>}
              <span className="text-muted-foreground">of {preview.total_rows} rows</span>
            </div>
            {preview.ignored_columns.length > 0 && <p className="text-xs text-muted-foreground">Ignored columns: {preview.ignored_columns.join(", ")}</p>}
            {preview.problems.length > 0 && (
              <div className="max-h-56 overflow-auto rounded-md border">
                <table className="w-full text-xs"><thead className="sticky top-0 bg-muted text-left"><tr><th className="px-2 py-1.5">Row</th><th className="px-2 py-1.5">Job</th><th className="px-2 py-1.5">Result</th></tr></thead>
                  <tbody>{preview.problems.map((p) => (
                    <tr key={p.row} className="border-t align-top"><td className="px-2 py-1.5 tabular">{p.row}</td><td className="px-2 py-1.5">{p.title || "—"}{p.client ? ` · ${p.client}` : ""}</td>
                      <td className="px-2 py-1.5">{[...p.errors, ...p.warnings].join("; ") || (p.matched ? `Matches existing “${p.matched}”` : p.action)}</td></tr>))}</tbody></table>
              </div>
            )}
            {preview.truncated && <p className="text-xs text-muted-foreground">Showing the first 100 rows with something to note.</p>}
            {importable === 0 && <p role="alert" className="flex items-center gap-2 text-sm text-destructive"><TriangleAlert className="size-4" /> No rows can be imported. Fix the file and check again.</p>}
          </section>
        )}

        {result && (
          <section role="status" className="space-y-2 rounded-md border border-success/40 bg-success/10 p-3 text-sm" aria-label="Import result">
            <p className="flex items-center gap-2 font-semibold"><CheckCircle2 className="size-4 text-success" /> Import finished</p>
            <p>{result.created} added · {result.updated} updated · {result.skipped} skipped · {result.failed} failed (of {result.total_rows} rows)</p>
            {result.problems.length > 0 && <p className="text-xs text-muted-foreground">Problems: {result.problems.slice(0, 5).map((p) => `row ${p.row} (${p.problems.join("; ")})`).join(" · ")}{result.problems.length > 5 ? " …" : ""}</p>}
          </section>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{result ? "Close" : "Cancel"}</Button>
          {!result && <Button variant="secondary" disabled={!file} loading={check.isPending} onClick={() => check.mutate()}>Check file</Button>}
          {!result && <Button disabled={!file || !preview || importable === 0} loading={run.isPending} onClick={() => run.mutate()}>{preview ? `Import ${importable} requirement${importable === 1 ? "" : "s"}` : "Import"}</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
