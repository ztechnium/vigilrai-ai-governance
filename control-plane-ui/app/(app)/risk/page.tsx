"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { SectionHeader } from "@/components/section-header";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { getRiskOverview } from "@/lib/api";
import type { RiskOverview } from "@/lib/types";

export default function RiskOverviewPage() {
  const [data, setData] = useState<RiskOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getRiskOverview();
      setData(res.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load risk overview");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const cards = [
    {
      label: "High/Critical Risks",
      value: data?.high_critical_risks ?? data?.critical_findings ?? "—",
      href: "/risk/findings",
    },
    {
      label: "Active Monitors",
      value: data?.monitored_scopes ?? "—",
      href: "/risk/monitoring",
    },
    {
      label: "Budgets Near Limit",
      value: data?.budgets_near_limit ?? "—",
      href: "/risk/budgets",
    },
    {
      label: "Budgets Exceeded",
      value: data?.budgets_exceeded ?? "—",
      href: "/risk/budgets",
    },
    {
      label: "Suspended Identities",
      value: data?.suspended_runtime_identities ?? "—",
      href: "/risk/emergency",
    },
  ];

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Risk Overview"
        subtitle="Continuous oversight across budgets, anomalies, monitors, and kill-switch state."
      />
      {error && <p className="text-sm text-red-600">{error}</p>}
      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <Link key={card.label} href={card.href}>
            <Panel>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">{card.label}</p>
              <p className="mt-2 text-3xl font-semibold">{card.value}</p>
            </Panel>
          </Link>
        ))}
      </div>
      <Panel>
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-medium">Content Evaluator</h2>
            <p className="text-sm text-muted-foreground">
              {data?.evaluator?.provider
                ? `${data.evaluator.provider} / ${data.evaluator.model}`
                : "Not configured"}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={data?.evaluator?.status || "NOT_ACTIVE"} />
            <Link className="text-sm underline" href="/risk/content-evaluator">
              Configure
            </Link>
          </div>
        </div>
      </Panel>
    </div>
  );
}
