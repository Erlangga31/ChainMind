import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function signIn(
  page: Page,
  role: "viewer" | "approver",
  language: "id" | "en" = "en",
  presenter = false,
) {
  await page.goto(presenter ? "/?presenter=1" : "/");
  await page
    .getByRole("group")
    .getByRole("button", { name: language === "id" ? "ID" : "EN" })
    .click();
  if (!presenter) {
    await page.getByRole("button", { name: language === "id" ? "Mulai" : "Get started" }).click();
  }
  if (role === "approver") {
    const screenshotDirectory = resolve(process.cwd(), "../docs/screenshots");
    mkdirSync(screenshotDirectory, { recursive: true });
    await page.screenshot({
      path: resolve(screenshotDirectory, language === "id" ? "login-id.png" : "login.png"),
      fullPage: true,
    });
  }
  await page
    .getByRole("button", {
      name: language === "id" ? "Masuk dengan ChainMind SSO" : "Sign in with ChainMind SSO",
    })
    .click();
  await page.locator('input[name="username"]').fill(role);
  await page.locator('input[name="password"]').fill("demo");
  await page.locator('button[type="submit"]').click();
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

async function triggerScenario(
  page: Page,
  title: string,
  scenario?: string,
  language: "id" | "en" = "en",
) {
  await page.getByText(language === "id" ? "Gangguan baru" : "New disruption").click();
  await page.getByRole("textbox", { name: language === "id" ? "Judul gangguan" : "Disruption title" }).fill(title);
  await page.getByRole("textbox", { name: language === "id" ? "Deskripsi gangguan" : "Disruption description" }).fill(`${title} reported by operator.`);
  await page.getByRole("textbox", { name: "Material ID" }).fill("microchip-x");
  await page.getByRole("textbox", { name: language === "id" ? "Nama material" : "Material name" }).fill("Microchip X");
  await page.getByRole("spinbutton", { name: language === "id" ? "Hari keterlambatan" : "Delay days" }).fill(scenario === "vendor_failure" ? "4" : "5");
  await page.getByRole("combobox", { name: language === "id" ? "Jenis gangguan" : "Event type" }).selectOption(
    scenario === "port_congestion" ? "logistics_delay" : scenario ?? "weather",
  );
  const trigger = page.getByRole("button", {
    name: language === "id" ? "Analisis gangguan" : "Analyze disruption",
  });
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
  await expect(page.getByText(/DRAFT-[A-Z0-9]{4}/)).toBeVisible();
  await expect(page.getByText("Expected date")).toBeVisible();
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
  await expect(charts.last()).toBeVisible();
  await charts.last().screenshot({ path: resolve(screenshotDirectory, "vendor-charts.png") });
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
  await expect(page.getByText("Monitor shipment")).toBeVisible();
  await expect(page.getByText("Update ETA")).toBeVisible();
  await expect(page.getByText("Update inventory")).toBeVisible();
  await expect(page.getByText("Deviation alert")).toBeVisible();
  await expect(page.getByText("KPI achieved")).toBeVisible();
  await page.getByRole("button", { name: "KPIs" }).click();
  await expect(page.getByRole("heading", { name: "Response KPIs" })).toBeVisible();
  await saveSection(page, "Response KPIs", "kpis.png");
});

test("viewer can inspect a draft but cannot approve it", async ({ page }) => {
  await signIn(page, "viewer");
  await triggerScenario(page, "Extreme weather delays cargo ship", "weather");
  const notifications = page.getByRole("region", { name: "Notification feed" });
  await expect(notifications.getByText(/Vendor B at \$135,000/).first()).toBeVisible();
  await expect(notifications.getByRole("button", { name: "Approve" })).toBeDisabled();
  await expect(notifications.getByRole("button", { name: "View details" })).toBeEnabled();
  await expect(page.getByText(/Viewer access is read-only/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Review approval" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reject" })).toHaveCount(0);
});

test("approver can filter notifications and mark distinct items as read", async ({ page }) => {
  await signIn(page, "approver");
  await triggerScenario(page, "Notification grouping scenario", "weather");
  await page.getByRole("button", { name: /Notification feed/ }).click();

  const search = page.getByRole("textbox", { name: "Search notifications" });
  await search.fill("Notification grouping scenario");
  await expect(page.getByText(/Raw material Microchip X delayed/)).toBeVisible();
  await page.getByRole("button", { name: "Mark all as read" }).click();
  await page.getByRole("button", { name: /Unread · 0/ }).click();
  await expect(page.getByText("No notifications match this filter.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Notification feed" })).toBeVisible();
});

test("approver can clear tenant demo history after confirmation", async ({ page }) => {
  await signIn(page, "approver");
  await triggerScenario(page, "Clear history scenario", "weather");
  await page.getByRole("button", { name: "Data Studio" }).click();
  await page.getByRole("button", { name: "Clear demo history" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("This tenant's runs and notifications will be removed.");
  await dialog.getByRole("button", { name: "Clear history" }).click();
  await expect(page.getByRole("status")).toContainText(/runs and notifications cleared/);
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

test("Indonesian dashboard is accessible and responsive", async ({ page }) => {
  const demoTitle = "Extreme weather delays cargo ship";
  await signIn(page, "approver", "id");
  await triggerScenario(page, demoTitle, "weather", "id");
  await expect(page.getByText("Deteksi Gangguan")).toBeVisible();
  await saveSection(page, demoTitle, "timeline-id.png");

  const screenshotDirectory = resolve(process.cwd(), "../docs/screenshots");
  const chartSection = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "Biaya vs waktu pengiriman" }) });
  if (await chartSection.count()) {
    await chartSection.last().screenshot({
      path: resolve(screenshotDirectory, "vendor-charts-id.png"),
    });
  }

  await saveSection(page, "Ringkasan Chain of Thought", "chain-of-thought-id.png");
  const notifications = page.getByRole("region", { name: "Feed notifikasi" });
  await notifications.screenshot({
    path: resolve(screenshotDirectory, "notification-feed-id.png"),
  });
  await saveSection(page, "Purchase order", "po-approval-id.png");
  await page.screenshot({
    path: resolve(screenshotDirectory, "chainmind-pending-approval-id.png"),
    fullPage: true,
  });

  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .exclude(".recharts-wrapper")
    .analyze();
  expect(
    accessibility.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? "")),
  ).toEqual([]);

  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toBeVisible();
  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.getByRole("heading", { name: demoTitle })).toBeVisible();
    const overflowingElements = await page.evaluate(() =>
      Array.from(document.querySelectorAll("body *"))
        .filter((element) => element.getBoundingClientRect().right > window.innerWidth + 1)
        .slice(0, 8)
        .map((element) => `${element.tagName}.${(element as HTMLElement).className}`),
    );
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      `horizontal page overflow at ${width}px: ${overflowingElements.join(", ")}`,
    ).toBe(true);
  }

  await notifications.getByRole("button", { name: "Setujui" }).last().click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Konfirmasi keputusan" }).click();
  await page.getByRole("button", { name: "KPI" }).click();
  await expect(page.getByRole("heading", { name: "KPI respons" })).toBeVisible();
  await saveSection(page, "KPI respons", "kpis-id.png");
});

test("live proposal flow highlights the seeded stages and decision branches in both languages", async ({ page }) => {
  const demoTitle = "Extreme weather delays cargo ship";
  const screenshotDirectory = resolve(process.cwd(), "../docs/screenshots");
  mkdirSync(screenshotDirectory, { recursive: true });

  await signIn(page, "approver", "en");
  await triggerScenario(page, demoTitle, "weather", "en");
  await page.getByRole("button", { name: "Flow", exact: true }).click();
  const diagram = page.getByRole("img", { name: "Live end-to-end disruption resolution flow" });
  await expect(diagram).toBeVisible();
  for (let stage = 1; stage <= 4; stage += 1) {
    await expect(page.getByTestId(`flow-stage-${stage}`)).toHaveAttribute("data-status", "complete");
  }
  await expect(page.getByTestId("flow-stage-5")).toHaveAttribute("data-status", "active");
  await expect(page.getByTestId("flow-stage-6")).toHaveAttribute("data-status", "waiting");
  await expect(page.getByTestId("flow-branch-significant-impact")).toHaveAttribute("data-active", "true");
  await expect(page.getByTestId("flow-branch-insignificant-end")).toHaveAttribute("data-active", "false");
  await expect(page.getByText(/Vendor B: 2d/)).toBeVisible();
  await expect(page.getByText(/PENDING_APPROVAL/)).toBeVisible();
  const englishAxe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(
    englishAxe.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? "")),
  ).toEqual([]);
  await page.screenshot({ path: resolve(screenshotDirectory, "flow-en.png"), fullPage: true });

  await page.getByRole("group").getByRole("button", { name: "ID" }).click();
  await expect(page.getByRole("heading", { name: "Alur" })).toBeVisible();
  await expect(page.getByTestId("flow-decision-significant")).toHaveText(/Gangguan[\s\S]*Signifikan\?/);
  const indonesianAxe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(
    indonesianAxe.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? "")),
  ).toEqual([]);
  await page.screenshot({ path: resolve(screenshotDirectory, "flow-id.png"), fullPage: true });
});

test("presenter mode auto-runs the weather fixture and advances narration", async ({ page }) => {
  await signIn(page, "approver", "en", true);
  await expect(page.getByRole("heading", { name: "Flow" })).toBeVisible();
  await expect(page.getByTestId("flow-stage-0")).toContainText("Extreme weather delays cargo ship");
  const presenter = page.getByRole("region", { name: "Presenter mode" });
  await expect(presenter).toContainText("The Microchip X cargo ship is delayed five days");
  for (let stage = 1; stage <= 4; stage += 1) {
    await expect(page.getByTestId(`flow-stage-${stage}`)).toHaveAttribute("data-status", "complete");
  }
  await expect(page.getByTestId("flow-stage-5")).toHaveAttribute("data-status", "active");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(presenter).toContainText("Monitoring classifies the disruption");
  await expect(page.getByText(/Vendor B: 2d/)).toBeVisible();
  await expect(page.getByText(/PENDING_APPROVAL/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Usage & Plan" })).toHaveCount(0);
});

test("offline replay loads the generated mock run read-only when the API is unavailable", async ({ page }) => {
  await page.route("http://127.0.0.1:18000/**", (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"API unavailable"}' }),
  );
  await signIn(page, "approver");
  await page.getByRole("button", { name: "Load recorded replay" }).click();
  await expect(page.getByRole("status", { name: "Replay mode" })).toContainText("REPLAY");
  await expect(page.getByRole("img", { name: "Live end-to-end disruption resolution flow" })).toBeVisible();
  await expect(page.getByText("Vendor B: 2d")).toBeVisible();
  await expect(page.getByRole("button", { name: "Analyze disruption" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Usage & Plan" })).toHaveCount(0);
});

test("dashboard fits projector and mobile viewports with bilingual light and dark screenshots", async ({ page }) => {
  await signIn(page, "approver", "en");
  const screenshotDirectory = resolve(process.cwd(), "../docs/screenshots");
  for (const language of ["en", "id"] as const) {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.getByRole("group").getByRole("button", { name: language === "en" ? "EN" : "ID" }).click();
    for (const theme of ["light", "dark"] as const) {
      const currentTheme = await page.locator("html").getAttribute("data-theme");
      if (currentTheme !== theme) {
        await page.getByRole("button", { name: language === "id" ? "Ganti tema" : "Toggle theme" }).click();
      }
      const dimensions = await page.evaluate(() => {
        const element = document.scrollingElement;
        return {
          clientHeight: element?.clientHeight ?? 0,
          scrollHeight: element?.scrollHeight ?? 0,
          clientWidth: element?.clientWidth ?? 0,
          scrollWidth: element?.scrollWidth ?? 0,
        };
      });
      expect(dimensions.scrollHeight).toBeLessThanOrEqual(dimensions.clientHeight + 1);
      expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
      await page.screenshot({
        path: resolve(screenshotDirectory, `dashboard-${language}-${theme}.png`),
      });
    }
  }
  await page.setViewportSize({ width: 375, height: 667 });
  const mobileDimensions = await page.evaluate(() => {
    const element = document.scrollingElement;
    return {
      clientHeight: element?.clientHeight ?? 0,
      scrollHeight: element?.scrollHeight ?? 0,
      clientWidth: element?.clientWidth ?? 0,
      scrollWidth: element?.scrollWidth ?? 0,
    };
  });
  expect(mobileDimensions.scrollHeight).toBeLessThanOrEqual(mobileDimensions.clientHeight + 1);
  expect(mobileDimensions.scrollWidth).toBeLessThanOrEqual(mobileDimensions.clientWidth + 1);
});

test("welcome, login, and sandbox IdP are accessible in Indonesian and English light/dark themes", async ({ page }) => {
  const screenshotDirectory = resolve(process.cwd(), "../docs/screenshots");
  mkdirSync(screenshotDirectory, { recursive: true });

  for (const language of ["id", "en"] as const) {
    for (const theme of ["light", "dark"] as const) {
      await page.addInitScript(
        ({ selectedLanguage, selectedTheme }) => {
          localStorage.setItem("chainmind.language", selectedLanguage);
          localStorage.setItem("chainmind.theme", selectedTheme);
          localStorage.setItem("chainmind.largeText", "false");
          localStorage.setItem("chainmind.highContrast", "false");
          sessionStorage.removeItem("chainmind.welcome.seen");
        },
        { selectedLanguage: language, selectedTheme: theme },
      );
      await page.setViewportSize({ width: 1280, height: 720 });
      await page.goto("/");

      const welcomeButton = language === "id" ? "Mulai" : "Get started";
      const loginButton = language === "id"
        ? "Masuk dengan ChainMind SSO"
        : "Sign in with ChainMind SSO";
      const themeSlug = `${language}-${theme}`;
      const assertNoDocumentScroll = async () => {
        const dimensions = await page.evaluate(() => {
          const element = document.scrollingElement;
          return {
            clientHeight: element?.clientHeight ?? 0,
            scrollHeight: element?.scrollHeight ?? 0,
            clientWidth: element?.clientWidth ?? 0,
            scrollWidth: element?.scrollWidth ?? 0,
          };
        });
        expect(dimensions.scrollHeight).toBeLessThanOrEqual(dimensions.clientHeight + 1);
        expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
      };
      const assertAxeClean = async () => {
        const results = await new AxeBuilder({ page }).analyze();
        expect(results.violations).toEqual([]);
      };

      await expect(page.getByRole("button", { name: welcomeButton })).toBeVisible();
      await assertNoDocumentScroll();
      await assertAxeClean();
      await page.screenshot({
        path: resolve(screenshotDirectory, `welcome-${themeSlug}.png`),
      });

      await page.getByRole("button", { name: welcomeButton }).click();
      await expect(page.getByRole("button", { name: loginButton })).toBeVisible();
      await assertNoDocumentScroll();
      await assertAxeClean();
      await page.screenshot({
        path: resolve(screenshotDirectory, `login-${themeSlug}.png`),
      });

      await page.getByRole("button", { name: loginButton }).click();
      await expect(page.locator("body")).toHaveAttribute("data-theme", theme);
      await expect(page.locator("body")).toHaveAttribute("data-text-scale", "normal");
      await expect(page.locator("body")).toHaveAttribute("data-contrast", "standard");
      await expect(page.getByRole("heading", {
        name: language === "id" ? "Masuk ke ChainMind" : "Sign in to ChainMind",
      })).toBeVisible();
      await assertNoDocumentScroll();
      await assertAxeClean();
      await page.screenshot({
        path: resolve(screenshotDirectory, `idp-${themeSlug}.png`),
      });
    }
  }
});

test("entry screens fit mobile with large text/high contrast and wrong IdP credentials show a generic error", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("chainmind.language", "id");
    localStorage.setItem("chainmind.theme", "dark");
    localStorage.setItem("chainmind.largeText", "true");
    localStorage.setItem("chainmind.highContrast", "true");
  });
  await page.setViewportSize({ width: 375, height: 667 });

  const assertNoVerticalDocumentScroll = async () => {
    const dimensions = await page.evaluate(() => {
      const element = document.scrollingElement;
      return {
        clientHeight: element?.clientHeight ?? 0,
        scrollHeight: element?.scrollHeight ?? 0,
      };
    });
    expect(dimensions.scrollHeight).toBeLessThanOrEqual(dimensions.clientHeight + 1);
  };

  await page.goto("/");
  await expect(page.getByRole("button", { name: "Mulai" })).toBeVisible();
  await assertNoVerticalDocumentScroll();
  await page.getByRole("button", { name: "Mulai" }).click();
  await expect(page.getByRole("button", { name: "Masuk dengan ChainMind SSO" })).toBeVisible();
  await assertNoVerticalDocumentScroll();
  await page.getByRole("button", { name: "Masuk dengan ChainMind SSO" }).click();
  await expect(page.locator("body")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("body")).toHaveAttribute("data-text-scale", "large");
  await expect(page.locator("body")).toHaveAttribute("data-contrast", "high");
  await assertNoVerticalDocumentScroll();

  await page.locator('input[name="username"]').fill("approver");
  await page.locator('input[name="password"]').fill("incorrect-password");
  await page.locator('button[type="submit"]').click();
  await expect(page.getByRole("alert")).toContainText(
    "Gagal masuk. Periksa nama pengguna dan kata sandi, lalu coba lagi.",
  );
  await expect(page.locator("body")).toHaveAttribute("data-theme", "dark");
  await assertNoVerticalDocumentScroll();
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
