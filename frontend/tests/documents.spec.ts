import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const folder = path.resolve("test-results/document-lifecycle");
test.beforeAll(() => {
  fs.mkdirSync(folder, { recursive: true });
  execFileSync(
    path.resolve("../warren_towers/bin/python"),
    [
      "-c",
      "import sys; from pathlib import Path; from tests.helpers import write_pdf,detail_lines; p=Path(sys.argv[1]); write_pdf(p/'lifecycle-a.pdf',[(50,[(20,'UC0999A')]),*detail_lines()]); write_pdf(p/'lifecycle-b.pdf',[(50,[(20,'UC0999B')]),*detail_lines()])",
      folder,
    ],
    { cwd: ".." },
  );
});

test.afterEach(async ({ page }) => {
  const documents = await (await page.request.get("/api/documents")).json();
  for (const document of documents.filter((d: { filename: string }) =>
    d.filename.startsWith("lifecycle-"),
  )) {
    const route = `/api/documents/${document.document_id}`;
    const preview = await (
      await page.request.get(route + "/deletion-preview")
    ).json();
    await page.request.delete(route, {
      data: { confirmation: preview.confirmation },
      headers: { Origin: "http://127.0.0.1:8000" },
    });
  }
});

async function upload(page: Page, filename: string) {
  await page
    .getByRole("button", { name: "Upload & review", exact: true })
    .click();
  await page.getByRole("tab", { name: "Upload document", exact: true }).click();
  await page
    .getByLabel("Choose document")
    .setInputFiles(path.join(folder, filename));
  await page.getByLabel("Project name").fill("Lifecycle demo");
  await page.getByLabel(/^Contractor/).fill("Example Contractor");
  await page
    .getByRole("button", { name: "Extract labor rates", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: filename, exact: true }),
  ).toBeVisible();
}

test("saved documents leave review, can be inspected, deleted and saved again", async ({
  page,
}) => {
  await page.goto("/");
  await upload(page, "lifecycle-a.pdf");
  await page
    .getByRole("button", { name: "Save selected rows", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Saved documents", exact: true }),
  ).toBeVisible();
  let card = page
    .locator(".saved-document")
    .filter({ hasText: "lifecycle-a.pdf" });
  await expect(card).toContainText("2 saved rows");
  await card.getByRole("button", { name: "View source", exact: true }).click();
  await expect(
    page.getByRole("dialog").getByAltText("Original printed source page"),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("Source page 1 of 1");
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await card
    .getByRole("button", { name: "View saved rates", exact: true })
    .click();
  await expect(page.locator("tbody tr")).toHaveCount(2);
  await expect(page.getByLabel("Filter saved document")).not.toHaveValue("");
  await page
    .getByRole("button", { name: "Upload & review", exact: true })
    .click();
  await page.getByRole("tab", { name: /Documents in review/ }).click();
  await expect(
    page
      .locator(".review-document-open")
      .filter({ hasText: "lifecycle-a.pdf" }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Saved documents", exact: true })
    .click();
  await card
    .getByRole("button", { name: "Check saved document", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("6 matched");
  await upload(page, "lifecycle-b.pdf");
  await page
    .getByRole("button", { name: "Save selected rows", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Saved documents", exact: true }),
  ).toBeVisible();
  await card
    .getByRole("button", { name: "Delete document", exact: true })
    .click();
  let dialog = page.getByRole("dialog", {
    name: "Delete document?",
    exact: true,
  });
  await expect(dialog).toContainText("2 saved rows");
  await expect(dialog).toContainText("1 check-history runs");
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(card).toBeVisible();
  await card
    .getByRole("button", { name: "Delete document", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Delete permanently", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  await expect(card).toHaveCount(0);
  await expect(
    page.locator(".saved-document").filter({ hasText: "lifecycle-b.pdf" }),
  ).toBeVisible();
  const remaining = await (await page.request.get("/api/records")).json();
  expect(remaining.records).toHaveLength(2);
  await page.reload();
  await expect(
    page.locator(".saved-document").filter({ hasText: "lifecycle-a.pdf" }),
  ).toHaveCount(0);
  await upload(page, "lifecycle-a.pdf");
  await page
    .getByRole("button", { name: "Save selected rows", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "2 rows saved. 0 already present",
  );
  card = page.locator(".saved-document").filter({ hasText: "lifecycle-a.pdf" });
  await expect(card).toBeVisible();
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    if (width !== 320)
      await page.screenshot({
        path: `test-results/saved-documents-${width}.png`,
        fullPage: true,
      });
  }
  await page.setViewportSize({ width: 1280, height: 1000 });
  const bad = path.join(folder, "bad-document.pdf");
  fs.writeFileSync(bad, "synthetic invalid PDF");
  await page
    .getByRole("button", { name: "Upload & review", exact: true })
    .click();
  await page.getByRole("tab", { name: "Upload document", exact: true }).click();
  await page.getByLabel("Choose document").setInputFiles(bad);
  await page
    .getByRole("button", { name: "Extract labor rates", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Upload document again", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Delete bad-document.pdf", exact: true })
    .click();
  dialog = page.getByRole("dialog", { name: "Delete document?", exact: true });
  await expect(dialog).toContainText("0 saved rows");
  await dialog
    .getByRole("button", { name: "Delete permanently", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole("tab", { name: /Documents in review/ }).click();
  await expect(
    page.getByRole("button", { name: "Delete bad-document.pdf", exact: true }),
  ).toHaveCount(0);
});
