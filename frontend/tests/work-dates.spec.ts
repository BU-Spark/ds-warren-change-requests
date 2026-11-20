import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const folder = path.resolve("test-results/work-dates");
test.beforeAll(() => {
  fs.mkdirSync(folder, { recursive: true });
  execFileSync(
    path.resolve("../warren_towers/bin/python"),
    [
      "-c",
      "import sys; from pathlib import Path; from tests.test_work_dates import source; source(Path(sys.argv[1])/'work-dates-demo.pdf')",
      folder,
    ],
    { cwd: ".." },
  );
});
test.afterEach(async ({ page }) => {
  const sessions = await (await page.request.get("/api/sessions")).json();
  for (const session of sessions.filter((s: { filename: string }) =>
    s.filename.startsWith("work-dates-"),
  )) {
    const route = `/api/sessions/${session.id}`;
    const preview = await page.request.get(route + "/deletion-preview");
    if (preview.ok())
      await page.request.delete(route, {
        data: { confirmation: (await preview.json()).confirmation },
        headers: { Origin: "http://127.0.0.1:8000" },
      });
  }
});
async function prepare(page: Page) {
  await page.goto("/");
  await page
    .getByLabel("Choose document")
    .setInputFiles(path.join(folder, "work-dates-demo.pdf"));
  await page.getByLabel("Project name").fill("Work dates demo");
  await page.getByLabel(/^Contractor/).fill("Example Contractor");
}
async function extract(page: Page) {
  await page
    .getByRole("button", { name: "Extract labor rates", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "work-dates-demo.pdf", exact: true }),
  ).toBeVisible();
}
async function range(page: Page, start: string, end: string) {
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Work start", { exact: true }).fill(start);
  await dialog.getByLabel("Work finish", { exact: true }).fill(end);
}
async function apply(page: Page) {
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Apply work dates", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

test("document range, page corrections, single-row dates and saved-document edits", async ({
  page,
}) => {
  await prepare(page);
  await page.getByLabel("Work start", { exact: true }).fill("2026-02-01");
  await page.getByLabel("Work finish", { exact: true }).fill("2026-02-10");
  await extract(page);
  const panel = page.getByRole("region", { name: "Document work dates" });
  await expect(panel).toContainText("0 of 4 rows still need work dates");
  await page.getByLabel("Source page", { exact: true }).selectOption("2");
  await expect(
    page.getByRole("cell", { name: "2026-02-10", exact: true }),
  ).toHaveCount(2);
  await expect(
    page.getByRole("cell", { name: "Reviewer entered", exact: true }),
  ).toHaveCount(2);
  await page
    .getByRole("button", { name: "Set document dates", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Remove entered dates \(2\)/ })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(panel).toContainText("2 of 4 rows still need work dates");
  await page
    .getByRole("button", { name: "Set dates for this page", exact: true })
    .click();
  await expect(
    page.getByRole("dialog").getByLabel("Apply dates to"),
  ).toHaveValue("page");
  await expect(
    page
      .getByRole("dialog")
      .getByRole("combobox", { name: "Source page", exact: true }),
  ).toHaveValue("2");
  await range(page, "2026-03-01", "2026-03-10");
  await apply(page);
  await page
    .getByRole("button", { name: "Set dates", exact: true })
    .first()
    .click();
  await range(page, "2026-03-05", "2026-03-05");
  await expect(
    page.getByRole("dialog").getByLabel("Only fill rows missing work dates"),
  ).not.toBeChecked();
  await apply(page);
  await expect(
    page.getByRole("cell", { name: "2026-03-05", exact: true }),
  ).toHaveCount(2);
  await page.reload();
  await expect(panel).toContainText("0 of 4 rows still need work dates");
  for (const checkbox of await page
    .getByRole("checkbox", { name: /I checked the original printed table/ })
    .all())
    await checkbox.check();
  await page
    .getByRole("button", { name: "Save selected rows", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Saved documents", exact: true }),
  ).toBeVisible();
  const card = page
    .locator(".saved-document")
    .filter({ hasText: "work-dates-demo.pdf" });
  await card
    .getByRole("button", { name: "Set work dates", exact: true })
    .click();
  await range(page, "2026-04-01", "2026-04-10");
  await page
    .getByRole("dialog")
    .getByLabel("Only fill rows missing work dates")
    .uncheck();
  await expect(page.getByRole("dialog")).toContainText(
    "4 of 4 rows will receive this range",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  const applyBox = await page
    .getByRole("dialog")
    .getByRole("button", { name: "Apply work dates", exact: true })
    .boundingBox();
  expect(applyBox!.y + applyBox!.height).toBeLessThanOrEqual(844);
  await page.screenshot({
    path: "test-results/work-dates-dialog-390.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await apply(page);
  await card
    .getByRole("button", { name: "View saved rates", exact: true })
    .click();
  await expect(
    page.getByRole("cell", { name: "2026-04-10", exact: true }),
  ).toHaveCount(4);
});

test("dates can be skipped, canceled and applied only to selected rows", async ({
  page,
}) => {
  await prepare(page);
  await extract(page);
  const panel = page.getByRole("region", { name: "Document work dates" });
  await expect(panel).toContainText("2 of 4 rows still need work dates");
  await page.getByLabel("Source page", { exact: true }).selectOption("2");
  await page
    .getByRole("button", { name: "Set dates for this page", exact: true })
    .click();
  await range(page, "2026-05-01", "2026-05-02");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await expect(panel).toContainText("2 of 4 rows still need work dates");
  await page.getByLabel("Source page", { exact: true }).selectOption("1");
  await page.getByLabel("Select all visible records").uncheck();
  await page.getByLabel("Source page", { exact: true }).selectOption("2");
  await page.getByLabel("Select all visible records").uncheck();
  await page
    .getByRole("checkbox", { name: /Select record/ })
    .first()
    .check();
  await page
    .getByRole("button", {
      name: "Set dates for selected rows (1)",
      exact: true,
    })
    .click();
  await range(page, "2026-05-01", "2026-05-01");
  await apply(page);
  await expect(panel).toContainText("1 of 4 rows still need work dates");
});
