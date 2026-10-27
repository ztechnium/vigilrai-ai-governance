import type { ReactNode } from "react";

export function FormField({
  label,
  hint,
  children,
  required,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  required?: boolean;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
        {label}
        {required && <span className="text-danger-500"> *</span>}
      </span>
      {children}
      {hint && <p className="text-[11px] text-ink-400">{hint}</p>}
    </label>
  );
}
