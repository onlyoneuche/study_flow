import { test, expect } from "@playwright/test";

test("solo session uses authenticated socket and survives leave/rejoin/reload", async ({ page, request }, testInfo) => {
  const email = `study-${crypto.randomUUID()}@example.com`; const password = "studyflow-browser-password";
  expect((await request.post("/api/v1/auth/register", { data: { email, password, display_name: "Ada Study", level: "SS2", audience_band: "secondary", guardian_consent: true } })).status()).toBe(201);
  const signed = await request.post("/api/v1/auth/jwt/login", { form: { username: email, password } });
  const token = (await signed.json()).access_token;
  await page.goto("/"); await page.evaluate(token => sessionStorage.setItem("studyflow-token", token), token);
  await page.goto("/study");
  await expect(page.getByRole("heading", { name: "New session", exact: true })).toBeVisible();
  await page.getByLabel("What are you studying?", { exact: true }).fill("Mole concept");
  await page.getByLabel("Subject", { exact: true }).fill("Chemistry");
  await page.getByRole("button", { name: "Start solo session", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Mole concept", level: 1, exact: true })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Connected · server clock");
  await expect(page.getByRole("button", { name: "Finish early", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "React 💪", exact: true }).click();
  await expect(page.getByRole("complementary").getByText("💪", { exact: true }).last()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("solo-session.png"), fullPage: true });
  await page.getByRole("button", { name: "Leave session", exact: true }).click();
  await expect(page.getByRole("button", { name: "Rejoin session", exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Rejoin session", exact: true }).click();
  await expect(page.getByRole("button", { name: "Leave session", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test("live room shows members on independent topics through the frontend socket proxy", async ({ page, context, request }, testInfo) => {
  async function account(name: string) {
    const email = `live-${crypto.randomUUID()}@example.com`; const password = "studyflow-browser-password";
    await request.post("/api/v1/auth/register", { data: { email, password, display_name: name, level: "SS2", audience_band: "secondary", guardian_consent: true } });
    return (await (await request.post("/api/v1/auth/jwt/login", { form: { username: email, password } })).json()).access_token as string;
  }
  const owner = await account("Ada Live"); const friendToken = await account("Tunde Live");
  const auth = { Authorization: `Bearer ${owner}` }; const friendAuth = { Authorization: `Bearer ${friendToken}` };
  const group = await (await request.post("/api/v1/groups", { headers: auth, data: { name: "Live Browser Squad" } })).json();
  const invite = await (await request.post(`/api/v1/groups/${group.id}/invites`, { headers: auth, data: { max_uses: 7 } })).json();
  await request.post(`/api/v1/invites/${invite.code}/accept`, { headers: friendAuth });
  await page.goto("/"); await page.evaluate(token => sessionStorage.setItem("studyflow-token", token), owner);
  await page.goto(`/study?group=${group.id}`);
  await page.getByLabel("What are you studying?", { exact: true }).fill("Alkenes");
  await page.getByLabel("Subject", { exact: true }).fill("Chemistry");
  await expect(page.getByLabel("Study group", { exact: true })).toHaveValue(String(group.id));
  await page.getByRole("button", { name: "Start live session", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Alkenes", level: 1, exact: true })).toBeVisible();
  const room = new URL(page.url()).pathname;
  const friend = await context.newPage(); await friend.goto("/"); await friend.evaluate(token => sessionStorage.setItem("studyflow-token", token), friendToken); await friend.goto(room);
  await friend.getByLabel("Your subject", { exact: true }).fill("Physics");
  await friend.getByLabel("Your topic", { exact: true }).fill("Newton’s laws");
  await friend.getByRole("button", { name: "Join live session", exact: true }).click();
  await expect(friend.getByRole("heading", { name: "Newton’s laws", exact: true })).toBeVisible();
  await expect(page.getByText("Tunde Live", { exact: true })).toBeVisible();
  await expect(page.getByText("Physics", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("live-session.png"), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await friend.close();
});
