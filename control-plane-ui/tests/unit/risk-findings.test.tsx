import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/lib/api", () => ({
  getRiskFindings: vi.fn().mockResolvedValue({
    data: {
      items: [
        {
          id: "finding-1",
          ai_system_id: "sys-1",
          ai_system_name: "Lapeep AI",
          agent_name: "Lapeep Customer Agent",
          agent_version_number: 1,
          model_name: "gemini/gemini-3.8-flash",
          finding_type: "UNUSUAL_TOOL_FREQUENCY",
          policy_kind: "tool",
          title: "Unusual tool frequency: Send Customer Reply",
          description: "Observed 21 calls to Send Customer Reply within 600s (threshold 20)",
          severity: "HIGH",
          confidence: 1,
          sensitivity: "HIGH",
          status: "OPEN",
          explanation: { tool_name: "Send Customer Reply" },
          created_at: "2026-09-22T07:16:49.000Z",
        },
      ],
      total: 1,
      limit: 10,
      offset: 0,
    },
  }),
}));

import RiskFindingsPage from "@/app/(app)/risk/findings/page";

describe("Risk findings page", () => {
  it("labels the policy and the action separately", async () => {
    render(<RiskFindingsPage />);

    expect(await screen.findByText("Unusual tool frequency")).toBeInTheDocument();
    expect(screen.getByText("Send Customer Reply")).toBeInTheDocument();
    expect(screen.getByText("Policy")).toBeInTheDocument();
    expect(screen.getByText("Action")).toBeInTheDocument();
    expect(screen.queryByText(/TOOL · UNUSUAL_TOOL_FREQUENCY/)).not.toBeInTheDocument();
  });
});
