import { expect, test } from "@playwright/test";

test("login page is the site root", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign In" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Register your company/i })).toHaveCount(0);
});

test("legacy login path redirects to the root", async ({ page }) => {
  await page.goto("/login");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "Sign In" })).toBeVisible();
});
