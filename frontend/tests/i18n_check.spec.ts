import { test, expect } from "@playwright/test";
import fs from "fs";
import path from "path";

/**
 * Live verification of the multilingual system: first-visit language picker,
 * language persistence across reload, and the persistent header switcher.
 * Screenshots land in ../../visual_checks/ (gitignored).
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const SCREENSHOT_DIR = path.join(REPO_ROOT, "visual_checks");
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

test("first visit shows the language picker modal", async ({ page }) => {
  await page.goto("/");
  const modal = page.getByRole("dialog");
  await expect(modal).toBeVisible();
  await expect(page.getByTestId("language-option-hi")).toBeVisible();
  await expect(page.getByTestId("language-option-ta")).toBeVisible();
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "i18n_01_picker_modal.png"), fullPage: true });
});

test("choosing Hindi translates the page and persists across reload", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("language-option-hi").click();
  await expect(page.getByRole("dialog")).not.toBeVisible();

  await expect(page.getByText("किसान मित्र")).toBeVisible();
  await expect(page.getByTestId("wizard-next")).toHaveText("आगे");
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "i18n_02_hindi.png"), fullPage: true });

  await page.reload();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.getByText("किसान मित्र")).toBeVisible();
});

test("language switcher in header changes language to Tamil live", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("language-option-en").click();
  await expect(page.getByText("Kisan Mitra")).toBeVisible();

  await page.getByTestId("language-switcher").selectOption("ta");
  await expect(page.getByText("கிசான் மித்ரா")).toBeVisible();
  await expect(page.getByTestId("wizard-next")).toHaveText("அடுத்து");
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "i18n_03_tamil_switch.png"), fullPage: true });
});

test("full flow with results renders translated dashboard in Punjabi", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("language-option-pa").click();

  await page.getByTestId("input-pincode").fill("141001");
  await page.getByTestId("input-land-size").fill("2.5");
  await page.getByTestId("wizard-next").click();
  await page.getByTestId("select-crop").selectOption("Wheat");
  await page.getByTestId("wizard-next").click();
  await page.getByTestId("irrigation-borewell").click();
  await page.getByTestId("soil-test-yes").click();
  await page.getByTestId("wizard-next").click();
  await page.getByTestId("submit-farm-form").click();

  await expect(page.getByTestId("module-card-soil_status")).toBeVisible({ timeout: 45000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "i18n_04_punjabi_dashboard.png"), fullPage: true });
});
