import { AlertTriangle, Mail, MoreHorizontal, Plus, RefreshCw, Send, Settings2, ShieldAlert, Star, Unplug } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/app/auth";
import { ConfirmDialog, EmptyState, ErrorState, LoadingRows, PageHeader, StatusBadge } from "@/components/common/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown";
import { Checkbox, Field, Input, Select } from "@/components/ui/form";
import { useConnectGmail, useReauthorize, useSyncAccount } from "@/hooks/use-gmail";
import { api } from "@/lib/api";
import { fmtDateTime, fmtRelative } from "@/lib/utils";
import { useAccounts, useAction } from "@/services/hooks";
import type { Account } from "@/types/api";

const KEYS = [["accounts"], ["overview"]];
const REASONS: Record<string, string> = {
  invalid_oauth_state: "The authorization request expired or was invalid. Please try connecting again.",
  missing_scope: "Gmail read permission was not granted, but it is required to import recruitment emails.",
  no_refresh_token: "Google did not return a long-lived token. Remove RecruitmentDesk at myaccount.google.com/permissions and connect again.",
  account_mismatch: "Reauthorization must use the same Google account.", failed: "Google sign-in could not be completed.",
};

function AccountSettings({ account, onClose }: { account: Account; onClose: () => void }) {
  const [name, setName] = useState(account.display_name ?? "");
  const [days, setDays] = useState(account.import_days);
  const [enabled, setEnabled] = useState(account.sync_enabled);
  const [query, setQuery] = useState(account.extra_query ?? "");
  const save = useAction<void, Account>({
    fn: () => api.patch(`/email-accounts/${account.id}`, { display_name: name || null, import_days: days, sync_enabled: enabled, extra_query: query || null }),
    invalidate: KEYS, success: "Account settings saved", onDone: onClose,
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Account settings" description={account.email_address} size="sm">
        <Field label="Display name" htmlFor="dn"><Input id="dn" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Import window" htmlFor="days" hint="How far back an initial or full synchronization reads"><Select id="days" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          {[7, 30, 90, 180, 365].map((d) => <option key={d} value={d}>Last {d} days</option>)}</Select></Field>
        <Field label="Extra Gmail search terms" htmlFor="xq" hint="Optional, e.g. label:recruiters. Added to the default query."><Input id="xq" value={query} maxLength={500} onChange={(e) => setQuery(e.target.value)} /></Field>
        <label className="flex items-center gap-2 text-sm"><Checkbox checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Automatic synchronization enabled</label>
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate()}>Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AccountCard({ a }: { a: Account }) {
  const { can } = useAuth();
  const sync = useSyncAccount();
  const reauth = useReauthorize();
  const [settings, setSettings] = useState(false);
  const [disc, setDisc] = useState(false);
  const [fullDays, setFullDays] = useState<number | null>(null);
  const setDefault = useAction<void, Account>({ fn: () => api.patch(`/email-accounts/${a.id}`, { is_default_sender: true }), invalidate: KEYS, success: "Default sending account updated" });
  const disconnect = useAction<void, { revoked_at_google: boolean }>({
    fn: () => api.del(`/email-accounts/${a.id}`), invalidate: KEYS,
    success: (d) => (d.revoked_at_google ? "Disconnected; access revoked at Google" : "Disconnected; stored credentials removed (revoke manually at myaccount.google.com/permissions if needed)"),
    onDone: () => setDisc(false),
  });
  const needsAuth = a.connection_status === "expired" || a.connection_status === "disconnected";
  return (
    <Card><CardContent className="space-y-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-medium">{a.display_name || a.email_address}</p>
          <p className="truncate text-xs text-muted-foreground">Gmail · added {fmtDateTime(a.created_at)}</p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" aria-label={`More actions for ${a.email_address}`}><MoreHorizontal /></Button></DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem disabled={!can("admin")} onSelect={() => setSettings(true)}><Settings2 /> Settings</DropdownMenuItem>
            <DropdownMenuItem disabled={!can("member") || needsAuth} onSelect={() => setFullDays(a.import_days)}><RefreshCw /> Full re-import…</DropdownMenuItem>
            <DropdownMenuItem disabled={!can("admin") || !a.can_send || a.is_default_sender || needsAuth} onSelect={() => setDefault.mutate()}><Star /> Use as default sender</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled={!can("admin") || a.connection_status === "disconnected"} onSelect={() => setDisc(true)}><Unplug /> Disconnect</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div className="flex flex-wrap gap-1.5">
        <StatusBadge status={a.connection_status} />
        {a.is_default_sender && <Badge variant="default"><Send className="size-3" /> Default sender</Badge>}
        {!a.can_send && <Badge variant="muted" title="Connected without send permission">Read-only</Badge>}
        {!a.sync_enabled && <Badge variant="muted">Auto-sync off</Badge>}
      </div>
      {a.last_error && <div role="alert" className="flex gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-2 text-xs"><AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-destructive" /><span>{a.last_error}</span></div>}
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <div><dt className="text-xs text-muted-foreground">Last successful sync</dt><dd title={fmtDateTime(a.last_synced_at)}>{fmtRelative(a.last_synced_at)}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Import window</dt><dd>{a.import_days} days</dd></div>
        <div><dt className="text-xs text-muted-foreground">Emails synced</dt><dd className="tabular">{a.stats.messages ?? 0}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Requirements</dt><dd className="tabular">{a.stats.requirements ?? 0}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Processed</dt><dd className="tabular">{a.stats.processed ?? 0}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Failed / pending</dt><dd className="tabular">{a.stats.failed ?? 0} / {a.stats.pending ?? 0}</dd></div>
      </dl>
      <div className="flex flex-wrap gap-2 border-t pt-3">
        {needsAuth ? (
          <Button size="sm" disabled={!can("admin")} loading={reauth.isPending} onClick={() => reauth.mutate({ id: a.id, enable_send: true })}><ShieldAlert /> Reauthorize</Button>
        ) : (
          <Button size="sm" disabled={!can("member") || a.connection_status === "syncing"} loading={sync.isPending && sync.variables?.id === a.id} onClick={() => sync.mutate({ id: a.id })}>
            <RefreshCw className={a.connection_status === "syncing" ? "animate-spin" : ""} /> {a.connection_status === "syncing" ? "Syncing…" : "Sync now"}
          </Button>
        )}
        {!a.can_send && !needsAuth && <Button size="sm" variant="outline" disabled={!can("admin")} onClick={() => reauth.mutate({ id: a.id, enable_send: true })}>Grant send permission</Button>}
      </div>
      {settings && <AccountSettings account={a} onClose={() => setSettings(false)} />}
      <ConfirmDialog open={disc} onOpenChange={setDisc} title={`Disconnect ${a.email_address}?`} destructive confirmLabel="Disconnect" loading={disconnect.isPending}
        description="Stored Google credentials are deleted and access is revoked at Google. Already imported emails and requirements are kept." onConfirm={() => disconnect.mutate()} />
      <ConfirmDialog open={fullDays !== null} onOpenChange={(o) => !o && setFullDays(null)} title="Full re-import" confirmLabel="Start import" description="Re-reads the selected window from Gmail. Emails already imported are skipped, so no duplicates are created."
        onConfirm={() => { sync.mutate({ id: a.id, mode: "full", import_days: fullDays ?? undefined }); setFullDays(null); }}>
        <Field label="Window"><Select value={fullDays ?? 30} onChange={(e) => setFullDays(Number(e.target.value))} aria-label="Import window">{[7, 30, 90, 180, 365].map((d) => <option key={d} value={d}>Last {d} days</option>)}</Select></Field>
      </ConfirmDialog>
    </CardContent></Card>
  );
}

export function AccountsPage() {
  const q = useAccounts();
  const { can } = useAuth();
  const connect = useConnectGmail();
  const [sp, setSp] = useSearchParams();
  const [sendScope, setSendScope] = useState(true);

  useEffect(() => {  // result of the Google consent redirect
    const c = sp.get("connect");
    if (!c) return;
    if (c === "success") toast.success("Gmail account connected", { id: "connect-result" });
    else if (c === "denied") toast.warning("Google access was not granted, so no account was connected", { id: "connect-result" });
    else toast.error(REASONS[sp.get("reason") ?? "failed"] ?? REASONS.failed, { duration: 9000, id: "connect-result" });
    const n = new URLSearchParams(sp); n.delete("connect"); n.delete("reason"); n.delete("account"); setSp(n, { replace: true });
  }, [sp, setSp]);

  return (
    <>
      <PageHeader title="Connected Accounts" description="Gmail accounts are connected through Google's consent screen. Your password is never seen or stored."
        actions={<><label className="flex items-center gap-2 text-sm"><Checkbox checked={sendScope} onChange={(e) => setSendScope(e.target.checked)} /> Allow sending exports</label>
          <Button disabled={!can("admin")} loading={connect.isPending} onClick={() => connect.mutate({ enable_send: sendScope })}><Plus /> Connect Gmail</Button></>} />
      {q.error && !q.data ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <LoadingRows rows={3} /> : !q.data?.length ? (
        <EmptyState icon={Mail} title="No Gmail accounts connected" description="Connect up to as many accounts as you need. Read access imports recruitment emails; send access is only needed to email Excel exports."
          action={can("admin") ? <Button onClick={() => connect.mutate({ enable_send: sendScope })} loading={connect.isPending}><Plus /> Connect Gmail</Button> : <p className="text-xs text-muted-foreground">Ask an administrator to connect an account.</p>} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{q.data.map((a) => <AccountCard key={a.id} a={a} />)}</div>
      )}
      <p className="mt-6 max-w-3xl text-xs text-muted-foreground">Permissions requested: <strong>gmail.readonly</strong> (read mail to find job requirements) and optionally <strong>gmail.send</strong> (send exports you confirm). Google treats Gmail scopes as restricted; production use with many users requires Google OAuth verification (see docs/GMAIL_SETUP.md).</p>
    </>
  );
}
