import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
import type { Finding, Run } from "../src/types";

function finding(
  id: string,
  document: string,
  outcome: Finding["outcome"],
  contractor: string,
): Finding {
  return {
    finding_id: id,
    record_id: id,
    document_id: document,
    run_id: "report-run",
    project: "Synthetic project",
    contractor,
    classification: "Carpenter",
    work_start: "2026-01-02",
    work_end: "2026-01-02",
    source_file: "PCI-001.pdf",
    source_page: "3",
    table_id: "table-1",
    document_reference: document === "document-a" ? "PCI-001" : "PCI-002",
    ticket_id: "1001",
    rate_type: "REG",
    submitted_rate: "11.00",
    approved_rate: outcome === "needs_review" ? "" : "10.00",
    difference_per_hour: outcome === "difference" ? "1.00" : "",
    reference_version: "reference-123",
    reference_row: "2",
    reference_rate_field: "reg_rate",
    effective_start: "2026-01-01",
    effective_finish: "2026-12-31",
    approval_status: "Approved",
    bu_approval_received: "",
    outcome,
    reason:
      outcome === "needs_review"
        ? "Confirm the work date."
        : outcome === "difference"
          ? "Submitted rate differs from the approved rate."
          : "Rate matches an approved schedule.",
    candidates: [],
    review_details: {},
    reference_rows: ["2"],
    approved_rates: outcome === "needs_review" ? [] : ["10.00"],
  };
}

function run(results: Finding[], stale = false): Run {
  return {
    id: "report-run",
    created_at: "2026-11-12T12:00:00Z",
    reference_version: "reference-123",
    reference_name: "Synthetic schedule.csv",
    stale,
    record_ids: [...new Set(results.map((r) => r.record_id))],
    results,
    counts: {
      match: results.filter((r) => r.outcome === "match").length,
      difference: results.filter((r) => r.outcome === "difference").length,
      needs_review: results.filter((r) => r.outcome === "needs_review").length,
    },
  };
}

async function setup(page: Page, snapshot: Run) {
  await page.addInitScript(() => {
    localStorage.setItem("warren-tab", "differences");
    localStorage.setItem("warren-run", "report-run");
  });
  await page.route("**/api/checks", (route) =>
    route.fulfill({ json: [snapshot] }),
  );
  await page.route("**/api/records", (route) =>
    route.fulfill({ json: { records: [], details: {} } }),
  );
  await page.route("**/api/sessions", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/reference", (route) =>
    route.fulfill({ json: { active: null, versions: [] } }),
  );
  await page.goto("/");
}

test("document and contractor match percentages scope findings and reports", async ({
  page,
}) => {
  const results = [
    finding("a", "document-a", "match", "Alpha"),
    {
      ...finding("b", "document-a", "difference", "Alpha"),
      approved_rate: "",
      approved_rates: ["10.00", "15.00"],
      difference_per_hour: "",
      finding_kind: "rate_not_in_schedule",
      reason: "Rate is not among the applicable approved rates.",
    },
    finding("c", "document-a", "needs_review", "Beta"),
    {
      ...finding("d", "document-a", "match", "Alpha"),
      record_id: "a",
      rate_type: "OT",
    },
    finding("e", "document-b", "match", "Beta"),
    finding("f", "document-b", "match", "Beta"),
  ];
  await setup(page, run(results));
  const summary = page.getByRole("region", { name: "Results summary" });
  await expect(summary).toContainText("6 rate comparisons");
  await expect(
    summary.locator(".stat-card").filter({ hasText: "Matching rates" }),
  ).toContainText("66.7%");
  await expect(
    page.getByRole("list", { name: "Document results" }).getByRole("button"),
  ).toHaveCount(2);
  await page.getByLabel("Filter check document").selectOption("document-a");
  await expect(summary).toContainText("4 rate comparisons");
  await expect(
    summary.locator(".stat-card").filter({ hasText: "Matching rates" }),
  ).toContainText("50%");
  await page.getByLabel("Filter contractor").selectOption("Alpha");
  await expect(summary).toContainText("3 rate comparisons");
  await expect(
    summary.locator(".stat-card").filter({ hasText: "Matching rates" }),
  ).toContainText("66.7%");
  await page.getByLabel("Search findings…").fill("does not exist");
  await expect(page.locator(".findings-card tbody tr")).toHaveCount(0);
  await expect(summary).toContainText("3 rate comparisons");
  await page
    .getByRole("button", { name: "Print PCI report", exact: true })
    .click();
  let dialog = page.getByRole("dialog", { name: "Print PCI report" });
  await expect(dialog.locator(".report-findings tbody tr")).toHaveCount(1);
  await expect(dialog).not.toContainText("All contractors");
  await expect(dialog).toContainText("Alpha");
  await expect(dialog).toContainText("PCI-001");
  await expect(dialog).not.toContainText("PCI-002");
  await expect(dialog).toContainText("No single approved rate");
  await expect(dialog).toContainText("$10.00 / $15.00");
  await dialog.getByRole("button", { name: "Close dialog" }).click();
  await page.getByLabel("Filter contractor").selectOption("Beta");
  await expect(summary).toContainText("1 rate comparisons");
  await expect(
    summary.locator(".stat-card").filter({ hasText: "Matching rates" }),
  ).toContainText("0%");
  await expect(
    summary.locator(".stat-card").filter({ hasText: "Needs review" }),
  ).toContainText("100%");
  await page
    .getByRole("button", { name: "Print PCI report", exact: true })
    .click();
  dialog = page.getByRole("dialog", { name: "Print PCI report" });
  await expect(dialog).toContainText("Items needing review (1)");
  await expect(dialog).toContainText("Confirm the work date.");
  await expect(dialog).toContainText("No confirmed rate differences");
  await dialog.getByLabel("Include items needing review").uncheck();
  await expect(dialog).toContainText("Unresolved item details were excluded");
  await expect(dialog).not.toContainText("Confirm the work date.");
  await dialog.getByRole("button", { name: "Close dialog" }).click();
  await page.getByLabel("Filter check document").selectOption("document-b");
  await expect(summary).toContainText("2 rate comparisons");
  await expect(
    summary.locator(".stat-card").filter({ hasText: "Matching rates" }),
  ).toContainText("100%");
  await page.getByLabel("Filter contractor").selectOption("Alpha");
  await expect(summary).toContainText("0 rate comparisons");
  await expect(
    summary.locator(".stat-card").filter({ hasText: "Matching rates" }),
  ).toContainText("—");
  await expect(
    page.getByRole("button", { name: "Print PCI report", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("Filter check document").selectOption("");
  await page.getByLabel("Filter contractor").selectOption("");
  for (const width of [1280, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    if (width === 1280 || width === 390)
      await page.screenshot({
        path: `test-results/results-summary-${width}.png`,
        fullPage: true,
      });
  }
});

test("print PDF includes all pages, source evidence and outdated warning without app chrome", async ({
  page,
}) => {
  const results = Array.from({ length: 45 }, (_, i) => ({
    ...finding(`difference-${i}`, "document-a", "difference", "Alpha"),
    source_page: String(i + 1),
    reason:
      i === 44
        ? "END-OF-REPORT: submitted rate differs from the approved schedule."
        : "Submitted rate differs from the approved schedule. Confirm the original printed rate and source work date before responding.",
  }));
  await setup(page, run(results, true));
  await page
    .getByRole("button", { name: "Print PCI report", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Print PCI report" });
  await expect(dialog).toContainText("OUTDATED CHECK — RERUN REQUIRED");
  await page.evaluate(() => {
    window.print = () => {
      document.body.dataset.printInvoked = "true";
    };
  });
  await dialog.getByRole("button", { name: "Print / Save PDF" }).click();
  await expect(page.locator("body")).toHaveAttribute(
    "data-print-invoked",
    "true",
  );
  await page.emulateMedia({ media: "print" });
  await expect(page.locator("#pci-print-root")).toBeVisible();
  await expect(page.locator("#root")).toBeHidden();
  const destination = path.resolve("test-results/pci-review-report.pdf");
  await page.pdf({ path: destination, preferCSSPageSize: true });
  const output = JSON.parse(
    execFileSync(
      path.resolve("../warren_towers/bin/python"),
      [
        "-c",
        "import json,sys,pymupdf; d=pymupdf.open(sys.argv[1]); print(json.dumps({'pages':len(d),'text':' '.join(p.get_text() for p in d)}))",
        destination,
      ],
      { encoding: "utf8" },
    ),
  );
  expect(output.pages).toBeGreaterThan(1);
  expect(output.text).toContain("END-OF-REPORT");
  expect(output.text).toContain("Source page 45");
  expect(output.text).toContain("OUTDATED CHECK");
  expect(output.text).toContain("Tracker rows: 2");
  expect(output.text).not.toContain("Upload & review");
  await page.emulateMedia({ media: "screen" });
  await dialog.getByRole("button", { name: "Close dialog" }).click();
  await expect(page.locator("#pci-print-root")).toHaveCount(0);
});

test("a historical category rate is identified as outside the entered work period", async ({
  page,
}) => {
  const outside = {
    ...finding("outside", "document-a", "difference", "Example Contractor"),
    classification: "Operator",
    finding_kind: "rate_outside_work_period",
    reason:
      "This rate exists in approved schedules for the mapped category, but those schedules do not cover the entered work period (2026-01-02 to 2026-01-02). Matching reference periods: Operating Engineer Journey Person: 2025-06-01 to 2025-11-30. Confirm the actual work dates; this is not an applicable rate match.",
  };
  await setup(page, run([outside]));
  await expect(
    page.getByText("Outside approved period", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Not in approved rates", { exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Review", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Operating Engineer Journey Person: 2025-06-01 to 2025-11-30",
  );
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await page
    .getByRole("button", { name: "Print PCI report", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "Operating Engineer Journey Person: 2025-06-01 to 2025-11-30",
  );
  await expect(
    page.getByRole("dialog").locator(".report-metrics"),
  ).toContainText("Rate differences");
});
