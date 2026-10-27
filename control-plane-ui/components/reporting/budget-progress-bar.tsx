"use client";

import { cn } from "@/lib/utils";
import type { BudgetStatus } from "@/lib/types";

interface BudgetProgressBarProps {
  budget: BudgetStatus;
}

export function BudgetProgressBar({ budget }: BudgetProgressBarProps) {
  const warningPct = (budget.warning_threshold / budget.limit_value) * 100;

  const getBarColor = () => {
    if (budget.status === "EXCEEDED") return "bg-danger-600";
    if (budget.status === "WARNING") return "bg-warn-600";
    return "bg-accent-600";
  };

  const getStatusColor = () => {
    if (budget.status === "EXCEEDED") return "text-danger-700";
    if (budget.status === "WARNING") return "text-warn-700";
    return "text-ink-700";
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-ink-900">{budget.name}</span>
        <span className={cn("font-semibold", getStatusColor())}>
          {budget.utilization_pct.toFixed(1)}%
        </span>
      </div>

      <div className="relative h-2.5 overflow-hidden rounded-full bg-ink-100">
        {/* Warning threshold line */}
        <div
          className="absolute top-0 h-full w-0.5 bg-warn-400"
          style={{ left: `${warningPct}%` }}
        />

        {/* Progress bar */}
        <div
          className={cn("h-full transition-all duration-300", getBarColor())}
          style={{ width: `${Math.min(budget.utilization_pct, 100)}%` }}
        />
      </div>

      <div className="flex items-center justify-between text-xs text-ink-500">
        <span>
          {budget.current_usage.toLocaleString()} / {budget.limit_value.toLocaleString()}{" "}
          {budget.metric}
        </span>
        <span className="font-mono">{budget.window}</span>
      </div>
    </div>
  );
}
