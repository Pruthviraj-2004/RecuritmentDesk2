import { CheckCircle2, ShieldCheck, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useAuth } from "@/app/auth";
import { ErrorState, LoadingRows, PageHeader, StatusBadge } from "@/components/common/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Field, Input, Select } from "@/components/ui/form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SchedulesSection } from "@/features/settings/schedules";
import { useTheme } from "@/hooks/use-theme";
import { api } from "@/lib/api";
import { fmtDateTime, titleCase } from "@/lib/utils";
import { useAccounts, useAction, useAiStatus, useHealth, useSettings } from "@/services/hooks";
import type { Role } from "@/types/api";

type S = Record<string, string | number | boolean | string[]>;

/** Generic settings section editor: one form per backend section, validated server-side. */
function SectionForm({ section, title, description, fields }: { section: string; title: string; description: string; fields: { key: string; label: string; type: "text" | "number" | "bool" | "select"; options?: string[]; step?: number; hint?: string }[] }) {
  const { can } = useAuth();
  const q = useSettings<S>(section);
  const { register, handleSubmit, reset, formState: { isDirty } } = useForm<S>();
  useEffect(() => { if (q.data) reset(q.data); }, [q.data, reset]);
  const save = useAction<S, S>({ fn: (v) => api.put(`/settings/${section}`, { values: v }), invalidate: [["settings", section], ["audit"]], success: "Settings saved" });
  if (q.isLoading) return <LoadingRows rows={4} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const submit = handleSubmit((raw) => {
    const out: S = {};
    fields.forEach((f) => { const v = raw[f.key]; out[f.key] = f.type === "number" ? Number(v) : f.type === "bool" ? Boolean(v) : (v as string); });
    save.mutate(out);
  });
  return (
    <Card><CardHeader><CardTitle>{title}</CardTitle><CardDescription>{description}</CardDescription></CardHeader><CardContent>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2" noValidate>
        {fields.map((f) => f.type === "bool" ? (
          <label key={f.key} className="flex items-center gap-2 text-sm sm:col-span-2"><Checkbox disabled={!can("admin")} {...register(f.key)} /> {f.label}</label>
        ) : (
          <Field key={f.key} label={f.label} htmlFor={`${section}-${f.key}`} hint={f.hint}>
            {f.type === "select" ? <Select id={`${section}-${f.key}`} disabled={!can("admin")} {...register(f.key)}>{f.options!.map((o) => <option key={o} value={o}>{titleCase(o)}</option>)}</Select>
              : <Input id={`${section}-${f.key}`} type={f.type} step={f.step} disabled={!can("admin")} {...register(f.key)} />}
          </Field>
        ))}
        <div className="sm:col-span-2"><Button type="submit" disabled={!can("admin") || !isDirty} loading={save.isPending}>Save changes</Button>{!can("admin") && <span className="ml-3 text-xs text-muted-foreground">Administrators only</span>}</div>
      </form>
    </CardContent></Card>
  );
}

function AiSection() {
  const [check, setCheck] = useState(false);
  const q = useAiStatus(check);
  const ai = q.data;
  return (
    <div className="space-y-4">
      <Card><CardHeader><CardTitle>AI provider</CardTitle><CardDescription>Provider, model and API key are read from server environment variables and are never sent to the browser.</CardDescription></CardHeader><CardContent>
        {q.isLoading ? <LoadingRows rows={2} /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
          <div className="space-y-3 text-sm">
            <dl className="grid gap-3 sm:grid-cols-3"><div><dt className="text-xs text-muted-foreground">Provider</dt><dd>{ai?.provider === "none" ? "Not configured" : titleCase(ai?.provider ?? "")}</dd></div>
              <div><dt className="text-xs text-muted-foreground">Model</dt><dd>{ai?.model ?? "—"}</dd></div><div><dt className="text-xs text-muted-foreground">Endpoint host</dt><dd>{ai?.base_url_host ?? "—"}</dd></div></dl>
            <div className="flex flex-wrap items-center gap-2">
              {ai?.configured ? <Badge variant="success"><CheckCircle2 className="size-3" /> Configured</Badge> : <Badge variant="warning">Not configured</Badge>}
              {ai?.health && (ai.health.status === "ok" ? <Badge variant="success">Live check passed</Badge> : <Badge variant="destructive"><XCircle className="size-3" /> {ai.health.detail ?? "Check failed"}</Badge>)}
              <Button size="sm" variant="outline" disabled={!ai?.configured} loading={q.isFetching && check} onClick={() => { if (check) q.refetch(); else setCheck(true); }}>Run live health check</Button>
            </div>
            {ai?.message && <p className="rounded-md border bg-muted/50 p-3 text-muted-foreground">{ai.message} Set <code>AI_PROVIDER</code>, <code>AI_API_KEY</code>, <code>AI_BASE_URL</code> and <code>AI_MODEL</code> on the server (see docs/AI_SETUP.md).</p>}
          </div>)}
      </CardContent></Card>
      <SectionForm section="ai" title="Review threshold" description="Records whose computed confidence is below this value are flagged “low confidence” for careful review."
        fields={[{ key: "review_confidence_threshold", label: "Low-confidence threshold (0–1)", type: "number", step: 0.05 }]} />
      <p className="text-xs text-muted-foreground">Timeout, retry count and prompt version are server settings (<code>AI_TIMEOUT_SECONDS</code>, <code>AI_MAX_RETRIES</code>; prompt version <code>v1</code>) so they cannot be changed from the browser.</p>
    </div>
  );
}

function HealthSection() {
  const q = useHealth();
  if (q.isLoading) return <LoadingRows rows={4} />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const rows: [string, { status: string; detail?: string | null }][] = [["API", { status: "ok" }], ["Database", q.data.database], ["Redis", q.data.redis], ["Background worker", q.data.worker], ["AI provider", { status: q.data.ai.status, detail: q.data.ai.provider }], ["Gmail integration (Google OAuth)", q.data.gmail]];
  return (
    <Card><CardHeader><CardTitle>System health</CardTitle><CardDescription>Application version {q.data.version}. No secrets or infrastructure details are exposed here.</CardDescription></CardHeader><CardContent>
      <ul className="divide-y">{rows.map(([name, s]) => (
        <li key={name} className="flex items-center justify-between gap-3 py-2.5 text-sm"><span>{name}</span><span className="flex items-center gap-2">{s.detail && <span className="text-xs text-muted-foreground">{s.detail}</span>}
          <Badge variant={s.status === "ok" ? "success" : s.status === "not_configured" ? "muted" : "destructive"}>{s.status === "ok" ? "Healthy" : titleCase(s.status)}</Badge></span></li>))}</ul>
    </CardContent></Card>
  );
}

function SecuritySection() {
  const { me } = useAuth();
  const sessions = useSessions();
  const [cur, setCur] = useState(""); const [nw, setNw] = useState("");
  const change = useAction<void, void>({ fn: () => api.post("/auth/change-password", { current_password: cur, new_password: nw }), success: "Password changed; other sessions were signed out", onDone: () => { setCur(""); setNw(""); sessions.refetch(); } });
  const revoke = useAction<string, void>({ fn: (id) => api.post(`/auth/sessions/${id}/revoke`), success: "Session revoked", onDone: () => sessions.refetch() });
  const accounts = useAccounts();
  return (
    <div className="space-y-4">
      <Card><CardHeader><CardTitle>Your account</CardTitle><CardDescription>{me?.user.email} · role <strong className="capitalize">{me?.role as Role}</strong></CardDescription></CardHeader><CardContent>
        <form onSubmit={(e) => { e.preventDefault(); change.mutate(); }} className="grid max-w-xl gap-3 sm:grid-cols-2">
          <Field label="Current password" htmlFor="cp"><Input id="cp" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} /></Field>
          <Field label="New password" htmlFor="np" hint="At least 8 characters, mixed case and a digit"><Input id="np" type="password" autoComplete="new-password" value={nw} onChange={(e) => setNw(e.target.value)} /></Field>
          <div className="sm:col-span-2"><Button type="submit" disabled={!cur || nw.length < 8} loading={change.isPending}>Change password</Button></div>
        </form></CardContent></Card>
      <Card><CardHeader><CardTitle>Active sessions</CardTitle></CardHeader><CardContent>
        {sessions.data?.length ? <ul className="divide-y">{sessions.data.map((s) => (
          <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm"><div className="min-w-0"><p className="truncate">{s.user_agent ?? "Unknown device"}{s.current && <Badge className="ml-2">This session</Badge>}</p><p className="text-xs text-muted-foreground">{s.ip_address} · signed in {fmtDateTime(s.created_at)} · last active {fmtDateTime(s.last_seen_at)}</p></div>
            {!s.current && <Button size="sm" variant="outline" loading={revoke.isPending && revoke.variables === s.id} onClick={() => revoke.mutate(s.id)}>Revoke</Button>}</li>))}</ul> : <p className="text-sm text-muted-foreground">Loading…</p>}
      </CardContent></Card>
      <Card><CardHeader><CardTitle>Connected Google access</CardTitle><CardDescription>Disconnect accounts from the Connected Accounts page; credentials are encrypted at rest and never reach the browser.</CardDescription></CardHeader><CardContent>
        <ul className="space-y-1 text-sm">{accounts.data?.map((a) => <li key={a.id} className="flex items-center gap-2"><ShieldCheck className="size-4 text-success" />{a.masked_email} <StatusBadge status={a.connection_status} /></li>)}</ul></CardContent></Card>
      <Card><CardHeader><CardTitle>Retention</CardTitle><CardDescription>Controlled by server configuration so it cannot be weakened from the browser.</CardDescription></CardHeader><CardContent className="space-y-1 text-sm text-muted-foreground">
        <p>Email bodies are purged after <code>EMAIL_BODY_RETENTION_DAYS</code> (default 90) and unrelated mail right after classification; re-fetched from Gmail only when reprocessing.</p>
        <p>Export files expire after <code>EXPORT_RETENTION_DAYS</code> (default 14). Sessions last <code>SESSION_TTL_HOURS</code> (default 12). Audit logs and requirement history are kept.</p></CardContent></Card>
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import type { Page } from "@/types/api";
function useSessions() {
  return useQuery({ queryKey: ["sessions"], queryFn: () => api.get<{ id: string; created_at: string; last_seen_at: string | null; user_agent: string | null; ip_address: string | null; current: boolean }[]>("/auth/sessions") });
}
void ({} as Page<unknown>);

function GeneralSection() {
  const { theme, setTheme } = useTheme();
  return (
    <div className="space-y-4">
      <Card><CardHeader><CardTitle>Appearance</CardTitle><CardDescription>Stored on this device only.</CardDescription></CardHeader><CardContent>
        <Field label="Theme" htmlFor="theme"><Select id="theme" className="max-w-xs" value={theme} onChange={(e) => setTheme(e.target.value as "light" | "dark" | "system")}><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></Select></Field></CardContent></Card>
      <SectionForm section="general" title="Workspace" description="Defaults used across the application and exports."
        fields={[{ key: "display_name", label: "Application display name", type: "text" }, { key: "timezone", label: "Default timezone", type: "text", hint: "Stored preference (IANA name); dates currently display in your browser locale" }, { key: "date_format", label: "Date format", type: "text" }, { key: "export_filename_format", label: "Default export filename", type: "text", hint: "{date} is replaced with today's date" }]} />
    </div>
  );
}

export function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="Workspace configuration. Secrets live in server environment variables, never here." />
      <Tabs defaultValue="general">
        <TabsList><TabsTrigger value="general">General</TabsTrigger><TabsTrigger value="gmail">Gmail</TabsTrigger><TabsTrigger value="ai">AI extraction</TabsTrigger><TabsTrigger value="dedup">Deduplication</TabsTrigger>
          <TabsTrigger value="digest">Scheduled email</TabsTrigger><TabsTrigger value="notifications">Notifications</TabsTrigger><TabsTrigger value="security">Security</TabsTrigger><TabsTrigger value="health">System health</TabsTrigger></TabsList>
        <TabsContent value="general"><GeneralSection /></TabsContent>
        <TabsContent value="gmail"><p className="mb-3 text-sm text-muted-foreground">Sync frequency is set by <code>SYNC_INTERVAL_MINUTES</code> on the server; the import window and Gmail search terms are set per account on the Connected Accounts page.</p><SectionForm section="gmail" title="Gmail synchronization" description="Defaults for automatic synchronization and attachment handling."
          fields={[{ key: "only_recruitment_emails", label: "Only keep recruitment emails (searches Gmail for hiring-related mail and never stores clearly unrelated mail)", type: "bool" }, { key: "process_attachments", label: "Read text from PDF, DOCX and TXT attachments", type: "bool" }, { key: "retain_attachment_files", label: "Keep original attachment files (default: only extracted text is kept)", type: "bool" }]} /></TabsContent>
        <TabsContent value="ai"><AiSection /></TabsContent>
        <TabsContent value="dedup"><SectionForm section="dedup" title="Duplicate detection" description="Changing thresholds only affects future emails. Existing records are never re-merged silently."
          fields={[{ key: "auto_attach_exact", label: "Automatically attach exact duplicates (same client + job ID, or identical fingerprint)", type: "bool" }, { key: "require_client_for_auto_attach", label: "Require a matching client for automatic attachment", type: "bool" },
            { key: "create_related_links", label: "Record relationships between related (non-duplicate) requirements", type: "bool" }, { key: "probable_threshold", label: "Probable-duplicate threshold (0.3–0.99)", type: "number", step: 0.01, hint: "At or above this, a human review item is created" },
            { key: "related_threshold", label: "Related-requirement threshold", type: "number", step: 0.01 }, { key: "time_window_days", label: "Time window (days)", type: "number", hint: "Similar requirements further apart than this are treated as distinct" }]} /></TabsContent>
        <TabsContent value="digest"><SchedulesSection /></TabsContent>
        <TabsContent value="notifications"><SectionForm section="notifications" title="Notifications" description="Which events create in-app notifications."
          fields={[{ key: "sync_failure", label: "Synchronization failures", type: "bool" }, { key: "extraction_failure", label: "Extraction failures", type: "bool" }, { key: "duplicate_review", label: "Duplicates awaiting review", type: "bool" }, { key: "export_completed", label: "Export completed", type: "bool" }, { key: "send_failure", label: "Email sending failures", type: "bool" }]} /></TabsContent>
        <TabsContent value="security"><SecuritySection /></TabsContent>
        <TabsContent value="health"><HealthSection /></TabsContent>
      </Tabs>
    </>
  );
}
