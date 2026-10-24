import { zodResolver } from "@hookform/resolvers/zod";
import { Download, FileSpreadsheet, Mail, Plus, RotateCcw, Send } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";
import { useAuth } from "@/app/auth";
import { ConfirmDialog, EmptyState, ErrorState, LoadingRows, PageHeader, StatusBadge } from "@/components/common/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { ExportDialog } from "@/features/exports/export-dialog";
import { api, downloadUrl } from "@/lib/api";
import { fmtBytes, fmtDateTime } from "@/lib/utils";
import { useAccounts, useAction, useDeliveries, useEmailTemplates, useExports } from "@/services/hooks";
import type { Delivery, ExportJob } from "@/types/api";

const splitAddr = (s: string) => s.split(/[,;\s]+/).map((x) => x.trim()).filter(Boolean);
const addrList = (label: string, required: boolean) => z.string().refine((v) => { const l = splitAddr(v); return (required ? l.length > 0 : true) && l.length <= 20 && l.every((a) => z.string().email().safeParse(a).success); },
  required ? `Enter 1–20 valid ${label} email addresses` : `Enter valid ${label} email addresses (max 20)`);
const composeSchema = z.object({ sender: z.string().min(1, "Choose a sending account"), exportId: z.string().min(1, "Choose an export to attach"), to: addrList("recipient", true), cc: addrList("CC", false),
  subject: z.string().trim().min(1, "Enter a subject").max(300), body: z.string().max(20000) });
type ComposeValues = z.infer<typeof composeSchema>;

function Composer({ open, onClose, initialExport }: { open: boolean; onClose: () => void; initialExport?: string }) {
  const accounts = useAccounts();
  const exports = useExports({ page_size: 50 });
  const templates = useEmailTemplates();
  const [confirm, setConfirm] = useState<ComposeValues | null>(null);
  const [idem] = useState(() => crypto.randomUUID());
  const ready = useMemo(() => exports.data?.items.filter((e) => e.status === "completed") ?? [], [exports.data]);
  const senders = useMemo(() => accounts.data?.filter((a) => a.can_send && a.connection_status !== "expired" && a.connection_status !== "disconnected") ?? [], [accounts.data]);
  const def = senders.find((a) => a.is_default_sender) ?? senders[0];
  const { register, handleSubmit, watch, setValue, formState: { errors } } = useForm<ComposeValues>({
    resolver: zodResolver(composeSchema), values: { sender: def?.id ?? "", exportId: initialExport ?? ready[0]?.id ?? "", to: "", cc: "", subject: "", body: "" }, resetOptions: { keepDirtyValues: true },
  });
  const chosen = ready.find((e) => e.id === watch("exportId"));
  const send = useAction<ComposeValues, Delivery>({
    fn: (v) => api.post<Delivery>(`/exports/${v.exportId}/send`, { sender_account_id: v.sender, to: splitAddr(v.to), cc: splitAddr(v.cc), subject: v.subject, body: v.body, confirm: true }, { "Idempotency-Key": idem }),
    invalidate: [["deliveries"], ["overview"], ["accounts"]], success: null,
    onDone: (d) => {
      setConfirm(null);
      if (d.status === "accepted_by_gmail") toast.success("Gmail accepted the message. (Inbox delivery is not guaranteed.)");
      else if (d.status === "uncertain") toast.warning(d.error_summary ?? "Delivery outcome is uncertain. Check your Sent folder before retrying.", { duration: 10000 });
      else if (d.status === "failed") toast.error(d.error_summary ?? "The email could not be sent");
      else toast.info("Sending… the delivery status below updates automatically.");  // queued / sending: still in progress, not a failure
      onClose();
    },
  });
  const applyTemplate = (key: string) => {
    const t = templates.data?.[key];
    if (!t) return;
    setValue("subject", t.subject, { shouldValidate: true });
    setValue("body", t.body.replace("{count}", String(chosen?.record_count ?? "")), { shouldValidate: true });
  };
  const noSender = senders.length === 0;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Email an export" description="Nothing is sent until you review and confirm. Gmail accepting a message does not guarantee it reaches the recipient's inbox." size="lg">
        {noSender && <div role="alert" className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">No connected account has send permission. Connect or reauthorize an account with “Allow sending exports” on the Connected Accounts page.</div>}
        {ready.length === 0 && !exports.isLoading && <div role="status" className="rounded-md border p-3 text-sm">There is no completed export to attach yet. Create one from Requirements, then come back.</div>}
        <form onSubmit={handleSubmit((v) => setConfirm(v))} className="space-y-3" noValidate>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Send from" htmlFor="sender" error={errors.sender?.message}><Select id="sender" {...register("sender")}><option value="">Choose account…</option>{senders.map((a) => <option key={a.id} value={a.id}>{a.email_address}{a.is_default_sender ? " (default)" : ""}</option>)}</Select></Field>
            <Field label="Attachment" htmlFor="exportId" error={errors.exportId?.message}><Select id="exportId" {...register("exportId")}><option value="">Choose export…</option>{ready.map((e) => <option key={e.id} value={e.id}>{e.filename} · {e.record_count} rows</option>)}</Select></Field>
          </div>
          {chosen && <p className="text-xs text-muted-foreground">Attachment: <strong>{chosen.filename}</strong> · {fmtBytes(chosen.file_size_bytes)} · {chosen.record_count} unique requirements</p>}
          <Field label="To" htmlFor="to" error={errors.to?.message} hint="Separate multiple addresses with commas"><Input id="to" autoComplete="off" placeholder="client@example.com" aria-invalid={!!errors.to} {...register("to")} /></Field>
          <Field label="CC" htmlFor="cc" error={errors.cc?.message}><Input id="cc" autoComplete="off" aria-invalid={!!errors.cc} {...register("cc")} /></Field>
          <Field label="Template" htmlFor="tpl"><Select id="tpl" defaultValue="" onChange={(e) => e.target.value && applyTemplate(e.target.value)}><option value="">Start from a template…</option>
            <option value="summary">Recruitment Requirements Summary</option><option value="weekly">Weekly Hiring Requirements</option><option value="client_wise">Client-wise Requirement Report</option><option value="custom">Custom Recruitment Report</option></Select></Field>
          <Field label="Subject" htmlFor="subject" error={errors.subject?.message}><Input id="subject" aria-invalid={!!errors.subject} {...register("subject")} /></Field>
          <Field label="Message" htmlFor="body" error={errors.body?.message}><Textarea id="body" rows={6} {...register("body")} /></Field>
          <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button type="submit" disabled={noSender || ready.length === 0}><Send /> Review & send</Button></DialogFooter>
        </form>
        <ConfirmDialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)} title="Send this email now?" confirmLabel="Send email" loading={send.isPending} onConfirm={() => confirm && send.mutate(confirm)}
          description={confirm ? `From ${senders.find((a) => a.id === confirm.sender)?.email_address} to ${splitAddr(confirm.to).join(", ")}${splitAddr(confirm.cc).length ? ` (CC ${splitAddr(confirm.cc).join(", ")})` : ""}. Attachment: ${chosen?.filename} (${fmtBytes(chosen?.file_size_bytes)}, ${chosen?.record_count} requirements).` : ""} />
      </DialogContent>
    </Dialog>
  );
}

function ExportRow({ e, onEmail }: { e: ExportJob; onEmail: (id: string) => void }) {
  return (
    <tr className="border-b last:border-0 align-top">
      <td className="px-3 py-2.5 font-medium">{e.filename}</td><td className="px-3 py-2.5"><StatusBadge status={e.status === "expired" ? "expired_export" : e.status} />{e.status === "failed" && <p className="mt-1 max-w-[260px] text-xs text-destructive">{e.error_summary}</p>}</td>
      <td className="tabular px-3 py-2.5">{e.record_count ?? "—"}</td><td className="px-3 py-2.5 text-xs">{fmtBytes(e.file_size_bytes)}</td><td className="whitespace-nowrap px-3 py-2.5 text-xs">{fmtDateTime(e.created_at)}</td>
      <td className="whitespace-nowrap px-3 py-2.5 text-xs">{e.expires_at ? fmtDateTime(e.expires_at) : "—"}</td>
      <td className="px-3 py-2.5"><div className="flex gap-1.5">
        {e.status === "completed" && <><Button size="sm" variant="outline" onClick={() => { window.location.assign(downloadUrl(`/exports/${e.id}/download`)); }}><Download /> Download</Button><Button size="sm" variant="outline" onClick={() => onEmail(e.id)}><Mail /> Email</Button></>}
      </div></td>
    </tr>
  );
}

export function ExportsPage() {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const { can } = useAuth();
  const exports = useExports({ page_size: 20 });
  const deliveries = useDeliveries({ page_size: 20 });
  const [composeFor, setComposeFor] = useState<string | undefined>();
  const [newExport, setNewExport] = useState(false);
  const compose = sp.get("compose") === "1" || composeFor !== undefined;
  const closeCompose = () => { setComposeFor(undefined); const n = new URLSearchParams(sp); n.delete("compose"); setSp(n, { replace: true }); };
  const [retryTarget, setRetryTarget] = useState<Delivery | null>(null);
  const retry = useAction<Delivery, Delivery>({
    fn: (d) => api.post(`/deliveries/${d.id}/retry`, { acknowledge_possible_duplicate: d.status === "uncertain" }), invalidate: [["deliveries"]],
    success: null, onDone: (d) => { setRetryTarget(null); if (d.status === "accepted_by_gmail") toast.success("Gmail accepted the message"); else toast.error(d.error_summary ?? "Still not sent"); },
  });

  return (
    <>
      <PageHeader title="Exports & Deliveries" description="Generate Excel workbooks, email them through a connected Gmail account, and track every delivery."
        actions={<><Button variant="outline" disabled={!can("member")} onClick={() => setComposeFor("")}><Mail /> Compose email</Button><Button onClick={() => setNewExport(true)}><Plus /> New export</Button></>} />
      <Card className="mb-6"><CardHeader><CardTitle>Excel exports</CardTitle></CardHeader><CardContent>
        {exports.error && !exports.data ? <ErrorState error={exports.error} onRetry={() => exports.refetch()} /> : exports.isLoading ? <LoadingRows rows={3} /> : !exports.data?.items.length ? (
          <EmptyState icon={FileSpreadsheet} title="No exports yet" description="Select requirements (or use the current filters) and generate an .xlsx file." action={<Button onClick={() => nav("/requirements")}>Go to requirements</Button>} />
        ) : (
          <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-sm"><thead className="border-b text-left text-xs text-muted-foreground"><tr>{["File", "Status", "Rows", "Size", "Created", "Expires", ""].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr></thead>
            <tbody>{exports.data.items.map((e) => <ExportRow key={e.id} e={e} onEmail={(id) => setComposeFor(id)} />)}</tbody></table></div>
        )}
      </CardContent></Card>

      <Card><CardHeader><CardTitle>Email delivery history</CardTitle></CardHeader><CardContent>
        {deliveries.error && !deliveries.data ? <ErrorState error={deliveries.error} onRetry={() => deliveries.refetch()} /> : deliveries.isLoading ? <LoadingRows rows={3} /> : !deliveries.data?.items.length ? <p className="py-6 text-center text-sm text-muted-foreground">No emails have been sent from RecruitmentDesk yet.</p> : (
          <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-sm"><thead className="border-b text-left text-xs text-muted-foreground"><tr>{["Subject", "From", "To", "Status", "Created", ""].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr></thead>
            <tbody>{deliveries.data.items.map((d) => (
              <tr key={d.id} className="border-b last:border-0 align-top">
                <td className="max-w-[240px] truncate px-3 py-2.5 font-medium" title={d.subject}>{d.subject}</td><td className="px-3 py-2.5 text-xs">{d.sender_email ?? "—"}</td>
                <td className="max-w-[220px] truncate px-3 py-2.5 text-xs" title={[...d.recipient_addresses, ...d.cc_addresses].join(", ")}>{d.recipient_addresses.join(", ")}{d.cc_addresses.length ? ` (+${d.cc_addresses.length} cc)` : ""}</td>
                <td className="px-3 py-2.5"><StatusBadge status={d.status} /><p className="mt-1 max-w-[260px] text-xs text-muted-foreground">{d.error_summary ?? (d.status === "accepted_by_gmail" ? "Accepted by Gmail; inbox delivery is not guaranteed" : "")}</p></td>
                <td className="whitespace-nowrap px-3 py-2.5 text-xs">{fmtDateTime(d.created_at)}</td>
                <td className="px-3 py-2.5">{(d.status === "failed" || d.status === "uncertain") && <Button size="sm" variant="outline" disabled={!can("member")} onClick={() => setRetryTarget(d)}><RotateCcw /> Retry</Button>}{d.status === "uncertain" && <Badge variant="warning" className="ml-1">Check Sent</Badge>}</td>
              </tr>))}</tbody></table></div>
        )}
      </CardContent></Card>

      {compose && <Composer open onClose={closeCompose} initialExport={composeFor || undefined} />}
      {newExport && <ExportDialog open onOpenChange={setNewExport} selectedIds={[]} filters={{}} defaultScope="approved" />}
      <ConfirmDialog open={!!retryTarget} onOpenChange={(o) => !o && setRetryTarget(null)} title="Retry sending?" confirmLabel="Retry send" loading={retry.isPending} onConfirm={() => retryTarget && retry.mutate(retryTarget)}
        description={retryTarget?.status === "uncertain" ? "The earlier attempt may have been delivered. RecruitmentDesk will check Gmail's Sent folder first and only send again if it finds nothing. Continue?" : "The earlier attempt was not sent. Send it again?"} />
    </>
  );
}
