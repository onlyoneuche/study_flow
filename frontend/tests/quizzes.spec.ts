import { execFileSync } from "node:child_process";
import { test, expect } from "@playwright/test";

test("quiz stays timed through reload, keyboard answers submit and personal review works", async ({ page, request }, testInfo) => {
  if (!process.env.DATABASE_URL?.includes("/tmp/")) throw new Error("Browser fixtures require an isolated DATABASE_URL under /tmp.");
  const email = `quiz-${crypto.randomUUID()}@example.com`; const password = "studyflow-browser-password";
  await request.post("/api/v1/auth/register", { data: { email, password, display_name: "Quiz Learner", level: "SS2", audience_band: "secondary", guardian_consent: true } });
  const token = (await (await request.post("/api/v1/auth/jwt/login", { form: { username: email, password } })).json()).access_token as string;
  const headers = { Authorization: `Bearer ${token}` };
  const group = await (await request.post("/api/v1/groups", { headers, data: { name: "Quiz Study Squad" } })).json();
  const session = await (await request.post("/api/v1/sessions/solo", { headers, data: { planned_minutes: 25, subject: "Chemistry", topic: "Mole concept" } })).json();
  const participantId = session.mine.id;
  await expect.poll(async () => (await (await request.get(`/api/v1/sessions/${session.id}`, { headers })).json()).mine.quiz_status).toBe("ready");
  // Advance only this isolated fixture's persisted study time. Production exposes no clock bypass.
  execFileSync("../backend/.venv/bin/python", ["-c", `
import sys
from datetime import timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.calendar import lagos_date
from app.db.database import database_url, configure_sqlite
from app.db.types import utc_now
from app.models import SessionParticipant, StudySession
engine = create_engine(database_url(get_settings().database_url).replace('sqlite+aiosqlite:', 'sqlite:'))
configure_sqlite(engine)
with Session(engine) as db:
    db.connection(execution_options={"sqlite_transaction_mode": "IMMEDIATE"})
    p = db.get(SessionParticipant, int(sys.argv[1]))
    s = db.get(StudySession, p.session_id)
    s.started_at = utc_now() - timedelta(minutes=26)
    s.scheduled_at = s.started_at
    s.end_at = s.started_at + timedelta(minutes=25)
    s.status = 'ended'
    p.joined_at = s.started_at
    p.session_date = lagos_date(s.started_at)
    p.ended_at = s.end_at
    p.active_seconds = 1500
    p.last_heartbeat_at = s.end_at
    p.status = 'joined'
    db.commit()
engine.dispose()
`, String(participantId)], { env: { ...process.env, PYTHONPATH: "../backend" } });
  const responses: string[] = [];
  page.on("response", async response => { if (response.url().endsWith(`/api/v1/participants/${participantId}/quiz`)) responses.push(await response.text()); });
  await page.goto("/"); await page.evaluate(token => sessionStorage.setItem("studyflow-token", token), token);
  await page.goto(`/participants/${participantId}/quiz`);
  await expect(page.getByText("Question 1 of 15", { exact: true })).toBeVisible();
  await page.getByRole("radio").nth(1).click();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Question 2 of 15", { exact: true })).toBeVisible();
  await page.keyboard.press("3");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Question 3 of 15", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("quiz.png"), fullPage: true });
  await page.reload();
  await expect(page.getByRole("radio").nth(1)).toHaveAttribute("aria-checked", "true");
  await expect.poll(() => responses.length).toBeGreaterThanOrEqual(2);
  const opened = responses.map(text => JSON.parse(text));
  expect(opened.length).toBeGreaterThanOrEqual(2);
  expect(opened[0].started_at).toBe(opened.at(-1).started_at);
  expect(responses.every(text => !text.includes("correct_index") && !text.includes("explanation"))).toBeTruthy();
  for (let index = 0; index < 15; index++) {
    await page.getByRole("button", { name: `Go to question ${index + 1}`, exact: true }).click();
    await page.getByRole("radio").nth(index % 4).click();
  }
  await page.getByRole("button", { name: "Submit quiz", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Nice work!", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Review your answers", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Points saved to your squads", exact: true })).toBeVisible();
  const scoreBox = await page.getByRole("heading", { name: "Your quiz result", exact: true }).boundingBox();
  const pointsBox = await page.getByRole("heading", { name: "Points saved to your squads", exact: true }).boundingBox();
  const progress = page.getByRole("region", { name: "Current squad progress", exact: true });
  await expect(progress).toBeVisible();
  if ((page.viewportSize()?.width ?? 0) > 1024) {
    const progressBox = await progress.boundingBox();
    expect(pointsBox!.x).toBeGreaterThan(scoreBox!.x);
    expect(progressBox!.x).toBeGreaterThan(pointsBox!.x);
    expect(Math.abs(progressBox!.y - pointsBox!.y)).toBeLessThan(60);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath("results.png") });
  if (testInfo.project.name === "chrome-390") {
    const review = page.getByRole("article").first();
    await review.getByRole("button", { name: "Flag question", exact: true }).click();
    await review.getByLabel("Reason", { exact: true }).selectOption("unclear");
    await review.getByLabel("Optional note", { exact: true }).fill("Please review the wording.");
    await review.getByRole("button", { name: "Send flag", exact: true }).click();
    await expect(review.getByRole("status")).toContainText("Your result stays the same");
  }
  const detail = await (await request.get(`/api/v1/groups/${group.id}`, { headers })).json();
  expect(detail.weekly_points).toBeGreaterThan(0);
  expect(detail.completed_today).toBeGreaterThan(0);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Quiz Learner", exact: false })).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Weekly squad points", exact: true })).toHaveAttribute("aria-valuenow", String(detail.weekly_points));
  await expect(page.getByRole("region", { name: "Today's squad goal", exact: true })).toContainText(`${detail.completed_today} / 1`);
  await page.getByRole("link", { name: "View result", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Nice work!", exact: true })).toBeVisible();
  await page.goto("/ranks");
  await expect(page.getByRole("heading", { name: "In my squad", exact: true })).toBeVisible();
  await expect(page.getByText("Personal improvement points", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("rankings.png"), fullPage: true });
  await page.getByRole("link", { name: "See your points history", exact: false }).click();
  await expect(page.getByRole("heading", { name: "Your points history", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
