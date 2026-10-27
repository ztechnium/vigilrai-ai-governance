import { cn } from "@/lib/utils";

export function Select({
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-9 w-full rounded-md border border-base-200 bg-base-100 px-3 pr-8 text-sm text-ink-700 outline-none",
        "focus:border-accent-600 focus:ring-1 focus:ring-accent-600 disabled:opacity-60",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}
