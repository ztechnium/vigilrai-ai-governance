"use client";

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { CHART, chartTooltipStyle } from "@/components/reporting/chart-colors";
import type { EffectDistribution } from "@/lib/types";

interface EffectDonutChartProps {
  data: EffectDistribution;
}

const COLORS = {
  allow: CHART.accent,
  monitor: CHART.accentSoft,
  require_approval: CHART.warn,
  deny: CHART.danger,
  suspend: CHART.ink,
};

export function EffectDonutChart({ data }: EffectDonutChartProps) {
  const chartData = [
    { name: "Allow", value: data.allow, color: COLORS.allow },
    { name: "Monitor", value: data.monitor, color: COLORS.monitor },
    { name: "Require Approval", value: data.require_approval, color: COLORS.require_approval },
    { name: "Deny", value: data.deny, color: COLORS.deny },
    { name: "Suspend", value: data.suspend, color: COLORS.suspend },
  ].filter((item) => item.value > 0);

  if (chartData.length === 0) {
    return (
      <div className="flex h-[280px] items-center justify-center text-sm text-ink-500">
        No policy effects to display
      </div>
    );
  }

  return (
    <div className="h-[280px] w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={100}
            fill="#8884d8"
            paddingAngle={2}
            dataKey="value"
            label={(entry) => `${entry.name}: ${entry.value}`}
          >
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip contentStyle={chartTooltipStyle} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
