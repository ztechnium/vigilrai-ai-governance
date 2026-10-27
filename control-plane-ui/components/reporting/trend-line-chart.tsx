"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { CHART, chartTooltipStyle } from "@/components/reporting/chart-colors";
import type { TimeSeriesPoint } from "@/lib/types";

interface TrendLineChartProps {
  data: TimeSeriesPoint[];
  dataKey?: string;
  color?: string;
  title?: string;
}

export function TrendLineChart({
  data,
  dataKey = "value",
  color = CHART.accent,
  title,
}: TrendLineChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex h-[280px] items-center justify-center text-sm text-ink-500">
        No trend data available
      </div>
    );
  }

  const chartData = data.map((point) => ({
    timestamp: new Date(point.timestamp).toLocaleDateString("en-GB", {
      month: "short",
      day: "numeric",
    }),
    value: point.value,
    label: point.label,
  }));

  return (
    <div className="h-[280px] w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <LineChart data={chartData} margin={{ top: 5, right: 16, left: 0, bottom: 5 }}>
          <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" tick={{ fill: CHART.tick, fontSize: 12 }} />
          <YAxis allowDecimals={false} tick={{ fill: CHART.tick, fontSize: 12 }} />
          <Tooltip contentStyle={chartTooltipStyle} />
          {title && <Legend />}
          <Line
            type="monotone"
            dataKey={dataKey}
            stroke={color}
            strokeWidth={2}
            dot={{ r: 4 }}
            activeDot={{ r: 6 }}
            name={title}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
