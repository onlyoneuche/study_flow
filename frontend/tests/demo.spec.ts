import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

test.skip(process.env.STUDYFLOW_BROWSER_DEMO !== "1", "Run make test-demo against its own seeded test database.");

test("Ada's seeded demo goes from dashboard and live room to quiz, points and rankings", async ({ page, request }, testInfo) => {
  const password = "StudyFlow-demo-2026!";
  await page.goto("/auth/sign-in?next=/");
  await page.getByLabel("Email", { exact: true }).fill("ada@demo.studyflow.example.com");
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ada", exact: false })).toBeVisible();
  const token = await page.evaluate(() => sessionStorage.getItem("studyflow-token"));
  const headers = { Authorization: `Bearer ${token}` };
  const data = await (await request.get("/api/v1/users/me/dashboard", { headers })).json();
  const squad = data.groups.find((g: { name: string }) => g.name === "Study Squad");
  const ready = data.recent.find((p: { quiz_available: boolean }) => p.quiz_available);
  expect(squad.streak).toBe(12);
  expect(squad.weekly_target).toBe(600);
  expect(ready).toBeTruthy();
  await expect(page.getByRole("region", { name: "Group streak", exact: true })).toContainText("12");
  await expect(page.getByRole("progressbar", { name: "Weekly group points", exact: true })).toHaveAttribute("aria-valuenow", String(squad.weekly_points));
  await page.screenshot({ path: testInfo.outputPath("demo-dashboard.png") });
  await page.getByRole("link", { name: "Visit your squad", exact: false }).click();
  await expect(page.getByRole("heading", { name: "Study Squad", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Share on WhatsApp", exact: true })).toHaveAttribute("href", /wa.me\/\?text=.*join/);
  await page.getByRole("link", { name: "Study together", exact: true }).click();
  await expect(page.getByRole("heading", { name: "New session", exact: true })).toBeVisible();
  await page.getByLabel("What are you studying?", { exact: true }).fill("Alkenes");
  await page.getByLabel("Subject", { exact: true }).fill("Chemistry");
  await page.getByRole("button", { name: "Start live session", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Alkenes", exact: true, level: 1 })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Connected");
  await page.screenshot({ path: testInfo.outputPath("demo-live.png") });
  await page.getByRole("button", { name: "Leave session", exact: true }).click();
  // Keep production durations intact; the pitch explicitly switches to Ada's pre-studied quiz.
  await page.goto(`/participants/${ready.participant_id}/quiz`);
  await expect(page.getByText("Question 1 of 15", { exact: true })).toBeVisible();
  const banks = JSON.parse(readFileSync("../backend/app/quizzes/demo_quizzes.json", "utf8")) as { topic: string; questions: { question: string; options: string[]; correct_index: number }[] }[];
  const bank = banks.find(entry => entry.topic === "Mole concept")!;
  for (let index = 0; index < 15; index++) {
    await expect(page.getByText(`Question ${index + 1} of 15`, { exact: true })).toBeVisible();
    const text = await page.getByRole("heading", { level: 1 }).innerText();
    const question = bank.questions.find(q => q.question === text)!;
    const correct = question.options[question.correct_index];
    const answer = page.getByRole("radio").filter({ has: page.getByText(correct, { exact: true }) });
    await expect(answer).toHaveCount(1);
    await answer.click();
    await expect(answer).toBeChecked();
    await page.keyboard.press("Enter");
  }
  await expect(page.getByRole("heading", { name: "Nice work!", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your quiz result", exact: true })).toBeVisible();
  const updated = await (await request.get(`/api/v1/groups/${squad.id}`, { headers })).json();
  expect(updated.weekly_points).toBe(squad.weekly_points + 25);
  expect(updated.streak).toBe(12);
  await page.screenshot({ path: testInfo.outputPath("demo-results.png") });
  await page.goto("/ranks");
  await expect(page.getByRole("heading", { name: "In my group", exact: true })).toBeVisible();
  await expect(page.getByText("Ada (you)", { exact: true })).toBeVisible();
  await expect(page.getByText("Lagos Brainiacs", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("demo-rankings.png") });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
