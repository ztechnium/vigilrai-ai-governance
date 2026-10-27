"use client";

import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const widths = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-xl",
  "2xl": "max-w-2xl",
} as const;

export function SideDrawer({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  width = "md",
  "data-testid": dataTestId = "side-drawer",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  width?: keyof typeof widths;
  "data-testid"?: string;
}) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open || !mounted) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex justify-end"
      data-testid={dataTestId}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <button
        type="button"
        aria-label="Close drawer"
        className="absolute inset-0 bg-black/50 transition-opacity"
        onClick={onClose}
      />
      <aside
        className={cn(
          "relative flex h-full w-full flex-col border-l border-base-200 bg-base-50 shadow-2xl",
          widths[width],
        )}
      >
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-base-200 px-5 py-4">
          <div className="min-w-0 space-y-1">
            <h2 className="text-base font-semibold text-ink-900">{title}</h2>
            {description ? <p className="text-xs text-ink-500">{description}</p> : null}
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label="Close"
            className="shrink-0 px-2 text-ink-400 hover:text-ink-900"
            onClick={onClose}
          >
            <span aria-hidden className="text-lg leading-none">
              ×
            </span>
          </Button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>

        {footer ? (
          <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-base-200 bg-base-50 px-5 py-3">
            {footer}
          </footer>
        ) : null}
      </aside>
    </div>,
    document.body,
  );
}
