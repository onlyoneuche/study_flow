import { expect, test } from "@playwright/test";

test("responsive navigation and the real API connection work", async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Welcome to StudyFlow" })).toBeVisible();
  await expect(page.getByText("StudyFlow is online")).toBeVisible();
  const health = await page.request.get("/api/v1/health");
  expect(health.ok()).toBeTruthy();
  expect(["ok", "degraded"]).toContain((await health.json()).status);
  const retry = page.getByRole("button", { name: "Check again" });
  await retry.click();
  await expect(retry).toBeEnabled();
  await expect(page.getByText("StudyFlow is online")).toBeVisible();

  const navigation = page.getByRole("navigation", { name: "Main navigation" }).filter({ visible: true });
  await expect(navigation).toHaveCount(1);
  for (const link of await navigation.getByRole("link").all()) {
    const box = await link.boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(44);
    expect(box?.width).toBeGreaterThanOrEqual(44);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  const navBox = await navigation.boundingBox();
  if ((page.viewportSize()?.width ?? 0) > 1024) expect(navBox?.width).toBeLessThan(250);
  else expect(navBox?.width).toBe(page.viewportSize()?.width);
  await page.screenshot({ path: testInfo.outputPath("home.png"), fullPage: true });

  for (const [label, heading] of [
    ["Study", "Your squad is waiting"],
    ["Ranks", "Your squad is waiting"],
    ["Squad", "Your squad is waiting"],
  ]) {
    await navigation.getByRole("link", { name: label, exact: true }).click();
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await expect(navigation.getByRole("link", { name: label, exact: true })).toHaveAttribute("aria-current", "page");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  }
  expect(errors).toEqual([]);
});

test("PWA manifest, icons and public offline fallback work", async ({ page, context }) => {
  const manifestResponse = await page.request.get("/manifest.webmanifest");
  expect(manifestResponse.ok()).toBeTruthy();
  const manifest = await manifestResponse.json();
  expect(manifest.name).toBe("StudyFlow");
  expect(manifest.display).toBe("standalone");
  for (const icon of manifest.icons) expect((await page.request.get(icon.src)).ok()).toBeTruthy();
  await page.goto("/");
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise<void>((resolve) => navigator.serviceWorker.addEventListener("controllerchange", () => resolve(), { once: true }));
    }
  });
  const cachedUrls = await page.evaluate(async () => {
    const cache = await caches.open("studyflow-offline-v1");
    return (await cache.keys()).map((request) => new URL(request.url).pathname);
  });
  expect(cachedUrls).toEqual(["/offline.html"]);
  await context.setOffline(true);
  await page.goto("/study");
  await expect(page.getByRole("heading", { name: "You’re offline" })).toBeVisible();
  await context.setOffline(false);
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "Your squad is waiting" })).toBeVisible();
});
