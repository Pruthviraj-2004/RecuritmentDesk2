import { Briefcase, Building2, Copy, ExternalLink, FileUp, GraduationCap, Info, Lightbulb, ShieldAlert, Sparkles, Trash2, Wand2 } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog, EmptyState, ErrorState, KeyValue, LoadingRows } from "@/components/common/common";
import { SkillChips } from "@/components/common/skill-chips";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Checkbox, Field, Select, Textarea } from "@/components/ui/form";
import { api, upload } from "@/lib/api";
import { fmtBytes, fmtDateTime, fmtMonths, fmtYm, monthsBetween, titleCase } from "@/lib/utils";
import { candidateKeys, useAction, useAiProfile, useAiProfileHistory, useAiStatus } from "@/services/hooks";
import type { AiProfileRecord, Candidate } from "@/types/api";

const APPLY_LABELS: Record<string, string> = { title: "Current title", company: "Current company", location: "Location", experience: "Total experience (calculated from dates)", skills: "Skills (added to existing)", education: "Education", certifications: "Certifications (added to existing)", summary: "Profile summary" };

function currentValue(c: Candidate, f: string): string {
  switch (f) {
    case "title": return c.current_title ?? "";
    case "company": return c.current_company ?? "";
    case "location": return c.current_location ?? "";
    case "experience": return c.total_experience != null ? `${c.total_experience} yrs` : "";
    case "skills": return c.skills.join(", ");
    case "education": return c.education ?? "";
    case "certifications": return c.certifications.join(", ");
    default: return c.summary ?? "";
  }
}
function newValue(r: AiProfileRecord, f: string): string {
  const p = r.result.profile, a = r.result.analytics;
  switch (f) {
    case "title": return p.current_title ?? "";
    case "company": return p.current_company ?? "";
    case "location": return p.location ?? "";
    case "experience": return a.total_experience_years != null ? `${a.total_experience_years} yrs` : "";
    case "skills": return p.skills.join(", ");
    case "education": { const e = p.education[0]; return e ? [e.degree, e.field, e.school].filter(Boolean).join(", ") : ""; }
    case "certifications": return p.certifications.join(", ");
    default: return p.ai_summary ?? "";
  }
}

function ApplyDialog({ c, rec, onClose }: { c: Candidate; rec: AiProfileRecord; onClose: () => void }) {
  const fields = Object.keys(APPLY_LABELS).filter((f) => newValue(rec, f));
  const [checked, setChecked] = useState<string[]>(() => fields.filter((f) => ["skills", "certifications"].includes(f) || !currentValue(c, f)));
  const apply = useAction<void, unknown>({
    fn: () => api.post(`/candidates/${c.id}/ai-profiles/${rec.id}/apply`, { fields: checked }), invalidate: [...candidateKeys, ["candidate", c.id]],
    success: "AI profile applied to the candidate record", onDone: onClose,
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Apply to candidate profile" description="Choose what to copy onto the record. Name, email and phone are never changed. Fields that already have a value are unticked by default." size="lg">
        {fields.length === 0 ? <p className="text-sm text-muted-foreground">This AI profile has no data that can be applied.</p> : (
          <ul className="divide-y rounded-md border text-sm">{fields.map((f) => {
            const cur = currentValue(c, f), nv = newValue(rec, f);
            return (
              <li key={f} className="flex gap-3 px-3 py-2.5">
                <Checkbox id={`ap-${f}`} className="mt-1" checked={checked.includes(f)} onChange={(e) => setChecked((s) => (e.target.checked ? [...s, f] : s.filter((x) => x !== f)))} />
                <label htmlFor={`ap-${f}`} className="min-w-0 flex-1 cursor-pointer">
                  <span className="font-medium">{APPLY_LABELS[f]}</span>
                  <span className="mt-0.5 block break-words text-xs text-muted-foreground">Now: {cur || "empty"}</span>
                  <span className="block break-words text-xs">New: {nv.length > 220 ? `${nv.slice(0, 220)}…` : nv}</span>
                </label>
              </li>
            );
          })}</ul>
        )}
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button disabled={checked.length === 0} loading={apply.isPending} onClick={() => apply.mutate()}>Apply {checked.length} field{checked.length === 1 ? "" : "s"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Results({ c, rec, writable }: { c: Candidate; rec: AiProfileRecord; writable: boolean }) {
  const [applyOpen, setApplyOpen] = useState(false);
  const [delOpen, setDelOpen] = useState(false);
  const p = rec.result.profile, a = rec.result.analytics, verify = rec.result.verify;
  const remove = useAction<void, unknown>({ fn: () => api.del(`/candidates/${c.id}/ai-profiles/${rec.id}`), invalidate: [["candidate", c.id]], success: "AI profile deleted", onDone: () => setDelOpen(false) });
  const copy = async (text: string) => { try { await navigator.clipboard.writeText(text); toast.success("Copied"); } catch { toast.error("Could not copy automatically; select the text and copy it"); } };
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Badge variant="secondary">AI-generated</Badge><span>{fmtDateTime(rec.created_at)} · {rec.model ?? rec.provider} · from {rec.source_label ?? titleCase(rec.source_type)}</span>
        {rec.applied_fields.length > 0 && <Badge variant="success">Applied: {rec.applied_fields.join(", ")}</Badge>}
        <span className="ml-auto flex gap-2">
          <Button size="sm" disabled={!writable} onClick={() => setApplyOpen(true)}><Wand2 /> Apply to profile</Button>
          <Button size="sm" variant="ghost" disabled={!writable} aria-label="Delete this AI profile" onClick={() => setDelOpen(true)}><Trash2 /></Button>
        </span>
      </div>

      <Card><CardContent className="space-y-3 p-4">
        {p.headline && <p className="text-base font-semibold">{p.headline}</p>}
        {p.ai_summary ? <p className="text-sm leading-relaxed">{p.ai_summary}</p> : <p className="text-sm text-muted-foreground">No summary was produced.</p>}
        <div className="flex flex-wrap gap-1.5">{p.seniority && <Badge>{titleCase(p.seniority)}</Badge>}{p.industries.map((i) => <Badge key={i} variant="secondary">{i}</Badge>)}{p.location && <Badge variant="muted">{p.location}</Badge>}</div>
      </CardContent></Card>

      <Card><CardHeader><CardTitle>Key facts <span className="text-xs font-normal text-muted-foreground">(calculated from the dates, not estimated by AI)</span></CardTitle></CardHeader><CardContent>
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-3">
          <KeyValue label="Current role">{[p.current_title, p.current_company].filter(Boolean).join(" at ")}</KeyValue>
          <KeyValue label="Total experience">{a.total_experience_years != null ? `${a.total_experience_years} years` : null}</KeyValue>
          <KeyValue label="Currently employed">{a.currently_employed ? "Yes" : a.roles ? "No current role listed" : null}</KeyValue>
          <KeyValue label="Employers / roles">{a.roles ? `${a.employers} / ${a.roles}` : null}</KeyValue>
          <KeyValue label="Average tenure">{a.average_tenure_months != null ? fmtMonths(a.average_tenure_months) : null}</KeyValue>
          <KeyValue label="Longest tenure">{a.longest_tenure ? `${a.longest_tenure.company} (${fmtMonths(a.longest_tenure.months)})` : null}</KeyValue>
        </dl>
        {a.recent_companies.length > 0 && <p className="mt-3 flex flex-wrap items-center gap-2 text-sm"><Building2 className="size-4 text-muted-foreground" /><span className="text-muted-foreground">Recent companies:</span>{a.recent_companies.map((n) => <Badge key={n} variant="default">{n}</Badge>)}</p>}
      </CardContent></Card>

      {verify.length > 0 && (
        <div role="note" className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">
          <p className="mb-1 flex items-center gap-2 font-medium"><ShieldAlert className="size-4 text-warning" /> Worth verifying with the candidate</p>
          <ul className="list-disc space-y-0.5 pl-6">{verify.map((v) => <li key={v}>{v}</li>)}</ul>
          <p className="mt-1 text-xs text-muted-foreground">Neutral prompts generated from the dates and the source text. They are not a judgement about the person.</p>
        </div>
      )}

      <Card><CardHeader><CardTitle className="flex items-center gap-2"><Briefcase className="size-4" /> Experience</CardTitle></CardHeader><CardContent>
        {p.positions.length === 0 ? <p className="text-sm text-muted-foreground">No roles found in the text.</p> : (
          <ol className="space-y-4 border-l pl-4">{p.positions.map((x, i) => {
            const months = monthsBetween(x.start, x.end);
            return (
              <li key={`${x.company}-${i}`} className="relative">
                <span className="absolute -left-[21px] top-1.5 size-2.5 rounded-full bg-primary" aria-hidden />
                <p className="text-sm font-medium">{x.title ?? "Role"} <span className="font-normal text-muted-foreground">at</span> {x.company}</p>
                <p className="text-xs text-muted-foreground">{[x.start ? `${fmtYm(x.start)} – ${x.end ? fmtYm(x.end) : "?"}` : null, months ? fmtMonths(months) : null, x.location].filter(Boolean).join(" · ") || "Dates not stated"}</p>
                {x.description && <p className="mt-1 text-sm">{x.description}</p>}
                {x.skills_used.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{x.skills_used.map((s) => <Badge key={s} variant="muted">{s}</Badge>)}</div>}
              </li>);
          })}</ol>
        )}
      </CardContent></Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card><CardHeader><CardTitle>Skills</CardTitle></CardHeader><CardContent className="space-y-3">
          {p.top_skills.length > 0 && <div className="flex flex-wrap gap-1.5">{p.top_skills.map((s) => <Badge key={s} variant="default">{s}</Badge>)}</div>}
          {p.skills.some((s) => !p.top_skills.includes(s)) && <SkillChips skills={p.skills.filter((s) => !p.top_skills.includes(s))} limit={10} width={420} />}
          {p.skills.length === 0 && <p className="text-sm text-muted-foreground">No skills found in the text.</p>}
        </CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><GraduationCap className="size-4" /> Education & credentials</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">
          {p.education.map((e) => <p key={e.school}>{[e.degree, e.field].filter(Boolean).join(", ") || "Studied"} · <span className="font-medium">{e.school}</span>{e.start_year || e.end_year ? <span className="text-muted-foreground"> ({[e.start_year, e.end_year].filter(Boolean).join("–")})</span> : null}</p>)}
          {p.certifications.length > 0 && <div className="flex flex-wrap gap-1.5">{p.certifications.map((x) => <Badge key={x} variant="secondary">{x}</Badge>)}</div>}
          {(p.languages.length > 0 || p.honors.length > 0) && <p className="text-xs text-muted-foreground">{[p.languages.length ? `Languages: ${p.languages.join(", ")}` : "", p.honors.length ? `Honors: ${p.honors.join(", ")}` : ""].filter(Boolean).join(" · ")}</p>}
          {p.education.length === 0 && p.certifications.length === 0 && <p className="text-muted-foreground">Nothing found in the text.</p>}
        </CardContent></Card>
      </div>

      {p.projects.length > 0 && (
        <Card><CardHeader><CardTitle>Projects (high level)</CardTitle></CardHeader><CardContent className="grid gap-3 sm:grid-cols-2">
          {p.projects.map((pr) => (
            <div key={pr.name} className="rounded-md border p-3 text-sm"><p className="font-medium">{pr.name}{pr.url && <a className="ml-1 inline-flex align-middle text-primary" href={pr.url} target="_blank" rel="noopener noreferrer" aria-label={`Open ${pr.name}`}><ExternalLink className="size-3" /></a>}</p>
              {pr.description && <p className="mt-0.5 text-muted-foreground">{pr.description}</p>}{pr.technologies.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{pr.technologies.map((t) => <Badge key={t} variant="muted">{t}</Badge>)}</div>}</div>))}
        </CardContent></Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {p.career_highlights.length > 0 && <Card><CardHeader><CardTitle className="flex items-center gap-2"><Sparkles className="size-4" /> Career highlights</CardTitle></CardHeader><CardContent><ul className="list-disc space-y-1 pl-5 text-sm">{p.career_highlights.map((h) => <li key={h}>{h}</li>)}</ul></CardContent></Card>}
        {p.screening_questions.length > 0 && (
          <Card><CardHeader className="flex-row items-center justify-between space-y-0"><CardTitle className="flex items-center gap-2"><Lightbulb className="size-4" /> Suggested screening questions</CardTitle>
            <Button size="sm" variant="ghost" aria-label="Copy questions" onClick={() => copy(p.screening_questions.map((q, i) => `${i + 1}. ${q}`).join("\n"))}><Copy /> Copy</Button></CardHeader>
            <CardContent><ol className="list-decimal space-y-1 pl-5 text-sm">{p.screening_questions.map((q) => <li key={q}>{q}</li>)}</ol></CardContent></Card>
        )}
      </div>
      {applyOpen && <ApplyDialog c={c} rec={rec} onClose={() => setApplyOpen(false)} />}
      <ConfirmDialog open={delOpen} onOpenChange={setDelOpen} title="Delete this AI profile?" destructive confirmLabel="Delete" loading={remove.isPending} description="The extracted profile is removed. Anything you already applied to the candidate record stays." onConfirm={() => remove.mutate()} />
    </div>
  );
}

export function AiProfileTab({ c, writable }: { c: Candidate; writable: boolean }) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [source, setSource] = useState<"linkedin_text" | "resume_text">("linkedin_text");
  const [file, setFile] = useState<File | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const ai = useAiStatus(false);
  const latest = useAiProfile(c.id, selected);
  const history = useAiProfileHistory(c.id);
  const configured = ai.data?.configured !== false;
  const run = useAction<void, AiProfileRecord>({
    fn: () => {
      const f = new FormData();
      f.append("source", source);
      if (file) f.append("file", file); else f.append("text", text);
      return upload<AiProfileRecord>(`/candidates/${c.id}/ai-profile`, f);
    },
    invalidate: [["candidate", c.id]], success: "AI profile created", onDone: (r) => { setSelected(r.id); setText(""); setFile(null); },
  });
  const ready = !!file || text.trim().length >= 200;

  return (
    <div className="space-y-4">
      <Card><CardHeader><CardTitle className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> Build an AI profile</CardTitle></CardHeader><CardContent className="space-y-3">
        <div className="flex gap-2 rounded-md border bg-muted/40 p-3 text-sm"><Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <div className="space-y-1">
            <p>LinkedIn does not allow automated reading of profiles, so RecruitmentDesk never opens the link itself. Give the AI the profile content instead, and it will structure it for you:</p>
            <ol className="list-decimal pl-5 text-muted-foreground"><li>Open the profile while signed in to LinkedIn{c.linkedin_url && <> (<a className="inline-flex items-center gap-0.5 text-primary hover:underline" href={c.linkedin_url} target="_blank" rel="noopener noreferrer">open on LinkedIn <ExternalLink className="size-3" /></a>).</>}</li>
              <li>Select all the profile text and copy it, or use <b>More → Save to PDF</b>.</li><li>Paste it below or upload the PDF. A resume (PDF, DOCX, TXT) works too.</li></ol>
          </div></div>
        {!configured && <div role="alert" className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">{ai.data?.message ?? "AI is not configured on the server."} Set the AI provider in the server settings to use this feature.</div>}
        <div className="grid gap-3 sm:grid-cols-[220px_1fr]">
          <Field label="Content is" htmlFor="ai-source"><Select id="ai-source" value={source} onChange={(e) => setSource(e.target.value as "linkedin_text" | "resume_text")} disabled={!!file}><option value="linkedin_text">LinkedIn profile text</option><option value="resume_text">Resume text</option></Select></Field>
          <div className="flex items-end gap-2">
            <input ref={fileInput} data-testid="ai-file" type="file" accept=".pdf,.docx,.txt" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <Button variant="outline" onClick={() => fileInput.current?.click()}><FileUp /> {file ? "Change file" : "Upload PDF / DOCX / TXT"}</Button>
            {file && <span className="truncate text-sm">{file.name} <span className="text-muted-foreground">({fmtBytes(file.size)})</span> <button type="button" className="text-primary hover:underline" onClick={() => setFile(null)}>remove</button></span>}
          </div>
        </div>
        <Field label="Or paste the text" htmlFor="ai-text" hint={`${text.trim().length.toLocaleString()} characters${text.trim().length > 0 && text.trim().length < 200 ? " (at least 200 needed)" : ""}`}>
          <Textarea id="ai-text" rows={8} placeholder="Paste the LinkedIn profile text here…" value={text} disabled={!!file} onChange={(e) => setText(e.target.value)} />
        </Field>
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={!writable || !configured || !ready} loading={run.isPending} onClick={() => run.mutate()}><Sparkles /> {run.isPending ? "Reading profile…" : "Extract with AI"}</Button>
          <p className="text-xs text-muted-foreground">Runs only when you click. The text goes to your configured AI provider{ai.data?.base_url_host ? ` (${ai.data.base_url_host})` : ""} for this request and is not stored; only the extracted result is kept.</p>
        </div>
      </CardContent></Card>

      {history.data && history.data.length > 1 && (
        <Field label="Earlier extractions" htmlFor="ai-history"><Select id="ai-history" className="max-w-md" value={selected ?? history.data[0].id} onChange={(e) => setSelected(e.target.value)}>
          {history.data.map((h) => <option key={h.id} value={h.id}>{fmtDateTime(h.created_at)} · {h.source_label ?? titleCase(h.source_type)}</option>)}</Select></Field>
      )}
      {latest.isLoading ? <LoadingRows rows={4} /> : latest.error ? <ErrorState error={latest.error} onRetry={() => latest.refetch()} /> : latest.data ? <Results key={latest.data.id} c={c} rec={latest.data} writable={writable} /> : (
        <EmptyState icon={Sparkles} title="No AI profile yet" description="Add the profile content above and click Extract with AI to see skills, recent companies, projects and more." />
      )}
    </div>
  );
}
