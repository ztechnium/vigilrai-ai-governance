"use client";

import { Button } from "@/components/ui/button";
import type { Organization } from "@/lib/types";

type OrgPortfolioFilterProps = {
  orgs: Organization[];
  organizationId: string;
  onOrganizationChange: (organizationId: string) => void;
  onRefresh?: () => void;
  loading?: boolean;
  children?: React.ReactNode;
};

export function OrgPortfolioFilter({ onRefresh, loading, children }: OrgPortfolioFilterProps) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      {children}
      {onRefresh && (
        <Button variant="secondary" onClick={onRefresh} disabled={loading}>
          Refresh
        </Button>
      )}
    </div>
  );
}

export function formatShortDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString();
}

export function formatShortId(value: string | null | undefined): string {
  if (!value) return "—";
  return value.length > 8 ? `${value.slice(0, 8)}…` : value;
}

export function countMapRows(map: Record<string, number> | undefined): Array<[string, string]> {
  if (!map) return [];
  return Object.entries(map)
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => [key, String(value)]);
}
