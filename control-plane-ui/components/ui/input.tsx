import { cn } from "@/lib/utils";

const fieldClass =
  "h-9 w-full rounded-md border border-base-200 bg-base-100 px-3 text-sm text-ink-900 outline-none placeholder:text-ink-300 focus:border-accent-600 focus:ring-1 focus:ring-accent-600 disabled:opacity-60";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(fieldClass, className)} {...props} />;
}
