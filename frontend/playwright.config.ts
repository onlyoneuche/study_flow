import { randomUUID } from "node:crypto";
import { defineConfig } from "@playwright/test";

const database = process.env.DATABASE_URL ?? `sqlite+aiosqlite:////tmp/studyflow-browser-${randomUUID()}.db`;
if (!database.startsWith("sqlite+aiosqlite:////tmp/studyflow-")) throw new Error("Browser checks require a disposable /tmp/studyflow- database.");
process.env.DATABASE_URL = database;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  workers: 2,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure" },
  projects: ["chrome", "webkit"].flatMap((browser) =>
    [360, 390, 768, 1440].map((width) => ({
      name: `${browser}-${width}`,
      use: {
        browserName: browser === "chrome" ? "chromium" as const : "webkit" as const,
        ...(browser === "chrome" ? { channel: "chrome" } : {}),
        viewport: { width, height: 900 },
      },
    })),
  ),
  webServer: [
    {
      command: "../backend/.venv/bin/python ../scripts/browser_backend.py",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: false,
    },
    {
      command: "npm run start",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
