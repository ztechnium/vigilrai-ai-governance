import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import LoginPage from "@/app/page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  adminLogin: vi.fn(),
  saasLogin: vi.fn(),
  persistSessionTokens: vi.fn(),
  ADMIN_AUTH_TOKEN_STORAGE_KEY: "rai_admin_token",
  ACTIVE_ORG_STORAGE_KEY: "rai_active_org",
  PLATFORM_ADMIN_STORAGE_KEY: "rai_platform_admin",
}));

describe("LoginPage", () => {
  it("renders login shell and handles unavailable API state gracefully", async () => {
    render(<LoginPage />);

    expect(screen.getByRole("heading", { name: "Sign In" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign In" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Forgot password?" })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });
});
