import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page, role: "viewer" | "approver") {
  await page.goto("/");
  if (role === "approver") {
    const screenshotDirectory = resolve(process.cwd(), "../docs/screenshots");
    mkdirSync(screenshotDirectory, { recursive: true });
    await page.screenshot({
      path: resolve(screenshotDirectory, "login.png"),
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "Sign in with ChainMind SSO" }).click();
  await page.locator('input[name="username"]').fill(role);
  await page.locator('input[name="password"]').fill("demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText(`${role} · ${role}`)).toBeVisible();
}

async function saveSection(page: Page, heading: string, filename: string) {
  const section = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: heading }) })
    .first();
  await expect(section).toBeVisible();
  const screenshotDirectory = resolve(process.cwd(), "../docs/screenshots");
  mkdirSync(screenshotDirectory, { recursive: true });
  await section.screenshot({ path: resolve(screenshotDirectory, filename) });
}

async function triggerScenario(page: Page, title: string, scenario?: string) {
  if (scenario) {
    await page.getByRole("combobox", { name: "Disruption scenario" }).selectOption(scenario);
  }
  const trigger = page.getByRole("button", { name: "Trigger demo disruption" });
  await expect(trigger).toBeEnabled();
  await trigger.click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText("PENDING APPROVAL", { exact: true }).first()).toBeVisible();
}

test("approver resolves weather disruption and completes execution tracking", async ({ page }) => {
  const demoTitle = "Extreme weather delays cargo ship";
  await signIn(page, "approver");
  await triggerScenario(page, demoTitle, "weather");
  await expect(page.getByText("Vendor B", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("$135,000", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Air Freight")).toBeVisible();
  const notifications = page.getByRole("region", { name: "Notification feed" });
  await expect(
    notifications.getByText(
      "Raw material Microchip X delayed 5 days. Stock for 3 days (source: SAP S/4HANA). Recommendation: buy from Vendor B at $135,000 (source: SAP Ariba).",
    ),
  ).toBeVisible();

  const screenshotDirectory = resolve(process.cwd(), "../docs/screenshots");
  mkdirSync(screenshotDirectory, { recursive: true });
  await saveSection(page, demoTitle, "timeline.png");
  const charts = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "Cost vs lead time" }) });
  await expect(charts).toBeVisible();
  await charts.screenshot({ path: resolve(screenshotDirectory, "vendor-charts.png") });
  await saveSection(page, "Chain of Thought summary", "chain-of-thought.png");
  await notifications.screenshot({
    path: resolve(screenshotDirectory, "notification-feed.png"),
  });
  await saveSection(page, "Purchase order", "po-approval.png");
  await page.screenshot({
    path: resolve(screenshotDirectory, "chainmind-pending-approval.png"),
    fullPage: true,
  });

  await notifications.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Confirm decision" }).click();
  await expect(page.getByRole("heading", { name: "Execution & tracking" })).toBeVisible();
  await expect(page.getByText("EXECUTED", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Supplier confirmation").first()).toBeVisible();
  await expect(page.getByText("Projected stock").first()).toBeVisible();
  await page.getByRole("button", { name: "KPIs" }).click();
  await expect(page.getByRole("heading", { name: "Response KPIs" })).toBeVisible();
  await saveSection(page, "Response KPIs", "kpis.png");
});

test("viewer can inspect a draft but cannot approve it", async ({ page }) => {
  await signIn(page, "viewer");
  await triggerScenario(page, "Extreme weather delays cargo ship", "weather");
  const notifications = page.getByRole("region", { name: "Notification feed" });
  await expect(notifications.getByText(/Vendor B at \$135,000/)).toBeVisible();
  await expect(notifications.getByRole("button", { name: "Approve" })).toBeDisabled();
  await expect(notifications.getByRole("button", { name: "View details" })).toBeEnabled();
  await expect(page.getByText(/Viewer access is read-only/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Review approval" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reject" })).toHaveCount(0);
});

test("approver can request a vendor revision", async ({ page }) => {
  await signIn(page, "approver");
  await triggerScenario(page, "Extreme weather delays cargo ship", "weather");
  await page.getByRole("combobox", { name: "Vendor for revision" }).selectOption("vendor-a");
  await page.getByRole("button", { name: "Revise vendor" }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Confirm decision" }).click();
  await expect(page.getByText("Vendor A", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("PENDING APPROVAL", { exact: true }).first()).toBeVisible();
});

for (const [id, title] of [
  ["geopolitical", "Geopolitical disruption delays component supply"],
  ["vendor_failure", "Primary vendor reports a supply failure"],
  ["port_congestion", "Port congestion delays inbound shipment"],
] as const) {
  test(`approver can trigger the ${id} scenario`, async ({ page }) => {
    await signIn(page, "approver");
    await triggerScenario(page, title, id);
  });
}
