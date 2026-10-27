import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  searchRuntimeAudit: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(""),
}));

vi.mock("@/lib/api", () => ({
  searchRuntimeAudit: mocks.searchRuntimeAudit,
  getAISystems: vi.fn().mockResolvedValue({ data: [] }),
  getAgents: vi.fn().mockResolvedValue({ data: [] }),
  getConversations: vi.fn().mockResolvedValue({ data: { items: [] } }),
}));

import AuditExplorerPage from "@/app/(app)/runtime/audit/page";

describe("Audit Explorer", () => {
  it("loads enforcement records immediately with filters collapsed", async () => {
    mocks.searchRuntimeAudit.mockResolvedValue({
      data: { items: [], has_more: false },
    });
    render(<AuditExplorerPage />);
    expect(await screen.findByTestId("audit-explorer-page")).toBeInTheDocument();
    expect(screen.getByTestId("audit-filters-toggle")).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("audit-content-search")).not.toBeInTheDocument();
    expect(await screen.findByText(/No records matched/i)).toBeInTheDocument();
    expect(mocks.searchRuntimeAudit).toHaveBeenCalledWith(
      expect.objectContaining({ entity_types: "ENFORCEMENT" }),
    );
  });

  it("shows allow, block, and require approval in the action column", async () => {
    mocks.searchRuntimeAudit.mockResolvedValue({
      data: {
        items: [
          {
            id: "1",
            record_type: "ENFORCEMENT",
            occurred_at: "2026-09-26T10:00:00.000Z",
            action: "list-projects",
            decision: "ALLOW",
          },
          {
            id: "2",
            record_type: "ENFORCEMENT",
            occurred_at: "2026-09-26T10:01:00.000Z",
            action: "delete-file",
            decision: "DENY",
          },
          {
            id: "3",
            record_type: "ENFORCEMENT",
            occurred_at: "2026-09-26T10:02:00.000Z",
            action: "send-email",
            decision: "REQUIRE_APPROVAL",
          },
        ],
        has_more: false,
      },
    });

    render(<AuditExplorerPage />);
    fireEvent.click(await screen.findByTestId("audit-filters-toggle"));
    fireEvent.click(await screen.findByRole("button", { name: "Search" }));

    expect(await screen.findByText("ALLOW")).toBeInTheDocument();
    expect(screen.getByText("BLOCK")).toBeInTheDocument();
    expect(screen.getByText("REQUIRE APPROVAL")).toBeInTheDocument();
    expect(screen.getByText("list-projects")).toBeInTheDocument();
  });
});
