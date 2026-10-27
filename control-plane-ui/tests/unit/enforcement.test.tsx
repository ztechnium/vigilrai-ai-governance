import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const redirectMock = vi.fn((url: string) => {
  throw new Error(`NEXT_REDIRECT:${url}`);
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => ({ decisionId: "test-receipt-id" }),
  redirect: (url: string) => redirectMock(url),
}));

vi.mock("@/lib/api", () => ({
  getEnforcementReceipts: vi.fn().mockResolvedValue({ data: [] }),
  getEnforcementReceipt: vi.fn().mockResolvedValue({
    data: {
      id: "test-receipt-id",
      decision: "ALLOW",
      reason: "Approved and allowed",
      reason_code: "ALLOWED",
      identity: {
        ai_system_id: "sys-1",
        ai_system_name: "Demo System",
        agent_id: "agent-1",
        agent_name: "Demo Agent",
        agent_version_id: "ver-1",
        agent_version_number: 1,
        runtime_identity_id: "rt-1",
        runtime_identity_name: "Demo Runtime",
        delegation_id: null,
      },
      client_context: {
        client_type: "cursor",
        hook_event: "beforeMCPExecution",
      },
      action: {
        integration_type: "mcp",
        tool_name: "searchJiraIssuesUsingJql",
        action_digest: "abc123",
        parameters: {},
      },
      policy_evaluation: {
        final_effect: "ALLOW",
        matched_rule_ids: [],
        matched_rules: [],
        condition_details: [],
        tool_rule_enforcement: { status: "ACTIVE", mode: "DETERMINISTIC" },
        content_rule_enforcement: {
          status: "NOT_ACTIVE",
          reason: "CONTENT_EVALUATOR_NOT_CONFIGURED",
        },
      },
      approval: { required: false, status: "Not required" },
      execution: {
        attempted: true,
        status: "SUCCEEDED",
        source: "CLIENT_REPORTED",
      },
      assurance: {
        enforcement_mode: "PROXY_ENFORCED",
        deployment_control: "PROXY_CONTROLLED",
        verification_status: "VERIFIED",
      },
      trace: {
        receipt_id: "test-receipt-id",
        correlation_id: "corr-1",
      },
      timestamps: {
        started_at: "2026-09-06T10:00:00.000Z",
        completed_at: "2026-09-06T10:00:09.000Z",
      },
    },
  }),
}));

import RuntimeEnforcementPage from "@/app/(app)/runtime/enforcement/page";
import EnforcementDetailPage from "@/app/(app)/runtime/enforcement/[decisionId]/page";

describe("Runtime enforcement pages", () => {
  it("redirects enforcement list to audit explorer", () => {
    redirectMock.mockClear();
    expect(() => {
      RuntimeEnforcementPage();
    }).toThrow(/NEXT_REDIRECT:\/runtime\/audit\?type=enforcement/);
    expect(redirectMock).toHaveBeenCalledWith("/runtime/audit?type=enforcement");
  });

  it("renders enforcement detail", async () => {
    render(<EnforcementDetailPage />);
    expect(
      await screen.findByRole("heading", { name: "Runtime Action Detail" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Identity")).toBeInTheDocument();
    expect(screen.getByText("Policy Evaluation")).toBeInTheDocument();
  });
});
