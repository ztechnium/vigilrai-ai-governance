"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { CHART, chartTooltipStyle } from "@/components/reporting/chart-colors";
import type { SeverityDistribution } from "@/lib/types";

interface SeverityBarChartProps {
  data: SeverityDistribution;
  onClick?: (severity: string) => void;
}

export function SeverityBarChart({ data, onClick }: SeverityBarChartProps) {
  const chartData = [
    { name: "Critical", value: data.critical, fill: CHART.critical },
    { name: "High", value: data.high, fill: CHART.high },
    { name: "Medium", value: data.medium, fill: CHART.medium },
    { name: "Low", value: data.low, fill: CHART.low },
  ];
  if ((data.info ?? 0) > 0) {
    chartData.push({ name: "Info", value: data.info ?? 0, fill: CHART.ink });
  }
  const max = Math.max(...chartData.map((item) => item.value), 0);

  return (
    <div className="h-[280px] w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 5, right: 16, left: 8, bottom: 5 }}
        >
          <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" />
          <XAxis
            type="number"
            domain={[0, max === 0 ? 1 : max]}
            allowDecimals={false}
            tick={{ fill: CHART.tick, fontSize: 12 }}
          />
          <YAxis
            dataKey="name"
            type="category"
            width={72}
            tick={{ fill: CHART.tick, fontSize: 12 }}
          />
          <Tooltip contentStyle={chartTooltipStyle} />
          <Bar
            dataKey="value"
            onClick={(entry) => onClick?.(entry.name)}
            cursor={onClick ? "pointer" : "default"}
            radius={[0, 4, 4, 0]}
            maxBarSize={28}
          >
            {chartData.map((entry) => (
              <Cell key={entry.name} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
