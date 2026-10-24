import { subDays } from "date-fns";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { BarList, ChartCard } from "@/components/charts/charts";
import { ErrorState, PageHeader } from "@/components/common/common";
import { Card, CardContent, Skeleton } from "@/components/ui/card";
import { Select } from "@/components/ui/form";
import { pct } from "@/lib/utils";
import { useRecruitmentAnalytics } from "@/services/hooks";

function Metric({ label, value, note, loading }: { label: string; value: string; note: string; loading: boolean }) {
  return <Card><CardContent className="p-4"><p className="text-xs text-muted-foreground">{label}</p>{loading ? <Skeleton className="mt-2 h-7 w-20" /> : <p className="tabular mt-1 text-2xl font-semibold">{value}</p>}<p className="mt-0.5 text-xs text-muted-foreground">{note}</p></CardContent></Card>;
}

export function AnalyticsPage() {
  const [days, setDays] = useState(90);
  const nav = useNavigate();
  const range = useMemo(() => ({ date_from: subDays(new Date(), days).toISOString(), date_to: new Date().toISOString() }), [days]);
  const { data, isLoading, error, refetch } = useRecruitmentAnalytics(range);
  const drill = (key: string) => (name: string) => nav(`/requirements?${key}=${encodeURIComponent(name)}&date_from=${encodeURIComponent(range.date_from)}`);
  if (error && !data) return <><PageHeader title="Analytics" /><ErrorState error={error} onRetry={() => refetch()} /></>;
  const d = data;
  return (
    <>
      <PageHeader title="Analytics" description="Recruitment activity and pipeline quality. Metrics with no underlying data show “—” rather than an invented value."
        actions={<Select aria-label="Date range" className="w-44" value={days} onChange={(e) => setDays(Number(e.target.value))}><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option><option value={180}>Last 6 months</option><option value={365}>Last 12 months</option></Select>} />
      <section className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Quality metrics">
        <Metric loading={isLoading} label="Requirements in range" value={String(d?.total_requirements ?? 0)} note="Unique, excluding merged" />
        <Metric loading={isLoading} label="Duplicate rate" value={pct(d?.duplicate_rate.value)} note={d ? `${d.duplicate_rate.duplicate_candidates} candidates · ${d.duplicate_rate.cross_account_copies} cross-account copies` : ""} />
        <Metric loading={isLoading} label="Extraction success rate" value={pct(d?.extraction_success_rate.value)} note={d ? `${d.extraction_success_rate.runs} AI runs` : ""} />
        <Metric loading={isLoading} label="Manual correction rate" value={pct(d?.manual_correction_rate.value)} note={d ? `${d.manual_correction_rate.corrected} of ${d.manual_correction_rate.extracted} AI-extracted edited` : ""} />
        <Metric loading={isLoading} label="Avg. job duration" value={d?.average_job_duration_seconds != null ? `${d.average_job_duration_seconds}s` : "—"} note="Completed sync/export jobs" />
      </section>
      <section className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="By client" description="Click a client in Requirements to drill down" loading={isLoading} empty={!d?.by_client.length} rows={d?.by_client}><BarList rows={d?.by_client ?? []} max={10} /></ChartCard>
        <ChartCard title="By skill" description="Required skills" loading={isLoading} empty={!d?.by_skill.length} rows={d?.by_skill}><BarList rows={d?.by_skill ?? []} max={10} /></ChartCard>
        <ChartCard title="By location" loading={isLoading} empty={!d?.by_location.length} rows={d?.by_location}><BarList rows={d?.by_location ?? []} max={10} /></ChartCard>
        <ChartCard title="By experience range" description="Minimum years required" loading={isLoading} empty={!d?.by_experience.length} rows={d?.by_experience}><BarList rows={d?.by_experience ?? []} /></ChartCard>
        <ChartCard title="By work mode" loading={isLoading} empty={!d?.by_work_mode.length} emptyHint="Work mode is only counted when stated in the email." rows={d?.by_work_mode}><BarList rows={d?.by_work_mode ?? []} /></ChartCard>
        <ChartCard title="Connected account activity" description="Emails received per account" loading={isLoading} empty={!d?.account_activity.length} rows={d?.account_activity}><BarList rows={d?.account_activity ?? []} unit="emails" /></ChartCard>
        <ChartCard title="Failed jobs by category" loading={isLoading} empty={!d?.failed_jobs_by_type.length} emptyHint="No failed jobs in this period." rows={d?.failed_jobs_by_type}><BarList rows={d?.failed_jobs_by_type ?? []} unit="jobs" /></ChartCard>
      </section>
      <p className="mt-4 text-xs text-muted-foreground">Drill-down: <button className="text-primary hover:underline" onClick={() => drill("client")(d?.by_client[0]?.name ?? "")} disabled={!d?.by_client.length}>open top client in Requirements</button></p>
    </>
  );
}
