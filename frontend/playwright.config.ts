import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8000",
    headless: true,
    channel: "chrome",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "warren_towers/bin/python -m tests.browser_server",
    cwd: "..",
    url: "http://127.0.0.1:8000/api/health",
    reuseExistingServer: false,
    timeout: 30000,
  },
  timeout: 60000,
});
