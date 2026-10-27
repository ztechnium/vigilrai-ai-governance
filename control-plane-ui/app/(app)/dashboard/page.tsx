"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { KpiCard } from "@/components/kpi-card";
import { MetricStrip } from "@/components/console/page-parts";
import { SectionHeader } from "@/components/section-header";
import { Badge } from "@/components/ui/badge";
import { Table } from "@/components/ui/table";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { SeverityBarChart } from "@/components/reporting/severity-bar-chart";
import { EffectDonutChart } from "@/components/reporting/effect-donut-chart";
import { ApiError, getTrajectories, getReportSummary } from "@/lib/api";
import { formatCost } from "@/lib/finops-format";
import type { ReportSummary, TrajectorySummary } from "@/lib/types";

function formatTime(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export default function DashboardPage() {
  const router = useRouter();
  const [executions, setExecutions] = useState<TrajectorySummary[]>([]);
  const [reportSummary, setReportSummary] = useState<ReportSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [reportLoading, setReportLoading] = useState(true);
  const [executionAccessMessage, setExecutionAccessMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    // Recent executions are runtime trajectories, not the legacy prompt audit log.
    getTrajectories({ limit: 5 })
      .then((response) => {
        if (!active) return;
        setExecutions(response.data.items ?? []);
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 403) {
          setExecutionAccessMessage(
            "Your role can access the dashboard, but not execution details.",
          );
          return;
        }
        setExecutionAccessMessage("Unable to load recent executions right now.");
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });

    // Load report summary
    getReportSummary()
      .then((response) => {
        if (!active) return;
        setReportSummary(response.data);
      })
      .catch((error: unknown) => {
        if (!active) return;
        console.error("Failed to load report summary:", error);
      })
      .finally(() => {
        if (!active) return;
        setReportLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Control Plane"
        title="Control Posture"
        subtitle="Current AI risk exposure and runtime control outcomes. Recent executions are loaded from the control plane."
        actions={<Badge variant="neutral">Ops View</Badge>}
      />

      <div className="rounded-lg border border-accent-200 bg-accent-50 p-4">
        <h2 className="text-sm font-semibold text-ink-900">New organization?</h2>
        <p className="mt-1 text-sm text-ink-600">
          Start with guided onboarding: register an AI system, choose an integration, test the
          connection, then run your first governed action.
        </p>
        <div className="mt-3 flex flex-wrap gap-3 text-sm font-semibold">
          <a href="/app/onboarding" className="text-accent-700 hover:text-accent-500">
            Continue onboarding →
          </a>
          <a
            href="/governance/runtime-identities"
            className="text-accent-700 hover:text-accent-500"
          >
            Runtime identities →
          </a>
        </div>
      </div>

      <MetricStrip>
        {reportLoading ? (
          <>
            <KpiCard title="Loading..." value="..." trend="Loading" />
            <KpiCard title="Loading..." value="..." trend="Loading" />
            <KpiCard title="Loading..." value="..." trend="Loading" />
            <KpiCard title="Loading..." value="..." trend="Loading" />
            <KpiCard title="Loading..." value="..." trend="Loading" />
            <KpiCard title="Loading..." value="..." trend="Loading" />
          </>
        ) : reportSummary ? (
          <>
            <KpiCard
              title="AI Spend"
              value="Open FinOps"
              trend="Actual, estimated, and unavailable stay separate"
            />
            <KpiCard
              title="Risk Exposure"
              value={reportSummary.current_risk_exposure.value.toLocaleString()}
              tone={reportSummary.open_critical_findings.value > 0 ? "danger" : "neutral"}
            />
            <KpiCard
              title="Governed Activity"
              value={reportSummary.governed_actions.value.toLocaleString()}
            />
            <KpiCard
              title="Needs Attention"
              value={String(reportSummary.attention?.length ?? 0)}
              tone={(reportSummary.attention?.length ?? 0) > 0 ? "warn" : "neutral"}
            />
          </>
        ) : (
          <>
            <KpiCard title="Governed Actions" value="0" trend="No data" />
            <KpiCard title="Policy Triggers" value="0" trend="No data" />
            <KpiCard title="Denied Actions" value="0" trend="No data" />
            <KpiCard title="Open Risk Findings" value="0" trend="No data" />
            <KpiCard title="Critical Findings" value="0" trend="No data" />
            <KpiCard title="AI Systems" value="0" trend="No data" />
          </>
        )}
      </MetricStrip>

      <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr_0.8fr]">
        <Panel title="Recent Executions">
          {loading ? (
            <p className="text-sm text-ink-500">Loading recent executions...</p>
          ) : executionAccessMessage ? (
            <p className="text-sm text-ink-500">{executionAccessMessage}</p>
          ) : executions.length === 0 ? (
            <p className="text-sm text-ink-500">No recent executions.</p>
          ) : (
            <div className="space-y-3">
              <Table
                columns={["Started", "AI System", "Agent", "Status", "Findings", "Cost"]}
                rows={executions.map((execution) => [
                  formatTime(execution.started_at),
                  execution.ai_system_name ?? "—",
                  execution.agent_name ?? "—",
                  <StatusBadge key={`${execution.id}-status`} status={execution.status} />,
                  String(execution.finding_count ?? 0),
                  formatCost(
                    execution.economics?.total_cost,
                    execution.economics?.cost_state,
                    execution.economics?.currency,
                  ),
                ])}
                onRowClick={(index) => {
                  const execution = executions[index];
                  if (execution) router.push(`/runtime/trajectories/${execution.id}`);
                }}
              />
              <Link
                href="/runtime/trajectories"
                className="text-sm font-semibold text-accent-700 hover:text-accent-500"
              >
                View all executions
              </Link>
            </div>
          )}
        </Panel>
        <Panel title="Risk Severity" className="min-w-0">
          {reportLoading ? (
            <p className="text-sm text-ink-500">Loading risk metrics...</p>
          ) : reportSummary ? (
            <SeverityBarChart
              data={reportSummary.risk_by_severity}
              onClick={(severity) => {
                window.location.href = `/risk/findings?severity=${severity}`;
              }}
            />
          ) : (
            <p className="text-sm text-ink-500">No risk data available.</p>
          )}
        </Panel>
        <Panel title="Policy Effects" className="min-w-0">
          {reportLoading ? (
            <p className="text-sm text-ink-500">Loading policy effects...</p>
          ) : reportSummary ? (
            <EffectDonutChart data={reportSummary.policy_effects} />
          ) : (
            <p className="text-sm text-ink-500">No policy data available.</p>
          )}
        </Panel>
      </div>
      <p className="text-xs text-ink-400">
        Metrics are aggregated from live governance data in real-time. Recent executions are the
        latest runtime trajectories. Reporting period defaults to last 30 days.
      </p>
    </div>
  );
}
