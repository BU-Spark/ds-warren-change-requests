import { test, expect } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:8001" });

test("admin invitations, account setup, recovery and disable work without email", async ({
  page,
  browser,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Sign up", exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("Email", { exact: true }).fill("admin@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-admin-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "Manage accounts" }).click();
  await page.getByLabel("Reviewer email").fill("reviewer@example.test");
  await page.getByRole("button", { name: "Create invitation link" }).click();
  const invitation = await page
    .getByLabel("Private single-use access link")
    .inputValue();
  const context = await browser.newContext();
  const reviewer = await context.newPage();
  await reviewer.goto(invitation);
  await expect(reviewer).toHaveURL("http://127.0.0.1:8001/");
  await reviewer.getByRole("button", { name: "Continue", exact: true }).click();
  await reviewer
    .getByLabel("New password", { exact: true })
    .fill("synthetic-reviewer-password");
  await reviewer
    .getByLabel("Confirm new password")
    .fill("synthetic-reviewer-password");
  await reviewer
    .getByRole("button", { name: "Save password", exact: true })
    .click();
  await reviewer
    .getByLabel("Email", { exact: true })
    .fill("reviewer@example.test");
  await reviewer
    .getByLabel("Password", { exact: true })
    .fill("synthetic-reviewer-password");
  await reviewer.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    reviewer.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeVisible();
  await expect(
    reviewer.getByRole("button", { name: "Manage accounts" }),
  ).toHaveCount(0);
  expect(await reviewer.evaluate(() => document.cookie)).not.toContain(
    "warren-session",
  );

  // Reload the list to display the now-active account.
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("button", { name: "Manage accounts" }).click();
  const row = page
    .locator("article")
    .filter({ hasText: "reviewer@example.test" });
  await row.getByRole("button", { name: "Create reset link" }).click();
  const recovery = await page
    .getByLabel("Private single-use access link")
    .inputValue();
  const resetPage = await context.newPage();
  await resetPage.goto(recovery);
  await resetPage
    .getByRole("button", { name: "Continue", exact: true })
    .click();
  await resetPage
    .getByLabel("New password", { exact: true })
    .fill("replacement-reviewer-password");
  await resetPage
    .getByLabel("Confirm new password")
    .fill("replacement-reviewer-password");
  await resetPage
    .getByRole("button", { name: "Save password", exact: true })
    .click();
  await expect(
    resetPage.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await reviewer.reload();
  await expect(
    reviewer.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await reviewer
    .getByLabel("Email", { exact: true })
    .fill("reviewer@example.test");
  await reviewer
    .getByLabel("Password", { exact: true })
    .fill("replacement-reviewer-password");
  await reviewer.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    reviewer.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeVisible();
  await row.getByRole("button", { name: "Disable access" }).click();
  await expect(row).toContainText("Disabled");
  await reviewer.reload();
  await expect(
    reviewer.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await context.close();
});
