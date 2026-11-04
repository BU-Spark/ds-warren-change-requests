import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
const fixtures = path.resolve("test-results/fixtures");
test.beforeAll(() => {
  execFileSync(
    "warren_towers/bin/python",
    ["-m", "tests.browser_server", fixtures],
    { cwd: ".." },
  );
});

test("upload, review, save, resolve and export exactly eight differences", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Upload & review" }),
  ).toBeVisible();
  await page
    .getByLabel("Choose document")
    .setInputFiles(path.join(fixtures, "hundred-rates.pdf"));
  await page.getByLabel("Project name").fill("Example project");
  await page.getByLabel(/^Contractor/).fill("Example Contractor");
  await page.getByRole("button", { name: "Extract labor rates" }).click();
  await expect(
    page.getByRole("heading", { name: "hundred-rates.pdf" }),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    page.getByText("100 rows selected", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Save selected rows" }).click();
  await expect(page.getByRole("status")).toContainText("100 rows saved");
  await page.getByRole("button", { name: "Saved data", exact: true }).click();
  await expect(
    page.getByRole("columnheader", { name: "Regular rate", exact: true }),
  ).toHaveCount(1);
  await page.getByLabel("Select all visible records").check();
  await page
    .getByRole("button", { name: "Set comparison details (100)" })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Classification", { exact: true }).fill("Carpenter");
  await expect(dialog.getByLabel("Generic rate type")).toHaveCount(0);
  await dialog.getByRole("button", { name: "Save comparison details" }).click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole("button", { name: "Check selected (100)" }).click();
  await expect(page.getByRole("status")).toContainText(
    "92 matched, 8 differences, 0 need review",
  );
  await page
    .getByRole("button", { name: "Differences", exact: false })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Confirmed rate differences" }),
  ).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(8);
  await expect(
    page.getByRole("cell", { name: "Regular (REG)", exact: true }),
  ).toHaveCount(8);
  await expect(
    page.getByText("Out of 100 rates checked · 0 need review"),
  ).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download differences CSV" }).click();
  const download = await downloadPromise;
  const output = await download.path();
  const csv = fs.readFileSync(output!, "utf8");
  expect(csv.trim().split("\n")).toHaveLength(9);
  expect(csv).toContain("difference_per_hour");
  expect(csv).toContain("Example Contractor");
  expect(csv).toContain("reference_rate_field");
  expect(csv).toContain("REG");
  expect(csv).toContain("reg_rate");
  expect(csv).not.toContain("Unspecified");
  await page
    .getByRole("button", { name: "Review", exact: true })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "Submitted rate differs",
  );
  await expect(
    page.getByRole("dialog").getByAltText("Original printed source page"),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("Tracker row 2");
  await page.keyboard.press("Escape");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Confirmed rate differences" }),
  ).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(8);
  for (const width of [1280, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    const overflow = await page.evaluate(() => ({
      width: window.innerWidth,
      scroll: document.documentElement.scrollWidth,
      offenders: [...document.querySelectorAll("body *")]
        .filter(
          (el) =>
            el.getBoundingClientRect().right > window.innerWidth + 1 &&
            getComputedStyle(el).position !== "absolute",
        )
        .map((el) => ({
          tag: el.tagName,
          cls: el.className,
          right: el.getBoundingClientRect().right,
        }))
        .slice(0, 12),
    }));
    expect(overflow.scroll, JSON.stringify(overflow)).toBeLessThanOrEqual(
      width,
    );
    if (width === 1280 || width === 390)
      await page.screenshot({
        path: `test-results/differences-${width}.png`,
        fullPage: true,
      });
  }
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.getByRole("button", { name: "Upload & review" }).click();
  await page.getByRole("button", { name: "Upload another" }).click();
  await page.screenshot({
    path: "test-results/upload-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.screenshot({
    path: "test-results/upload-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("unresolved checks, reference activation, and outdated results remain explicit", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("Choose document")
    .setInputFiles(path.join(fixtures, "worker-detail.pdf"));
  await page.getByLabel("Project name").fill("Example project");
  await page.getByLabel(/^Contractor/).fill("Different Contractor");
  await page.getByRole("button", { name: "Extract labor rates" }).click();
  await expect(
    page.getByRole("heading", { name: "worker-detail.pdf" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Save selected rows" }).click();
  await expect(page.getByRole("status")).toContainText("2 rows saved");
  await page.getByRole("button", { name: "Check saved document" }).click();
  await expect(page.getByRole("status")).toContainText(
    "0 matched, 0 differences, 6 need review",
  );
  await page
    .getByRole("button", { name: "Differences", exact: false })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "No confirmed rate differences" }),
  ).toBeVisible();
  await expect(
    page.getByText("6 checks still need review.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Labor checks", exact: true }).click();
  await page
    .getByRole("button", { name: "Review", exact: true })
    .first()
    .click();
  await page
    .getByRole("button", { name: "Set comparison details", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/^Contractor/).fill("Example Contractor");
  await dialog.getByRole("button", { name: "Save comparison details" }).click();
  await expect(
    page.getByText("This run is outdated", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Rerun check" }).click();
  await expect(page.getByRole("status")).toContainText(
    "3 matched, 0 differences, 3 need review",
  );
  await page.getByRole("button", { name: "Manage schedule" }).click();
  const referenceDialog = page.getByRole("dialog");
  await expect(
    referenceDialog.getByText("Current schedule", { exact: true }),
  ).toBeVisible();
  await referenceDialog
    .getByLabel("Upload reference CSV")
    .setInputFiles(path.join(fixtures, "schedule.csv"));
  await expect(
    referenceDialog.getByRole("heading", { name: /^Preview:/ }),
  ).toBeVisible();
  await referenceDialog
    .getByRole("button", { name: "Activate this schedule" })
    .click();
  await expect(referenceDialog).not.toBeVisible();
  await expect(page.getByRole("status")).toContainText(
    "Reference schedule activated",
  );
});

test("keyboard navigation and dialogs stay usable on small screens", async ({
  page,
}) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await nav.getByRole("button", { name: "Saved data", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Saved data" })).toBeVisible();
  await page
    .getByRole("button", { name: "Review", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog", { name: "Saved labor record" });
  await expect(dialog).toBeVisible();
  for (let index = 0; index < 8; index++) {
    await page.keyboard.press("Tab");
    expect(
      await page.evaluate(
        () =>
          // Native dialogs may let Tab reach browser chrome (BODY), but never background controls.
          document.activeElement === document.body ||
          document.querySelector("dialog")?.contains(document.activeElement),
      ),
    ).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await page.setViewportSize({ width: 320, height: 900 });
  for (const button of await nav.getByRole("button").all()) {
    const rect = await button.boundingBox();
    expect(rect!.x).toBeGreaterThanOrEqual(0);
    expect(rect!.x + rect!.width).toBeLessThanOrEqual(320);
  }
  await nav.getByRole("button", { name: "Upload & review" }).click();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(320);
});

test("display IDs stay distinct and selection survives presentation changes", async ({
  page,
}) => {
  await page.route("**/api/records", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    const records = data.records
      .slice(0, 2)
      .map((row: Record<string, string>, index: number) => ({
        ...row,
        record_id: "a".repeat(12) + String(index + 1).repeat(52),
      }));
    await route.fulfill({ json: { records, details: {} } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Saved data", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(2);
  await expect(
    page.getByRole("cell", { name: "a".repeat(12) + "1", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "a".repeat(12) + "2", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Select all visible records").check();
  await page.getByLabel("Show technical columns and full IDs").check();
  await expect(
    page.getByRole("cell", {
      name: "a".repeat(12) + "1".repeat(52),
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Check selected (2)" }),
  ).toBeEnabled();
  await page.getByLabel("Show technical columns and full IDs").uncheck();
  await expect(page.getByLabel("Select all visible records")).toBeChecked();
});

test("document reading is automatic with no OCR configuration section", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Upload a change request" }),
  ).toBeVisible();
  await expect(
    page.getByRole("checkbox", { name: /ocr|scanned/i }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Use local OCR when the document is an image or scan.", {
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "User settings", exact: true }),
  ).toHaveCount(0);
  await page
    .getByLabel("Choose document")
    .setInputFiles(path.join(fixtures, "worker-detail.pdf"));
  await page.getByLabel("Project name").fill("Example project");
  await page.getByLabel(/^Contractor/).fill("Example Contractor");
  const uploaded = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === "/api/sessions" &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Extract labor rates" }).click();
  expect((await (await uploaded).json()).use_ocr).toBe(true);
  await expect(
    page.getByRole("heading", { name: "Printed labor rates" }),
  ).toBeVisible();
});

test("review queue prioritizes documents, jumps to required tables and remembers progress", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("Choose document")
    .setInputFiles(path.join(fixtures, "needs-review.pdf"));
  await page.getByLabel("Project name").fill("Review queue project");
  await page.getByLabel(/^Contractor/).fill("Example Contractor");
  await page.getByRole("button", { name: "Extract labor rates" }).click();
  const checklist = page.getByRole("region", { name: "Review checklist" });
  await expect(checklist).toBeVisible();
  await expect(
    checklist.getByText("3 need attention", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Source page")).toHaveValue("2");
  await expect(
    page.getByRole("button", { name: "Save selected rows" }),
  ).toBeDisabled();
  await page.locator(".review-check input").first().check();
  await expect(
    checklist.getByText("2 need attention", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    checklist.getByText("2 need attention", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".review-check input").first()).toBeChecked();
  await checklist.getByRole("button", { name: "Next table to review" }).click();
  await expect(page.locator(".table-review.target-table")).toBeFocused();
  await page.locator(".table-review.target-table input[type=checkbox]").check();
  await expect(
    checklist.getByText("1 need attention", { exact: true }),
  ).toBeVisible();
  await checklist.getByRole("button", { name: "Next table to review" }).click();
  await expect(page.getByLabel("Source page")).toHaveValue("3");
  await page.locator(".table-review.target-table input[type=checkbox]").check();
  await expect(
    checklist.getByText("0 need attention", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save selected rows" }),
  ).toBeEnabled();
  await page.locator(".review-check input").first().uncheck();
  await expect(
    checklist.getByText("1 need attention", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Upload another" }).click();
  await page
    .getByLabel("Choose document")
    .setInputFiles(path.join(fixtures, "worker-detail.pdf"));
  await page.getByLabel("Project name").fill("Review queue project");
  await page.getByLabel(/^Contractor/).fill("Example Contractor");
  await page.getByRole("button", { name: "Extract labor rates" }).click();
  await expect(
    page.getByRole("heading", { name: "worker-detail.pdf" }),
  ).toBeVisible();
  const docs = page.locator(".recent-list");
  await expect(docs.getByRole("button").first()).toContainText(
    "needs-review.pdf",
  );
  await page.getByLabel(/Show only documents needing attention/).check();
  await expect(docs.getByRole("button")).toHaveCount(1);
  await docs.getByRole("button").first().click();
  await expect(page.getByLabel("Source page")).toHaveValue("3");
  await page.setViewportSize({ width: 390, height: 900 });
  expect(
    (await page
      .getByRole("heading", { name: "needs-review.pdf" })
      .boundingBox())!.width,
  ).toBeGreaterThan(150);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: "test-results/review-queue-mobile.png",
    fullPage: true,
  });
});

test("classification graph matches mason rates and saved relationships refine grades", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Labor checks", exact: true }).click();
  await page
    .getByRole("button", { name: "Manage schedule", exact: true })
    .click();
  let dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Upload reference CSV")
    .setInputFiles(path.join(fixtures, "graph-schedule.csv"));
  await dialog.getByRole("button", { name: "Activate this schedule" }).click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole("button", { name: "Upload & review" }).click();
  await page
    .getByLabel("Choose document")
    .setInputFiles(path.join(fixtures, "masonry.pdf"));
  await page.getByLabel("Project name").fill("Graph test project");
  await page.getByLabel(/^Contractor/).fill("Example Contractor");
  await page.getByRole("button", { name: "Extract labor rates" }).click();
  await expect(
    page.getByRole("heading", { name: "masonry.pdf" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Save selected rows" }).click();
  await expect(page.getByRole("status")).toContainText("3 rows saved");
  await page.getByRole("button", { name: "Check saved document" }).click();
  await expect(page.getByRole("status")).toContainText(
    "2 matched, 1 differences, 0 need review",
  );
  await page
    .getByRole("button", { name: "Differences", exact: false })
    .first()
    .click();
  await expect(
    page.getByText("Not in approved rates", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Review", exact: true }).click();
  dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Multiple classifications are possible");
  await expect(dialog).toContainText("Masonry");
  await dialog.getByRole("button", { name: "Close dialog" }).click();
  await page
    .getByRole("button", { name: "Classification map", exact: true })
    .click();
  dialog = page.getByRole("dialog", { name: "Classification map" });
  await expect(
    dialog
      .locator(".classification-tree")
      .getByText("Bricklayer Journey Person", { exact: true }),
  ).toBeVisible();
  await expect(
    dialog
      .locator(".classification-tree")
      .getByText("Bricklayer Foreperson", { exact: true }),
  ).toBeVisible();
  await dialog.getByLabel("Title printed in the document").fill("Mason");
  await dialog
    .getByLabel("Equivalent tracker classification")
    .selectOption("Bricklayer Journey Person");
  await dialog.getByRole("button", { name: "Save relationship" }).click();
  await expect(
    dialog.getByRole("heading", { name: "Saved relationships" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/classification-map-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 900 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: "test-results/classification-map-mobile.png",
    fullPage: true,
  });
  await dialog.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("button", { name: "Rerun check" }).click();
  await expect(page.getByRole("status")).toContainText(
    "1 matched, 2 differences, 0 need review",
  );
  await page
    .getByRole("button", { name: "Classification map", exact: true })
    .click();
  dialog = page.getByRole("dialog", { name: "Classification map" });
  await dialog
    .getByRole("button", { name: "Remove relationship Mason" })
    .click();
  await expect(
    dialog.getByRole("heading", { name: "Saved relationships" }),
  ).not.toBeVisible();
  await dialog.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("button", { name: "Rerun check" }).click();
  await expect(page.getByRole("status")).toContainText(
    "2 matched, 1 differences, 0 need review",
  );
});

test("initial load selects a fresh replacement for obsolete rules while preserving history", async ({
  page,
}) => {
  await page.route("**/api/checks", async (route) => {
    const response = await route.fetch();
    const runs = await response.json();
    const fresh = {
      ...runs[0],
      id: "fresh-rules",
      stale: false,
      rules_changed: false,
    };
    const legacy = {
      ...fresh,
      id: "old-rules",
      stale: true,
      rules_changed: true,
    };
    await route.fulfill({ json: [fresh, legacy] });
  });
  await page.addInitScript(() => {
    localStorage.setItem("warren-run", "old-rules");
    localStorage.setItem("warren-tab", "checks");
  });
  await page.goto("/");
  await expect(page.getByLabel("Check run")).toHaveValue("fresh-rules");
  await page.getByLabel("Check run").selectOption("old-rules");
  await page.getByRole("button", { name: "Refresh workspace" }).click();
  await expect(page.getByLabel("Check run")).toHaveValue("old-rules");
  await expect(
    page.getByText("This run is outdated.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Refresh workspace" }),
  ).toBeEnabled();
  await page.unrouteAll({ behavior: "wait" });
});

test("uploads and reviews remain navigable without losing active documents", async ({
  page,
  request,
}) => {
  const originalCount = (await (await request.get("/api/records")).json())
    .records.length;
  await page.goto("/");
  await page
    .getByLabel("Choose document")
    .setInputFiles(path.join(fixtures, "needs-review.pdf"));
  await page.getByLabel("Project name").fill("Navigation project");
  await page.getByLabel(/^Contractor/).fill("Navigation contractor");
  const posted = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === "/api/sessions" &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Extract labor rates" }).click();
  const first = await (await posted).json();
  const ready = page.waitForResponse(
    async (r) =>
      new URL(r.url()).pathname === `/api/sessions/${first.id}` &&
      r.request().method() === "GET" &&
      (await r.json()).status === "ready",
  );
  await page.getByRole("tab", { name: "Upload document", exact: true }).click();
  await page
    .getByLabel("Choose document")
    .setInputFiles(path.join(fixtures, "worker-detail.pdf"));
  await page.getByLabel("Project name").fill("Second project");
  await page.getByLabel(/^Contractor/).fill("Second contractor");
  await ready;
  await expect(
    page.getByRole("heading", { name: "Upload a change request" }),
  ).toBeVisible();
  await expect(page.getByLabel("Project name")).toHaveValue("Second project");
  await page.getByRole("tab", { name: /Documents in review/ }).click();
  await expect(
    page.getByRole("heading", { name: "needs-review.pdf" }),
  ).toBeVisible();
  await page.locator(".review-check input").first().check();
  await expect(
    page.getByText("2 need attention", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Source page").selectOption("3");
  await page
    .getByRole("checkbox", { name: /Select record/ })
    .first()
    .uncheck();
  await expect(
    page.getByText("7 rows selected", { exact: true }),
  ).toBeVisible();
  await page.locator(".steps").getByRole("button").nth(0).click();
  await expect(
    page.getByRole("tab", { name: "Upload document", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(
    page.getByRole("heading", { name: "worker-detail.pdf" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Upload document", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: /Documents in review/ }),
  ).toBeFocused();
  await expect(page.getByLabel("Source page")).toHaveValue("3");
  await expect(
    page.getByText("7 rows selected", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Upload document", exact: true }).click();
  await page.getByRole("button", { name: "Extract labor rates" }).click();
  await expect(
    page.getByRole("heading", { name: "worker-detail.pdf" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Printed labor rates" }),
  ).toBeVisible();
  await page
    .locator(".recent-list")
    .getByRole("button")
    .filter({ hasText: "needs-review.pdf" })
    .filter({ hasText: "Navigation contractor" })
    .click();
  await expect(page.getByLabel("Source page")).toHaveValue("3");
  await expect(
    page.getByText("7 rows selected", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("2 need attention", { exact: true }),
  ).toBeVisible();
  await page.locator(".steps").getByRole("button").nth(2).click();
  await expect(
    page.locator(".steps").getByRole("button").nth(2),
  ).toHaveAttribute("aria-current", "step");
  await expect(
    page.getByRole("region", { name: "Save and check document" }),
  ).toBeFocused();
  expect(
    (await (await request.get("/api/records")).json()).records.length,
  ).toBe(originalCount);
  await page.getByRole("button", { name: "Saved data", exact: true }).click();
  await page
    .getByRole("button", { name: "Upload document", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Upload a change request" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Upload a change request" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: /Documents in review/ }).click();
  await expect(
    page.getByRole("heading", { name: "needs-review.pdf" }),
  ).toBeVisible();
  await expect(
    page.getByText("2 need attention", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 900 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: "test-results/document-workflow-mobile.png",
    fullPage: true,
  });
});
