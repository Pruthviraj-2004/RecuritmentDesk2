import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RequirementImportDialog } from "@/features/requirements/import-dialog";
import { setCsrfToken } from "@/lib/api";
import { mockApi, renderApp } from "@/test/utils";

const PREVIEW = {
  total_rows: 4, counts: { create: 2, update: 0, skip_duplicate: 1, skip_in_file: 0, error: 1 }, recognised_columns: ["job_title", "client_name"], ignored_columns: ["Notes"],
  problems: [{ row: 3, title: "Java Architect", client: "Initech", action: "skip_duplicate", errors: [], warnings: [], matched: "Java Architect at Initech" },
    { row: 4, title: "", client: null, action: "error", errors: ["job_title is required"], warnings: [] }], sample: [], truncated: false,
};

beforeEach(() => { vi.unstubAllGlobals(); setCsrfToken("t"); });

describe("requirement import dialog", () => {
  it("offers the sample files, checks the file without saving, then imports", async () => {
    const calls = mockApi({ "POST /requirements/import/preview": PREVIEW, "POST /requirements/import": { filename: "jobs.xlsx", total_rows: 4, created: 2, updated: 0, skipped: 1, failed: 1, problems: [] } });
    renderApp(<RequirementImportDialog open onOpenChange={() => {}} />);
    expect(screen.getByRole("button", { name: /Excel sample/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /CSV sample/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check file" })).toBeDisabled();
    await userEvent.upload(screen.getByTestId("requirement-file"), new File(["x"], "jobs.xlsx"));
    await userEvent.click(screen.getByRole("button", { name: "Check file" }));
    expect(await screen.findByText("2 to add")).toBeInTheDocument();
    expect(screen.getByText("1 already exist (skipped)")).toBeInTheDocument();
    expect(screen.getByText(/job_title is required/)).toBeInTheDocument();
    expect(screen.getByText(/Ignored columns: Notes/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/requirements/import")).toBe(false); // the check saved nothing
    await userEvent.click(screen.getByRole("button", { name: "Import 2 requirements" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/requirements/import")!.body).toMatchObject({ file: "file:jobs.xlsx", on_duplicate: "skip", mark_approved: "true" }));
    expect(await screen.findByText(/2 added · 0 updated · 1 skipped · 1 failed/)).toBeInTheDocument();
  });

  it("changing an option clears a stale check so the preview always matches what will be imported", async () => {
    mockApi({ "POST /requirements/import/preview": PREVIEW });
    renderApp(<RequirementImportDialog open onOpenChange={() => {}} />);
    await userEvent.upload(screen.getByTestId("requirement-file"), new File(["x"], "jobs.csv"));
    await userEvent.click(screen.getByRole("button", { name: "Check file" }));
    await screen.findByText("2 to add");
    await userEvent.selectOptions(screen.getByLabelText(/If the job already exists/), "update");
    expect(screen.queryByText("2 to add")).not.toBeInTheDocument();
  });
});
