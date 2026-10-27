import { cn } from "@/lib/utils";

interface RateProgressProps {
  label: string;
  value: number;
  hint?: string;
  tone?: "accent" | "warn" | "danger";
}

const BAR_TONE = {
  accent: "bg-accent-600",
  warn: "bg-warn-600",
  danger: "bg-danger-600",
} as const;

export function RateProgress({ label, value, hint, tone = "accent" }: RateProgressProps) {
  const clamped = Math.max(0, Math.min(value, 100));

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="text-ink-600">{label}</span>
        <span className="font-semibold text-ink-900">{value.toFixed(1)}%</span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-base-200">
        <div
          className={cn("h-full rounded-full transition-all duration-300", BAR_TONE[tone])}
          style={{ width: `${clamped}%` }}
        />
      </div>
      {hint && <p className="text-xs text-ink-500">{hint}</p>}
    </div>
  );
}
