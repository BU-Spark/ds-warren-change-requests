import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const folder = path.resolve("test-results/regular-only");
test.beforeAll(() => {
  fs.mkdirSync(folder, { recursive: true });
  execFileSync(
    path.resolve("../warren_towers/bin/python"),
    [
      "-c",
      "import sys; from pathlib import Path; from tests.helpers import write_pdf,detail_lines; lines=[(y,[(x,'999.00' if y!=100 and x in (515,560) else v) for x,v in cells]) for y,cells in detail_lines()]; lines += [(300,[(20,'Date/Personnel'),(470,'Manhours'),(560,'Rate'),(660,'Extended')]),(330,[(20,'Signal Technician (OT)'),(470,'0'),(560,'999.00')]),(350,[(20,'Signal Technician (DT)'),(470,'0'),(560,'999.00')])]; write_pdf(Path(sys.argv[1])/'regular-only-demo.pdf',lines)",
      folder,
    ],
    { cwd: ".." },
  );
});
test.afterEach(async ({ page }) => {
  const documents = await (await page.request.get("/api/documents")).json();
  for (const doc of documents.filter(
    (d: { filename: string }) => d.filename === "regular-only-demo.pdf",
  )) {
    const route = `/api/documents/${doc.document_id}`;
    const preview = await (
      await page.request.get(route + "/deletion-preview")
    ).json();
    await page.request.delete(route, {
      data: { confirmation: preview.confirmation },
      headers: { Origin: "http://127.0.0.1:8000" },
    });
  }
});

test("new checks and reports count regular rates and ignore premium-only rows", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("Choose document")
    .setInputFiles(path.join(folder, "regular-only-demo.pdf"));
  await page.getByLabel("Project name").fill("Regular rates demo");
  await page.getByLabel(/^Contractor/).fill("Example Contractor");
  await page
    .getByRole("button", { name: "Extract labor rates", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "regular-only-demo.pdf", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("4 rows selected", { exact: true }),
  ).toBeVisible();
  for (const checkbox of await page
    .getByRole("checkbox", { name: /I checked the original printed table/ })
    .all())
    await checkbox.check();
  await page
    .getByRole("button", { name: "Save selected rows", exact: true })
    .click();
  await page
    .locator(".saved-document")
    .filter({ hasText: "regular-only-demo.pdf" })
    .getByRole("button", { name: "Check saved document", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "2 matched, 0 differences, 0 need review",
  );
  await expect(page.getByRole("status")).toContainText(
    "2 rows without regular/ST rates were skipped",
  );
  const summary = page.getByRole("region", { name: "Results summary" });
  await expect(summary).toContainText("2 rate comparisons");
  await expect(
    summary.locator(".stat-card").filter({ hasText: "Matching rates" }),
  ).toContainText("100%");
  await expect(summary).toContainText("Only regular/ST rates are counted");
  await expect(
    page.getByRole("cell", { name: "Regular (REG)", exact: true }),
  ).toHaveCount(2);
  await page
    .getByRole("button", { name: "Print PCI report", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "Only regular/ST rates are counted",
  );
  await expect(page.getByRole("dialog")).not.toContainText("Overtime (OT)");
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  const data = await (await page.request.get("/api/records")).json();
  const stored = data.records.filter(
    (r: { source_file: string }) => r.source_file === "regular-only-demo.pdf",
  );
  expect(stored).toHaveLength(4);
  expect(stored.some((r: { ot_rate: string }) => r.ot_rate === "999.00")).toBe(
    true,
  );
  expect(stored.some((r: { dt_rate: string }) => r.dt_rate === "999.00")).toBe(
    true,
  );
});
