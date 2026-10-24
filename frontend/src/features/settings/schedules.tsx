import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useAuth } from "@/app/auth";
import { ErrorState, LoadingRows } from "@/components/common/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Field, Input, Select } from "@/components/ui/form";
import { api } from "@/lib/api";
import { useAction, useSettings } from "@/services/hooks";

export interface Schedule {
  id: string; name: string; enabled: boolean; recipients: string[] | string; sender_email: string;
  mode: "delta" | "all" | "last_days"; days: number; frequency: "hours" | "daily"; interval_hours: number; time_of_day: string; timezone: string;
}
interface Digest { schedules: Schedule[] }

const newSchedule = (): Schedule => ({
  id: Math.random().toString(36).slice(2, 12), name: "Requirements update", enabled: true, recipients: "", sender_email: "", mode: "delta", days: 7,
  frequency: "hours", interval_hours: 3, time_of_day: "09:00", timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
});
const recipientText = (r: string[] | string) => (Array.isArray(r) ? r.join(", ") : r);

/** Any number of scheduled emails: what to send (changes only, everything, or the last N days) and when (every N hours or daily at a time). */
export function SchedulesSection() {
  const { can } = useAuth();
  const q = useSettings<Digest>("digest");
  const [items, setItems] = useState<Schedule[]>([]);
  const [dirty, setDirty] = useState(false);
  useEffect(() => { if (q.data) { setItems(q.data.schedules); setDirty(false); } }, [q.data]);
  const save = useAction<Schedule[], Digest>({
    fn: (schedules) => api.put("/settings/digest", { values: { schedules: schedules.map((s) => ({ ...s, recipients: recipientText(s.recipients), days: Number(s.days), interval_hours: Number(s.interval_hours) })) } }),
    invalidate: [["settings", "digest"], ["audit"]], success: "Scheduled emails saved",
  });
  if (q.isLoading) return <LoadingRows rows={4} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const admin = can("admin");
  const set = (i: number, patch: Partial<Schedule>) => { setItems((cur) => cur.map((s, j) => (j === i ? { ...s, ...patch } : s))); setDirty(true); };
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">Each schedule emails an Excel file of requirements. Nothing is sent when there is nothing to send. Rejected requirements are always left out. Sync frequency itself is <code>SYNC_INTERVAL_MINUTES</code> on the server, and the schedules need the background worker (Redis) to run on their own.</p>
      {items.length === 0 && <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">No scheduled emails yet.</CardContent></Card>}
      {items.map((s, i) => (
        <Card key={s.id}>
          <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
            <div><CardTitle className="text-base">{s.name || "Scheduled email"}</CardTitle>
              <CardDescription>{s.mode === "delta" ? "Only new or changed requirements" : s.mode === "all" ? "All active requirements" : `New or updated in the last ${s.days} days`} · {s.frequency === "hours" ? `every ${s.interval_hours} hour(s)` : `daily at ${s.time_of_day} (${s.timezone})`}</CardDescription></div>
            <Button size="sm" variant="outline" disabled={!admin} aria-label={`Delete ${s.name}`} onClick={() => { setItems((cur) => cur.filter((_, j) => j !== i)); setDirty(true); }}><Trash2 /> Delete</Button>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-sm sm:col-span-2"><Checkbox disabled={!admin} checked={s.enabled} onChange={(e) => set(i, { enabled: e.target.checked })} /> This schedule is on</label>
            <Field label="Name (used as the email subject)" htmlFor={`n-${s.id}`}><Input id={`n-${s.id}`} disabled={!admin} value={s.name} onChange={(e) => set(i, { name: e.target.value })} /></Field>
            <Field label="Recipients" htmlFor={`r-${s.id}`} hint="Comma separated, up to 20 addresses"><Input id={`r-${s.id}`} disabled={!admin} value={recipientText(s.recipients)} onChange={(e) => set(i, { recipients: e.target.value })} /></Field>
            <Field label="What to send" htmlFor={`m-${s.id}`}>
              <Select id={`m-${s.id}`} disabled={!admin} value={s.mode} onChange={(e) => set(i, { mode: e.target.value as Schedule["mode"] })}>
                <option value="delta">Only new or changed since this schedule's last email</option><option value="all">All active requirements</option><option value="last_days">New or updated in the last N days</option></Select></Field>
            {s.mode === "last_days" ? <Field label="Number of days" htmlFor={`d-${s.id}`}><Input id={`d-${s.id}`} type="number" min={1} max={365} disabled={!admin} value={s.days} onChange={(e) => set(i, { days: Number(e.target.value) })} /></Field> : <div />}
            <Field label="When" htmlFor={`f-${s.id}`}>
              <Select id={`f-${s.id}`} disabled={!admin} value={s.frequency} onChange={(e) => set(i, { frequency: e.target.value as Schedule["frequency"] })}><option value="hours">Every N hours</option><option value="daily">Once a day at a set time</option></Select></Field>
            {s.frequency === "hours"
              ? <Field label="Every (hours)" htmlFor={`h-${s.id}`} hint="1–24"><Input id={`h-${s.id}`} type="number" min={1} max={24} disabled={!admin} value={s.interval_hours} onChange={(e) => set(i, { interval_hours: Number(e.target.value) })} /></Field>
              : <div className="grid grid-cols-2 gap-3">
                <Field label="Time of day" htmlFor={`t-${s.id}`}><Input id={`t-${s.id}`} type="time" disabled={!admin} value={s.time_of_day} onChange={(e) => set(i, { time_of_day: e.target.value })} /></Field>
                <Field label="Timezone" htmlFor={`z-${s.id}`} hint="e.g. Asia/Kolkata"><Input id={`z-${s.id}`} disabled={!admin} value={s.timezone} onChange={(e) => set(i, { timezone: e.target.value })} /></Field></div>}
            <Field label="Send from (connected account)" htmlFor={`s-${s.id}`} hint="Leave blank to use the default sender; the account needs send access"><Input id={`s-${s.id}`} disabled={!admin} value={s.sender_email} onChange={(e) => set(i, { sender_email: e.target.value })} /></Field>
          </CardContent>
        </Card>))}
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" disabled={!admin || items.length >= 10} onClick={() => { setItems((cur) => [...cur, newSchedule()]); setDirty(true); }}><Plus /> Add scheduled email</Button>
        <Button disabled={!admin || !dirty} loading={save.isPending} onClick={() => save.mutate(items)}>Save changes</Button>
        {!admin && <span className="text-xs text-muted-foreground">Administrators only</span>}
      </div>
    </div>
  );
}
