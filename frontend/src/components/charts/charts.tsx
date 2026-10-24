import { BarChart3, Table2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState } from "@/components/common/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Skeleton } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/* Chart colors are roles (validated categorical palette: slot 2 orange = brand series; slot 1 blue; light/dark selected separately). */
export const CHART_CSS = `
.chart-root{--c-series:#eb6834;--c-series-2:#2a78d6;--c-grid:hsl(var(--border));--c-text:hsl(var(--muted-foreground));--c-surface:hsl(var(--card))}
.dark .chart-root{--c-series:#d95926;--c-series-2:#3987e5}
`;

interface Row { name: string; count: number }

function Tip({ active, payload, label, unit }: { active?: boolean; payload?: { value: number }[]; label?: string; unit: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border bg-card px-2.5 py-1.5 text-xs shadow-md">
      <p className="font-medium">{label}</p>
      <p className="tabular text-muted-foreground">{payload[0].value.toLocaleString()} {unit}</p>
    </div>
  );
}

export function ChartCard({ title, description, loading, empty, emptyHint, rows, children, className }: {
  title: string; description?: string; loading?: boolean; empty: boolean; emptyHint?: string; rows?: Row[]; children: ReactNode; className?: string;
}) {
  const [table, setTable] = useState(false);
  return (
    <Card className={cn("chart-root", className)}>
      <style>{CHART_CSS}</style>
      <CardHeader className="flex-row items-start justify-between gap-2 space-y-0">
        <div className="space-y-1"><CardTitle>{title}</CardTitle>{description && <CardDescription>{description}</CardDescription>}</div>
        {!empty && !loading && rows && (
          <Button variant="ghost" size="icon" className="h-7 w-7" aria-pressed={table} aria-label={table ? "Show chart" : "Show as table"} onClick={() => setTable((t) => !t)}>
            {table ? <BarChart3 /> : <Table2 />}
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {loading ? <Skeleton className="h-52 w-full" /> : empty ? (
          <div className="grid h-52 place-items-center text-center text-sm text-muted-foreground"><div><BarChart3 className="mx-auto mb-2 size-5" /><p>No data for this period</p>{emptyHint && <p className="mt-1 text-xs">{emptyHint}</p>}</div></div>
        ) : table && rows ? (
          <div className="max-h-52 overflow-auto"><table className="w-full text-sm"><thead className="text-left text-xs text-muted-foreground"><tr><th className="py-1">Name</th><th className="py-1 text-right">Count</th></tr></thead>
            <tbody>{rows.map((r) => <tr key={r.name} className="border-t"><td className="py-1">{r.name}</td><td className="tabular py-1 text-right">{r.count}</td></tr>)}</tbody></table></div>
        ) : children}
      </CardContent>
    </Card>
  );
}

export function TimeSeries({ data, unit = "requirements" }: { data: { label: string; count: number }[]; unit?: string }) {
  return (
    <div className="h-52 w-full" role="img" aria-label={`${unit} over time`}>
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
          <defs><linearGradient id="g1" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--c-series)" stopOpacity={0.25} /><stop offset="100%" stopColor="var(--c-series)" stopOpacity={0} /></linearGradient></defs>
          <CartesianGrid stroke="var(--c-grid)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: "var(--c-text)", fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={24} />
          <YAxis allowDecimals={false} tick={{ fill: "var(--c-text)", fontSize: 11 }} tickLine={false} axisLine={false} />
          <Tooltip content={<Tip unit={unit} />} cursor={{ stroke: "var(--c-grid)" }} />
          <Area isAnimationActive={false} type="monotone" dataKey="count" stroke="var(--c-series)" strokeWidth={2} fill="url(#g1)" activeDot={{ r: 4, stroke: "var(--c-surface)", strokeWidth: 2 }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Horizontal bars for ranked categories (single series, so no legend; the title names it). Values are shown directly. */
export function BarList({ rows, unit = "requirements", max = 8 }: { rows: Row[]; unit?: string; max?: number }) {
  const data = rows.slice(0, max);
  const h = Math.max(160, data.length * 30 + 20);
  return (
    <div style={{ height: h }} className="w-full" role="img" aria-label={`${unit} by category`}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 28, bottom: 0, left: 0 }} barCategoryGap={6}>
          <XAxis type="number" hide allowDecimals={false} />
          <YAxis type="category" dataKey="name" width={118} tick={{ fill: "var(--c-text)", fontSize: 11 }} tickLine={false} axisLine={false} tickFormatter={(v: string) => (v.length > 18 ? `${v.slice(0, 17)}…` : v)} />
          <Tooltip content={<Tip unit={unit} />} cursor={{ fill: "hsl(var(--muted))" }} />
          <Bar isAnimationActive={false} dataKey="count" fill="var(--c-series)" radius={[0, 4, 4, 0]} barSize={14} label={{ position: "right", fill: "var(--c-text)", fontSize: 11 }} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Part-to-whole as one stacked bar with a 2px surface gap between segments, legend + direct values (identity is never color-alone). */
export function StackedStatus({ parts }: { parts: { name: string; value: number; color: string }[] }) {
  const total = parts.reduce((a, p) => a + p.value, 0);
  return (
    <div>
      <div className="flex h-5 w-full gap-[2px] overflow-hidden rounded-sm" role="img" aria-label={parts.map((p) => `${p.name}: ${p.value}`).join(", ")}>
        {parts.filter((p) => p.value > 0).map((p) => <div key={p.name} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} title={`${p.name}: ${p.value}`} />)}
      </div>
      <ul className="mt-3 grid gap-1.5 text-sm">
        {parts.map((p) => (
          <li key={p.name} className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-2"><span className="size-2.5 rounded-[3px]" style={{ background: p.color }} aria-hidden />{p.name}</span>
            <span className="tabular font-medium">{p.value.toLocaleString()} <span className="text-xs font-normal text-muted-foreground">({total ? Math.round((p.value / total) * 100) : 0}%)</span></span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function EmptyChartNote() { return <EmptyState title="No data" />; }
