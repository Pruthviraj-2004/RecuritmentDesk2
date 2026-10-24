import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "Str0ngPassword!23";

async function login(page: Page, email = "owner@example.com") {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
}

test.describe.configure({ mode: "serial" });

test("1-2. logs in, rejects bad credentials, and shows real dashboard metrics", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/); // protected route
  await page.getByLabel("Email").fill("owner@example.com");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid email or password");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  // metrics come from the API: 4 unique requirements out of 9 emails across 2 accounts
  await expect(page.getByTestId("kpi-Unique requirements")).toHaveText("5");
  await expect(page.getByTestId("kpi-Connected accounts")).toHaveText("2");
  await expect(page.getByText("Recent activity")).toBeVisible();
  await page.screenshot({ path: "test-results/overview.png", fullPage: true });
});

test("3. requirements table: search, filter, clear, deep-link detail", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Recruitment Requirements" }).click();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(6); // header + 5 unique requirements
  await page.getByLabel("Search requirements", { exact: true }).last().fill("java");
  await expect(page.getByRole("row")).toHaveCount(3);
  await page.getByRole("button", { name: /Clear all/ }).click();
  await expect(page.getByRole("row")).toHaveCount(6);
  await page.getByLabel("Work mode").selectOption("remote");
  await expect(page.getByRole("row")).toHaveCount(2);
  await page.getByRole("button", { name: /Clear all/ }).click();
  await page.screenshot({ path: "test-results/requirements.png", fullPage: true });
});

test("4. reviews a duplicate candidate and keeps both", async ({ page }) => {
  await login(page);
  await page.goto("/duplicates");
  await expect(page.getByText(/% match/).first()).toBeVisible();
  await page.getByRole("button", { name: "Review" }).first().click();
  await expect(page.getByRole("heading", { name: "Compare possible duplicate" })).toBeVisible();
  await expect(page.getByText("Source emails")).toBeVisible();
  await page.screenshot({ path: "test-results/duplicate-compare.png" });
  await page.getByRole("button", { name: "Keep both" }).click();
  await expect(page.getByText("Kept both requirements")).toBeVisible();
  await expect(page.getByText("No duplicates waiting for review")).toBeVisible();
});

test("5. edits and approves a requirement", async ({ page }) => {
  await login(page);
  await page.goto("/requirements");
  await page.getByRole("link", { name: "Senior Python Developer" }).click();
  await expect(page.getByRole("heading", { name: "Senior Python Developer" })).toBeVisible();
  await page.getByRole("button", { name: "Edit" }).click();
  await page.getByLabel("Job title *").fill("Lead Python Developer");
  await page.getByLabel("Recruiter email").fill("not-an-email");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Enter a valid email address")).toBeVisible(); // client-side validation
  await page.getByLabel("Recruiter email").fill("jane@staffing.com");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("heading", { name: "Lead Python Developer" })).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Requirement approved")).toBeVisible();
  await page.getByRole("tab", { name: /Source emails/ }).click();
  await expect(page.getByText("work@gmail.com").first()).toBeVisible();
  await page.getByRole("tab", { name: "Versions" }).click();
  await expect(page.getByText("Manual Edit")).toBeVisible();
});

test("6. generates an Excel export and downloads it", async ({ page }) => {
  await login(page);
  await page.goto("/requirements?review_status=approved");
  await page.getByRole("button", { name: /^Export/ }).click();
  await page.getByLabel("Export scope").selectOption("approved");
  await page.getByLabel("File name").fill("e2e-report");
  await page.getByRole("button", { name: "Generate Excel file" }).click();
  await expect(page).toHaveURL(/\/exports/);
  await expect(page.getByText("e2e-report.xlsx")).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download" }).first().click()]);
  expect(download.suggestedFilename()).toBe("e2e-report.xlsx");
  await page.screenshot({ path: "test-results/exports.png", fullPage: true });
});

test("7. email composer validates and requires confirmation; nothing is sent", async ({ page }) => {
  await login(page);
  await page.goto("/exports?compose=1");
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Email an export" })).toBeVisible();
  await dialog.getByLabel("To").fill("not an address");
  await dialog.getByLabel("Subject").fill("Weekly requirements");
  await dialog.getByRole("button", { name: "Review & send" }).click();
  await expect(dialog.getByText(/valid recipient email/)).toBeVisible();
  await dialog.getByLabel("To").fill("client@example.com");
  await dialog.getByRole("button", { name: "Review & send" }).click();
  await expect(page.getByRole("heading", { name: "Send this email now?" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).last().click();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByText("No emails have been sent from RecruitmentDesk yet.")).toBeVisible();
});

test("8. connect Gmail flow returns to the app with a real result", async ({ page }) => {
  await login(page);
  await page.goto("/accounts");
  await expect(page.getByText("work@gmail.com").first()).toBeVisible();
  await page.getByRole("button", { name: "Connect Gmail" }).first().click();
  await expect(page.getByText("Gmail account connected")).toBeVisible();
  await expect(page.getByText("New Account")).toBeVisible();
  await page.getByRole("button", { name: "Sync now" }).first().click();
  await expect(page.getByText("Sync started")).toBeVisible();
  await page.screenshot({ path: "test-results/accounts.png", fullPage: true });
});

test("9. viewer role cannot perform write actions", async ({ page }) => {
  await login(page, "viewer@example.com");
  await page.goto("/requirements");
  await expect(page.getByRole("button", { name: "New requirement" })).toBeDisabled();
  await page.goto("/accounts");
  await expect(page.getByRole("button", { name: "Connect Gmail" }).first()).toBeDisabled();
  // the API enforces it too, not just the UI
  const res = await page.request.post("/api/v1/requirements", { data: { job_title: "x" } });
  expect(res.status()).toBe(403);
});

test("10. no Email Inbox module exists; theme toggle persists", async ({ page }) => {
  await login(page);
  await expect(page.getByRole("link", { name: "Email Inbox" })).toHaveCount(0);
  await page.goto("/emails");
  await expect(page.getByText("Page not found")).toBeVisible();
  await page.getByRole("button", { name: "Change theme" }).click();
  await page.getByRole("menuitem", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/dark/);
});

test("11. every screen loads without console errors and settings changes persist", async ({ page }) => {
  await login(page); // the unauthenticated /auth/me probe before sign-in legitimately returns 401, so listen afterwards
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  for (const [path, heading] of [["/", "Overview"], ["/requirements", "Recruitment Requirements"], ["/candidates", "Candidate Profiles"], ["/duplicates", "Duplicate Review"], ["/accounts", "Connected Accounts"],
    ["/sync-jobs", "Synchronization Jobs"], ["/exports", "Exports & Deliveries"], ["/audit", "Activity & Audit Logs"], ["/analytics", "Analytics"], ["/settings", "Settings"]]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading, exact: true }).first()).toBeVisible();
  }
  await page.getByRole("tab", { name: "Deduplication" }).click();
  await page.getByLabel(/Probable-duplicate threshold/).fill("0.8");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Settings saved")).toBeVisible();
  await page.reload();
  await page.getByRole("tab", { name: "Deduplication" }).click();
  await expect(page.getByLabel(/Probable-duplicate threshold/)).toHaveValue("0.8");
  await page.getByRole("tab", { name: "AI extraction" }).click();
  await expect(page.getByText("AI provider", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "System health" }).click();
  await expect(page.getByText("Healthy").first()).toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
});

test("12. mobile layout: no horizontal overflow and navigation drawer works", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 800 } });
  const page = await ctx.newPage();
  await login(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Duplicate Review" }).click();
  await expect(page.getByRole("heading", { name: "Duplicate Review" })).toBeVisible();
  await ctx.close();
});

test("13. add a candidate manually: name, email and phone are required, the rest is optional", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Candidate Profiles" }).click();
  await expect(page.getByRole("heading", { name: "Candidate Profiles" })).toBeVisible();
  await page.getByRole("button", { name: "Add candidate" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Add candidate" }).click();
  await expect(dialog.getByText("Name is required")).toBeVisible();
  await expect(dialog.getByText("Email is required")).toBeVisible();
  await expect(dialog.getByText("Phone number is required")).toBeVisible();
  await dialog.getByLabel(/^Name/).fill("Asha");
  await dialog.getByLabel(/^Email/).fill("asha.manual@example.com");
  await dialog.getByLabel(/^Phone/).fill("+91 98765 11111");
  await dialog.getByRole("button", { name: "Add candidate" }).click();
  await expect(page.getByRole("heading", { name: "Asha" })).toBeVisible();
  await expect(page.getByText("asha.manual@example.com")).toBeVisible();
  // a second profile with the same phone in another format is refused
  await page.goto("/candidates");
  await page.getByRole("button", { name: "Add candidate" }).first().click();
  const d2 = page.getByRole("dialog");
  await d2.getByLabel(/^Name/).fill("Copy");
  await d2.getByLabel(/^Email/).fill("copy@example.com");
  await d2.getByLabel(/^Phone/).fill("098765-11111");
  await d2.getByRole("button", { name: "Add candidate" }).click();
  await expect(page.getByText(/already exists with the same phone number/)).toBeVisible();
});

test("14. import candidates from a CSV file using the template, with a check step first", async ({ page }) => {
  await login(page);
  await page.goto("/candidates");
  await page.getByRole("button", { name: "Import file" }).click();
  const dialog = page.getByRole("dialog");
  const [download] = await Promise.all([page.waitForEvent("download"), dialog.getByRole("button", { name: /CSV template/ }).click()]);
  expect(download.suggestedFilename()).toBe("candidate-import-template.csv");
  const csv = [
    "first_name,last_name,email,phone,skills,total_experience_years,current_location,status",
    "Priya,Nair,priya@example.com,9811111111,Python;Django;AWS,6,Bengaluru,screening",
    "Karan,Shah,karan@example.com,9822222222,Java;Spring Boot,4,Pune,new",
    "NoPhone,Case,nophone@example.com,,Go,2,Delhi,new",
  ].join("\n");
  await dialog.getByTestId("candidate-file").setInputFiles({ name: "people.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await dialog.getByRole("button", { name: "Check file" }).click();
  await expect(dialog.getByText("2 to add")).toBeVisible();
  await expect(dialog.getByText("1 with errors")).toBeVisible();
  await expect(dialog.getByText("phone is required")).toBeVisible();
  await dialog.getByRole("button", { name: "Import 2 candidates" }).click();
  await expect(dialog.getByText("Import finished")).toBeVisible();
  await dialog.getByRole("button", { name: "Close", exact: true }).last().click(); // footer button (the corner X has the same name)
  await expect(page.getByRole("link", { name: "Priya Nair" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Karan Shah" })).toBeVisible();
  await expect(page.getByRole("link", { name: "NoPhone Case" })).toHaveCount(0);
  await page.getByLabel("Search candidates").fill("django");
  await expect(page.getByRole("link", { name: "Priya Nair" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Karan Shah" })).toHaveCount(0);
  const [xlsx] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /^Export/ }).click()]);
  expect(xlsx.suggestedFilename()).toMatch(/^candidates-.*\.xlsx$/);
});

test("15. matching: a requirement suggests candidates, and adding one creates a pipeline entry", async ({ page }) => {
  await login(page);
  await page.goto("/requirements");
  await page.getByRole("link", { name: "Lead Python Developer" }).click(); // renamed by test 5
  await page.getByRole("tab", { name: "Candidates" }).click();
  await expect(page.getByText("Priya Nair")).toBeVisible();   // Python, Django, AWS, 6 yrs, Bengaluru vs the job's needs
  await expect(page.getByText(/Has \d of \d required skills/).first()).toBeVisible();
  await page.locator("li").filter({ hasText: "Priya Nair" }).getByRole("button", { name: "Add to pipeline" }).click();
  await expect(page.getByText("Added to pipeline as shortlisted")).toBeVisible();
  await expect(page.getByLabel("Stage for Priya Nair")).toHaveValue("shortlisted");
  await page.getByLabel("Stage for Priya Nair").selectOption("interview");
  await expect(page.getByText("Stage updated")).toBeVisible();
  await page.goto("/candidates");
  await expect(page.getByText("1 in pipeline")).toBeVisible();
  await page.getByRole("link", { name: "Priya Nair" }).click();
  await page.getByRole("tab", { name: /Notes/ }).click();
  await expect(page.getByText(/Pipeline stage changed from shortlisted to interview/)).toBeVisible();
});

