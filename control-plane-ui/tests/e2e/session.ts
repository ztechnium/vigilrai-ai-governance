import type { Page } from "@playwright/test";

const AUTH_ME = {
  user: {
    id: "e2e-user",
    email: "admin@raigateway.local",
    name: "E2E Admin",
    email_verified: true,
  },
  roles: ["ORGANIZATION_ADMIN"],
  memberships: [{ id: "e2e-membership", role: "ORGANIZATION_ADMIN" }],
  welcome_completed: true,
  platform_roles: ["platform_admin"],
};

/** Keep the app shell on the requested page. A token alone is not enough: AuthProvider calls /v1/auth/me. */
export async function seedAdminSession(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("rai.cp.adminAuthToken", "e2e-test-token");
    window.localStorage.setItem("rai.cp.activeAdminRole", "General Admin");
  });
  await page.route(/\/v1\/auth\/me(\?|$)/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(AUTH_ME),
    });
  });
  await page.route(/\/v1\/auth\/context(\?|$)/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        roles: ["ORGANIZATION_ADMIN"],
        permissions: ["runtime:read", "evidence:read"],
      }),
    });
  });
}
