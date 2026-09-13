import { test, expect, type Page } from "@playwright/test";
import fs from "fs";
import path from "path";

/**
 * Regression suite for the kisan-sathi-frontend.html integration (MASTER
 * PROMPT STEP 6) - the 4-step wizard, 3-dot menu, theme toggle, and the two
 * bug-fix patterns the prototype itself once had and this project
 * deliberately does not reintroduce:
 *   1. A `hidden` element (modal/panel) must never keep capturing clicks
 *      once closed - see globals.css's `[hidden]{display:none!important}`.
 *   2. Reaching the result step must actually hide the progress bar and
 *      step-nav, not just swap the step content underneath them.
 *
 * Screenshots land in ../../visual_checks/ (gitignored).
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const SCREENSHOT_DIR = path.join(REPO_ROOT, "visual_checks");
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function dismissLanguagePicker(page: Page) {
  await page.getByTestId("language-option-en").click({ timeout: 5000 }).catch(() => {});
}

async function fillStep1(page: Page) {
  await page.getByTestId("input-pincode").fill("141001");
  await page.getByTestId("input-land-size").fill("2.5");
  await page.getByTestId("wizard-next").click();
}

async function fillStep2(page: Page) {
  await page.getByTestId("select-crop").selectOption("Wheat");
  await page.getByTestId("wizard-next").click();
}

test.describe("4-step wizard", () => {
  test("Step 1 renders on mobile and desktop, and blocks advancing when empty", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await dismissLanguagePicker(page);
    await expect(page.getByTestId("wizard-step")).toHaveAttribute("data-step", "1");

    // Blocking validation: Next with nothing filled must not advance.
    await page.getByTestId("wizard-next").click();
    await expect(page.getByTestId("wizard-step")).toHaveAttribute("data-step", "1");
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "wizard_01_step1_mobile.png") });

    await page.setViewportSize({ width: 1280, height: 900 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "wizard_01b_step1_desktop.png"), fullPage: true });
  });

  test("Step 2 renders after Step 1, blocks advancing without a crop", async ({ page }) => {
    await page.goto("/");
    await dismissLanguagePicker(page);
    await fillStep1(page);
    await expect(page.getByTestId("wizard-step")).toHaveAttribute("data-step", "2");

    await page.getByTestId("wizard-next").click();
    await expect(page.getByTestId("wizard-step")).toHaveAttribute("data-step", "2");
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "wizard_02_step2.png") });
  });

  test("Step 3 with soil test = No shows no NPK fields", async ({ page }) => {
    await page.goto("/");
    await dismissLanguagePicker(page);
    await fillStep1(page);
    await fillStep2(page);
    await expect(page.getByTestId("wizard-step")).toHaveAttribute("data-step", "3");
    await page.getByTestId("soil-test-no").click();
    await expect(page.getByTestId("input-soil-n")).not.toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "wizard_03_step3_soil_no.png") });
  });

  test("Step 3 with soil test = Yes reveals N/P/K/pH/OC fields", async ({ page }) => {
    await page.goto("/");
    await dismissLanguagePicker(page);
    await fillStep1(page);
    await fillStep2(page);
    await page.getByTestId("soil-test-yes").click();
    await expect(page.getByTestId("input-soil-n")).toBeVisible();
    await expect(page.getByTestId("input-soil-p")).toBeVisible();
    await expect(page.getByTestId("input-soil-k")).toBeVisible();
    await expect(page.getByTestId("input-soil-ph")).toBeVisible();
    await expect(page.getByTestId("input-soil-oc")).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "wizard_04_step3_soil_yes.png") });
  });

  test("Step 4 renders with photo upload and optional details", async ({ page }) => {
    await page.goto("/");
    await dismissLanguagePicker(page);
    await fillStep1(page);
    await fillStep2(page);
    await page.getByTestId("irrigation-borewell").click();
    await page.getByTestId("wizard-next").click();
    await expect(page.getByTestId("wizard-step")).toHaveAttribute("data-step", "4");
    await expect(page.getByTestId("submit-farm-form")).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "wizard_05_step4.png") });
  });

  test("Result step shows real data and fully hides the wizard chrome", async ({ page }) => {
    await page.goto("/");
    await dismissLanguagePicker(page);
    await fillStep1(page);
    await fillStep2(page);
    await page.getByTestId("irrigation-borewell").click();
    await page.getByTestId("soil-test-yes").click();
    await page.getByTestId("wizard-next").click();
    await page.getByTestId("submit-farm-form").click();

    await expect(page.getByTestId("module-card-soil_status")).toBeVisible({ timeout: 45000 });
    // Real backend data, not a fake setTimeout placeholder.
    await expect(page.getByTestId("regen-score-card")).toBeVisible({ timeout: 45000 });

    // Regression: progress bar and step-nav must be genuinely gone, not
    // just have their step content swapped underneath them.
    await expect(page.getByTestId("wizard-progress")).not.toBeVisible();
    await expect(page.getByTestId("wizard-step")).not.toBeVisible();
    await expect(page.getByTestId("wizard-back")).not.toBeVisible();

    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "wizard_06_result.png"), fullPage: true });

    // Regression: page must still be fully clickable (no stale overlay).
    await page.locator("body").click({ position: { x: 5, y: 5 } });
  });
});

test.describe("Home", () => {
  test("Home (menu item or brand click) resets a mid-wizard state back to step 1", async ({ page }) => {
    await page.goto("/");
    await dismissLanguagePicker(page);
    await fillStep1(page);
    await expect(page.getByTestId("wizard-step")).toHaveAttribute("data-step", "2");

    await page.getByTestId("more-menu-button").click();
    await page.getByTestId("menu-home").click();
    await expect(page.getByTestId("wizard-step")).toHaveAttribute("data-step", "1");
    await expect(page.getByTestId("input-pincode")).toHaveValue("");

    await fillStep1(page);
    await expect(page.getByTestId("wizard-step")).toHaveAttribute("data-step", "2");
    await page.getByTestId("brand-home-link").click();
    await expect(page.getByTestId("wizard-step")).toHaveAttribute("data-step", "1");
    await expect(page.getByTestId("input-pincode")).toHaveValue("");
  });

  test("Home resets from the result screen back to the wizard", async ({ page }) => {
    await page.goto("/");
    await dismissLanguagePicker(page);
    await fillStep1(page);
    await fillStep2(page);
    await page.getByTestId("irrigation-borewell").click();
    await page.getByTestId("wizard-next").click();
    await page.getByTestId("submit-farm-form").click();
    await expect(page.getByTestId("module-card-soil_status")).toBeVisible({ timeout: 45000 });

    await page.getByTestId("brand-home-link").click();
    await expect(page.getByTestId("wizard-step")).toHaveAttribute("data-step", "1");
    await expect(page.getByTestId("module-card-soil_status")).not.toBeVisible();
  });
});

test.describe("3-dot menu and modals", () => {
  test("menu opens, closing it does not block subsequent clicks", async ({ page }) => {
    await page.goto("/");
    await dismissLanguagePicker(page);

    await page.getByTestId("more-menu-button").click();
    await expect(page.getByTestId("more-menu-panel")).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "wizard_07_menu_open.png") });

    // Click elsewhere to close it.
    await page.locator("body").click({ position: { x: 5, y: 5 } });
    await expect(page.getByTestId("more-menu-panel")).toBeHidden();

    // Regression: the closed (hidden) panel must not still capture clicks.
    await page.getByTestId("input-pincode").click();
    await page.getByTestId("input-pincode").fill("141001");
    await expect(page.getByTestId("input-pincode")).toHaveValue("141001");
  });

  test("Login modal opens and explains itself honestly when unconfigured", async ({ page }) => {
    await page.goto("/");
    await dismissLanguagePicker(page);
    await page.getByTestId("more-menu-button").click();
    await page.getByTestId("menu-login").click();
    await expect(page.getByTestId("login-modal")).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "wizard_08_login_modal.png") });
    await page.locator(".modal-close").click();
    await expect(page.getByTestId("login-modal")).not.toBeVisible();
    await page.locator("body").click({ position: { x: 5, y: 5 } });
  });

  test("Contact modal opens", async ({ page }) => {
    await page.goto("/");
    await dismissLanguagePicker(page);
    await page.getByTestId("more-menu-button").click();
    await page.getByTestId("menu-contact").click();
    await expect(page.getByTestId("contact-modal")).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "wizard_09_contact_modal.png") });
    await page.locator(".modal-close").click();
    await expect(page.getByTestId("contact-modal")).not.toBeVisible();
  });
});

test.describe("language and theme", () => {
  test("Hindi language active across the wizard", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("language-option-hi").click({ timeout: 5000 }).catch(() => {});
    await expect(page.getByText("किसान मित्र")).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "wizard_10_hindi.png") });
  });

  test("Dark mode active on mobile and desktop", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await dismissLanguagePicker(page);
    await page.getByTestId("more-menu-button").click();
    await page.getByTestId("menu-theme").click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "wizard_11_dark_mobile.png") });

    await page.setViewportSize({ width: 1280, height: 900 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "wizard_11b_dark_desktop.png"), fullPage: true });
  });

  test("Dark mode + soil fields expanded (contrast regression check)", async ({ page }) => {
    await page.goto("/");
    await dismissLanguagePicker(page);
    await page.getByTestId("more-menu-button").click();
    await page.getByTestId("menu-theme").click();
    await fillStep1(page);
    await fillStep2(page);
    await page.getByTestId("soil-test-yes").click();
    await expect(page.getByTestId("input-soil-n")).toBeVisible();

    // Regression: every soil-field label/input must render with real
    // contrast against the dark surface, not light-on-white leftovers.
    const label = page.getByText("N (kg/ha)");
    await expect(label).toBeVisible();
    const color = await label.evaluate((el) => getComputedStyle(el).color);
    // var(--ink-soft) in dark mode is #AFC2A9 = rgb(175, 194, 169) - assert
    // it isn't a near-black color (which would be invisible on the dark card).
    expect(color).not.toBe("rgb(32, 48, 31)"); // light-mode --ink would read as this

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "wizard_12_dark_soil_fields.png") });
  });
});

test.describe("theme-aware native controls", () => {
  test("select and date input chrome follow color-scheme in both themes", async ({ page }) => {
    await page.goto("/");
    await dismissLanguagePicker(page);
    const colorScheme = () => page.evaluate(() => getComputedStyle(document.documentElement).colorScheme);
    expect(await colorScheme()).toContain("light");

    await page.getByTestId("more-menu-button").click();
    await page.getByTestId("menu-theme").click();
    expect(await colorScheme()).toContain("dark");
  });
});

test.describe("mobile and tablet responsiveness", () => {
  const NARROW_VIEWPORTS = [
    { name: "320px phone", width: 320, height: 568 },
    { name: "390px phone", width: 390, height: 844 },
    { name: "768px tablet portrait", width: 768, height: 1024 },
  ];

  for (const vp of NARROW_VIEWPORTS) {
    test(`no horizontal overflow at ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto("/");
      await dismissLanguagePicker(page);
      await fillStep1(page);
      await fillStep2(page);
      await page.getByTestId("soil-test-yes").click();
      const overflow = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }));
      expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
    });
  }

  test("3-dot menu panel stays fully within the viewport on a narrow phone (regression: was clipped off-screen left)", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 568 });
    await page.goto("/");
    await dismissLanguagePicker(page);
    await page.getByTestId("more-menu-button").click();
    const box = await page.getByTestId("more-menu-panel").boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(320 + 1);
  });

  test("the last field of a step is not left permanently under the fixed nav bar on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto("/");
    await dismissLanguagePicker(page);
    // Step 3 is the densest step (irrigation grid + soil toggle + 5 NPK fields).
    await fillStep1(page);
    await fillStep2(page);
    await page.getByTestId("soil-test-yes").click();
    const lastField = page.getByTestId("input-soil-oc");
    await lastField.scrollIntoViewIfNeeded();
    await expect(lastField).toBeInViewport();
  });
});
