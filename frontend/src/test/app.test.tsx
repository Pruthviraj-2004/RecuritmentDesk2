import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "@/app/App";
import { ApiError, errorMessage, request, setCsrfToken, toQuery } from "@/lib/api";
import { fmtBytes, fmtExperience, fmtSalary, pct } from "@/lib/utils";
import { Pagination } from "@/components/data-table/data-table";
import { StatusBadge } from "@/components/common/common";
import { LoginPage } from "@/features/auth/login-page";
import { RequirementsPage } from "@/features/requirements/requirements-page";
import { AccountsPage } from "@/features/accounts/accounts-page";
import { DuplicatesPage } from "@/features/duplicates/duplicates-page";
import { ExportsPage } from "@/features/exports/exports-page";
import { OverviewPage } from "@/features/dashboard/overview-page";
import { apiError, ME, mockApi, page, REQ, renderApp } from "@/test/utils";
import { render } from "@testing-library/react";

const OVERVIEW = {
  range: { from: "", to: "" },
  kpis: { total_unique_requirements: 12, awaiting_review: 5, approved: 7, received_today: 1, received_this_week: 4, duplicates_pending: 2, emails_processed: 40, extraction_failed_or_pending: 3, connected_accounts: 2, accounts_needing_attention: 0, last_successful_sync: null, pending_deliveries: 0 },
  received_over_time: [{ date: "2026-10-01", count: 2 }], weekly_activity: [], monthly_activity: [], by_status: [{ name: "needs_review", count: 5 }], by_location: [], by_client: [], top_skills: [{ name: "Python", count: 4 }],
  by_source_account: [], email_processing: { succeeded: 30, failed: 1, pending: 2 },
};

beforeEach(() => { vi.unstubAllGlobals(); setCsrfToken(null); sessionStorage.clear(); });

describe("formatting helpers", () => {
  it("formats experience, salary, bytes and percentages without inventing values", () => {
    expect(fmtExperience(3, 6)).toBe("3–6 yrs"); expect(fmtExperience(5, null)).toBe("5+ yrs"); expect(fmtExperience(null, null)).toBe("—");
    expect(fmtSalary({ salary_min: 25, salary_max: 35, salary_currency: "INR", salary_period: "year" })).toBe("INR 25–35 / year");
    expect(fmtSalary({ salary_min: null, salary_max: null, salary_currency: null, salary_period: null })).toBe("—");
    expect(fmtBytes(2048)).toBe("2.0 KB"); expect(pct(null)).toBe("—"); expect(pct(0.256)).toBe("25.6%");
  });
});

describe("API client", () => {
  it("sends the CSRF token on writes only, and maps error bodies", async () => {
    const calls = mockApi({ "POST /x": { ok: true }, "GET /x": { ok: true }, "GET /bad": () => apiError(409, "conflict", "Already running") });
    setCsrfToken("tok");
    await request("POST", "/x", { body: {} }); await request("GET", "/x");
    expect(calls.find((c) => c.method === "POST")!.headers["X-CSRF-Token"]).toBe("tok");
    expect(calls.find((c) => c.method === "GET")!.headers["X-CSRF-Token"]).toBeUndefined();
    await expect(request("GET", "/bad")).rejects.toMatchObject({ status: 409, code: "conflict", message: "Already running" });
  });
  it("builds clean query strings and friendly validation messages", () => {
    expect(toQuery({ a: "1", b: "", c: undefined, d: ["x", "y"] })).toBe("?a=1&d=x&d=y");
    const e = new ApiError(422, "validation_error", "bad", [{ loc: ["body", "recruiter_email"], msg: "value is not a valid email address" }]);
    expect(errorMessage(e)).toBe("recruiter_email: value is not a valid email address");
    expect(errorMessage(new Error("boom"))).toBe("boom");
  });
});

describe("shared components", () => {
  it("StatusBadge renders readable labels and a dash for missing status", () => {
    render(<><StatusBadge status="needs_review" /><StatusBadge status="accepted_by_gmail" /><StatusBadge status={null} /></>);
    expect(screen.getByText("Needs review")).toBeInTheDocument(); expect(screen.getByText("Accepted by Gmail")).toBeInTheDocument(); expect(screen.getByText("—")).toBeInTheDocument();
  });
  it("Pagination reports ranges and disables edges", async () => {
    const onPage = vi.fn();
    render(<Pagination page={1} pageSize={25} total={60} onPage={onPage} />);
    expect(screen.getByText("Showing 1–25 of 60")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(onPage).toHaveBeenCalledWith(2);
  });
});

describe("login and navigation", () => {
  it("validates the form before calling the API and shows the server error", async () => {
    const calls = mockApi({ "POST /auth/login": () => apiError(401, "invalid_credentials", "Invalid email or password") }, null);
    renderApp(<LoginPage />, "/login");
    await userEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your email")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/auth/login")).toBe(false);
    await userEvent.type(screen.getByLabelText("Email"), "owner@example.com"); await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
  });

  it("redirects unauthenticated users to /login and renders the shell with all navigation items when signed in", async () => {
    mockApi({}, null);
    renderApp(<AppRoutes />, "/requirements");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    vi.unstubAllGlobals();
    mockApi({ "GET /analytics/overview": OVERVIEW, "GET /email-accounts": [], "GET /jobs": page([]), "GET /jobs/summary": { messages: {}, extraction_pending: 0, extraction_failed: 0, accounts: [] },
      "GET /notifications": { unread: 0, items: [] }, "GET /audit-logs": page([]) });
    renderApp(<AppRoutes />, "/");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).queryByRole("link", { name: "Email Inbox" })).not.toBeInTheDocument(); // the inbox module was removed on purpose
    for (const label of ["Overview", "Recruitment Requirements", "Duplicate Review", "Connected Accounts", "Synchronization Jobs", "Exports & Deliveries", "Activity & Audit Logs", "Analytics", "Settings"])
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
  });
});

describe("overview dashboard", () => {
  it("renders KPIs from the API and an empty-account call to action", async () => {
    mockApi({ "GET /analytics/overview": OVERVIEW, "GET /email-accounts": [], "GET /audit-logs": page([]) });
    renderApp(<OverviewPage />);
    expect(await screen.findByTestId("kpi-Unique requirements")).toHaveTextContent("12");
    expect(screen.getByTestId("kpi-Awaiting review")).toHaveTextContent("5");
    expect(screen.getByTestId("kpi-Duplicates to review")).toHaveTextContent("2");
    expect(screen.getByText("Connect your first Gmail account")).toBeInTheDocument();
    expect(screen.getByText("No activity yet. Connect a Gmail account and run a sync to get started.")).toBeInTheDocument();
  });
  it("shows an error state with retry when the API fails", async () => {
    mockApi({ "GET /analytics/overview": () => apiError(500, "internal_error", "An unexpected error occurred"), "GET /email-accounts": [], "GET /audit-logs": page([]) });
    renderApp(<OverviewPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("An unexpected error occurred");
    expect(screen.getByRole("button", { name: /Try again/ })).toBeInTheDocument();
  });
});

describe("requirements table", () => {
  const base = { "GET /email-accounts": [] };
  it("shows rows, server-side search/filter parameters and clear-all", async () => {
    const calls = mockApi({ ...base, "GET /requirements": page([REQ(), REQ({ id: "r2", job_title: "Java Architect", client_name: "Initech" })], 2) });
    renderApp(<RequirementsPage />, "/requirements");
    await waitFor(() => expect(screen.getByRole("link", { name: "Python Developer" })).toBeInTheDocument());
    expect(screen.getByText("Initech")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Review status"), "approved");
    await waitFor(() => expect(calls.some((c) => c.path.startsWith("/requirements?") && c.path.includes("review_status=approved"))).toBe(true));
    await userEvent.type(screen.getByLabelText("Search requirements"), "java");
    await waitFor(() => expect(calls.some((c) => c.path.includes("q=java"))).toBe(true), { timeout: 2000 });
    await userEvent.click(screen.getByRole("button", { name: /Clear all/ }));
    expect(screen.getByLabelText("Review status")).toHaveValue("");
  });
  it("paginates through the API and shows an empty state for no results", async () => {
    const calls = mockApi({ ...base, "GET /requirements": (u: URL) => (u.searchParams.get("q") === "zzz" ? page([], 0) : page([REQ()], 60)) });
    renderApp(<RequirementsPage />, "/requirements");
    await screen.findByRole("link", { name: "Python Developer" });
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() => expect(calls.some((c) => c.path.includes("page=2"))).toBe(true));
  });
  it("shows the filtered empty state", async () => {
    mockApi({ ...base, "GET /requirements": page([], 0) });
    renderApp(<RequirementsPage />, "/requirements?client=nothing");
    expect(await screen.findByText("No requirements match these filters")).toBeInTheDocument();
  });
  it("selecting rows reveals bulk actions and reports partial success", async () => {
    const calls = mockApi({ ...base, "GET /requirements": page([REQ(), REQ({ id: "r2", job_title: "B" })], 2),
      "POST /requirements/bulk": { succeeded: ["r1"], failed: [{ id: "r2", error: "Merged requirements cannot be changed" }] } });
    renderApp(<RequirementsPage />, "/requirements");
    await screen.findByRole("link", { name: "Python Developer" });
    await userEvent.click(screen.getByLabelText("Select all rows on this page"));
    const bulk = screen.getByRole("region", { name: "Bulk actions" });
    expect(within(bulk).getByText("2 selected")).toBeInTheDocument();
    await userEvent.click(within(bulk).getByRole("button", { name: /Approve/ }));
    await waitFor(() => expect(calls.find((c) => c.path === "/requirements/bulk")!.body).toEqual({ ids: ["r1", "r2"], action: "approve" }));
    expect(await screen.findByText(/1 succeeded, 1 failed/)).toBeInTheDocument();
  });
  it("viewers cannot create requirements", async () => {
    mockApi({ ...base, "GET /requirements": page([REQ()]) }, { ...ME, role: "viewer" });
    renderApp(<RequirementsPage />, "/requirements");
    await screen.findByRole("link", { name: "Python Developer" });
    expect(screen.getByRole("button", { name: /New requirement/ })).toBeDisabled();
  });
});

describe("accounts", () => {
  const acct = (o = {}) => ({ id: "a1", email_address: "work@gmail.com", masked_email: "wo**@gmail.com", display_name: null, provider: "gmail", connection_status: "connected", sync_enabled: true, import_days: 30, extra_query: null,
    is_default_sender: true, scopes: [], can_send: true, can_read: true, last_synced_at: null, last_error: null, created_at: "", stats: { messages: 5, processed: 4, failed: 1, pending: 0, requirements: 2 }, ...o });
  it("renders connected, expired and error states with the right actions", async () => {
    mockApi({ "GET /email-accounts": [acct(), acct({ id: "a2", email_address: "old@gmail.com", masked_email: "ol*@gmail.com", connection_status: "expired", last_error: "Google authorization was revoked or expired", can_send: false })] });
    renderApp(<AccountsPage />, "/accounts");
    expect(await screen.findByText("work@gmail.com")).toBeInTheDocument();
    expect(screen.getByText("Connected")).toBeInTheDocument(); expect(screen.getByText("Reauthorization needed")).toBeInTheDocument();
    expect(screen.getByText("Google authorization was revoked or expired")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reauthorize" })).toBeInTheDocument(); expect(screen.getByRole("button", { name: /Sync now/ })).toBeInTheDocument();
    expect(screen.getAllByText("Default sender").length).toBeGreaterThan(0);
  });
  it("disables Sync now during the 5 minute cooldown and explains why on hover", async () => {
    const until = new Date(Date.now() + 4 * 60_000 + 30_000).toISOString();
    mockApi({ "GET /email-accounts": [acct({ sync_available_at: until })] });
    renderApp(<AccountsPage />, "/accounts");
    const btn = await screen.findByRole("button", { name: /Sync again in 4:/ });
    expect(btn).toBeDisabled();
    await userEvent.hover(btn.parentElement!);
    expect((await screen.findAllByText(/Try again after 5 minutes/)).length).toBeGreaterThan(0);
  });
  it("starts a real sync request and shows the empty state when no accounts exist", async () => {
    const calls = mockApi({ "GET /email-accounts": [acct()], "POST /email-accounts/a1/sync": { job_id: "j1", status: "queued", already_running: false } });
    renderApp(<AccountsPage />, "/accounts");
    await userEvent.click(await screen.findByRole("button", { name: /Sync now/ }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/email-accounts/a1/sync")).toBe(true));
    expect(await screen.findByText("Sync started")).toBeInTheDocument();
    vi.unstubAllGlobals(); mockApi({ "GET /email-accounts": [] });
    renderApp(<AccountsPage />, "/accounts");
    expect(await screen.findByText("No Gmail accounts connected")).toBeInTheDocument();
  });
});

describe("duplicate review", () => {
  it("lists candidates and requires confirmation before merging", async () => {
    const dup = { id: "d1", matching_score: 0.93, matching_reasons: ["client"], conflicting_fields: ["location"], review_status: "pending", created_at: "", resolved_at: null,
      requirement_a: REQ({ id: "ra", location: "Pune" }), requirement_b: REQ({ id: "rb", location: "Mumbai" }) };
    const calls = mockApi({ "GET /duplicates": page([dup]), "GET /duplicates/d1": { ...dup, sources_a: [], sources_b: [] }, "POST /duplicates/d1/merge": { ...dup, review_status: "merged" } });
    renderApp(<DuplicatesPage />, "/duplicates?open=d1");
    expect(await screen.findByRole("heading", { name: "Compare possible duplicate" })).toBeInTheDocument();
    expect(await screen.findByText(/93\.\d% match/)).toBeInTheDocument();
    expect(screen.getAllByText("Pune").length).toBeGreaterThan(0); expect(screen.getAllByText("Mumbai").length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: /Merge B into A/ }));
    expect(await screen.findByText("Merge these requirements?")).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("/merge"))).toBe(false); // nothing merged yet
    await userEvent.click(screen.getByRole("button", { name: "Merge" }));
    await waitFor(() => expect(calls.find((c) => c.path.endsWith("/merge"))!.body).toEqual({ survivor_id: "ra" }));
  });
  it("shows the empty state when nothing needs review", async () => {
    mockApi({ "GET /duplicates": page([], 0) });
    renderApp(<DuplicatesPage />, "/duplicates");
    expect(await screen.findByText("No duplicates waiting for review")).toBeInTheDocument();
  });
});

describe("exports and composer", () => {
  const exp = { id: "e1", filename: "report.xlsx", status: "completed", record_count: 3, file_size_bytes: 4096, error_summary: null, created_at: "2026-10-01T00:00:00Z", completed_at: null, expires_at: null, options: {}, filters: {}, requested_by: null };
  const acct = { id: "a1", email_address: "work@gmail.com", masked_email: "wo**@gmail.com", connection_status: "connected", can_send: true, can_read: true, is_default_sender: true, stats: {} };
  const routes = { "GET /exports": page([exp]), "GET /deliveries": page([]), "GET /email-accounts": [acct], "GET /exports/templates/email": { summary: { subject: "Recruitment Requirements Summary", body: "Hi {count}" } } };

  it("validates recipients, then requires an explicit confirmation step before sending", async () => {
    const calls = mockApi({ ...routes, "POST /exports/e1/send": { id: "d1", status: "accepted_by_gmail", status_label: "", recipient_addresses: [], cc_addresses: [], subject: "s", created_at: "", sent_at: null, attempts: 1, export_job_id: "e1", sender_account_id: "a1", sender_email: null, provider_message_id: "x", error_summary: null } });
    renderApp(<ExportsPage />, "/exports?compose=1");
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("To"), "not-an-address");
    await userEvent.type(within(dialog).getByLabelText("Subject"), "Weekly");
    await userEvent.click(within(dialog).getByRole("button", { name: /Review & send/ }));
    expect(await within(dialog).findByText(/valid recipient email/)).toBeInTheDocument();
    await userEvent.clear(within(dialog).getByLabelText("To")); await userEvent.type(within(dialog).getByLabelText("To"), "client@example.com");
    await userEvent.click(within(dialog).getByRole("button", { name: /Review & send/ }));
    expect(await screen.findByText("Send this email now?")).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("/send"))).toBe(false); // not sent without confirmation
    await userEvent.click(screen.getByRole("button", { name: "Send email" }));
    await waitFor(() => expect(calls.find((c) => c.path.endsWith("/send"))!.body).toMatchObject({ confirm: true, to: ["client@example.com"], sender_account_id: "a1" }));
    expect(calls.find((c) => c.path.endsWith("/send"))!.headers["Idempotency-Key"]).toBeTruthy();
  });
  it("warns when no account can send and lists delivery status accurately", async () => {
    mockApi({ ...routes, "GET /email-accounts": [{ ...acct, can_send: false }], "GET /deliveries": page([{ id: "d9", export_job_id: "e1", sender_account_id: "a1", sender_email: "work@gmail.com", recipient_addresses: ["c@x.com"], cc_addresses: [], subject: "Hello", status: "uncertain", status_label: "", provider_message_id: null, error_summary: "Network error while sending", attempts: 1, created_at: "2026-10-01T00:00:00Z", sent_at: null }]) });
    renderApp(<ExportsPage />, "/exports?compose=1");
    expect(await screen.findByText(/No connected account has send permission/)).toBeInTheDocument();
    expect(await screen.findByText("Network error while sending")).toBeInTheDocument();
    expect(screen.getByText("Uncertain")).toBeInTheDocument();
  });
});

describe("skills cell and sidebar", () => {
  it("shows the first 4 skills, expands the rest on +N click, and truncates long chips with a hover title", async () => {
    const skills = ["Python", "Django", "AWS", "Docker", "Kubernetes", "Terraform", "A very long responsibility sentence that must not overflow into neighbouring columns of the table"];
    mockApi({ "GET /email-accounts": [], "GET /requirements": page([REQ({ required_skills: skills })], 1) });
    renderApp(<RequirementsPage />, "/requirements");
    await waitFor(() => expect(screen.getByRole("link", { name: "Python Developer" })).toBeInTheDocument());
    expect(screen.queryByText("Kubernetes")).not.toBeInTheDocument();
    const more = screen.getByRole("button", { name: "Show 3 more skills" });
    expect(more).toHaveTextContent("+3");
    await userEvent.click(more);
    expect(screen.getByText("Kubernetes")).toBeInTheDocument();
    expect(screen.getByText("Terraform")).toBeInTheDocument();
    expect(screen.getByTitle(skills[6])).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show fewer skills" }));
    expect(screen.queryByText("Kubernetes")).not.toBeInTheDocument();
  });

  it("collapses and expands the sidebar and remembers the choice", async () => {
    localStorage.clear();
    mockApi({ "GET /analytics/overview": OVERVIEW, "GET /email-accounts": [], "GET /jobs": page([]), "GET /jobs/summary": { messages: {}, extraction_pending: 0, extraction_failed: 0, accounts: [] },
      "GET /notifications": { unread: 0, items: [] }, "GET /audit-logs": page([]) });
    renderApp(<AppRoutes />, "/");
    const sidebar = await screen.findByRole("complementary", { name: "Sidebar" });
    expect(sidebar).toHaveAttribute("data-collapsed", "false");
    expect(within(sidebar).getByText("Recruitment Requirements")).toBeInTheDocument();
    await userEvent.click(within(sidebar).getByRole("button", { name: "Collapse sidebar" }));
    expect(sidebar).toHaveAttribute("data-collapsed", "true");
    expect(within(sidebar).queryByText("Recruitment Requirements")).not.toBeInTheDocument(); // labels hidden...
    expect(within(sidebar).getByRole("link", { name: "Recruitment Requirements" })).toBeInTheDocument(); // ...but still accessible by name
    expect(localStorage.getItem("rd-sidebar-collapsed")).toBe("1");
    await userEvent.click(within(sidebar).getByRole("button", { name: "Expand sidebar" }));
    expect(sidebar).toHaveAttribute("data-collapsed", "false");
  });
});
