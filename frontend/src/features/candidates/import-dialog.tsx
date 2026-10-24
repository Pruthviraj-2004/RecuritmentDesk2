import { CheckCircle2, Download, FileSpreadsheet, FileUp, TriangleAlert } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Select } from "@/components/ui/form";
import { downloadUrl, upload } from "@/lib/api";
import { fmtBytes, fmtDateTime } from "@/lib/utils";
import { candidateKeys, useAction, useImportHistory } from "@/services/hooks";
import type { ImportPreview, ImportResult } from "@/types/api";

const ACCEPT = ".csv,.xlsx,.txt";

function form(file: File, onDuplicate: string) {
  const f = new FormData();
  f.append("file", file);
  f.append("on_duplicate", onDuplicate);
  return f;
}

export function ImportDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [onDuplicate, setOnDuplicate] = useState<"skip" | "update">("skip");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [drag, setDrag] = useState(false);
  const history = useImportHistory(open);

  const reset = () => { setPreview(null); setResult(null); };
  const pick = (f: File | null) => { setFile(f); reset(); };
  const check = useAction<void, ImportPreview>({ fn: () => upload<ImportPreview>("/candidates/import/preview", form(file!, onDuplicate)), onDone: setPreview });
  const run = useAction<void, ImportResult>({
    fn: () => upload<ImportResult>("/candidates/import", form(file!, onDuplicate)), invalidate: candidateKeys,
    success: (r) => `Imported ${r.created} new and ${r.updated} updated candidate(s)`, onDone: (r) => { setResult(r); setPreview(null); },
  });
  const onDrop = (e: DragEvent) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) pick(f); };
  const importable = preview ? preview.counts.create + preview.counts.update : 0;

  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) { pick(null); } }}>
      <DialogContent title="Import candidates" description="Upload a CSV or Excel file. Name, email and phone are required for every candidate; all other columns are optional." size="lg">
        <section className="space-y-2">
          <h3 className="text-sm font-semibold">1. Download the standard template</h3>
          <p className="text-xs text-muted-foreground">Use these exact column names (other common names like “Mobile”, “Key Skills” or “Full Name” are understood too). The Excel template has an Instructions sheet.</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => window.location.assign(downloadUrl("/candidates/import/template?format=xlsx"))}><Download /> Excel template (.xlsx)</Button>
            <Button variant="outline" size="sm" onClick={() => window.location.assign(downloadUrl("/candidates/import/template?format=csv"))}><Download /> CSV template (.csv)</Button>
            <Button variant="ghost" size="sm" onClick={() => window.location.assign(downloadUrl("/candidates/import/template?format=xlsx&examples=false"))}>Blank Excel (no example rows)</Button>
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
            <input ref={input} id="candidate-file" data-testid="candidate-file" type="file" accept={ACCEPT} className="sr-only" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
            <Button variant="outline" size="sm" onClick={() => input.current?.click()}>{file ? "Choose a different file" : "Browse files"}</Button>
          </div>
          <Field label="If a candidate already exists (same email or phone)" htmlFor="on-dup">
            <Select id="on-dup" value={onDuplicate} onChange={(e) => { setOnDuplicate(e.target.value as "skip" | "update"); reset(); }}>
              <option value="skip">Skip it (keep the existing profile as is)</option>
              <option value="update">Update it (fill empty fields, add skills and tags; name, email and phone are never changed)</option>
            </Select>
          </Field>
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
                <table className="w-full text-xs"><thead className="sticky top-0 bg-muted text-left"><tr><th className="px-2 py-1.5">Row</th><th className="px-2 py-1.5">Name</th><th className="px-2 py-1.5">Result</th></tr></thead>
                  <tbody>{preview.problems.map((p) => (
                    <tr key={p.row} className="border-t align-top"><td className="px-2 py-1.5 tabular">{p.row}</td><td className="px-2 py-1.5">{p.name || "—"}</td>
                      <td className="px-2 py-1.5">{[...p.errors, ...p.warnings].join("; ") || (p.matched_name ? `Matches existing “${p.matched_name}”` : p.action)}{p.errors.length === 0 && p.matched_name && !p.warnings.length ? ` (${p.action === "update" ? "will update" : "skipped"})` : ""}</td></tr>))}</tbody></table>
              </div>
            )}
            {preview.truncated && <p className="text-xs text-muted-foreground">Showing the first 100 problem rows.</p>}
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

        {history.data && history.data.length > 0 && !preview && !result && (
          <section>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Recent imports</h3>
            <ul className="divide-y rounded-md border text-xs">{history.data.slice(0, 4).map((h) => (
              <li key={h.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-1.5"><span className="truncate font-medium">{h.filename}</span><span className="text-muted-foreground">{fmtDateTime(h.created_at)} · +{h.created} / ~{h.updated} / skipped {h.skipped} / failed {h.failed}</span></li>))}</ul>
          </section>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{result ? "Close" : "Cancel"}</Button>
          {!result && <Button variant="secondary" disabled={!file} loading={check.isPending} onClick={() => check.mutate()}>Check file</Button>}
          {!result && <Button disabled={!file || !preview || importable === 0} loading={run.isPending} onClick={() => run.mutate()}>{preview ? `Import ${importable} candidate${importable === 1 ? "" : "s"}` : "Import"}</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
