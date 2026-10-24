import { AlertTriangle, Archive, Check, ExternalLink, FileSpreadsheet, Pencil, RotateCcw, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useAuth } from "@/app/auth";
import { EmptyState, ErrorState, KeyValue, LoadingRows, PageHeader, StatusBadge } from "@/components/common/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RequirementCandidates } from "@/features/candidates/requirement-candidates";
import { ExportDialog } from "@/features/exports/export-dialog";
import { RequirementForm } from "@/features/requirements/requirement-form";
import { fmtDate, fmtDateTime, fmtExperience, fmtSalary, pct, titleCase } from "@/lib/utils";
import { useAudit, useRequirement, useRequirementAction, useRequirementSources, useRequirementVersions, useSimilar } from "@/services/hooks";
import type { RequirementDetail } from "@/types/api";

const WARNING_TEXT: Record<string, string> = {
  insufficient_information: "Not enough identifying information was extracted. Please verify and complete this record.",
  low_confidence: "Extraction confidence is low. Verify key fields against the source email.",
  closure_notice_received: "A closure / cancellation notice was received for this requirement. Review and close it if appropriate.",
  salary_currency_missing: "A salary was extracted without a currency.",
};
function warningText(w: string): string {
  if (w.startsWith("conflict:")) return `A newer email disagrees on “${titleCase(w.slice(9))}”. The existing value was kept; review the source emails.`;
  if (w.startsWith("body_attachment_conflict")) return "The email body and its attachment disagree on a key detail. Check both sources.";
  if (w.endsWith("_not_found_in_source")) return `${titleCase(w.replace("_not_found_in_source", ""))} could not be verified in the source text.`;
  if (w.includes("unsupported_removed")) return "Some extracted skills were not found in the source and were removed.";
  return WARNING_TEXT[w] ?? titleCase(w);
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <Card><CardHeader><CardTitle>{title}</CardTitle></CardHeader><CardContent><dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">{children}</dl></CardContent></Card>;
}
const Chips = ({ items, variant = "secondary" }: { items: string[]; variant?: "secondary" | "default" }) => items.length ? <div className="flex flex-wrap gap-1.5">{items.map((s) => <Badge key={s} variant={variant} className="h-auto max-w-full whitespace-normal text-left">{s}</Badge>)}</div> : null;

function Overview({ r }: { r: RequirementDetail }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title="Job"><KeyValue label="Client">{r.client_name}</KeyValue><KeyValue label="Job title">{r.job_title}</KeyValue><KeyValue label="Job reference ID">{r.job_reference_id}</KeyValue>
        <KeyValue label="Openings">{r.number_of_openings}</KeyValue><KeyValue label="Department">{r.department}</KeyValue><KeyValue label="Seniority">{r.seniority}</KeyValue></Section>
      <Section title="Skills">
        <div className="sm:col-span-2"><KeyValue label="Required skills"><Chips items={r.required_skills} variant="default" /></KeyValue></div>
        <div className="sm:col-span-2"><KeyValue label="Preferred skills"><Chips items={r.preferred_skills} /></KeyValue></div>
        <div className="sm:col-span-2"><KeyValue label="Certifications"><Chips items={r.certifications} /></KeyValue></div>
      </Section>
      <Section title="Experience & qualifications"><KeyValue label="Experience">{fmtExperience(r.minimum_experience, r.maximum_experience)}</KeyValue><KeyValue label="Education">{r.education}</KeyValue><div className="sm:col-span-2"><KeyValue label="Domain experience">{r.domain_experience}</KeyValue></div></Section>
      <Section title="Salary & employment"><KeyValue label="Salary / rate">{fmtSalary(r) === "—" ? null : fmtSalary(r)}</KeyValue><KeyValue label="Employment type">{r.employment_type}</KeyValue><KeyValue label="Notice period">{r.notice_period}</KeyValue></Section>
      <Section title="Location & work mode"><KeyValue label="Location">{r.location}</KeyValue><KeyValue label="Work mode">{r.work_mode === "unknown" ? null : <StatusBadge status={r.work_mode} />}</KeyValue><KeyValue label="Relocation">{r.relocation}</KeyValue><KeyValue label="Travel">{r.travel}</KeyValue></Section>
      <Section title="Recruiter & contacts"><KeyValue label="Recruiter">{r.recruiter_name}</KeyValue><KeyValue label="Recruiter email">{r.recruiter_email && <a className="text-primary hover:underline" href={`mailto:${r.recruiter_email}`}>{r.recruiter_email}</a>}</KeyValue>
        <KeyValue label="Phone">{r.recruiter_phone}</KeyValue><KeyValue label="Submission email">{r.submission_email}</KeyValue><div className="sm:col-span-2"><KeyValue label="Submission instructions">{r.submission_instructions}</KeyValue></div>
        <div className="sm:col-span-2"><KeyValue label="Required documents"><Chips items={r.required_documents} /></KeyValue></div></Section>
      <Card className="lg:col-span-2"><CardHeader><CardTitle>Job description</CardTitle></CardHeader><CardContent>{r.job_description ? <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{r.job_description}</p> : <p className="text-sm text-muted-foreground">No description extracted.</p>}</CardContent></Card>
    </div>
  );
}

function Sources({ id }: { id: string }) {
  const q = useRequirementSources(id);
  if (q.isLoading) return <LoadingRows rows={3} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data?.length) return <EmptyState title="No source emails" description="This requirement was created manually and is not linked to any email yet." />;
  return (
    <div className="space-y-2">
      {q.data.map((s) => (
        <Card key={s.id}><CardContent className="flex flex-wrap items-start justify-between gap-3 p-4">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{s.subject ?? "(manual)"}</p>
            <p className="text-xs text-muted-foreground">{s.sender ?? "—"} → {s.account_email ?? "—"} · {fmtDateTime(s.received_at)}</p>
            <div className="mt-1.5 flex flex-wrap gap-1"><Badge variant="secondary">{titleCase(s.source_type)}</Badge>{typeof s.evidence?.match === "string" && <Badge variant="muted">Matched: {String(s.evidence.match)}</Badge>}</div>
          </div>
          <div className="flex gap-2">
            {s.gmail_url && <Button variant="outline" size="sm" onClick={() => window.open(s.gmail_url!, "_blank", "noopener,noreferrer")}><ExternalLink /> Open in Gmail</Button>}
          </div>
        </CardContent></Card>
      ))}
    </div>
  );
}

function Versions({ id }: { id: string }) {
  const q = useRequirementVersions(id);
  if (q.isLoading) return <LoadingRows rows={3} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return (
    <ol className="space-y-3">
      {q.data?.map((v) => (
        <li key={v.id}><Card><CardContent className="p-4">
          <div className="mb-2 flex flex-wrap items-center gap-2 text-sm"><Badge>v{v.version_number}</Badge><Badge variant="secondary">{titleCase(v.change_source)}</Badge><span className="text-xs text-muted-foreground">{fmtDateTime(v.created_at)}</span></div>
          {Object.keys(v.new_values).length === 0 ? <p className="text-sm text-muted-foreground">No field changes.</p> : (
            <table className="w-full text-sm"><thead className="text-left text-xs text-muted-foreground"><tr><th className="w-1/4 py-1">Field</th><th className="w-[37%] py-1">Before</th><th className="py-1">After</th></tr></thead><tbody>
              {Object.keys(v.new_values).filter((k) => v.version_number > 1 || k !== "review_status").slice(0, 25).map((k) => (
                <tr key={k} className="border-t align-top"><td className="py-1 pr-2">{titleCase(k)}</td><td className="py-1 pr-2 text-muted-foreground break-words">{fmt(v.previous_values[k])}</td><td className="py-1 break-words">{fmt(v.new_values[k])}</td></tr>
              ))}
            </tbody></table>
          )}
        </CardContent></Card></li>
      ))}
    </ol>
  );
}
const fmt = (v: unknown) => (v == null || v === "" ? "—" : Array.isArray(v) ? v.join(", ") || "—" : String(v));

function Similar({ id }: { id: string }) {
  const q = useSimilar(id, true);
  if (q.isLoading) return <LoadingRows rows={3} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data?.length) return <EmptyState title="No similar requirements" description="Nothing in your database resembles this record." />;
  return (
    <div className="space-y-2">
      {q.data.map((s) => (
        <Card key={s.requirement.id}><CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
          <div className="min-w-0"><Link className="font-medium text-primary hover:underline" to={`/requirements/${s.requirement.id}`}>{s.requirement.job_title ?? "(untitled)"}</Link>
            <p className="text-xs text-muted-foreground">{s.requirement.client_name ?? "—"} · {s.requirement.location ?? "—"} · {fmtDate(s.requirement.received_at)}</p>
            <div className="mt-1 flex flex-wrap gap-1">{s.reasons.slice(0, 4).map((x) => <Badge key={x} variant="secondary">{x}</Badge>)}{s.conflicts.slice(0, 3).map((x) => <Badge key={x} variant="warning">differs: {titleCase(x)}</Badge>)}</div></div>
          <Badge variant={s.score >= 0.72 ? "warning" : "muted"}>{pct(s.score)} match</Badge>
        </CardContent></Card>
      ))}
    </div>
  );
}

function History({ id }: { id: string }) {
  const q = useAudit({ entity_type: "requirement", entity_id: id, page_size: 50 });
  if (q.isLoading) return <LoadingRows rows={3} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data?.items.length) return <EmptyState title="No audit entries" />;
  return <ul className="divide-y rounded-lg border bg-card">{q.data.items.map((e) => <li key={e.id} className="flex flex-wrap justify-between gap-2 px-4 py-2.5 text-sm"><span>{titleCase(e.action.replace(".", " "))}</span><span className="text-xs text-muted-foreground">{e.user_email ?? "system"} · {fmtDateTime(e.created_at)}</span></li>)}</ul>;
}

export function RequirementDetailPage() {
  const { id } = useParams();
  const [sp, setSp] = useSearchParams();
  const { can } = useAuth();
  const q = useRequirement(id);
  const [exportOpen, setExportOpen] = useState(false);
  const approve = useRequirementAction("approve");
  const reject = useRequirementAction("reject");
  const archive = useRequirementAction("archive");
  const restore = useRequirementAction("restore");
  const editing = sp.get("edit") === "1";
  const tab = sp.get("tab") ?? "overview";
  const setTab = (t: string) => { const n = new URLSearchParams(sp); n.set("tab", t); setSp(n, { replace: true }); };

  if (q.isLoading) return <LoadingRows />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} title="Requirement could not be loaded" />;
  const r = q.data;
  const w = can("member") && r.lifecycle_status !== "merged";

  return (
    <>
      <PageHeader
        breadcrumb={<><Link to="/requirements" className="hover:underline">Requirements</Link> / {r.job_reference_id ?? r.id.slice(0, 8)}</>}
        title={r.job_title ?? "(untitled requirement)"}
        description={`${r.client_name ?? "Unknown client"}${r.location ? ` · ${r.location}` : ""}`}
        actions={<>
          <Button variant="outline" onClick={() => setExportOpen(true)}><FileSpreadsheet /> Export</Button>
          <Button variant="outline" disabled={!w} onClick={() => setSp(new URLSearchParams({ edit: "1" }))}><Pencil /> Edit</Button>
          {r.review_status !== "approved" && <Button disabled={!w} loading={approve.isPending} onClick={() => approve.mutate(r.id)}><Check /> Approve</Button>}
          {r.review_status !== "rejected" && <Button variant="outline" disabled={!w} loading={reject.isPending} onClick={() => reject.mutate(r.id)}><X /> Reject</Button>}
          {r.lifecycle_status === "archived" ? <Button variant="outline" disabled={!w} loading={restore.isPending} onClick={() => restore.mutate(r.id)}><RotateCcw /> Restore</Button>
            : <Button variant="outline" disabled={!w} loading={archive.isPending} onClick={() => archive.mutate(r.id)}><Archive /> Archive</Button>}
        </>}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
        <StatusBadge status={r.review_status} /><StatusBadge status={r.lifecycle_status} />{r.has_pending_duplicate && <Badge variant="warning">Possible duplicate</Badge>}
        <span className="text-muted-foreground">Received {fmtDate(r.received_at)} · Updated {fmtDateTime(r.last_updated_at)} · v{r.version_number}</span>
      </div>
      {r.lifecycle_status === "merged" && r.merged_into_id && (
        <div role="status" className="mb-4 rounded-md border bg-muted px-4 py-3 text-sm">This requirement was merged into another record. <Link className="font-medium text-primary hover:underline" to={`/requirements/${r.merged_into_id}`}>Open the surviving requirement</Link>.</div>
      )}
      {r.validation_warnings.length > 0 && (
        <div role="alert" className="mb-4 space-y-1 rounded-md border border-warning/40 bg-warning/10 px-4 py-3 text-sm">
          <p className="flex items-center gap-2 font-medium"><AlertTriangle className="size-4 text-warning" /> Needs verification</p>
          <ul className="list-disc space-y-0.5 pl-6">{r.validation_warnings.map((x) => <li key={x}>{warningText(x)}</li>)}</ul>
        </div>
      )}
      {editing ? (
        <Card><CardContent className="p-5"><RequirementForm mode="edit" requirement={r} onDone={() => setSp(new URLSearchParams(), { replace: true })} onCancel={() => setSp(new URLSearchParams(), { replace: true })} /></CardContent></Card>
      ) : (
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger><TabsTrigger value="sources">Source emails ({r.source_count})</TabsTrigger><TabsTrigger value="extraction">Extraction</TabsTrigger>
            <TabsTrigger value="candidates">Candidates</TabsTrigger><TabsTrigger value="similar">Duplicates & similar</TabsTrigger><TabsTrigger value="versions">Versions</TabsTrigger><TabsTrigger value="audit">Audit history</TabsTrigger>
          </TabsList>
          <TabsContent value="overview"><Overview r={r} /></TabsContent>
          <TabsContent value="sources"><Sources id={r.id} /></TabsContent>
          <TabsContent value="extraction">
            <Section title="Extraction metadata"><KeyValue label="Model">{r.extraction_model ?? "Manual entry"}</KeyValue><KeyValue label="Confidence">{pct(r.extraction_confidence)}</KeyValue>
              <KeyValue label="Created">{fmtDateTime(r.created_at)}</KeyValue><KeyValue label="Last changed">{fmtDateTime(r.updated_at)}</KeyValue>
              <div className="sm:col-span-2"><KeyValue label="Validation warnings">{r.validation_warnings.length ? <ul className="list-disc pl-5">{r.validation_warnings.map((x) => <li key={x}>{warningText(x)}</li>)}</ul> : null}</KeyValue></div></Section>
          </TabsContent>
          <TabsContent value="candidates"><RequirementCandidates requirementId={r.id} /></TabsContent>
          <TabsContent value="similar">{r.has_pending_duplicate && <p className="mb-3 text-sm">This record has a pending duplicate review. <Link className="font-medium text-primary hover:underline" to="/duplicates">Open Duplicate Review</Link></p>}<Similar id={r.id} /></TabsContent>
          <TabsContent value="versions"><Versions id={r.id} /></TabsContent>
          <TabsContent value="audit"><History id={r.id} /></TabsContent>
        </Tabs>
      )}
      {exportOpen && <ExportDialog open onOpenChange={setExportOpen} selectedIds={[r.id]} filters={{}} defaultScope="selected" />}
    </>
  );
}
