import type { ApiErrorBody } from "@/types/api";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown, public requestId?: string) {
    super(message);
  }
}

const BASE = "/api/v1";
// The CSRF token is held in memory only (never localStorage); the session itself lives in an HttpOnly cookie.
let csrfToken: string | null = null;
export const setCsrfToken = (t: string | null) => { csrfToken = t; };
export const getCsrfToken = () => csrfToken;
let onUnauthorized: (() => void) | null = null;
export const setUnauthorizedHandler = (fn: (() => void) | null) => { onUnauthorized = fn; };

type Query = Record<string, string | number | boolean | null | undefined | string[]>;
export function toQuery(params?: Query): string {
  const sp = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, x)); else sp.set(k, String(v));
  });
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export async function request<T>(method: string, path: string, opts: { body?: unknown; query?: Query; headers?: Record<string, string> } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...(opts.headers ?? {}) };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (csrfToken && method !== "GET") headers["X-CSRF-Token"] = csrfToken;
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}${toQuery(opts.query)}`, {
      method, headers, credentials: "same-origin", body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the server. Check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    let body: ApiErrorBody | null = null;
    try { body = (await res.json()) as ApiErrorBody; } catch { /* non-JSON error body */ }
    const err = new ApiError(res.status, body?.error?.code ?? "http_error", body?.error?.message ?? `Request failed (${res.status})`, body?.error?.details, body?.error?.request_id);
    if (res.status === 401 && onUnauthorized && !path.startsWith("/auth/login")) onUnauthorized();
    throw err;
  }
  return (await res.json()) as T;
}

export const api = {
  get: <T,>(path: string, query?: Query) => request<T>("GET", path, { query }),
  post: <T,>(path: string, body?: unknown, headers?: Record<string, string>) => request<T>("POST", path, { body: body ?? {}, headers }),
  patch: <T,>(path: string, body: unknown) => request<T>("PATCH", path, { body }),
  put: <T,>(path: string, body: unknown) => request<T>("PUT", path, { body }),
  del: <T,>(path: string) => request<T>("DELETE", path),
};

/** multipart/form-data upload (the browser sets the boundary header itself). */
export async function upload<T>(path: string, form: FormData): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { method: "POST", credentials: "same-origin", headers: csrfToken ? { "X-CSRF-Token": csrfToken, Accept: "application/json" } : { Accept: "application/json" }, body: form });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the server. Check your connection and try again.");
  }
  if (!res.ok) {
    let body: ApiErrorBody | null = null;
    try { body = (await res.json()) as ApiErrorBody; } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, body?.error?.code ?? "http_error", body?.error?.message ?? `Request failed (${res.status})`, body?.error?.details, body?.error?.request_id);
  }
  return (await res.json()) as T;
}

export const downloadUrl = (path: string) => `${BASE}${path}`;

/** Human-friendly message for any thrown value. Field validation details from the API are folded in. */
export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 422 && Array.isArray(e.details) && e.details.length) {
      const d = e.details[0] as { loc?: string[]; msg?: string };
      return `${d.loc?.slice(1).join(".") || "Input"}: ${d.msg ?? e.message}`;
    }
    return e.message;
  }
  return e instanceof Error ? e.message : "Something went wrong";
}
