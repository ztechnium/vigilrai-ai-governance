import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import LoginPage from "@/app/page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  adminLogin: vi.fn(),
  ADMIN_AUTH_TOKEN_STORAGE_KEY: "rai_admin_token",
}));

vi.mock("@/lib/public-api", () => ({
  toDisplayRole: (role: string) => (role === "admin" ? "General Admin" : role),
}));

describe("Application shell", () => {
  it("login page renders without runtime failure", () => {
    render(<LoginPage />);

    expect(screen.getByRole("heading", { name: "Sign In" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Forgot password?" })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign In" })).toBeInTheDocument();
  });
});
