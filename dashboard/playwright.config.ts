import { existsSync } from "node:fs";
import { delimiter, join } from "node:path";
import { defineConfig, devices } from "@playwright/test";

const dashboardDirectory = process.cwd();
const projectRoot = join(dashboardDirectory, "..");
const venvScripts = join(projectRoot, ".venv", process.platform === "win32" ? "Scripts" : "bin");
const pythonFromVenv = join(venvScripts, process.platform === "win32" ? "python.exe" : "python");
const pythonCommand =
  process.env.CHAINMIND_PYTHON
  ?? (existsSync(pythonFromVenv)
    ? `"${pythonFromVenv}"`
    : process.env.CI
      ? "uv run python"
      : "python");
const path = process.env.PATH ?? "";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
  },
  webServer: [
    {
      command: `${pythonCommand} -m uvicorn chainmind.api.main:app --app-dir src --host 127.0.0.1 --port 8000`,
      cwd: projectRoot,
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ...process.env,
        PATH: `${venvScripts}${delimiter}${path}`,
        CHAINMIND_MODE: "mock",
        CHAINMIND_AUTH_DEV_BYPASS: "false",
        CHAINMIND_EVENT_DATABASE_PATH: ":memory:",
        CHAINMIND_NOTIFICATION_BACKENDS: "[]",
      },
    },
    {
      command: `${pythonCommand} -m uvicorn sap_sandbox.main:app --app-dir sandbox --host 127.0.0.1 --port 8100`,
      cwd: projectRoot,
      url: "http://127.0.0.1:8100/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ...process.env,
        PATH: `${venvScripts}${delimiter}${path}`,
      },
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173",
      cwd: dashboardDirectory,
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
