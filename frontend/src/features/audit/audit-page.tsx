import { History } from "lucide-react";
import { useState } from "react";
import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common/common";
import { Pagination } from "@/components/data-table/data-table";
import { Badge } from "@/components/ui/badge";
import { Input, Select } from "@/components/ui/form";
import { fmtDateTime, titleCase } from "@/lib/utils";
import { useAudit } from "@/services/hooks";

const GROUPS = [["", "All activity"], ["auth", "Sign-ins"], ["account", "Gmail accounts"], ["sync", "Synchronization"], ["requirement", "Requirements"], ["duplicate", "Duplicates"],
  ["export", "Exports"], ["delivery", "Email deliveries"], ["settings", "Settings"], ["job", "Jobs"], ["email", "Emails"]];

export function AuditPage() {
  const [group, setGroup] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const q = useAudit({ action: group || undefined, date_from: from ? `${from}T00:00:00Z` : undefined, date_to: to ? `${to}T23:59:59Z` : undefined, page, page_size: 30 });
  return (
    <>
      <PageHeader title="Activity & Audit Logs" description="A tamper-resistant record of who did what. Tokens, passwords and email bodies are never logged." />
      <div className="mb-3 flex flex-wrap gap-3 rounded-lg border bg-card p-3">
        <Select aria-label="Activity type" className="w-48" value={group} onChange={(e) => { setGroup(e.target.value); setPage(1); }}>{GROUPS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>
        <Input aria-label="From date" type="date" className="w-40" value={from} onChange={(e) => { setFrom(e.target.value); setPage(1); }} />
        <Input aria-label="To date" type="date" className="w-40" value={to} onChange={(e) => { setTo(e.target.value); setPage(1); }} />
      </div>
      {q.error && !q.data ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <LoadingRows /> : !q.data?.items.length ? <EmptyState icon={History} title="No activity recorded" description="Actions you and the system take will appear here." /> : (
        <>
          <div className="overflow-x-auto rounded-lg border bg-card"><table className="w-full min-w-[640px] text-sm">
            <thead className="border-b bg-muted/50 text-left text-xs text-muted-foreground"><tr><th className="px-3 py-2.5">When</th><th className="px-3 py-2.5">Who</th><th className="px-3 py-2.5">Action</th><th className="px-3 py-2.5">Details</th></tr></thead>
            <tbody>{q.data.items.map((e) => (
              <tr key={e.id} className="border-b last:border-0 align-top">
                <td className="whitespace-nowrap px-3 py-2.5 text-xs">{fmtDateTime(e.created_at)}</td><td className="px-3 py-2.5 text-xs">{e.user_email ?? <Badge variant="muted">system</Badge>}</td>
                <td className="px-3 py-2.5"><Badge variant="secondary">{e.action}</Badge></td>
                <td className="max-w-[420px] break-words px-3 py-2.5 text-xs text-muted-foreground">{e.entity_type ? `${titleCase(e.entity_type)} ` : ""}{Object.entries(e.metadata).slice(0, 4).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join(" · ")}</td>
              </tr>))}</tbody></table></div>
          <Pagination page={page} pageSize={30} total={q.data.total} onPage={setPage} />
        </>
      )}
    </>
  );
}
