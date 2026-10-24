import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SchedulesSection } from "@/features/settings/schedules";
import { setCsrfToken } from "@/lib/api";
import { mockApi, renderApp } from "@/test/utils";

const SCHED = { id: "s1", name: "Delta", enabled: true, recipients: ["a@example.com"], sender_email: "", mode: "delta", days: 7, frequency: "hours", interval_hours: 3, time_of_day: "09:00", timezone: "UTC" };

beforeEach(() => { vi.unstubAllGlobals(); setCsrfToken("t"); });

describe("scheduled emails", () => {
  it("lists schedules, adds a daily 'all requirements' one, and saves them together", async () => {
    const calls = mockApi({ "GET /settings/digest": { schedules: [SCHED] }, "PUT /settings/digest": { schedules: [] } });
    renderApp(<SchedulesSection />);
    expect(await screen.findByText(/Only new or changed requirements · every 3 hour/)).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Save changes" });
    expect(save).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /Add scheduled email/ }));
    const modes = screen.getAllByLabelText("What to send");
    await userEvent.selectOptions(modes[1], "all");
    await userEvent.selectOptions(screen.getAllByLabelText("When")[1], "daily");
    await userEvent.clear(screen.getByLabelText("Time of day"));
    await userEvent.type(screen.getByLabelText("Time of day"), "09:00");
    await userEvent.type(screen.getAllByLabelText("Recipients")[1], "boss@example.com");
    await userEvent.click(save);
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")).toBeTruthy());
    const sent = (calls.find((c) => c.method === "PUT")!.body as { values: { schedules: { mode: string; frequency: string; recipients: string; time_of_day: string }[] } }).values.schedules;
    expect(sent).toHaveLength(2);
    expect(sent[1]).toMatchObject({ mode: "all", frequency: "daily", recipients: "boss@example.com", time_of_day: "09:00" });
  });

  it("deletes a schedule", async () => {
    const calls = mockApi({ "GET /settings/digest": { schedules: [SCHED] }, "PUT /settings/digest": { schedules: [] } });
    renderApp(<SchedulesSection />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete Delta" }));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect((calls.find((c) => c.method === "PUT")!.body as { values: { schedules: unknown[] } }).values.schedules).toHaveLength(0));
  });
});

describe("test button", () => {
  it("sends a test for a saved schedule and is disabled while there are unsaved changes", async () => {
    const calls = mockApi({ "GET /settings/digest": { schedules: [SCHED] }, "POST /settings/digest/s1/test": { status: "accepted_by_gmail", count: 3, sample: false, sender: "me@gmail.com", recipients: ["a@example.com"] } });
    renderApp(<SchedulesSection />);
    const btn = await screen.findByRole("button", { name: "Send test for Delta" });
    await userEvent.click(btn);
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/settings/digest/s1/test")).toBe(true));
    expect(await screen.findByText(/Test email sent from me@gmail.com to a@example.com with 3 requirements/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Name (used as the email subject)"), "x");
    expect(screen.getByRole("button", { name: "Send test for Deltax" })).toBeDisabled();
  });
});
