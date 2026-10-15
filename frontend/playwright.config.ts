import { defineConfig } from "@playwright/test";

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
      command: "../backend/.venv/bin/uvicorn app.main:create_app --factory --app-dir ../backend --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npm run start",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
