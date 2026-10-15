import { expect, test } from "@playwright/test";

// Routing the API failure must reach Playwright, rather than WebKit’s service-worker network.
// The separate PWA test exercises installation and offline recovery with workers enabled.
test.use({ serviceWorkers: "block" });

test("dashboard uses real squad data, handles connection errors and opens the live room", async ({ page, request }, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  async function account(name: string) {
    const email = `dashboard-${crypto.randomUUID()}@example.com`;
    const password = "studyflow-browser-password";
    expect((await request.post("/api/v1/auth/register", { data: { email, password, display_name: name, level: "SS2", audience_band: "secondary", guardian_consent: true } })).status()).toBe(201);
    return (await (await request.post("/api/v1/auth/jwt/login", { form: { username: email, password } })).json()).access_token as string;
  }
  const token = await account("Ada Dashboard");
  const headers = { Authorization: `Bearer ${token}` };
  await page.goto("/"); await page.evaluate(token => sessionStorage.setItem("studyflow-token", token), token); await page.reload();
  await expect(page.getByRole("heading", { name: "Ada Dashboard", exact: false })).toBeVisible();
  await expect(page.getByRole("link", { name: "Create or join a squad", exact: true })).toBeVisible();
  const group = await (await request.post("/api/v1/groups", { headers, data: { name: "Responsive Squad" } })).json();
  const invite = await (await request.post(`/api/v1/groups/${group.id}/invites`, { headers, data: { max_uses: 7 } })).json();
  for (const name of ["Tunde", "Zainab"]) {
    const friend = await account(name);
    expect((await request.post(`/api/v1/invites/${invite.code}/accept`, { headers: { Authorization: `Bearer ${friend}` } })).ok()).toBeTruthy();
  }
  const live = await (await request.post(`/api/v1/groups/${group.id}/sessions`, { headers, data: { planned_minutes: 45, scheduled_at: new Date(Date.now() + 30 * 60_000).toISOString() } })).json();
  let fail = true;
  await page.route("**/api/v1/users/me/dashboard", async route => {
    if (fail) await route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"Please try again."}' });
    else await route.continue();
  });
  await page.getByRole("button", { name: "Refresh dashboard", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Please try again");
  fail = false;
  await page.getByRole("button", { name: "Refresh dashboard", exact: true }).click();
  const weekly = page.getByRole("region", { name: "Weekly squad progress", exact: true });
  await expect(weekly).toContainText("Responsive Squad");
  await expect(weekly).toContainText("/ 300 pts");
  await expect(page.getByRole("progressbar", { name: "Weekly squad points", exact: true })).toHaveAttribute("aria-valuenow", "0");
  await expect(page.getByRole("region", { name: "Today's squad goal", exact: true })).toContainText("0 / 3");
  await expect(page.getByText("0 of 3", { exact: true })).toBeVisible();
  await expect(page.getByText("Tunde", { exact: true })).toBeVisible();
  await expect(page.getByText(/going|raw quiz score|Nudge on WhatsApp/)).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath("dashboard.png"), fullPage: true });
  await page.getByRole("link", { name: "Join session", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/sessions/${live.id}$`));
  await page.getByLabel("Your subject", { exact: true }).fill("Chemistry");
  await page.getByLabel("Your topic", { exact: true }).fill("Mole concept");
  await page.getByRole("button", { name: "Join live session", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Mole concept", level: 1, exact: true })).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Weekly squad points", exact: true })).toHaveAttribute("aria-valuenow", "0");
  const timer = await page.getByLabel("Session timer", { exact: true }).boundingBox();
  const members = await page.getByRole("heading", { name: "Studying with you", exact: true }).boundingBox();
  if ((page.viewportSize()?.width ?? 0) >= 768) expect(members!.x).toBeGreaterThan(timer!.x);
  else expect(members!.y).toBeGreaterThan(timer!.y);
  expect(errors).toEqual([]);
});
