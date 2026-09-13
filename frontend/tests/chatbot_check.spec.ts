import { test, expect } from "@playwright/test";
import fs from "fs";
import path from "path";

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const SCREENSHOT_DIR = path.join(REPO_ROOT, "visual_checks");
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

test("chatbot: opens, greets, answers via suggestion chip and free text, and closes", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("language-option-en").click({ timeout: 5000 }).catch(() => {});

  await page.getByTestId("chatbot-toggle").click();
  await expect(page.getByTestId("chatbot-panel")).toBeVisible();
  await expect(page.getByTestId("chatbot-messages")).toContainText("Hello! I'm the Kisan Mitra assistant");
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "_scratch_chatbot_open.png") });

  // Suggestion chip
  await page.getByTestId("chatbot-suggestion-identity").click();
  await expect(page.getByTestId("chatbot-messages")).toContainText("built-in assistant");

  // Free-text question
  await page.getByTestId("chatbot-input").fill("how do I check my soil health");
  await page.getByTestId("chatbot-send").click();
  await expect(page.getByTestId("chatbot-messages")).toContainText("Soil health card shows");

  // Fallback for gibberish
  await page.getByTestId("chatbot-input").fill("asdkjqwoe random gibberish");
  await page.getByTestId("chatbot-send").click();
  await expect(page.getByTestId("chatbot-messages")).toContainText("I'm not sure about that one");

  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "_scratch_chatbot_conversation.png") });

  await page.getByTestId("chatbot-close").click();
  await expect(page.getByTestId("chatbot-panel")).not.toBeVisible();
});

test("chatbot works in Hindi and matches on Hindi keywords too", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("language-option-hi").click({ timeout: 5000 }).catch(() => {});
  await page.getByTestId("chatbot-toggle").click();
  await expect(page.getByTestId("chatbot-messages")).toContainText("नमस्ते");

  await page.getByTestId("chatbot-input").fill("पानी");
  await page.getByTestId("chatbot-send").click();
  await expect(page.getByTestId("chatbot-messages")).toContainText("सिंचाई कार्ड");
});

test("Check my report: nudges to wizard when no report yet, jumps to results once submitted", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("language-option-en").click({ timeout: 5000 }).catch(() => {});

  await page.getByTestId("more-menu-button").click();
  await page.getByTestId("menu-my-report").click();
  await expect(page.getByTestId("report-hint")).toBeVisible();
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "_scratch_report_hint.png") });

  // Now actually submit, then use "Check my report" to jump straight to results.
  await page.getByTestId("input-pincode").fill("141001");
  await page.getByTestId("input-land-size").fill("2.5");
  await page.getByTestId("wizard-next").click();
  await page.getByTestId("select-crop").selectOption("Wheat");
  await page.getByTestId("wizard-next").click();
  await page.getByTestId("irrigation-borewell").click();
  await page.getByTestId("wizard-next").click();
  await page.getByTestId("submit-farm-form").click();
  await expect(page.getByTestId("module-card-soil_status")).toBeVisible({ timeout: 45000 });

  await page.evaluate(() => window.scrollTo(0, 0));
  await page.getByTestId("more-menu-button").click();
  await page.getByTestId("menu-my-report").click();
  await expect(page.getByTestId("module-card-soil_status")).toBeInViewport();
});
