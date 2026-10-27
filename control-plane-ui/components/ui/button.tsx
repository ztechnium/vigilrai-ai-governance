import { cn } from "@/lib/utils";

export function Button({
  children,
  variant = "primary",
  size = "md",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "outline" | "danger" | "default";
  size?: "sm" | "md" | "lg";
}) {
  const styles = {
    primary: "bg-accent-600 text-white hover:bg-accent-500",
    default: "bg-accent-600 text-white hover:bg-accent-500",
    secondary: "border border-base-200 bg-base-50 text-ink-700 hover:bg-base-700",
    ghost: "bg-transparent text-ink-600 hover:bg-base-700",
    outline: "border border-base-200 bg-base-50 text-ink-700 hover:bg-base-700",
    danger: "bg-danger-600 text-white hover:bg-danger-500",
  };

  const sizes = {
    sm: "h-7 rounded-md px-3 text-xs font-semibold",
    md: "h-9 rounded-md px-4 text-sm font-semibold",
    lg: "h-10 rounded-md px-5 text-sm font-semibold",
  };

  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 transition disabled:opacity-60",
        sizes[size],
        styles[variant],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
