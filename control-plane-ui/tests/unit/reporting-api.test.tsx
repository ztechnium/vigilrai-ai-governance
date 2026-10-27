import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { AISystemReportTab } from "@/components/reporting/ai-system-report-tab";
import * as api from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getAiSystemReport: vi.fn(),
}));

describe("Reporting Tabs", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("AISystemReportTab", () => {
    const mockSystemReport = {
      scope: {
        organization_id: "org-123",
        ai_system_id: "system-123",
        agent_id: null,
        runtime_identity_id: null,
      },
      period: {
        start: "2026-08-24T00:00:00Z",
        end: "2026-09-24T00:00:00Z",
      },
      freshness: {
        mode: "LIVE" as const,
        last_refreshed_at: "2026-09-24T14:30:00Z",
      },
      executions: 1000,
      conversations: 50,
      governed_actions: 2500,
      execution_success_rate: 98.5,
      open_findings: 5,
      critical_findings: 1,
      risk_score: 65.0,
      risk_trend: "stable",
      policy_trigger_rate: 12.5,
      deny_rate: 2.0,
      approval_rate: 5.5,
      budget_usage: 450.0,
      token_usage: 100000,
      cost: 25.5,
      assurance_status: "VALID",
      evidence_completeness_pct: 85.0,
      incidents: 0,
      exceptions: 1,
      evaluation_waivers: 0,
      risk_by_agent: [],
      risk_by_tool: [],
      risk_by_model: [],
    };

    it("should show loading state initially", () => {
      vi.mocked(api.getAiSystemReport).mockReturnValue(new Promise(() => {}));
      render(<AISystemReportTab systemId="system-123" />);
      expect(screen.getByText(/Loading report data/i)).toBeInTheDocument();
    });

    it("should display report metrics when loaded", async () => {
      vi.mocked(api.getAiSystemReport).mockResolvedValue({ data: mockSystemReport } as any);

      render(<AISystemReportTab systemId="system-123" />);

      await waitFor(() => {
        expect(screen.getByText("2,500")).toBeInTheDocument(); // Governed actions
        expect(screen.getByText("50")).toBeInTheDocument(); // Conversations
        expect(screen.getAllByText("98.5%").length).toBeGreaterThan(0);
      });
    });

    it("should display error message on failure", async () => {
      vi.mocked(api.getAiSystemReport).mockRejectedValue(new Error("Network error"));

      render(<AISystemReportTab systemId="system-123" />);

      await waitFor(() => {
        expect(screen.getByText("Network error")).toBeInTheDocument();
      });
    });

    it("should display risk metrics correctly", async () => {
      vi.mocked(api.getAiSystemReport).mockResolvedValue({ data: mockSystemReport } as any);

      render(<AISystemReportTab systemId="system-123" />);

      await waitFor(() => {
        expect(screen.getAllByText("5").length).toBeGreaterThan(0);
        expect(screen.getByText(/1 critical/i)).toBeInTheDocument();
        expect(screen.getByText("65.0")).toBeInTheDocument(); // Risk score
      });
    });

    it("should display cost and token metrics", async () => {
      vi.mocked(api.getAiSystemReport).mockResolvedValue({ data: mockSystemReport } as any);

      render(<AISystemReportTab systemId="system-123" />);

      await waitFor(() => {
        expect(screen.getByText("$25.50")).toBeInTheDocument();
        expect(screen.getByText("100,000")).toBeInTheDocument();
      });
    });
  });
});
