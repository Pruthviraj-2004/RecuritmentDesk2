import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/card";
import { errorMessage } from "@/lib/api";
import { cn, titleCase } from "@/lib/utils";

export function PageHeader({ title, description, actions, breadcrumb }: { title: string; description?: string; actions?: React.ReactNode; breadcrumb?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        {breadcrumb && <div className="mb-1 text-xs text-muted-foreground">{breadcrumb}</div>}
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

type Variant = "default" | "secondary" | "outline" | "success" | "warning" | "destructive" | "muted";
const STATUS: Record<string, { v: Variant; label?: string }> = {
  // review / lifecycle
  needs_review: { v: "warning", label: "Needs review" }, approved: { v: "success" }, rejected: { v: "destructive" },
  active: { v: "secondary" }, archived: { v: "muted" }, merged: { v: "muted" }, closed: { v: "muted" },
  // message processing
  pending: { v: "muted" }, processing: { v: "default" }, awaiting_ai: { v: "warning", label: "Awaiting AI" }, processed: { v: "success" },
  no_requirement: { v: "muted", label: "No requirement" }, duplicate: { v: "secondary" }, ignored: { v: "muted" }, failed: { v: "destructive" },
  // jobs
  queued: { v: "muted" }, running: { v: "default" }, completed: { v: "success" }, completed_with_errors: { v: "warning", label: "Completed with errors" },
  cancel_requested: { v: "warning", label: "Cancelling" }, cancelled: { v: "muted" },
  // accounts
  connected: { v: "success" }, syncing: { v: "default" }, disconnected: { v: "muted" }, expired: { v: "destructive", label: "Reauthorization needed" }, error: { v: "destructive" },
  // exports / deliveries
  expired_export: { v: "muted" }, accepted_by_gmail: { v: "success", label: "Accepted by Gmail" }, sending: { v: "default" }, uncertain: { v: "warning" },
  // duplicates
  kept_both: { v: "secondary", label: "Kept both" }, related: { v: "secondary" }, dismissed: { v: "muted" },
  // work mode
  remote: { v: "default" }, hybrid: { v: "default" }, onsite: { v: "default", label: "On-site" }, unknown: { v: "muted" },
  // candidates and pipeline
  screening: { v: "default" }, shortlisted: { v: "default" }, interviewing: { v: "warning" }, offered: { v: "success" }, hired: { v: "success" }, on_hold: { v: "muted", label: "On hold" },
  not_interested: { v: "muted", label: "Not interested" }, submitted: { v: "default" }, interview: { v: "warning" }, joined: { v: "success" }, withdrawn: { v: "muted" }, new: { v: "secondary" },
  // classification
  new_requirement: { v: "default", label: "New requirement" }, updated_requirement: { v: "default", label: "Updated requirement" },
  recruiter_followup: { v: "secondary", label: "Recruiter follow-up" }, candidate_submission: { v: "secondary" }, interview_scheduling: { v: "secondary" },
  job_closure: { v: "warning", label: "Job closure" }, unrelated: { v: "muted" },
};

export function StatusBadge({ status, className }: { status: string | null | undefined; className?: string }) {
  if (!status) return <span className="text-muted-foreground">—</span>;
  const s = STATUS[status] ?? { v: "muted" as Variant };
  return <Badge variant={s.v} className={className}>{s.label ?? titleCase(status)}</Badge>;
}

export function EmptyState({ icon: Icon = Inbox, title, description, action }: { icon?: React.ComponentType<{ className?: string }>; title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-12 text-center">
      <div className="rounded-full bg-muted p-3"><Icon className="size-5 text-muted-foreground" /></div>
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="max-w-md text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry, title = "Could not load this data" }: { error: unknown; onRetry?: () => void; title?: string }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-6 py-8 text-center">
      <AlertTriangle className="size-5 text-destructive" />
      <p className="text-sm font-medium">{title}</p>
      <p className="max-w-md text-sm text-muted-foreground">{errorMessage(error)}</p>
      {onRetry && <Button variant="outline" size="sm" onClick={onRetry}><RefreshCw /> Try again</Button>}
    </div>
  );
}

export function LoadingRows({ rows = 6, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)} role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
    </div>
  );
}

export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel = "Confirm", destructive, loading, onConfirm, children }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; description: string; confirmLabel?: string; destructive?: boolean; loading?: boolean;
  onConfirm: () => void; children?: React.ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={title} description={description} size="sm">
        {children}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant={destructive ? "destructive" : "default"} loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function KeyValue({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 break-words text-sm">{children || <span className="text-muted-foreground">—</span>}</dd>
    </div>
  );
}

export function useDebounced<T>(value: T, ms = 350): T {
  const [v, setV] = React.useState(value);
  React.useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}
