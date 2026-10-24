import { Archive, Download, ExternalLink, Mail, Pencil, Phone, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/app/auth";
import { EmptyState, ErrorState, KeyValue, LoadingRows, PageHeader, StatusBadge, useDebounced } from "@/components/common/common";
import { SkillChips } from "@/components/common/skill-chips";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AiProfileTab } from "@/features/candidates/ai-profile-tab";
import { CandidateForm } from "@/features/candidates/candidate-form";
import { Stars } from "@/features/candidates/candidates-page";
import { api, errorMessage } from "@/lib/api";
import { downloadPost } from "@/lib/download";
import { fmtDateTime, fmtRelative, titleCase } from "@/lib/utils";
import { candidateKeys, useAction, useCandidate, useCandidateMatches, useCandidateNotes, useCandidateSubmissions, useRequirements } from "@/services/hooks";
import { CANDIDATE_STATUSES, PIPELINE_STAGES, type Candidate, type CandidateStatus, type PipelineStage, type Submission } from "@/types/api";

const Section = ({ title, children }: { title: string; children: ReactNode }) => (
  <Card><CardHeader><CardTitle>{title}</CardTitle></CardHeader><CardContent><dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">{children}</dl></CardContent></Card>
);
const yn = (v: boolean | null) => (v == null ? null : v ? "Yes" : "No");

function Profile({ c }: { c: Candidate }) {
  const money = (v: number | null) => (v == null ? null : `${c.currency ?? ""} ${v.toLocaleString("en-IN")}`.trim());
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title="Contact">
        <KeyValue label="Email"><a className="inline-flex items-center gap-1 text-primary hover:underline" href={`mailto:${c.email}`}><Mail className="size-3.5" />{c.email}</a></KeyValue>
        <KeyValue label="Phone"><a className="inline-flex items-center gap-1 text-primary hover:underline" href={`tel:${c.phone}`}><Phone className="size-3.5" />{c.phone}</a></KeyValue>
        <KeyValue label="LinkedIn">{c.linkedin_url && <a className="inline-flex items-center gap-1 break-all text-primary hover:underline" href={c.linkedin_url} target="_blank" rel="noopener noreferrer">Open profile <ExternalLink className="size-3" /></a>}</KeyValue>
        <KeyValue label="Resume">{c.resume_url && <a className="inline-flex items-center gap-1 text-primary hover:underline" href={c.resume_url} target="_blank" rel="noopener noreferrer">Open resume <ExternalLink className="size-3" /></a>}</KeyValue>
      </Section>
      <Section title="Professional">
        <KeyValue label="Current title">{c.current_title}</KeyValue><KeyValue label="Current company">{c.current_company}</KeyValue>
        <KeyValue label="Total experience">{c.total_experience != null ? `${c.total_experience} yrs` : null}</KeyValue><KeyValue label="Relevant experience">{c.relevant_experience != null ? `${c.relevant_experience} yrs` : null}</KeyValue>
        <KeyValue label="Education">{c.education}</KeyValue><KeyValue label="Certifications">{c.certifications.join(", ")}</KeyValue>
      </Section>
      <Section title="Location & availability">
        <KeyValue label="Current location">{c.current_location}</KeyValue><KeyValue label="Preferred locations">{c.preferred_locations.join(", ")}</KeyValue>
        <KeyValue label="Willing to relocate">{yn(c.willing_to_relocate)}</KeyValue><KeyValue label="Notice period">{c.notice_period}</KeyValue>
        <KeyValue label="Work authorization">{c.work_authorization}</KeyValue>
      </Section>
      <Section title="Compensation">
        <KeyValue label="Current CTC">{money(c.current_ctc)}</KeyValue><KeyValue label="Expected CTC">{money(c.expected_ctc)}</KeyValue>
      </Section>
      <Card className="lg:col-span-2"><CardHeader><CardTitle>Skills, tags & summary</CardTitle></CardHeader><CardContent className="space-y-3">
        <div><p className="mb-1 text-xs text-muted-foreground">Skills</p><SkillChips skills={c.skills} limit={50} width={720} /></div>
        <div><p className="mb-1 text-xs text-muted-foreground">Tags</p>{c.tags.length ? <div className="flex flex-wrap gap-1.5">{c.tags.map((t) => <Badge key={t} variant="muted">{t}</Badge>)}</div> : <span className="text-sm text-muted-foreground">—</span>}</div>
        <div><p className="mb-1 text-xs text-muted-foreground">Summary</p>{c.summary ? <p className="whitespace-pre-wrap break-words text-sm">{c.summary}</p> : <span className="text-sm text-muted-foreground">—</span>}</div>
        <p className="text-xs text-muted-foreground">Source: {c.source} · Added {fmtDateTime(c.created_at)} · Last contacted {c.last_contacted_at ? fmtRelative(c.last_contacted_at) : "never"}</p>
      </CardContent></Card>
    </div>
  );
}

function Notes({ id, writable }: { id: string; writable: boolean }) {
  const q = useCandidateNotes(id);
  const [body, setBody] = useState("");
  const add = useAction<string, unknown>({ fn: (b) => api.post(`/candidates/${id}/notes`, { body: b }), invalidate: [["candidate", id, "notes"], ["candidate", id]], success: "Note added", onDone: () => setBody("") });
  return (
    <div className="space-y-4">
      <Card><CardContent className="space-y-2 p-4">
        <Field label="Add a note" htmlFor="note-body" hint="Call outcomes, feedback, anything worth remembering. Adding a note marks the candidate as contacted."><Textarea id="note-body" rows={3} value={body} onChange={(e) => setBody(e.target.value)} disabled={!writable} /></Field>
        <Button disabled={!writable || !body.trim()} loading={add.isPending} onClick={() => add.mutate(body.trim())}>Save note</Button>
      </CardContent></Card>
      {q.isLoading ? <LoadingRows rows={3} /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data?.length ? <EmptyState title="No activity yet" description="Notes, status changes and pipeline moves appear here." /> : (
        <ol className="space-y-2">{q.data.map((n) => (
          <li key={n.id} className="rounded-lg border bg-card p-3 text-sm">
            <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><Badge variant={n.kind === "note" ? "default" : "muted"}>{n.kind === "note" ? "Note" : n.kind === "status" ? "Status" : "Activity"}</Badge><span>{n.author ?? "system"} · {fmtDateTime(n.created_at)}</span></div>
            <p className="whitespace-pre-wrap break-words">{n.body}</p>
          </li>))}</ol>
      )}
    </div>
  );
}

function AddToPipeline({ candidateId, onAdded }: { candidateId: string; onAdded: () => void }) {
  const [q, setQ] = useState("");
  const [stage, setStage] = useState<PipelineStage>("shortlisted");
  const dq = useDebounced(q);
  const res = useRequirements({ q: dq, page_size: 6, lifecycle_status: "active" });
  const add = useAction<string, Submission>({ fn: (rid) => api.post(`/candidates/${candidateId}/submissions`, { requirement_id: rid, stage }), invalidate: [...candidateKeys, ["candidate", candidateId, "submissions"], ["candidate", candidateId, "notes"], ["requirement"]], success: "Added to pipeline", onDone: onAdded });
  return (
    <Card><CardContent className="space-y-3 p-4">
      <p className="text-sm font-medium">Add to a requirement's pipeline</p>
      <div className="grid gap-3 sm:grid-cols-[1fr_180px]">
        <Input aria-label="Search requirements" placeholder="Search requirement title, client or job ID" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select aria-label="Stage" value={stage} onChange={(e) => setStage(e.target.value as PipelineStage)}>{PIPELINE_STAGES.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</Select>
      </div>
      {dq && (res.data?.items.length ? (
        <ul className="divide-y rounded-md border text-sm">{res.data.items.map((r) => (
          <li key={r.id} className="flex items-center justify-between gap-2 px-3 py-2"><span className="min-w-0 truncate">{r.job_title ?? "(untitled)"} <span className="text-muted-foreground">· {r.client_name ?? "—"}</span></span>
            <Button size="sm" variant="outline" loading={add.isPending && add.variables === r.id} onClick={() => add.mutate(r.id)}><Plus /> Add</Button></li>))}</ul>
      ) : <p className="text-xs text-muted-foreground">No matching requirements.</p>)}
    </CardContent></Card>
  );
}

function Pipeline({ c, writable }: { c: Candidate; writable: boolean }) {
  const q = useCandidateSubmissions(c.id);
  const keys = [["candidate", c.id, "submissions"], ["candidate", c.id, "notes"], ["candidates"], ["candidate-stats"], ["requirement"]] as const;
  const stage = useAction<{ id: string; stage: PipelineStage }, Submission>({ fn: (v) => api.patch(`/candidates/submissions/${v.id}`, { stage: v.stage }), invalidate: [...keys], success: "Stage updated" });
  const remove = useAction<string, unknown>({ fn: (id) => api.del(`/candidates/submissions/${id}`), invalidate: [...keys], success: "Removed from pipeline" });
  return (
    <div className="space-y-4">
      {writable && <AddToPipeline candidateId={c.id} onAdded={() => q.refetch()} />}
      {q.isLoading ? <LoadingRows rows={2} /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data?.length ? <EmptyState title="Not in any pipeline" description="Add this candidate to a requirement above, or use the Matching jobs tab." /> : (
        <ul className="space-y-2">{q.data.map((s) => (
          <li key={s.id}><Card><CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
            <div className="min-w-0"><Link to={`/requirements/${s.requirement_id}`} className="font-medium text-primary hover:underline">{s.requirement_title ?? "(untitled)"}</Link>
              <p className="text-xs text-muted-foreground">{s.requirement_client ?? "—"} · updated {fmtRelative(s.updated_at)}</p></div>
            <div className="flex items-center gap-2">
              <Select aria-label={`Stage for ${s.requirement_title ?? "requirement"}`} className="h-8 w-40" value={s.stage} disabled={!writable} onChange={(e) => stage.mutate({ id: s.id, stage: e.target.value as PipelineStage })}>{PIPELINE_STAGES.map((st) => <option key={st} value={st}>{titleCase(st)}</option>)}</Select>
              <Button variant="ghost" size="icon" className="h-8 w-8" disabled={!writable} aria-label="Remove from pipeline" onClick={() => remove.mutate(s.id)}><Trash2 /></Button>
            </div>
          </CardContent></Card></li>))}</ul>
      )}
    </div>
  );
}

function Matches({ c, writable }: { c: Candidate; writable: boolean }) {
  const q = useCandidateMatches(c.id);
  const add = useAction<string, Submission>({ fn: (rid) => api.post(`/candidates/${c.id}/submissions`, { requirement_id: rid, stage: "shortlisted" }), invalidate: [["candidate", c.id], ["candidates"], ["candidate-stats"], ["requirement"]], success: "Added to pipeline as shortlisted" });
  if (q.isLoading) return <LoadingRows rows={3} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data?.length) return <EmptyState title="No matching jobs yet" description="Matches appear when active requirements share this candidate's skills, experience range or location. Add skills and experience to improve matching." />;
  return (
    <ul className="space-y-2">{q.data.map((m) => (
      <li key={m.requirement.id}><Card><CardContent className="space-y-2 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0"><Link to={`/requirements/${m.requirement.id}`} className="font-medium text-primary hover:underline">{m.requirement.job_title ?? "(untitled)"}</Link>
            <p className="text-xs text-muted-foreground">{m.requirement.client_name ?? "—"} · {m.requirement.location ?? "—"}</p></div>
          <div className="flex items-center gap-2"><ScoreBar score={m.score} />{m.stage ? <StatusBadge status={m.stage} /> : <Button size="sm" variant="outline" disabled={!writable} loading={add.isPending && add.variables === m.requirement.id} onClick={() => add.mutate(m.requirement.id)}><Plus /> Add to pipeline</Button>}</div>
        </div>
        <ul className="flex flex-wrap gap-1.5 text-xs">{m.reasons.map((r) => <li key={r} className="rounded bg-muted px-2 py-0.5">{r}</li>)}</ul>
        {m.ai_profile_used && <p className="text-xs text-primary">Includes the AI profile{(m.ai_only_matches?.length ?? 0) > 0 ? `: ${m.ai_only_matches!.join(", ")} found only there` : ""}</p>}
        {m.missing_skills.length > 0 && <p className="text-xs text-muted-foreground">Missing: {m.missing_skills.join(", ")}</p>}
      </CardContent></Card></li>))}</ul>
  );
}

export function ScoreBar({ score }: { score: number }) {
  const tone = score >= 75 ? "bg-success" : score >= 50 ? "bg-warning" : "bg-muted-foreground";
  return (
    <div className="flex items-center gap-2" aria-label={`Match score ${score} out of 100`}>
      <div className="h-2 w-24 overflow-hidden rounded-full bg-muted"><div className={`h-full ${tone}`} style={{ width: `${score}%` }} /></div>
      <span className="tabular w-10 text-sm font-semibold">{score}%</span>
    </div>
  );
}

export function CandidateDetailPage() {
  const { id } = useParams();
  const [sp, setSp] = useSearchParams();
  const { can } = useAuth();
  const q = useCandidate(id);
  const editing = sp.get("edit") === "1";
  const tab = sp.get("tab") ?? "profile";
  const writable = can("member");
  const setStatus = useAction<CandidateStatus, Candidate>({ fn: (s) => api.patch(`/candidates/${id}`, { status: s }), invalidate: [...candidateKeys, ["candidate", id ?? "", "notes"]], success: "Status updated" });
  const archive = useAction<void, unknown>({ fn: () => api.del(`/candidates/${id}`), invalidate: candidateKeys, success: "Candidate archived" });
  const restore = useAction<void, unknown>({ fn: () => api.post(`/candidates/${id}/restore`), invalidate: candidateKeys, success: "Candidate restored" });

  if (q.isLoading) return <LoadingRows />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} title="Candidate could not be loaded" />;
  const c = q.data;
  const setTab = (t: string) => { const n = new URLSearchParams(sp); n.set("tab", t); setSp(n, { replace: true }); };
  return (
    <>
      <PageHeader breadcrumb={<><Link to="/candidates" className="hover:underline">Candidate Profiles</Link> / {c.full_name}</>} title={c.full_name}
        description={[c.current_title, c.current_company].filter(Boolean).join(" at ") || "No current role added"}
        actions={<>
          <Button variant="outline" onClick={async () => { try { await downloadPost("/candidates/export", { ids: [c.id] }, "candidate.xlsx"); } catch (e) { toast.error(errorMessage(e)); } }}><Download /> Export</Button>
          <Button variant="outline" disabled={!writable} onClick={() => setSp(new URLSearchParams({ edit: "1" }))}><Pencil /> Edit</Button>
          {c.is_archived ? <Button variant="outline" disabled={!writable} loading={restore.isPending} onClick={() => restore.mutate()}><RotateCcw /> Restore</Button>
            : <Button variant="outline" disabled={!writable} loading={archive.isPending} onClick={() => archive.mutate()}><Archive /> Archive</Button>}
        </>} />
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <Select aria-label="Candidate status" className="h-8 w-44" value={c.status} disabled={!writable} onChange={(e) => setStatus.mutate(e.target.value as CandidateStatus)}>{CANDIDATE_STATUSES.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</Select>
        <Stars n={c.rating} />{c.is_archived && <Badge variant="muted">Archived</Badge>}
        <span className="text-muted-foreground">{c.total_experience != null ? `${c.total_experience} yrs · ` : ""}{c.current_location ?? "Location not set"}{c.notice_period ? ` · Notice: ${c.notice_period}` : ""}</span>
      </div>
      {editing ? (
        <Card><CardContent className="p-5"><CandidateForm mode="edit" candidate={c} onDone={() => setSp(new URLSearchParams(), { replace: true })} onCancel={() => setSp(new URLSearchParams(), { replace: true })} /></CardContent></Card>
      ) : (
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList><TabsTrigger value="profile">Profile</TabsTrigger><TabsTrigger value="notes">Notes & activity</TabsTrigger><TabsTrigger value="ai">AI Profile</TabsTrigger><TabsTrigger value="pipeline">Pipeline ({c.pipeline_count})</TabsTrigger><TabsTrigger value="matches">Matching jobs</TabsTrigger></TabsList>
          <TabsContent value="profile"><Profile c={c} /></TabsContent>
          <TabsContent value="notes"><Notes id={c.id} writable={writable} /></TabsContent>
          <TabsContent value="ai"><AiProfileTab c={c} writable={writable} /></TabsContent>
          <TabsContent value="pipeline"><Pipeline c={c} writable={writable} /></TabsContent>
          <TabsContent value="matches"><Matches c={c} writable={writable} /></TabsContent>
        </Tabs>
      )}
    </>
  );
}
