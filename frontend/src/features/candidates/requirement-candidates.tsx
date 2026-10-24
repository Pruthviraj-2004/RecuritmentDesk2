import { Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "@/app/auth";
import { EmptyState, ErrorState, LoadingRows, StatusBadge } from "@/components/common/common";
import { SkillChips } from "@/components/common/skill-chips";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select } from "@/components/ui/form";
import { ScoreBar } from "@/features/candidates/candidate-detail-page";
import { api } from "@/lib/api";
import { fmtRelative, titleCase } from "@/lib/utils";
import { candidateKeys, useAction, useRequirementMatches, useRequirementSubmissions } from "@/services/hooks";
import { PIPELINE_STAGES, type PipelineStage, type Submission } from "@/types/api";

/** "Candidates" tab of a requirement: who is already in its pipeline, and who else matches it (skills, experience, location). */
export function RequirementCandidates({ requirementId }: { requirementId: string }) {
  const { can } = useAuth();
  const writable = can("member");
  const subs = useRequirementSubmissions(requirementId);
  const matches = useRequirementMatches(requirementId);
  const keys = [...candidateKeys, ["requirement", requirementId, "submissions"], ["requirement", requirementId, "matching-candidates"]];
  const stage = useAction<{ id: string; stage: PipelineStage }, Submission>({ fn: (v) => api.patch(`/candidates/submissions/${v.id}`, { stage: v.stage }), invalidate: keys, success: "Stage updated" });
  const add = useAction<string, Submission>({ fn: (cid) => api.post(`/candidates/${cid}/submissions`, { requirement_id: requirementId, stage: "shortlisted" }), invalidate: keys, success: "Added to pipeline as shortlisted" });

  return (
    <div className="space-y-6">
      <section>
        <h3 className="mb-2 text-sm font-semibold">Pipeline</h3>
        {subs.isLoading ? <LoadingRows rows={2} /> : subs.error ? <ErrorState error={subs.error} onRetry={() => subs.refetch()} /> : !subs.data?.length ? <EmptyState title="No candidates in this pipeline yet" description="Add a suggested candidate below." /> : (
          <ul className="space-y-2">{subs.data.map((s) => (
            <li key={s.id}><Card><CardContent className="flex flex-wrap items-center justify-between gap-3 p-3">
              <div className="min-w-0"><Link to={`/candidates/${s.candidate_id}`} className="font-medium text-primary hover:underline">{s.candidate_name}</Link><p className="text-xs text-muted-foreground">{s.candidate_title ?? "—"} · updated {fmtRelative(s.updated_at)}</p></div>
              <Select aria-label={`Stage for ${s.candidate_name}`} className="h-8 w-40" value={s.stage} disabled={!writable} onChange={(e) => stage.mutate({ id: s.id, stage: e.target.value as PipelineStage })}>{PIPELINE_STAGES.map((st) => <option key={st} value={st}>{titleCase(st)}</option>)}</Select>
            </CardContent></Card></li>))}</ul>
        )}
      </section>
      <section>
        <h3 className="mb-1 text-sm font-semibold">Suggested candidates</h3>
        <p className="mb-2 text-xs text-muted-foreground">Ranked by required skills, experience, location and role title, using the saved profile combined with the latest AI profile (no need to apply it first). Rejected, hired and archived candidates are left out.</p>
        {matches.isLoading ? <LoadingRows rows={3} /> : matches.error ? <ErrorState error={matches.error} onRetry={() => matches.refetch()} /> : !matches.data?.length ? (
          <EmptyState title="No matching candidates" description="Add candidates with skills and experience, or import a file, and the best matches will show here." action={<Link className="text-sm font-medium text-primary hover:underline" to="/candidates">Open Candidate Profiles</Link>} />
        ) : (
          <ul className="space-y-2">{matches.data.map((m) => (
            <li key={m.candidate.id}><Card><CardContent className="space-y-2 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0"><Link to={`/candidates/${m.candidate.id}`} className="font-medium text-primary hover:underline">{m.candidate.full_name}</Link>
                  <p className="text-xs text-muted-foreground">{m.candidate.current_title ?? "—"}{m.candidate.total_experience != null ? ` · ${m.candidate.total_experience} yrs` : ""}{m.candidate.current_location ? ` · ${m.candidate.current_location}` : ""}</p></div>
                <div className="flex items-center gap-2"><ScoreBar score={m.score} />{m.stage ? <StatusBadge status={m.stage} /> : <Button size="sm" variant="outline" disabled={!writable} loading={add.isPending && add.variables === m.candidate.id} onClick={() => add.mutate(m.candidate.id)}><Plus /> Add to pipeline</Button>}</div>
              </div>
              <SkillChips skills={m.matched_skills} limit={8} width={520} />
              <ul className="flex flex-wrap gap-1.5 text-xs">{m.reasons.map((r) => <li key={r} className="rounded bg-muted px-2 py-0.5">{r}</li>)}</ul>
              {m.ai_profile_used && <p className="text-xs text-primary">Includes the AI profile{(m.ai_only_matches?.length ?? 0) > 0 ? `: ${m.ai_only_matches!.join(", ")} found only there` : ""}</p>}
              {m.missing_skills.length > 0 && <p className="text-xs text-muted-foreground">Missing: {m.missing_skills.join(", ")}</p>}
            </CardContent></Card></li>))}</ul>
        )}
      </section>
    </div>
  );
}
