import { format, parseISO, subDays } from "date-fns";
import { AlertTriangle, CheckCircle2, Clock, Copy, Inbox, Mail, Plus, RefreshCw, Send, Users, XCircle } from "lucide-react";
import { useMemo, useState, type ComponentType } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/app/auth";
import { BarList, ChartCard, StackedStatus, TimeSeries } from "@/components/charts/charts";
import { EmptyState, ErrorState, PageHeader } from "@/components/common/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, Skeleton } from "@/components/ui/card";
import { Select } from "@/components/ui/form";
import { useConnectGmail, useSyncAll } from "@/hooks/use-gmail";
import { fmtRelative, titleCase } from "@/lib/utils";
import { useAccounts, useAudit, useOverview } from "@/services/hooks";
import type { Overview } from "@/types/api";

function Kpi({ label, value, icon: Icon, to, hint, loading, tone }: { label: string; value: string | number; icon: ComponentType<{ className?: string }>; to?: string; hint?: string; loading?: boolean; tone?: "warn" | "bad" }) {
  const body = (
    <Card className="h-full hover:-translate-y-0.5 hover:border-primary/40">
      <CardContent className="flex items-start justify-between gap-2 p-4">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          {loading ? <Skeleton className="mt-2 h-7 w-16" /> : <p className="tabular mt-1 truncate text-2xl font-semibold" data-testid={`kpi-${label}`}>{value}</p>}
          {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
        </div>
        <span className={`rounded-md p-2 ${tone === "bad" ? "bg-destructive/10 text-destructive" : tone === "warn" ? "bg-warning/15 text-warning" : "bg-accent text-accent-foreground"}`}><Icon className="size-4" /></span>
      </CardContent>
    </Card>
  );
  return to ? <Link to={to} aria-label={`${label}: ${value}`} className="block">{body}</Link> : body;
}

const ACTION_LABEL: Record<string, string> = {
  "account.connected": "Gmail account connected", "sync.completed": "Synchronization completed", "sync.failed": "Synchronization failed", "sync.started": "Synchronization started",
  "requirement.extracted": "New requirement extracted", "duplicate.detected": "Duplicate detected", "duplicate.attached": "Duplicate source attached", "duplicate.merged": "Duplicates merged",
  "requirement.edited": "Requirement edited", "requirement.approved": "Requirement approved", "requirement.rejected": "Requirement rejected", "requirement.created": "Requirement created",
  "export.generated": "Excel file generated", "delivery.accepted": "Email accepted by Gmail", "delivery.failed": "Email delivery failed", "delivery.requested": "Email send requested",
  "job.retried": "Job retried", "auth.login": "Signed in", "auth.logout": "Signed out", "auth.login_failed": "Failed sign-in attempt", "account.connect_started": "Gmail connection started", "export.requested": "Export requested", "settings.updated": "Settings updated", "account.disconnected": "Gmail account disconnected",
};

function RecentActivity() {
  const q = useAudit({ page_size: 10 });
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0"><CardTitle>Recent activity</CardTitle><Link to="/audit" className="text-xs text-primary hover:underline">View all</Link></CardHeader>
      <CardContent>
        {q.isLoading ? <Skeleton className="h-40 w-full" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data?.items.length ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No activity yet. Connect a Gmail account and run a sync to get started.</p>
        ) : (
          <ol className="space-y-3">
            {q.data.items.map((e) => (
              <li key={e.id} className="flex items-start gap-3 text-sm">
                <span className="mt-1.5 size-2 shrink-0 rounded-full bg-primary" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate">{ACTION_LABEL[e.action] ?? titleCase(e.action.replace(".", " "))}{typeof e.metadata.title === "string" ? `: ${e.metadata.title}` : typeof e.metadata.account === "string" ? ` (${e.metadata.account})` : ""}</p>
                  <p className="text-xs text-muted-foreground">{fmtRelative(e.created_at)}{e.user_email ? ` · ${e.user_email}` : " · system"}</p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

export function OverviewPage() {
  const [days, setDays] = useState(30);
  const range = useMemo(() => ({ date_from: subDays(new Date(), days).toISOString(), date_to: new Date().toISOString() }), [days]);
  const { data, isLoading, error, refetch } = useOverview(range);
  const accounts = useAccounts();
  const { can } = useAuth();
  const sync = useSyncAll();
  const connect = useConnectGmail();
  const k = data?.kpis;

  const series = useMemo(() => (data?.received_over_time ?? []).map((p) => ({ label: format(parseISO(p.date), "d MMM"), count: p.count })), [data]);
  const noAccounts = accounts.data && accounts.data.length === 0;

  if (error && !data) return <><PageHeader title="Overview" /><ErrorState error={error} onRetry={() => refetch()} /></>;
  return (
    <>
      <PageHeader
        title="Overview"
        description="Live metrics from your synchronized recruitment emails."
        actions={<>
          <Select aria-label="Date range" className="w-40" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option><option value={365}>Last 12 months</option>
          </Select>
          <Button variant="outline" disabled={!can("member")} loading={sync.isPending} onClick={() => sync.mutate()}><RefreshCw /> Sync all</Button>
          <Button disabled={!can("admin")} loading={connect.isPending} onClick={() => connect.mutate()}><Plus /> Connect Gmail</Button>
        </>}
      />
      {noAccounts && (
        <div className="mb-5"><EmptyState icon={Mail} title="Connect your first Gmail account" description="RecruitmentDesk reads recruitment emails from your Gmail accounts, extracts job requirements with AI and removes duplicates across accounts."
          action={can("admin") ? <Button onClick={() => connect.mutate()} loading={connect.isPending}><Plus /> Connect Gmail</Button> : undefined} /></div>
      )}
      <section aria-label="Key metrics" className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
        <Kpi loading={isLoading} label="Unique requirements" value={k?.total_unique_requirements ?? 0} icon={Users} to="/requirements" hint="Excludes archived & merged" />
        <Kpi loading={isLoading} label="Awaiting review" value={k?.awaiting_review ?? 0} icon={Clock} to="/requirements?review_status=needs_review" tone={k && k.awaiting_review > 0 ? "warn" : undefined} />
        <Kpi loading={isLoading} label="Approved" value={k?.approved ?? 0} icon={CheckCircle2} to="/requirements?review_status=approved" />
        <Kpi loading={isLoading} label="Received today" value={k?.received_today ?? 0} icon={Inbox} to="/requirements" hint="By email received date (UTC)" />
        <Kpi loading={isLoading} label="Received this week" value={k?.received_this_week ?? 0} icon={Inbox} to="/requirements" hint="Since Monday (UTC)" />
        <Kpi loading={isLoading} label="Duplicates to review" value={k?.duplicates_pending ?? 0} icon={Copy} to="/duplicates" tone={k && k.duplicates_pending > 0 ? "warn" : undefined} />
        <Kpi loading={isLoading} label="Emails processed" value={k?.emails_processed ?? 0} icon={CheckCircle2} to="/sync-jobs" />
        <Kpi loading={isLoading} label="Failed / pending extraction" value={k?.extraction_failed_or_pending ?? 0} icon={AlertTriangle} to="/sync-jobs" tone={k && k.extraction_failed_or_pending > 0 ? "bad" : undefined} />
        <Kpi loading={isLoading} label="Connected accounts" value={k?.connected_accounts ?? 0} icon={Mail} to="/accounts" hint={k?.accounts_needing_attention ? `${k.accounts_needing_attention} need attention` : undefined} tone={k?.accounts_needing_attention ? "bad" : undefined} />
        <Kpi loading={isLoading} label="Last successful sync" value={k?.last_successful_sync ? fmtRelative(k.last_successful_sync) : "Never"} icon={RefreshCw} to="/sync-jobs" />
        <Kpi loading={isLoading} label="Pending deliveries" value={k?.pending_deliveries ?? 0} icon={Send} to="/exports" hint="Queued, sending or uncertain" />
        <Kpi loading={isLoading} label="Candidates" value={k?.candidates ?? 0} icon={Users} to="/candidates" hint="Talent database (not archived)" />
      </section>

      <section aria-label="Charts" className="mt-5 grid gap-4 lg:grid-cols-3">
        <ChartCard className="lg:col-span-2" title="Requirements received over time" description={`Daily, last ${days} days`} loading={isLoading} empty={!series.some((s) => s.count > 0)} emptyHint="Appears after emails are processed." rows={series.filter((s) => s.count).map((s) => ({ name: s.label, count: s.count }))}>
          <TimeSeries data={series} />
        </ChartCard>
        <RecentActivity />
        <ChartCard title="Requirements by status" loading={isLoading} empty={!data?.by_status.length} rows={data?.by_status.map((s) => ({ ...s, name: titleCase(s.name) }))}>
          <BarList rows={(data?.by_status ?? []).map((s) => ({ ...s, name: titleCase(s.name) }))} />
        </ChartCard>
        <ChartCard title="Requirements by location" description="Top 10" loading={isLoading} empty={!data?.by_location.length} rows={data?.by_location}><BarList rows={data?.by_location ?? []} max={10} /></ChartCard>
        <ChartCard title="Most requested skills" description="Required skills" loading={isLoading} empty={!data?.top_skills.length} rows={data?.top_skills}><BarList rows={data?.top_skills ?? []} max={10} unit="requirements" /></ChartCard>
        <ChartCard title="Requirements by client" description="Top 10" loading={isLoading} empty={!data?.by_client.length} emptyHint="Client names appear when extracted from emails." rows={data?.by_client}><BarList rows={data?.by_client ?? []} max={10} /></ChartCard>
        <ChartCard title="Source account distribution" loading={isLoading} empty={!data?.by_source_account.length} rows={data?.by_source_account}><BarList rows={data?.by_source_account ?? []} /></ChartCard>
        <ProcessingCard data={data} loading={isLoading} />
        <ChartCard title="Weekly & monthly activity" loading={isLoading} empty={!data?.weekly_activity.length}
          rows={[...(data?.weekly_activity ?? []).map((w) => ({ name: `Week of ${w.week}`, count: w.count })), ...(data?.monthly_activity ?? []).map((m) => ({ name: m.month, count: m.count }))]}>
          <div className="grid gap-4 sm:grid-cols-2">
            <div><p className="mb-1 text-xs text-muted-foreground">Weekly</p><BarList rows={(data?.weekly_activity ?? []).slice(-6).map((w) => ({ name: format(parseISO(w.week), "d MMM"), count: w.count }))} max={6} /></div>
            <div><p className="mb-1 text-xs text-muted-foreground">Monthly</p><BarList rows={(data?.monthly_activity ?? []).slice(-6).map((m) => ({ name: m.month, count: m.count }))} max={6} /></div>
          </div>
        </ChartCard>
      </section>
    </>
  );
}

function ProcessingCard({ data, loading }: { data?: Overview; loading: boolean }) {
  const p = data?.email_processing;
  const total = (p?.succeeded ?? 0) + (p?.failed ?? 0) + (p?.pending ?? 0);
  return (
    <ChartCard title="Email processing" description="Success vs failure in range" loading={loading} empty={total === 0} rows={p ? [{ name: "Succeeded", count: p.succeeded }, { name: "Failed", count: p.failed }, { name: "Pending", count: p.pending }] : []}>
      <StackedStatus parts={[{ name: "Succeeded", value: p?.succeeded ?? 0, color: "hsl(var(--success))" }, { name: "Failed", value: p?.failed ?? 0, color: "hsl(var(--destructive))" }, { name: "Pending", value: p?.pending ?? 0, color: "hsl(var(--muted-foreground))" }]} />
      {(p?.failed ?? 0) > 0 && <p className="mt-3 flex items-center gap-1.5 text-xs text-destructive"><XCircle className="size-3.5" /> Failures are retryable from <Link className="underline" to="/sync-jobs">Synchronization Jobs</Link>.</p>}
    </ChartCard>
  );
}
