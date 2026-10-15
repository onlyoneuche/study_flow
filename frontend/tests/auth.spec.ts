import { expect, test } from "@playwright/test";

const password = "StudyFlow-browser-password";
const email = () => `studyflow-${crypto.randomUUID()}@example.com`;

test("adult signup, sign-in, profile and sign-out work", async ({ page }, testInfo) => {
  const address = email();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/auth/sign-up");
  await page.getByLabel("Display name", { exact: true }).fill("Ada Browser");
  await page.getByLabel("Email", { exact: true }).fill(address);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Education level").selectOption("OTHER");
  expect((await page.getByLabel("Education level").boundingBox())?.height).toBeGreaterThanOrEqual(44);
  await expect(page.getByText("University / adult", { exact: true })).toBeVisible();
  await expect(page.getByRole("checkbox")).not.toBeChecked();
  await page.getByRole("checkbox").check();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath("signup-adult.png"), fullPage: true });
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Account created");
  await page.getByRole("link", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Welcome back", exact: true })).toBeVisible();
  await page.goto("/auth/sign-in?next=%2F%0A%2Fexample.com");
  await page.getByLabel("Email", { exact: true }).fill(address);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Your account", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Display name", { exact: true })).toHaveValue("Ada Browser");
  await page.getByLabel("Display name", { exact: true }).fill("Ada Updated");
  await page.getByRole("button", { name: "Save profile", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Profile saved");
  await page.getByRole("button", { name: "Resend verification email", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("verification link");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Welcome back", exact: true })).toBeVisible();
  await page.goto("/account");
  await expect(page.getByRole("heading", { name: "Your study space awaits" })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem("studyflow-token"))).toBeNull();
  expect(errors).toEqual([]);
});

test("secondary signup requires guardian consent and reset requests work", async ({ page }, testInfo) => {
  await page.goto("/auth/sign-up");
  await page.getByLabel("Display name", { exact: true }).fill("Tunde Browser");
  await page.getByLabel("Email", { exact: true }).fill(email());
  await page.getByLabel("Password", { exact: true }).fill(password);
  const checkbox = page.getByRole("checkbox");
  await expect(checkbox).not.toBeChecked();
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  expect(await checkbox.evaluate((element: HTMLInputElement) => element.validity.valueMissing)).toBeTruthy();
  await checkbox.check();
  await page.screenshot({ path: testInfo.outputPath("signup-secondary.png"), fullPage: true });
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Account created");
  await page.goto("/auth/forgot-password");
  await page.getByLabel("Email", { exact: true }).fill("nobody@example.com");
  await page.getByRole("button", { name: "Send reset link", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("If an active account");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test("bad email links show clear errors and consent resets after a level change", async ({ page }) => {
  await page.goto("/auth/verify#token=invalid");
  await page.getByRole("button", { name: "Verify email", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("invalid or has expired");
  await page.goto("/auth/reset-password#token=invalid");
  await page.getByLabel("New password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Set new password", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("invalid, expired or already used");
  await page.goto("/auth/sign-up");
  await page.getByRole("checkbox").check();
  await page.getByLabel("Education level").selectOption("UG_100");
  await expect(page.getByRole("checkbox")).not.toBeChecked();
});
