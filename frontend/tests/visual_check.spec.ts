import { test, expect, type Page } from "@playwright/test";
import fs from "fs";
import path from "path";

/**
 * Visual verification for the Kisan Sathi dashboard - Part A's 4 cards +
 * Part B's Regeneration Score + 5 module cards. Runs against the already-
 * running dev server (see playwright.config.ts) rather than curl, because
 * curl cannot confirm anything actually rendered in the DOM.
 *
 * Two scenarios per the Part B remediation brief:
 *   A. Soil test data provided, no crop photo.
 *   B. No soil test data, WITH a crop photo (exercises the CNN health-check
 *      upload flow end-to-end through the real UI).
 *
 * Screenshots land in ../../visual_checks/ (gitignored - see .gitignore).
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const SCREENSHOT_DIR = path.join(REPO_ROOT, "visual_checks");
const SAMPLE_PHOTO_DIR = path.join(REPO_ROOT, "backend", "cnn_training", "subset_small", "Potato___healthy");

fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

const MODULE_TEST_IDS = [
  "module-card-soil_status",
  "module-card-irrigation_advice",
  "module-card-crop_recommendation",
  "module-card-rotation_suggestion",
  "module-card-rotation",
  "module-card-soil_health",
  "module-card-fertilizer",
  "module-card-cover_cropping",
  "module-card-irrigation_efficiency",
];

async function fillCoreFields(page: Page, crop: string) {
  await page.goto("/");
  await page.getByTestId("input-pincode").fill("141001");
  await page.getByTestId("input-land-size").fill("2.5");
  const options = await page.getByTestId("select-crop").locator("option").allTextContents();
  const matchingOption = options.find((label) => label.toLowerCase().startsWith(crop.toLowerCase()));
  if (matchingOption) {
    await page.getByTestId("select-crop").selectOption({ label: matchingOption });
  } else {
    // Fall back to "Other crop" free-text entry if it's not in the dropdown.
    await page.getByTestId("select-crop").selectOption({ label: "Other crop (type it myself)" });
    await page.locator('input[placeholder="Type the crop name"]').fill(crop);
  }
  await page.getByTestId("irrigation-borewell").click();
}

async function waitForDashboard(page: Page) {
  await expect(page.getByTestId("regen-score-card")).toBeVisible({ timeout: 45_000 });
  for (const testId of [
    "module-card-soil_status",
    "module-card-irrigation_advice",
    "module-card-crop_recommendation",
    "module-card-rotation_suggestion",
  ]) {
    await expect(page.getByTestId(testId)).toBeVisible();
  }
  for (const testId of [
    "module-card-rotation",
    "module-card-soil_health",
    "module-card-fertilizer",
    "module-card-cover_cropping",
    "module-card-irrigation_efficiency",
  ]) {
    await expect(page.getByTestId(testId)).toBeVisible({ timeout: 20_000 });
  }
}

async function assertNonEmpty(page: Page, testId: string) {
  const text = (await page.getByTestId(testId).innerText()).trim();
  expect(text.length, `${testId} should have non-empty content`).toBeGreaterThan(0);
}

test("Scenario A: soil test data provided, no crop photo", async ({ page }) => {
  await fillCoreFields(page, "Wheat");

  await page.getByTestId("soil-test-yes").click();
  await page.getByTestId("input-soil-n").fill("240");
  await page.getByTestId("input-soil-p").fill("15");
  await page.getByTestId("input-soil-k").fill("140");
  await page.getByTestId("input-soil-ph").fill("6.8");
  await page.getByTestId("input-soil-oc").fill("0.6");

  await page.getByTestId("submit-farm-form").click();
  await waitForDashboard(page);

  await assertNonEmpty(page, "regen-score-card");
  for (const testId of MODULE_TEST_IDS) {
    if (await page.getByTestId(testId).count()) {
      await assertNonEmpty(page, testId);
    }
  }

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "scenario_a_soil_test_no_photo.png"),
    fullPage: true,
  });
});

test("Scenario B: no soil test, with crop photo (CNN health check)", async ({ page }) => {
  await fillCoreFields(page, "Potato");

  await page.getByTestId("soil-test-no").click();

  const sampleFiles = fs.readdirSync(SAMPLE_PHOTO_DIR).filter((f) => /\.(jpg|jpeg)$/i.test(f));
  expect(sampleFiles.length, "expected at least one sample photo for the health-check scenario").toBeGreaterThan(0);
  const samplePhoto = path.join(SAMPLE_PHOTO_DIR, sampleFiles[0]);

  await page.getByTestId("input-crop-photo").setInputFiles(samplePhoto);
  // The CNN health-check result must appear before we treat the upload as verified.
  await expect(page.getByTestId("photo-status-done")).toBeVisible({ timeout: 30_000 });
  await assertNonEmpty(page, "photo-status-done");

  await page.getByTestId("submit-farm-form").click();
  await waitForDashboard(page);

  await assertNonEmpty(page, "regen-score-card");
  for (const testId of MODULE_TEST_IDS) {
    if (await page.getByTestId(testId).count()) {
      await assertNonEmpty(page, testId);
    }
  }

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "scenario_b_photo_no_soil_test.png"),
    fullPage: true,
  });
});
