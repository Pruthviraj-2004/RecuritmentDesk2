import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/api";
import { CandidateDetailPage } from "@/features/candidates/candidate-detail-page";
import { CandidatesPage } from "@/features/candidates/candidates-page";
import { ME, mockApi, page, renderApp } from "@/test/utils";
import { Route, Routes } from "react-router-dom";

const CAND = (o: Record<string, unknown> = {}) => ({
  id: "c1", first_name: "Asha", last_name: "Verma", full_name: "Asha Verma", email: "asha@example.com", phone: "9876543210", current_title: "Python Developer", current_company: "Acme",
  total_experience: 6, relevant_experience: null, current_location: "Bengaluru", preferred_locations: [], willing_to_relocate: null, notice_period: "30 days", current_ctc: null, expected_ctc: 2400000,
  currency: "INR", education: null, certifications: [], work_authorization: null, linkedin_url: null, resume_url: null, summary: null, source: "manual", status: "new", rating: 4, tags: ["priority"],
  skills: ["Python", "Django", "AWS", "Docker", "Kubernetes", "Terraform"], is_archived: false, last_contacted_at: null, created_at: "2026-10-01T09:00:00Z", updated_at: "2026-10-01T09:00:00Z", pipeline_count: 0, ...o,
});
const STATS = { total: 12, new_this_week: 3, in_pipeline: 2, by_status: { shortlisted: 4, interviewing: 1 } };

beforeEach(() => { vi.unstubAllGlobals(); setCsrfToken(null); });

describe("candidate list", () => {
  it("shows candidates, summary counts and expands skills with +N", async () => {
    mockApi({ "GET /candidates": page([CAND()], 1), "GET /candidates/stats": STATS });
    renderApp(<CandidatesPage />, "/candidates");
    await waitFor(() => expect(screen.getByRole("link", { name: "Asha Verma" })).toBeInTheDocument());
    expect(screen.getByText("asha@example.com")).toBeInTheDocument();
    expect(await screen.findByTestId("cstat-Total candidates")).toHaveTextContent("12");
    expect(screen.getByTestId("cstat-Shortlisted")).toHaveTextContent("4");
    await userEvent.click(screen.getByRole("button", { name: "Show 2 more skills" }));
    expect(screen.getByText("Terraform")).toBeInTheDocument();
  });

  it("sends search and status filters to the server and shows the empty state", async () => {
    const calls = mockApi({ "GET /candidates": (u: URL) => (u.searchParams.get("q") === "zzz" ? page([], 0) : page([CAND()], 1)), "GET /candidates/stats": STATS });
    renderApp(<CandidatesPage />, "/candidates");
    await screen.findByRole("link", { name: "Asha Verma" });
    await userEvent.selectOptions(screen.getByLabelText("Status"), "shortlisted");
    await waitFor(() => expect(calls.some((c) => c.path.includes("status=shortlisted"))).toBe(true));
    await userEvent.type(screen.getByLabelText("Search candidates"), "zzz");
    expect(await screen.findByText("No candidates match these filters", undefined, { timeout: 3000 })).toBeInTheDocument();
  });

  it("selecting rows offers bulk status change", async () => {
    const calls = mockApi({ "GET /candidates": page([CAND()], 1), "GET /candidates/stats": STATS, "POST /candidates/bulk": { succeeded: ["c1"], failed: [] } });
    renderApp(<CandidatesPage />, "/candidates");
    await screen.findByRole("link", { name: "Asha Verma" });
    await userEvent.click(screen.getByLabelText("Select all rows on this page"));
    const bar = screen.getByRole("region", { name: "Bulk actions" });
    await userEvent.selectOptions(within(bar).getByLabelText("Set status for selected"), "shortlisted");
    await waitFor(() => expect(calls.find((c) => c.path === "/candidates/bulk")!.body).toEqual({ ids: ["c1"], action: "set_status", value: "shortlisted" }));
  });

  it("viewers cannot add or import", async () => {
    mockApi({ "GET /candidates": page([CAND()], 1), "GET /candidates/stats": STATS }, { ...ME, role: "viewer" });
    renderApp(<CandidatesPage />, "/candidates");
    await screen.findByRole("link", { name: "Asha Verma" });
    expect(screen.getByRole("button", { name: /Add candidate/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Import file/ })).toBeDisabled();
  });
});

describe("add candidate form", () => {
  it("requires name, email and phone but nothing else", async () => {
    const calls = mockApi({ "GET /candidates": page([], 0), "GET /candidates/stats": STATS, "POST /candidates": CAND({ id: "new1" }), "GET /candidates/new1": CAND({ id: "new1" }) });
    renderApp(<CandidatesPage />, "/candidates?add=1");
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add candidate" }));
    expect(await within(dialog).findByText("Name is required")).toBeInTheDocument();
    expect(within(dialog).getByText("Email is required")).toBeInTheDocument();
    expect(within(dialog).getByText("Phone number is required")).toBeInTheDocument();
    expect(within(dialog).queryByText(/Surname is required|Skills is required|Location is required/)).not.toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/candidates")).toBe(false);
    await userEvent.type(within(dialog).getByLabelText(/^Email/), "not-an-email");
    await userEvent.type(within(dialog).getByLabelText(/^Phone/), "12");
    await userEvent.type(within(dialog).getByLabelText(/^Name/), "Asha");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add candidate" }));
    expect(await within(dialog).findByText("Enter a valid email address")).toBeInTheDocument();
    expect(within(dialog).getByText("Enter a phone number with at least 7 digits")).toBeInTheDocument();
    await userEvent.clear(within(dialog).getByLabelText(/^Email/));
    await userEvent.type(within(dialog).getByLabelText(/^Email/), "asha@example.com");
    await userEvent.clear(within(dialog).getByLabelText(/^Phone/));
    await userEvent.type(within(dialog).getByLabelText(/^Phone/), "+91 98765 43210");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add candidate" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.path === "/candidates")!.body).toMatchObject({
      first_name: "Asha", email: "asha@example.com", phone: "+91 98765 43210", last_name: null, total_experience: null, skills: [], status: "new" }));
  });
});

describe("import dialog", () => {
  const preview = { total_rows: 4, counts: { create: 2, update: 0, skip_duplicate: 1, skip_in_file: 0, error: 1 }, recognised_columns: ["first_name", "email", "phone"], ignored_columns: ["Favourite colour"],
    problems: [{ row: 3, name: "Ravi", email: null, action: "error", errors: ["email is required"], warnings: [], matched_name: null }, { row: 4, name: "Dup", email: "d@x.com", action: "skip_duplicate", errors: [], warnings: [], matched_name: "Asha Verma" }], sample: [], truncated: false };

  it("offers both templates, checks the file without saving, then imports", async () => {
    const calls = mockApi({ "GET /candidates": page([], 0), "GET /candidates/stats": STATS, "GET /candidates/imports": [], "POST /candidates/import/preview": preview,
      "POST /candidates/import": { id: "i1", filename: "c.csv", total_rows: 4, created: 2, updated: 0, skipped: 1, failed: 1, problems: [] } });
    renderApp(<CandidatesPage />, "/candidates?import=1");
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: /Excel template/ })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /CSV template/ })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Check file" })).toBeDisabled();
    const file = new File(["first_name,email,phone\nA,a@b.com,9876543210"], "c.csv", { type: "text/csv" });
    await userEvent.upload(within(dialog).getByTestId("candidate-file"), file);
    await userEvent.click(within(dialog).getByRole("button", { name: "Check file" }));
    expect(await within(dialog).findByText("2 to add")).toBeInTheDocument();
    expect(within(dialog).getByText("1 with errors")).toBeInTheDocument();
    expect(within(dialog).getByText("email is required")).toBeInTheDocument();
    expect(within(dialog).getByText(/Ignored columns: Favourite colour/)).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/candidates/import")).toBe(false); // the check saves nothing
    expect(calls.find((c) => c.path === "/candidates/import/preview")!.body).toMatchObject({ file: "file:c.csv", on_duplicate: "skip" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Import 2 candidates" }));
    expect(await within(dialog).findByText("Import finished")).toBeInTheDocument();
    expect(within(dialog).getByText(/2 added · 0 updated · 1 skipped · 1 failed/)).toBeInTheDocument();
  });

  it("blocks the import when no row is valid", async () => {
    mockApi({ "GET /candidates": page([], 0), "GET /candidates/stats": STATS, "GET /candidates/imports": [], "POST /candidates/import/preview": { ...preview, counts: { create: 0, update: 0, skip_duplicate: 0, skip_in_file: 0, error: 4 } } });
    renderApp(<CandidatesPage />, "/candidates?import=1");
    const dialog = await screen.findByRole("dialog");
    await userEvent.upload(within(dialog).getByTestId("candidate-file"), new File(["x"], "bad.csv", { type: "text/csv" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Check file" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("No rows can be imported");
    expect(within(dialog).getByRole("button", { name: "Import 0 candidates" })).toBeDisabled();
  });
});

describe("candidate detail", () => {
  it("shows the profile, changes status, and shows matching jobs with explanations", async () => {
    const calls = mockApi({
      "GET /candidates/c1": CAND(), "PATCH /candidates/c1": CAND({ status: "shortlisted" }), "GET /candidates/c1/notes": [{ id: "n1", kind: "note", body: "Called, interested", author: "Owner", created_at: "2026-10-02T10:00:00Z" }],
      "GET /candidates/c1/submissions": [], "GET /candidates/c1/matching-requirements": [{ requirement: { id: "r1", job_title: "Senior Python Developer", client_name: "Globex", location: "Bengaluru", work_mode: "onsite", minimum_experience: 5, maximum_experience: 8, required_skills: ["Python"] },
        score: 92, matched_skills: ["Python"], missing_skills: ["Kafka"], reasons: ["Has 3 of 4 required skills", "Experience fits (6 yrs vs 5-8)"], stage: null }],
    });
    renderApp(<Routes><Route path="/candidates/:id" element={<CandidateDetailPage />} /></Routes>, "/candidates/c1?tab=matches");
    expect(await screen.findByRole("heading", { name: "Asha Verma" })).toBeInTheDocument();
    expect(await screen.findByText("Senior Python Developer")).toBeInTheDocument();
    expect(screen.getByLabelText("Match score 92 out of 100")).toBeInTheDocument();
    expect(screen.getByText("Has 3 of 4 required skills")).toBeInTheDocument();
    expect(screen.getByText(/Missing: Kafka/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Candidate status"), "shortlisted");
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH" && c.path === "/candidates/c1")!.body).toEqual({ status: "shortlisted" }));
    await userEvent.click(screen.getByRole("tab", { name: /Notes/ }));
    expect(await screen.findByText("Called, interested")).toBeInTheDocument();
  });
});
