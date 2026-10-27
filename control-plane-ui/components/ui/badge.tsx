import { cn } from "@/lib/utils";

export function Badge({
  children,
  variant = "neutral",
}: {
  children: React.ReactNode;
  variant?: "neutral" | "accent" | "warn" | "danger";
}) {
  const styles = {
    neutral: "border-base-200 bg-base-100 text-ink-600",
    accent: "border-accent-500/30 bg-accent-100 text-accent-700",
    warn: "border-warn-600/30 bg-warn-100 text-warn-700",
    danger: "border-danger-500/30 bg-danger-100 text-danger-700",
  };

  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-md border px-2 text-[11px] font-semibold",
        styles[variant],
      )}
    >
      {children}
    </span>
  );
}
