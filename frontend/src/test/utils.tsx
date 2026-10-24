import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { Toaster } from "sonner";
import { vi } from "vitest";
import { AuthProvider } from "@/app/auth";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { Me } from "@/types/api";

export const ME: Me = { user: { id: "u1", email: "owner@example.com", display_name: "Owner" }, organization: { id: "o1", name: "Org", slug: "org" }, role: "owner", csrf_token: "csrf-1" };

type Handler = unknown | ((url: URL, init: RequestInit) => unknown);
export interface Call { method: string; path: string; body: unknown; headers: Record<string, string> }

/** Mock fetch keyed by "METHOD /path" (query ignored unless the key contains '?'). Unmatched calls fail the test loudly. */
export function mockApi(routes: Record<string, Handler>, me: Me | null = ME) {
  const calls: Call[] = [];
  const all: Record<string, Handler> = { "GET /auth/me": me ? me : () => new Response(JSON.stringify({ error: { code: "unauthenticated", message: "Not authenticated" } }), { status: 401 }), ...routes };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init.method ?? "GET").toUpperCase();
    const path = url.pathname.replace("/api/v1", "");
    calls.push({ method, path: path + url.search, body: init.body instanceof FormData ? Object.fromEntries([...init.body.entries()].map(([k, v]) => [k, v instanceof File ? `file:${v.name}` : v])) : init.body ? JSON.parse(String(init.body)) : undefined, headers: (init.headers ?? {}) as Record<string, string> });
    const h = all[`${method} ${path}${url.search}`] ?? all[`${method} ${path}`];
    if (h === undefined) throw new Error(`Unmocked request: ${method} ${path}${url.search}`);
    const val = typeof h === "function" ? (h as (u: URL, i: RequestInit) => unknown)(url, init) : h;
    if (val instanceof Response) return val;
    return new Response(val === null ? null : JSON.stringify(val), { status: val === null ? 204 : 200, headers: { "Content-Type": "application/json" } });
  }));
  return calls;
}

export const apiError = (status: number, code: string, message: string) => new Response(JSON.stringify({ error: { code, message } }), { status });

export function renderApp(ui: ReactElement, route = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}><TooltipProvider><AuthProvider><MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter><Toaster /></AuthProvider></TooltipProvider></QueryClientProvider>,
  );
}

export const page = <T,>(items: T[], total = items.length, p = 1, size = 25) => ({ items, total, page: p, page_size: size });

export const REQ = (over: Record<string, unknown> = {}) => ({
  id: "r1", client_name: "Globex", job_title: "Python Developer", job_reference_id: "GX-1", required_skills: ["Python", "Django"], preferred_skills: [], minimum_experience: 3, maximum_experience: 6,
  salary_min: null, salary_max: null, salary_currency: null, salary_period: null, employment_type: null, location: "Pune", work_mode: "remote", recruiter_name: "Jane", recruiter_email: "j@x.com",
  number_of_openings: null, received_at: "2026-10-01T09:00:00Z", last_updated_at: "2026-10-02T09:00:00Z", lifecycle_status: "active", review_status: "needs_review", extraction_confidence: 0.8,
  validation_warnings: [], version_number: 1, merged_into_id: null, source_accounts: ["a@gmail.com"], source_count: 1, has_pending_duplicate: false, ...over,
});
