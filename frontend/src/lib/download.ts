import { getCsrfToken } from "@/lib/api";

/** POST that returns a file: fetched with the CSRF header, then saved through a temporary link. */
export async function downloadPost(path: string, body: unknown, fallbackName: string): Promise<void> {
  const res = await fetch(`/api/v1${path}`, {
    method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrfToken() ?? "" }, body: JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = `Download failed (${res.status})`;
    try { msg = ((await res.json()) as { error?: { message?: string } }).error?.message ?? msg; } catch { /* keep the default message */ }
    throw new Error(msg);
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
