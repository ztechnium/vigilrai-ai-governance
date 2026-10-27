"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { KpiCard } from "@/components/kpi-card";
import { MetricStrip } from "@/components/console/page-parts";
import { SectionHeader } from "@/components/section-header";
import { Panel } from "@/components/registry/panel";
import { NamedBarChart } from "@/components/reporting/named-bar-chart";
import { TrendLineChart } from "@/components/reporting/trend-line-chart";
import { Table } from "@/components/ui/table";
import { getFinOpsBreakdown, getFinOpsDashboard, getFinOpsTimeseries } from "@/lib/api";
import { formatCost, formatTokens } from "@/lib/finops-format";
import type { FinOpsBreakdownItem, FinOpsDashboard } from "@/lib/types";

const USAGE_VIEWS = [
  { id: "ai_system", label: "AI System" },
  { id: "agent", label: "Agent" },
  { id: "agent_version", label: "Agent version" },
  { id: "runtime_identity", label: "Runtime identity" },
  { id: "delegation", label: "Delegation" },
] as const;

type UsageDimension = (typeof USAGE_VIEWS)[number]["id"];

function BreakdownTable({
  loading,
  error,
  empty,
  columns,
  rows,
}: {
  loading: boolean;
  error: string | null;
  empty: string;
  columns: string[];
  rows: Array<Array<string>>;
}) {
  if (loading) return <p className="text-sm text-ink-500">Loading…</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (rows.length === 0) return <p className="text-sm text-ink-500">{empty}</p>;
  return <Table columns={columns} rows={rows} />;
}

export default function FinOpsOverviewPage() {
  const [dashboard, setDashboard] = useState<FinOpsDashboard | null>(null);
  const [series, setSeries] = useState<Array<{ timestamp: string; value: number }>>([]);
  const [systems, setSystems] = useState<Array<{ name: string; value: number }>>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [dimension, setDimension] = useState<UsageDimension>("ai_system");
  const [usageItems, setUsageItems] = useState<FinOpsBreakdownItem[]>([]);
  const [usageError, setUsageError] = useState<string | null>(null);
  const [usageLoading, setUsageLoading] = useState(true);

  const [models, setModels] = useState<FinOpsBreakdownItem[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [modelsLoading, setModelsLoading] = useState(true);

  const [tenants, setTenants] = useState<FinOpsBreakdownItem[]>([]);
  const [tenantsError, setTenantsError] = useState<string | null>(null);
  const [tenantsLoading, setTenantsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    Promise.all([
      getFinOpsDashboard(),
      getFinOpsTimeseries(),
      getFinOpsBreakdown({ dimension: "ai_system", limit: 8 }),
    ])
      .then(([dash, trend, breakdown]) => {
        if (!active) return;
        setDashboard(dash.data);
        setSeries(
          trend.data.points.map((point) => ({ timestamp: point.timestamp, value: point.cost })),
        );
        setSystems(
          breakdown.data.items.map((item) => ({
            name: item.label || "Unattributed",
            value: item.cost,
          })),
        );
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Unable to load FinOps");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    setUsageLoading(true);
    setUsageError(null);
    getFinOpsBreakdown({ dimension, limit: 50 })
      .then((res) => {
        if (active) setUsageItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (active) setUsageError(err instanceof Error ? err.message : "Unable to load usage");
      })
      .finally(() => {
        if (active) setUsageLoading(false);
      });
    return () => {
      active = false;
    };
  }, [dimension]);

  useEffect(() => {
    let active = true;
    getFinOpsBreakdown({ dimension: "model", limit: 50 })
      .then((res) => {
        if (active) setModels(res.data.items);
      })
      .catch((err: unknown) => {
        if (active) setModelsError(err instanceof Error ? err.message : "Unable to load models");
      })
      .finally(() => {
        if (active) setModelsLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    getFinOpsBreakdown({ dimension: "delegation", limit: 50 })
      .then((res) => {
        if (active) setTenants(res.data.items);
      })
      .catch((err: unknown) => {
        if (active) setTenantsError(err instanceof Error ? err.message : "Unable to load tenants");
      })
      .finally(() => {
        if (active) setTenantsLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const totals = dashboard?.totals;

  return (
    <div className="space-y-6" data-testid="finops-overview">
      <SectionHeader
        eyebrow="FinOps"
        title="AI spend"
        subtitle="Metered, estimated, and billed cost with explicit measurement confidence — never invent unavailable amounts."
      />
      {loading ? <p className="text-sm text-ink-500">Loading spend...</p> : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {totals ? (
        <MetricStrip>
          <KpiCard
            title="Metered Cost"
            value={formatCost(
              totals.metered_cost ?? totals.actual_cost,
              "METERED",
              totals.currency,
            )}
            trend={totals.cost_state}
          />
          <KpiCard
            title="Estimated Outstanding"
            value={formatCost(totals.estimated_cost, "ESTIMATED", totals.currency)}
          />
          <KpiCard
            title="Billed Cost"
            value={formatCost(
              totals.billed_cost,
              totals.billed_cost ? "BILLED" : "UNAVAILABLE",
              totals.currency,
            )}
          />
          <KpiCard title="Tokens" value={formatTokens(totals.total_tokens)} />
          <KpiCard
            title="Budget at Risk"
            value={`${dashboard?.budget_pressure.warning ?? 0} warn / ${dashboard?.budget_pressure.exceeded ?? 0} exceeded`}
          />
          <KpiCard
            title="Cost Measurement Coverage"
            value={`${dashboard?.coverage.cost_coverage_pct ?? 0}%`}
            trend={`Metered ${dashboard?.coverage.metered_pct ?? dashboard?.coverage.actual_pct ?? 0}% · Estimated ${dashboard?.coverage.estimated_pct ?? 0}% · Unavailable ${dashboard?.coverage.unavailable_pct ?? 0}%`}
          />
        </MetricStrip>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Cost over time">
          <TrendLineChart data={series} title="Cost" />
        </Panel>
        <Panel title="Cost by AI system">
          <NamedBarChart
            data={systems}
            layout="vertical"
            emptyLabel="No metered spend in this period"
          />
        </Panel>
      </div>
      {dashboard ? (
        <Panel title="Cost coverage">
          <p className="text-sm text-ink-600">
            {dashboard.coverage.cost_coverage_pct}% of spans have a cost. Metered{" "}
            {dashboard.coverage.metered_pct ?? dashboard.coverage.actual_pct}% · Estimated{" "}
            {dashboard.coverage.estimated_pct}% · Unavailable {dashboard.coverage.unavailable_pct}%.
            Missing pricing is never shown as $0.
          </p>
          <div className="mt-3 flex flex-wrap gap-4 text-sm">
            <a className="text-accent-700" href="#usage">
              Usage & cost
            </a>
            <a className="text-accent-700" href="#models">
              Models
            </a>
            <a className="text-accent-700" href="#tenants">
              Tenants
            </a>
            <Link className="text-accent-700" href="/finops/pricing">
              Pricing
            </Link>
            <Link className="text-accent-700" href="/risk/budgets">
              Spend controls ({dashboard.budget_pressure.warning} warning,{" "}
              {dashboard.budget_pressure.exceeded} exceeded)
            </Link>
          </div>
        </Panel>
      ) : null}

      <div id="usage" className="scroll-mt-6" data-testid="finops-usage">
        <Panel
          title="Usage & cost"
          description="Spend attributed along the control chain: system, agent, version, runtime identity, and delegation."
        >
          <div className="mb-4 flex flex-wrap gap-2">
            {USAGE_VIEWS.map((view) => (
              <button
                key={view.id}
                type="button"
                className={`rounded-md border px-3 py-1 text-sm ${dimension === view.id ? "border-accent-500 bg-accent-50" : "border-ink-200"}`}
                onClick={() => setDimension(view.id)}
              >
                {view.label}
              </button>
            ))}
          </div>
          <BreakdownTable
            loading={usageLoading}
            error={usageError}
            empty="No metered usage for this view."
            columns={["Name", "Cost", "Tokens", "Trajectories", "Calls"]}
            rows={usageItems.map((item) => [
              item.label || "Unattributed",
              formatCost(item.cost, item.cost ? "MIXED" : "UNAVAILABLE"),
              formatTokens(item.tokens),
              String(item.trajectories),
              String(item.calls),
            ])}
          />
        </Panel>
      </div>

      <div id="models" className="scroll-mt-6" data-testid="finops-models">
        <Panel
          title="Models"
          description="Calls, tokens, and cost by model. Cost state stays on the trajectory that produced the call."
        >
          <BreakdownTable
            loading={modelsLoading}
            error={modelsError}
            empty="No model usage recorded."
            columns={["Model", "Calls", "Input tokens", "Output tokens", "Cost", "Avg / call"]}
            rows={models.map((item) => [
              item.label || "Unknown model",
              String(item.calls),
              formatTokens(item.input_tokens),
              formatTokens(item.output_tokens),
              formatCost(item.cost, item.cost ? "MIXED" : "UNAVAILABLE"),
              item.avg_cost_per_call === null
                ? "Unavailable"
                : formatCost(item.avg_cost_per_call, "MIXED"),
            ])}
          />
        </Panel>
      </div>

      <div id="tenants" className="scroll-mt-6" data-testid="finops-tenants">
        <Panel
          title="Tenants"
          description="Spend separated by delegation. A friendly label is used when the delegation scope includes one."
        >
          <BreakdownTable
            loading={tenantsLoading}
            error={tenantsError}
            empty="No delegation-attributed spend."
            columns={["Tenant / delegation", "Cost", "Tokens", "Trajectories"]}
            rows={tenants.map((item) => [
              item.label || "Unattributed",
              formatCost(item.cost, item.cost ? "MIXED" : "UNAVAILABLE"),
              formatTokens(item.tokens),
              String(item.trajectories),
            ])}
          />
        </Panel>
      </div>
    </div>
  );
}
