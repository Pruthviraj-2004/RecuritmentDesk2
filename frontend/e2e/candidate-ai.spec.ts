import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "Str0ngPassword!23";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("owner@example.com");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
}

const PROFILE = [
  "Meera Kapoor",
  "Lead Engineer at Zeta Labs (Sep 2022 - Present). Leads a payments platform team and mentors junior engineers.",
  "Engineer at Yotta Systems (Mar 2019 - Dec 2021). Built Python services and data pipelines for retail clients.",
  "Education: B.Tech, NIT Calicut",
  "Skills: Python, Django, AWS, PostgreSQL",
  "Certifications: AWS Certified Developer",
  "Profile copied from LinkedIn by the recruiter for this demo run.",
].join("\n");

test("AI profile: paste LinkedIn text, extract on request, review the result, apply it to the candidate", async ({ page }) => {
  await login(page);
  const csrf = ((await (await page.request.get("/api/v1/auth/me")).json()) as { csrf_token: string }).csrf_token;
  const created = await page.request.post("/api/v1/candidates", {
    headers: { "X-CSRF-Token": csrf },
    data: { first_name: "Meera", last_name: "Kapoor", email: "meera.ai@example.com", phone: "9855500001", linkedin_url: "https://www.linkedin.com/in/meera-kapoor-demo" },
  });
  expect(created.status()).toBe(201);
  const id = ((await created.json()) as { id: string }).id;

  await page.goto(`/candidates/${id}?tab=ai`);
  await expect(page.getByText(/never opens the link itself/)).toBeVisible();
  await expect(page.getByRole("link", { name: /open on LinkedIn/ })).toHaveAttribute("href", "https://www.linkedin.com/in/meera-kapoor-demo");
  await expect(page.getByRole("button", { name: /Extract with AI/ })).toBeDisabled();
  await page.getByLabel(/Or paste the text/).fill(PROFILE);
  await page.getByRole("button", { name: /Extract with AI/ }).click();

  await expect(page.getByText("AI-generated")).toBeVisible();
  await expect(page.getByText("Lead Engineer at Zeta Labs").first()).toBeVisible();
  await expect(page.getByText("Sep 2022 – Present")).toBeVisible();
  await expect(page.getByText("Mar 2019 – Dec 2021")).toBeVisible();
  await expect(page.getByText(/Employment gap of 8 months/)).toBeVisible(); // calculated from the dates
  await expect(page.getByText("Recent companies:")).toBeVisible();
  await expect(page.getByText("AWS Certified Developer")).toBeVisible();
  await page.screenshot({ path: "test-results/ai-profile.png", fullPage: true });

  await page.getByRole("button", { name: /Apply to profile/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel(/Current title/)).toBeChecked(); // empty on the record, so ticked by default
  await dialog.getByRole("button", { name: /^Apply \d+ fields?$/ }).click();
  await expect(page.getByText("AI profile applied to the candidate record")).toBeVisible();

  await page.getByRole("tab", { name: "Profile", exact: true }).click();
  await expect(page.getByText("Lead Engineer").first()).toBeVisible();
  await expect(page.getByText("Zeta Labs").first()).toBeVisible();
  await page.getByRole("tab", { name: /Notes/ }).click();
  await expect(page.getByText(/AI profile applied to this record/)).toBeVisible();
});

test("AI profile: a LinkedIn login page or too-short text is rejected with a helpful message", async ({ page }) => {
  await login(page);
  await page.goto("/candidates");
  await page.getByRole("link", { name: /Meera Kapoor/ }).first().click();
  await page.getByRole("tab", { name: "AI Profile" }).click();
  await page.getByLabel(/Or paste the text/).fill("Sign in to view Meera's full profile. Join LinkedIn to see more. ".repeat(3) + " ".repeat(5));
  await expect(page.getByRole("button", { name: /Extract with AI/ })).toBeDisabled(); // under 200 characters: blocked before anything is sent
  await page.getByLabel(/Or paste the text/).fill("Sign in to view Meera's full profile. Join LinkedIn to see more. ".repeat(4) + "x".repeat(10));
  await page.getByRole("button", { name: /Extract with AI/ }).click();
  await expect(page.getByText(/looks like LinkedIn's sign-in page/)).toBeVisible();
});
