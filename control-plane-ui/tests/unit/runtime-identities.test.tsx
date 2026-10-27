import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import RuntimeIdentitiesPage from "@/app/(app)/governance/runtime-identities/page";

vi.mock("@/lib/api", () => ({
  getRuntimeIdentities: vi.fn().mockResolvedValue({ data: [] }),
  getAISystems: vi.fn().mockResolvedValue({ data: [] }),
  getAgents: vi.fn().mockResolvedValue({ data: [] }),
  getAgentVersions: vi.fn().mockResolvedValue({ data: [] }),
  createRuntimeIdentity: vi.fn(),
}));

describe("RuntimeIdentitiesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders page and empty state after load", async () => {
    render(<RuntimeIdentitiesPage />);
    expect(screen.getAllByRole("heading", { name: "Runtime Identities" }).length).toBeGreaterThan(
      0,
    );
    await waitFor(() => {
      expect(screen.getByText(/No runtime identities yet/i)).toBeInTheDocument();
    });
  });

  it("shows create form when button clicked", async () => {
    render(<RuntimeIdentitiesPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /New Runtime Identity/i })).toBeInTheDocument();
    });
    screen.getByRole("button", { name: /New Runtime Identity/i }).click();
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Create Runtime Identity" })).toBeInTheDocument();
    });
  });
});
