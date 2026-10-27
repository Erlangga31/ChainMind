import { existsSync } from "node:fs";
import { delimiter, join } from "node:path";
import { defineConfig, devices } from "@playwright/test";

const dashboardDirectory = process.cwd();
const projectRoot = join(dashboardDirectory, "..");
const apiPort = process.env.CHAINMIND_E2E_API_PORT ?? "18000";
const sandboxPort = process.env.CHAINMIND_E2E_SANDBOX_PORT ?? "18100";
const dashboardPort = process.env.CHAINMIND_E2E_DASHBOARD_PORT ?? "15173";
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
    baseURL: `http://127.0.0.1:${dashboardPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
  },
  webServer: [
    {
      command: `${pythonCommand} -m uvicorn chainmind.api.main:app --app-dir src --host 127.0.0.1 --port ${apiPort}`,
      cwd: projectRoot,
      url: `http://127.0.0.1:${apiPort}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        PATH: `${venvScripts}${delimiter}${path}`,
        CHAINMIND_MODE: "mock",
        CHAINMIND_AUTH_DEV_BYPASS: "false",
        CHAINMIND_EVENT_DATABASE_PATH: ":memory:",
        CHAINMIND_NOTIFICATION_BACKENDS: "[]",
        CHAINMIND_AUTH_ISSUER: `http://127.0.0.1:${sandboxPort}`,
        CHAINMIND_AUTH_JWKS_URL: `http://127.0.0.1:${sandboxPort}/.well-known/jwks.json`,
        CHAINMIND_API_CORS_ORIGINS: JSON.stringify([`http://127.0.0.1:${dashboardPort}`]),
      },
    },
    {
      command: `${pythonCommand} -m uvicorn sap_sandbox.main:app --app-dir sandbox --host 127.0.0.1 --port ${sandboxPort}`,
      cwd: projectRoot,
      url: `http://127.0.0.1:${sandboxPort}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        PATH: `${venvScripts}${delimiter}${path}`,
        SAP_SANDBOX_OIDC_ISSUER: `http://127.0.0.1:${sandboxPort}`,
        SAP_SANDBOX_OIDC_REDIRECT_URI: `http://127.0.0.1:${dashboardPort}/`,
        SAP_SANDBOX_EVENT_WEBHOOK_URL: `http://127.0.0.1:${apiPort}/event-bridge`,
        SAP_SANDBOX_WORKFLOW_CALLBACK_URL: `http://127.0.0.1:${apiPort}`,
      },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${dashboardPort}`,
      cwd: dashboardDirectory,
      url: `http://127.0.0.1:${dashboardPort}`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        VITE_API_URL: `http://127.0.0.1:${apiPort}`,
        VITE_OIDC_ISSUER: `http://127.0.0.1:${sandboxPort}`,
        VITE_OIDC_REDIRECT_URI: `http://127.0.0.1:${dashboardPort}/`,
      },
    },
  ],
});
