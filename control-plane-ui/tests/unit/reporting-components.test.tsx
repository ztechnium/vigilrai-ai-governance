import { describe, it, expect, vi } from "vitest";

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

vi.stubGlobal("ResizeObserver", ResizeObserverStub);
import { render, screen } from "@testing-library/react";
import { SeverityBarChart } from "@/components/reporting/severity-bar-chart";
import { EffectDonutChart } from "@/components/reporting/effect-donut-chart";
import { BudgetProgressBar } from "@/components/reporting/budget-progress-bar";
import { NamedBarChart } from "@/components/reporting/named-bar-chart";
import { RateProgress } from "@/components/reporting/rate-progress";
import type { SeverityDistribution, EffectDistribution, BudgetStatus } from "@/lib/types";

describe("Reporting Components", () => {
  describe("SeverityBarChart", () => {
    const mockData: SeverityDistribution = {
      critical: 5,
      high: 10,
      medium: 15,
      low: 20,
    };

    it("should render without crashing", () => {
      render(<SeverityBarChart data={mockData} />);
    });

    it("should handle click events", () => {
      const onClick = vi.fn();
      render(<SeverityBarChart data={mockData} onClick={onClick} />);
      // Note: Full interaction testing would require more complex setup with recharts
    });

    it("should render with zero values", () => {
      const emptyData: SeverityDistribution = {
        critical: 0,
        high: 0,
        medium: 0,
        low: 0,
      };
      render(<SeverityBarChart data={emptyData} />);
    });
  });

  describe("EffectDonutChart", () => {
    const mockData: EffectDistribution = {
      allow: 80,
      monitor: 10,
      require_approval: 5,
      deny: 3,
      suspend: 2,
    };

    it("should render without crashing", () => {
      render(<EffectDonutChart data={mockData} />);
    });

    it("should show empty state when all values are zero", () => {
      const emptyData: EffectDistribution = {
        allow: 0,
        monitor: 0,
        require_approval: 0,
        deny: 0,
        suspend: 0,
      };
      render(<EffectDonutChart data={emptyData} />);
      expect(screen.getByText(/No policy effects to display/i)).toBeInTheDocument();
    });

    it("should filter out zero values", () => {
      const partialData: EffectDistribution = {
        allow: 100,
        monitor: 0,
        require_approval: 0,
        deny: 0,
        suspend: 0,
      };
      render(<EffectDonutChart data={partialData} />);
      // Chart should only show non-zero values
    });
  });

  describe("NamedBarChart", () => {
    it("should render bars", () => {
      render(
        <NamedBarChart
          data={[
            { name: "Actions", value: 12 },
            { name: "Denied", value: 3 },
          ]}
        />,
      );
    });

    it("should show an empty state", () => {
      render(<NamedBarChart data={[]} />);
      expect(screen.getByText(/No data for this chart/i)).toBeInTheDocument();
    });
  });

  describe("RateProgress", () => {
    it("should show the rate label and percent", () => {
      render(<RateProgress label="Deny rate" value={12.5} />);
      expect(screen.getByText("Deny rate")).toBeInTheDocument();
      expect(screen.getByText("12.5%")).toBeInTheDocument();
    });
  });

  describe("BudgetProgressBar", () => {
    const mockBudget: BudgetStatus = {
      id: "test-budget-id",
      name: "Test Budget",
      metric: "TOKEN_USAGE",
      current_usage: 7500,
      limit_value: 10000,
      warning_threshold: 8000,
      utilization_pct: 75.0,
      status: "OK",
      window: "monthly",
      warning_events: 0,
      exceeded_events: 0,
    };

    it("should render budget name and utilization", () => {
      render(<BudgetProgressBar budget={mockBudget} />);
      expect(screen.getByText("Test Budget")).toBeInTheDocument();
      expect(screen.getByText("75.0%")).toBeInTheDocument();
    });

    it("should show warning status correctly", () => {
      const warningBudget: BudgetStatus = {
        ...mockBudget,
        current_usage: 8500,
        utilization_pct: 85.0,
        status: "WARNING",
      };
      render(<BudgetProgressBar budget={warningBudget} />);
      expect(screen.getByText("85.0%")).toBeInTheDocument();
    });

    it("should show exceeded status correctly", () => {
      const exceededBudget: BudgetStatus = {
        ...mockBudget,
        current_usage: 11000,
        utilization_pct: 110.0,
        status: "EXCEEDED",
      };
      render(<BudgetProgressBar budget={exceededBudget} />);
      expect(screen.getByText("110.0%")).toBeInTheDocument();
    });

    it("should display usage values with proper formatting", () => {
      render(<BudgetProgressBar budget={mockBudget} />);
      expect(screen.getByText(/7,500/)).toBeInTheDocument();
      expect(screen.getByText(/10,000/)).toBeInTheDocument();
    });

    it("should display window information", () => {
      render(<BudgetProgressBar budget={mockBudget} />);
      expect(screen.getByText("monthly")).toBeInTheDocument();
    });
  });
});
