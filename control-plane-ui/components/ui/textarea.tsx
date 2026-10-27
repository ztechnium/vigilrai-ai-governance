import { cn } from "@/lib/utils";

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "min-h-20 w-full rounded-md border border-base-200 bg-base-100 px-3 py-2 text-sm text-ink-900 outline-none",
        "placeholder:text-ink-300 focus:border-accent-600 focus:ring-1 focus:ring-accent-600 disabled:opacity-60",
        className,
      )}
      {...props}
    />
  );
}
