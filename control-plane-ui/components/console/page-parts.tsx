import type { CSSProperties, ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export type FilterDef = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
};

export function FilterToolbar({
  value,
  onChange,
  placeholder,
  filters = [],
  action,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  filters?: FilterDef[];
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 border-b border-base-200 bg-base-50 p-3 md:flex-row md:flex-wrap md:items-center">
      <div className="relative min-w-60 flex-1">
        <svg
          aria-hidden
          viewBox="0 0 16 16"
          className="pointer-events-none absolute left-3 top-2.5 size-4 text-ink-400"
        >
          <circle cx="7" cy="7" r="4.25" fill="none" stroke="currentColor" strokeWidth="1.4" />
          <path d="M10.2 10.2 13.5 13.5" stroke="currentColor" strokeWidth="1.4" />
        </svg>
        <Input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          aria-label={placeholder}
          className="bg-base-100 pl-9"
        />
      </div>
      {filters.map((filter) => (
        <select
          key={filter.label}
          aria-label={filter.label}
          value={filter.value}
          onChange={(event) => filter.onChange(event.target.value)}
          className="h-9 rounded-md border border-base-200 bg-base-100 px-3 text-sm text-ink-500"
        >
          <option value="">{filter.label}: All</option>
          {filter.options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ))}
      {action}
    </div>
  );
}

export function PaginationBar({
  total,
  page,
  pageSize,
  onPage,
}: {
  total: number;
  page: number;
  pageSize: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total ? page * pageSize + 1 : 0;
  return (
    <div className="flex items-center justify-between border-t border-base-200 px-3 py-2 text-xs text-ink-400">
      <span>
        Showing {from}–{Math.min(total, (page + 1) * pageSize)} of {total}
      </span>
      <div className="flex items-center gap-1">
        <Button variant="outline" size="sm" disabled={page === 0} onClick={() => onPage(page - 1)}>
          Previous
        </Button>
        <span className="px-2 font-mono">
          {page + 1} / {pages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= pages - 1}
          onClick={() => onPage(page + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}

export function MetricStrip({ children }: { children: ReactNode }) {
  return (
    <div className="grid gap-px overflow-hidden rounded-lg border border-base-200 bg-base-200 [grid-template-columns:repeat(auto-fit,minmax(180px,1fr))]">
      {children}
    </div>
  );
}

export function TechnicalValue({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <span className={cn("font-mono text-xs text-ink-600", className)}>{children}</span>;
}

export function MetaGrid({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <div key={item.label}>
          <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
            {item.label}
          </dt>
          <dd className="mt-1 text-sm text-ink-700">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function PostureStrip({
  items,
}: {
  items: { label: string; value: ReactNode; tone?: string }[];
}) {
  return (
    <div
      className="grid divide-y divide-base-200 overflow-hidden rounded-lg border border-base-200 bg-base-50 sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-[repeat(var(--count),minmax(0,1fr))]"
      style={{ "--count": items.length } as CSSProperties}
    >
      {items.map((item) => (
        <div key={item.label} className="min-w-0 px-3 py-3 sm:px-4">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
            {item.label}
          </div>
          <div
            className={cn(
              "mt-1.5 flex min-h-6 min-w-0 items-center text-sm font-semibold text-ink-900 [&>*]:min-w-0 [&>*]:max-w-full",
              item.tone,
            )}
          >
            {item.value}
          </div>
        </div>
      ))}
    </div>
  );
}

export function AssetHierarchy({ nodes }: { nodes: [string, ReactNode][] }) {
  return (
    <div className="flex flex-col overflow-hidden rounded-lg border border-base-200 bg-base-50 md:flex-row md:items-stretch">
      {nodes.map((node, index) => (
        <div className="contents" key={node[0]}>
          <div className="min-w-0 flex-1 px-4 py-3">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
              {node[0]}
            </div>
            <div className="mt-1 truncate font-mono text-sm font-semibold text-ink-900">
              {node[1]}
            </div>
          </div>
          {index < nodes.length - 1 ? (
            <div className="flex items-center justify-center border-y border-base-200 px-2 text-ink-400 md:border-x md:border-y-0">
              <span aria-hidden className="text-xs">
                →
              </span>
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}
