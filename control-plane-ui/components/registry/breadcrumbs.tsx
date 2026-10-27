import Link from "next/link";

export interface Crumb {
  label: string;
  href?: string;
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav className="flex flex-wrap items-center gap-2 text-sm text-ink-400">
      {items.map((item, index) => (
        <span key={`${item.label}-${index}`} className="flex items-center gap-2">
          {index > 0 && <span className="text-ink-200">/</span>}
          {item.href ? (
            <Link href={item.href} className="font-medium text-accent-600 hover:text-accent-500">
              {item.label}
            </Link>
          ) : (
            <span className="font-medium text-ink-700">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
