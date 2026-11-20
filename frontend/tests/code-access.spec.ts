import { test, expect } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:8002" });

test("access code opens the workspace, persists on reload and signs out", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Email", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Password", { exact: true })).toHaveCount(0);
  const code = page.getByLabel("Access code", { exact: true });
  await code.fill("wrong");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Incorrect access code");
  await code.fill("1234");
  await code.press("Enter");
  await expect(
    page.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Manage accounts" }),
  ).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeVisible();
  expect(await page.evaluate(() => document.cookie)).not.toContain(
    "warren-session",
  );
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(code).toBeVisible();
  await expect(code).toHaveValue("");
  await page.reload();
  await expect(code).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/access-code-390.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
});
