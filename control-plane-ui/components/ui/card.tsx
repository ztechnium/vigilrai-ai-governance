import { cn } from "@/lib/utils";

export function Card({
  title,
  value,
  tone = "neutral",
}: {
  title: string;
  value: string;
  tone?: "neutral" | "warn" | "danger";
}) {
  const toneStyles = {
    neutral: "text-ink-900",
    warn: "text-warn-700",
    danger: "text-danger-700",
  };

  return (
    <div className="rounded-lg border border-base-200 bg-base-50 px-4 py-3">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">{title}</p>
      <p className={cn("mt-1 font-mono text-lg font-semibold", toneStyles[tone])}>{value}</p>
    </div>
  );
}
