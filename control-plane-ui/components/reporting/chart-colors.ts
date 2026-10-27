export const CHART = {
  accent: "var(--accent-600)",
  accentSoft: "var(--accent-500)",
  warn: "var(--warn-600)",
  danger: "var(--danger-600)",
  ink: "var(--ink-400)",
  grid: "var(--base-300)",
  tick: "var(--ink-500)",
  critical: "var(--danger-600)",
  high: "var(--warn-600)",
  medium: "var(--accent-500)",
  low: "var(--ink-400)",
} as const;

export const chartTooltipStyle = {
  background: "var(--base-50)",
  border: "1px solid var(--base-200)",
  borderRadius: 8,
  color: "var(--ink-900)",
  fontSize: 12,
};
