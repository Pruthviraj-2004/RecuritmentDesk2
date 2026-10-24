import { clsx, type ClassValue } from "clsx";
import { format, formatDistanceToNowStrict, isValid, parseISO } from "date-fns";
import { twMerge } from "tailwind-merge";

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));

export function fmtDate(v: string | null | undefined, pattern = "dd MMM yyyy"): string {
  if (!v) return "—";
  const d = parseISO(v);
  return isValid(d) ? format(d, pattern) : "—";
}
export const fmtDateTime = (v: string | null | undefined) => fmtDate(v, "dd MMM yyyy, HH:mm");
export function fmtRelative(v: string | null | undefined): string {
  if (!v) return "never";
  const d = parseISO(v);
  return isValid(d) ? `${formatDistanceToNowStrict(d)} ago` : "never";
}
export function fmtBytes(n: number | null | undefined): string {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), u.length - 1);
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`;
}
export function fmtExperience(min: number | null, max: number | null): string {
  if (min == null && max == null) return "—";
  if (min != null && max != null && max !== min) return `${min}–${max} yrs`;
  return min != null ? `${min}+ yrs` : `≤ ${max} yrs`;
}
export function fmtSalary(r: { salary_min: number | null; salary_max: number | null; salary_currency: string | null; salary_period: string | null }): string {
  if (r.salary_min == null && r.salary_max == null) return "—";
  const n = (v: number) => v.toLocaleString("en-IN", { maximumFractionDigits: 0 });
  const range = r.salary_min != null && r.salary_max != null ? `${n(r.salary_min)}–${n(r.salary_max)}` : n((r.salary_min ?? r.salary_max) as number);
  return `${r.salary_currency ?? ""} ${range}${r.salary_period ? ` / ${r.salary_period}` : ""}`.trim();
}
export const titleCase = (s: string) => s.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
export const pct = (v: number | null | undefined) => (v == null ? "—" : `${(v * 100).toFixed(v === 1 || v === 0 ? 0 : 1)}%`);

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2022-01" -> "Jan 2022"; "2022" -> "2022"; "present" -> "Present". */
export function fmtYm(v: string | null | undefined): string {
  if (!v) return "";
  if (/^present$/i.test(v)) return "Present";
  const m = /^(\d{4})-(\d{2})$/.exec(v);
  return m ? `${MONTHS[Number(m[2]) - 1] ?? ""} ${m[1]}`.trim() : v;
}
export function fmtMonths(n: number | null | undefined): string {
  if (n == null) return "—";
  const y = Math.floor(n / 12), m = n % 12;
  return [y ? `${y} yr${y > 1 ? "s" : ""}` : "", m ? `${m} mo` : ""].filter(Boolean).join(" ") || "< 1 mo";
}
export function monthsBetween(start: string | null, end: string | null): number | null {
  const p = (s: string | null, isEnd: boolean) => {
    if (!s) return null;
    if (/^present$/i.test(s)) { const d = new Date(); return d.getFullYear() * 12 + d.getMonth() + 1; }
    const m = /^(\d{4})(?:-(\d{2}))?$/.exec(s);
    return m ? Number(m[1]) * 12 + (m[2] ? Number(m[2]) : isEnd ? 12 : 1) : null;
  };
  const a = p(start, false), b = p(end, true);
  return a != null && b != null && b >= a ? b - a + 1 : null;
}
