import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CandidateDetailPage } from "@/features/candidates/candidate-detail-page";
import { setCsrfToken } from "@/lib/api";
import { ME, mockApi, renderApp } from "@/test/utils";

const CAND = (o: Record<string, unknown> = {}) => ({
  id: "c1", first_name: "Priya", last_name: "Nair", full_name: "Priya Nair", email: "priya@example.com", phone: "9876543210", current_title: null, current_company: null, total_experience: null, relevant_experience: null,
  current_location: null, preferred_locations: [], willing_to_relocate: null, notice_period: null, current_ctc: null, expected_ctc: null, currency: null, education: null, certifications: [], work_authorization: null,
  linkedin_url: "https://www.linkedin.com/in/priya", resume_url: null, summary: null, source: "manual", status: "new", rating: null, tags: [], skills: ["Excel"], is_archived: false, last_contacted_at: null,
  created_at: "2026-10-01T09:00:00Z", updated_at: "2026-10-01T09:00:00Z", pipeline_count: 0, ...o,
});

const REC = {
  id: "p1", created_at: "2026-10-20T10:00:00Z", source_type: "linkedin_text", source_label: "LinkedIn text", provider: "openai_compatible", model: "test-model", prompt_version: "p1", applied_fields: [], applied_at: null,
  result: {
    profile: {
      headline: "Senior Backend Engineer | Python | AWS", ai_summary: "Backend engineer with about ten years in fintech platforms.", current_title: "Senior Backend Engineer", current_company: "Globex", location: "Bengaluru, India",
      seniority: "senior", industries: ["Fintech"], skills: ["Python", "Django", "AWS", "Docker"], top_skills: ["Python", "AWS"],
      positions: [{ company: "Globex", title: "Senior Backend Engineer", start: "2022-01", end: "present", location: null, description: "Led the migration to microservices.", skills_used: ["AWS"] },
        { company: "Initech", title: "Backend Engineer", start: "2019-03", end: "2021-12", location: null, description: null, skills_used: [] }],
      education: [{ school: "NIT Calicut", degree: "B.Tech", field: "Computer Science", start_year: 2012, end_year: 2016 }], certifications: ["AWS Certified Solutions Architect"],
      projects: [{ name: "Payments Gateway", description: "Unified payments API.", technologies: ["Python"], url: null }], languages: ["English"], honors: [], links: [], contact_email: null, contact_phone: null,
      career_highlights: ["Led a monolith to microservices migration"], screening_questions: ["How did you size the microservices split?"],
    },
    analytics: { total_experience_years: 10.4, employers: 2, roles: 2, average_tenure_months: 42, longest_tenure: { company: "Globex", months: 58 }, recent_companies: ["Globex", "Initech"], employers_last_5_years: 2,
      short_stints: [], gaps: [], currently_employed: true, undated_roles: 0 },
    verify: ["Employment gap of 8 months between 2021-12 and 2022-09"], warnings: [],
  },
};

const AI_ON = { provider: "openai_compatible", model: "m", configured: true, base_url_host: "ai.example.test", message: null };
const base = { "GET /candidates/c1": CAND(), "GET /candidates/c1/ai-profiles": [], "GET /settings-meta/ai": AI_ON };

function show(extra: Record<string, unknown>, me = ME) {
  const calls = mockApi({ ...base, ...extra }, me);
  renderApp(<Routes><Route path="/candidates/:id" element={<CandidateDetailPage />} /></Routes>, "/candidates/c1?tab=ai");
  return calls;
}

beforeEach(() => { vi.unstubAllGlobals(); setCsrfToken(null); });

describe("AI profile tab", () => {
  it("explains why the URL is not fetched, links to LinkedIn, and only enables Extract with enough content", async () => {
    show({ "GET /candidates/c1/ai-profile": { profile: null } });
    expect(await screen.findByText(/never opens the link itself/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open on LinkedIn/ })).toHaveAttribute("href", "https://www.linkedin.com/in/priya");
    expect(await screen.findByText("No AI profile yet")).toBeInTheDocument();
    const btn = screen.getByRole("button", { name: /Extract with AI/ });
    expect(btn).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Or paste the text/), "short");
    expect(screen.getByText(/at least 200 needed/)).toBeInTheDocument();
    expect(btn).toBeDisabled();
    await userEvent.click(screen.getByLabelText(/Or paste the text/));
    await userEvent.paste("x".repeat(250));
    await waitFor(() => expect(btn).toBeEnabled());
  });

  it("runs the extraction only on request, then shows summary, key facts, experience timeline and things to verify", async () => {
    const calls = show({ "GET /candidates/c1/ai-profile": { profile: null }, "POST /candidates/c1/ai-profile": REC, "GET /candidates/c1/ai-profiles/p1": REC });
    await screen.findByText("No AI profile yet");
    await userEvent.click(screen.getByLabelText(/Or paste the text/));
    await userEvent.paste("Priya Nair profile text ".repeat(20));
    expect(calls.some((c) => c.method === "POST" && c.path.includes("ai-profile"))).toBe(false); // nothing runs until the user asks
    await userEvent.click(screen.getByRole("button", { name: /Extract with AI/ }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.path === "/candidates/c1/ai-profile")!.body).toMatchObject({ source: "linkedin_text" }));
    expect(await screen.findByText("Backend engineer with about ten years in fintech platforms.")).toBeInTheDocument();
    expect(screen.getByText("10.4 years")).toBeInTheDocument();
    expect(screen.getByText(/Jan 2022 – Present/)).toBeInTheDocument();
    expect(screen.getByText(/Mar 2019 – Dec 2021/)).toBeInTheDocument();
    expect(screen.getByText(/Employment gap of 8 months/)).toBeInTheDocument();
    expect(screen.getByText(/not a judgement about the person/)).toBeInTheDocument();
    expect(screen.getByText("How did you size the microservices split?")).toBeInTheDocument();
    expect(screen.getByText("AI-generated")).toBeInTheDocument();
    expect(screen.getByText("Payments Gateway")).toBeInTheDocument();
  });

  it("apply dialog leaves already-filled fields unticked and posts exactly the chosen fields", async () => {
    const calls = show({ "GET /candidates/c1": CAND({ current_title: "Old title" }), "GET /candidates/c1/ai-profile": { profile: REC }, "POST /candidates/c1/ai-profiles/p1/apply": { applied: ["company"], candidate: CAND() } });
    await userEvent.click(await screen.findByRole("button", { name: /Apply to profile/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText(/Current title/)).not.toBeChecked(); // "Old title" is kept unless the user opts in
    expect(within(dialog).getByLabelText(/Current company/)).toBeChecked();
    expect(within(dialog).getByLabelText(/Skills/)).toBeChecked();
    expect(within(dialog).getByText(/Name, email and phone are never changed/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByLabelText(/Current company/)); // untick one
    await userEvent.click(within(dialog).getByRole("button", { name: /^Apply \d+ fields?$/ }));
    await waitFor(() => {
      const body = calls.find((c) => c.path.endsWith("/apply"))!.body as { fields: string[] };
      expect(body.fields).not.toContain("title");
      expect(body.fields).not.toContain("company");
      expect(body.fields).toEqual(expect.arrayContaining(["skills", "certifications", "location", "experience", "summary", "education"]));
    });
  });

  it("shows a clear message when AI is not configured and blocks viewers from running or applying", async () => {
    show({ "GET /candidates/c1/ai-profile": { profile: null }, "GET /settings-meta/ai": { provider: "none", model: null, configured: false, base_url_host: null, message: "No AI provider configured." } });
    expect(await screen.findByRole("alert")).toHaveTextContent("No AI provider configured.");
    expect(screen.getByRole("button", { name: /Extract with AI/ })).toBeDisabled();
  });

  it("viewers can read an existing AI profile but cannot run or apply it", async () => {
    show({ "GET /candidates/c1/ai-profile": { profile: REC } }, { ...ME, role: "viewer" });
    await screen.findByText("AI-generated");
    expect(screen.getByRole("button", { name: /Extract with AI/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Apply to profile/ })).toBeDisabled();
  });
});
