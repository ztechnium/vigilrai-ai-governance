"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART, chartTooltipStyle } from "@/components/reporting/chart-colors";

export interface BarDatum {
  name: string;
  value: number;
  fill?: string;
}

interface NamedBarChartProps {
  data: BarDatum[];
  layout?: "vertical" | "horizontal";
  height?: number;
  emptyLabel?: string;
}

export function NamedBarChart({
  data,
  layout = "horizontal",
  height = 280,
  emptyLabel = "No data for this chart",
}: NamedBarChartProps) {
  if (!data.length) {
    return (
      <div className="flex items-center justify-center text-sm text-ink-500" style={{ height }}>
        {emptyLabel}
      </div>
    );
  }

  const max = Math.max(...data.map((item) => item.value), 0);
  const valueDomain: [number, number] = [0, max === 0 ? 1 : max];
  const vertical = layout === "vertical";

  return (
    <div className="w-full min-w-0" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <BarChart
          data={data}
          layout={vertical ? "vertical" : "horizontal"}
          margin={{ top: 8, right: 16, left: vertical ? 8 : 0, bottom: 8 }}
        >
          <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" />
          {vertical ? (
            <>
              <XAxis
                type="number"
                domain={valueDomain}
                allowDecimals={false}
                tick={{ fill: CHART.tick, fontSize: 12 }}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={120}
                tick={{ fill: CHART.tick, fontSize: 12 }}
              />
            </>
          ) : (
            <>
              <XAxis dataKey="name" tick={{ fill: CHART.tick, fontSize: 12 }} interval={0} />
              <YAxis
                domain={valueDomain}
                allowDecimals={false}
                tick={{ fill: CHART.tick, fontSize: 12 }}
              />
            </>
          )}
          <Tooltip contentStyle={chartTooltipStyle} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={36}>
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.fill ?? CHART.accent} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
