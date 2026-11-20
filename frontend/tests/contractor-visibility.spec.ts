import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const folder = path.resolve("test-results/contractor-visibility");
test.beforeAll(() => {
  fs.mkdirSync(folder, { recursive: true });
  execFileSync(
    path.resolve("../warren_towers/bin/python"),
    [
      "-c",
      "import sys; from pathlib import Path; from tests.helpers import write_pdf,detail_lines; from tests.test_row_rate_extraction import summary_lines; p=Path(sys.argv[1]); write_pdf(p/'contractor-visibility-blank.pdf',summary_lines()[:6]); write_pdf(p/'contractor-visibility-original.pdf',detail_lines())",
      folder,
    ],
    { cwd: ".." },
  );
});
test.afterEach(async ({ page }) => {
  const sessions = await (await page.request.get("/api/sessions")).json();
  for (const session of sessions.filter((s: { filename: string }) =>
    s.filename.startsWith("contractor-visibility-"),
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
async function prepare(page: Page, filename: string, contractor: string) {
  await page.goto("/");
  await page
    .getByLabel("Choose document")
    .setInputFiles(path.join(folder, filename));
  await page.getByLabel("Project name").fill("Contractor visibility demo");
  await page.getByLabel(/^Contractor/).fill(contractor);
  await page
    .getByRole("button", { name: "Extract labor rates", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: filename, exact: true }),
  ).toBeVisible();
}
async function editContractor(page: Page, value: string) {
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Contractor", { exact: true }).fill(value);
  await dialog
    .getByRole("button", { name: "Save comparison details", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
}

test("confirmed contractor appears in data, filters, library and partial review without changing source", async ({
  page,
}) => {
  const filename = "contractor-visibility-blank.pdf";
  await prepare(page, filename, "Packet customer");
  await expect(
    page.getByRole("cell", {
      name: "Missing — needs confirmation",
      exact: true,
    }),
  ).toHaveCount(3);
  await page.getByLabel("Select all visible records").uncheck();
  await page
    .getByRole("checkbox", { name: /Select record/ })
    .first()
    .check();
  for (const checkbox of await page
    .getByRole("checkbox", { name: /I checked the original printed table/ })
    .all())
    await checkbox.check();
  await page
    .getByRole("button", { name: "Save selected rows", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("1 rows saved");
  await page.getByRole("button", { name: "Saved data", exact: true }).click();
  await page.getByLabel("Select all visible records").check();
  await page
    .getByRole("button", { name: "Set comparison details (1)", exact: true })
    .click();
  await editContractor(page, "Confirmed employer");
  await expect(
    page.getByRole("cell", { name: "Confirmed employer", exact: true }),
  ).toHaveCount(1);
  await expect(
    page.getByRole("cell", { name: "Reviewer entered", exact: true }),
  ).toHaveCount(1);
  await page.getByLabel("Filter contractor").selectOption("Confirmed employer");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.getByRole("button", { name: "Review", exact: true }).click();
  await expect(
    page
      .getByRole("dialog")
      .getByRole("heading", { name: "Confirmed employer", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText(
    "Original contractor: Not provided",
  );
  await expect(
    page.getByRole("button", {
      name: "Set contractor for this document",
      exact: true,
    }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await page
    .getByRole("button", { name: "Saved documents", exact: true })
    .click();
  const card = page.locator(".saved-document").filter({ hasText: filename });
  await expect(card).toContainText("Confirmed employer");
  await page.getByLabel("Search saved documents").fill("Confirmed employer");
  await expect(card).toBeVisible();
  await page
    .getByRole("button", { name: "Upload & review", exact: true })
    .click();
  await expect(
    page.getByRole("cell", { name: "Confirmed employer", exact: true }),
  ).toHaveCount(1);
  await expect(
    page.getByRole("cell", {
      name: "Missing — needs confirmation",
      exact: true,
    }),
  ).toHaveCount(2);
  await page.reload();
  await expect(
    page.getByRole("cell", { name: "Confirmed employer", exact: true }),
  ).toHaveCount(1);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  const data = await (await page.request.get("/api/records")).json();
  const source = data.records.find(
    (r: { source_file: string }) => r.source_file === filename,
  );
  expect(source.contractor).toBe("");
  const sessions = await (await page.request.get("/api/sessions")).json();
  const session = sessions.find(
    (s: { filename: string }) => s.filename === filename,
  );
  const evidence = await (
    await page.request.get(`/api/sessions/${session.id}/evidence`)
  ).json();
  expect(
    evidence.records.every((r: { contractor: string }) => r.contractor === ""),
  ).toBe(true);
});

test("clearing a reviewer contractor restores the original name and filter options", async ({
  page,
}) => {
  const filename = "contractor-visibility-original.pdf";
  await prepare(page, filename, "Original employer");
  await page
    .getByRole("button", { name: "Save selected rows", exact: true })
    .click();
  await page
    .locator(".saved-document")
    .filter({ hasText: filename })
    .getByRole("button", { name: "View saved rates", exact: true })
    .click();
  await page
    .getByRole("checkbox", { name: /Select record/ })
    .first()
    .check();
  await page
    .getByRole("button", { name: "Set comparison details (1)", exact: true })
    .click();
  await editContractor(page, "Reviewed employer");
  await expect(
    page.getByRole("cell", { name: "Reviewed employer", exact: true }),
  ).toHaveCount(1);
  await expect(
    page.getByRole("cell", { name: "Original employer", exact: true }),
  ).toHaveCount(1);
  await page.getByLabel("Filter contractor").selectOption("Reviewed employer");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.getByLabel("Filter contractor").selectOption("");
  await page
    .locator("tbody tr")
    .filter({ hasText: "Reviewed employer" })
    .getByRole("button", { name: "Review", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "Original contractor: Original employer",
  );
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Set comparison details", exact: true })
    .click();
  await editContractor(page, "");
  await expect(
    page.getByRole("cell", { name: "Original employer", exact: true }),
  ).toHaveCount(2);
  await expect(
    page.getByRole("cell", { name: "Upload/source", exact: true }),
  ).toHaveCount(2);
  await expect(
    page
      .getByLabel("Filter contractor")
      .getByRole("option", { name: "Reviewed employer", exact: true }),
  ).toHaveCount(0);
  const data = await (await page.request.get("/api/records")).json();
  expect(
    data.records
      .filter((r: { source_file: string }) => r.source_file === filename)
      .every(
        (r: { contractor: string }) => r.contractor === "Original employer",
      ),
  ).toBe(true);
});
