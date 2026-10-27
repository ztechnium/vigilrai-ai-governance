"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { SectionHeader } from "@/components/section-header";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/registry/panel";
import { SeverityBarChart } from "@/components/reporting/severity-bar-chart";
import { EffectDonutChart } from "@/components/reporting/effect-donut-chart";
import { TrendLineChart } from "@/components/reporting/trend-line-chart";
import { BudgetProgressBar } from "@/components/reporting/budget-progress-bar";
import { NamedBarChart } from "@/components/reporting/named-bar-chart";
import { RateProgress } from "@/components/reporting/rate-progress";
import { CHART } from "@/components/reporting/chart-colors";
import {
  getReportSummary,
  getRiskReport,
  getPolicyReport,
  getBudgetReport,
  getRuntimeReport,
  getAssuranceReport,
} from "@/lib/api";
import type {
  ReportSummary,
  RiskReport,
  PolicyReport,
  BudgetReport,
  RuntimeReport,
  AssuranceReport,
} from "@/lib/types";

export default function ReportsPage() {
  const [summary, setSummary] = useState<ReportSummary | null>(null);
  const [riskReport, setRiskReport] = useState<RiskReport | null>(null);
  const [policyReport, setPolicyReport] = useState<PolicyReport | null>(null);
  const [budgetReport, setBudgetReport] = useState<BudgetReport | null>(null);
  const [runtimeReport, setRuntimeReport] = useState<RuntimeReport | null>(null);
  const [assuranceReport, setAssuranceReport] = useState<AssuranceReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    Promise.all([
      getReportSummary(),
      getRiskReport(),
      getPolicyReport(),
      getBudgetReport(),
      getRuntimeReport(),
      getAssuranceReport(),
    ])
      .then(([summaryRes, riskRes, policyRes, budgetRes, runtimeRes, assuranceRes]) => {
        if (!active) return;
        setSummary(summaryRes.data);
        setRiskReport(riskRes.data);
        setPolicyReport(policyRes.data);
        setBudgetReport(budgetRes.data);
        setRuntimeReport(runtimeRes.data);
        setAssuranceReport(assuranceRes.data);
      })
      .catch((error) => {
        if (!active) return;
        console.error("Failed to load reports:", error);
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <SectionHeader
          eyebrow="Analytics"
          title="Reports"
          subtitle="Loading analytics workspace..."
        />
        <p className="text-sm text-ink-500">Loading reporting data...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Analytics"
        title="Reports"
        subtitle="Enterprise analytics workspace for governance, risk, and compliance metrics"
        actions={<Badge variant="neutral">Last 30 Days</Badge>}
      />

      {/* Executive Summary */}
      {summary && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-ink-900">Executive Summary</h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Panel title="AI Systems Governed">
              <div className="space-y-2">
                <p className="text-3xl font-bold text-ink-900">
                  {summary.ai_systems_governed.value}
                </p>
                {summary.ai_systems_governed.change_pct !== null &&
                  summary.ai_systems_governed.change_pct !== undefined && (
                    <p className="text-sm text-ink-500">
                      {summary.ai_systems_governed.change_pct > 0 ? "↑" : "↓"}{" "}
                      {Math.abs(summary.ai_systems_governed.change_pct).toFixed(1)}% vs previous
                      period
                    </p>
                  )}
              </div>
            </Panel>

            <Panel title="Governed Actions">
              <div className="space-y-2">
                <p className="text-3xl font-bold text-ink-900">
                  {summary.governed_actions.value.toLocaleString()}
                </p>
                {summary.governed_actions.change_pct !== null &&
                  summary.governed_actions.change_pct !== undefined && (
                    <p className="text-sm text-ink-500">
                      {summary.governed_actions.change_pct > 0 ? "↑" : "↓"}{" "}
                      {Math.abs(summary.governed_actions.change_pct).toFixed(1)}% vs previous period
                    </p>
                  )}
              </div>
            </Panel>

            <Panel title="Risk Exposure">
              <div className="space-y-2">
                <p className="text-3xl font-bold text-danger-700">
                  {summary.current_risk_exposure.value}
                </p>
                <p className="text-sm text-ink-500">
                  {summary.open_critical_findings.value} critical findings
                </p>
              </div>
            </Panel>

            <Panel title="Policy Intervention Rate">
              <div className="space-y-2">
                <p className="text-3xl font-bold text-ink-900">
                  {summary.policy_intervention_rate.value.toFixed(1)}%
                </p>
                {summary.policy_intervention_rate.change_pct !== null &&
                  summary.policy_intervention_rate.change_pct !== undefined && (
                    <p className="text-sm text-ink-500">
                      {summary.policy_intervention_rate.change_pct > 0 ? "↑" : "↓"}{" "}
                      {Math.abs(summary.policy_intervention_rate.change_pct).toFixed(1)}% vs
                      previous
                    </p>
                  )}
              </div>
            </Panel>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Policy Effects" className="min-w-0">
              <EffectDonutChart data={summary.policy_effects} />
            </Panel>
            <Panel title="Open Findings by Severity" className="min-w-0">
              <SeverityBarChart data={summary.risk_by_severity} />
            </Panel>
          </div>
          <Panel title="Coverage Rates">
            <div className="grid gap-6 md:grid-cols-3">
              <RateProgress
                label="Policy intervention"
                value={summary.policy_intervention_rate.value}
                tone={summary.policy_intervention_rate.value >= 20 ? "warn" : "accent"}
              />
              <RateProgress
                label="Budget utilization"
                value={summary.budget_utilization_pct.value}
                tone={summary.budget_utilization_pct.value >= 80 ? "warn" : "accent"}
              />
              <RateProgress
                label="Assurance coverage"
                value={summary.assurance_coverage_pct.value}
              />
            </div>
          </Panel>
        </div>
      )}

      {/* Risk Posture */}
      {riskReport && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-ink-900">Risk Posture</h2>
            <a
              href="/risk/findings"
              className="text-sm font-semibold text-accent-700 hover:text-accent-500"
            >
              View full report →
            </a>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Panel title="Severity Distribution">
              <SeverityBarChart
                data={riskReport.severity_distribution}
                onClick={(severity) => {
                  window.location.href = `/risk/findings?severity=${severity}`;
                }}
              />
            </Panel>

            <Panel title="Finding Summary">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-ink-500">Open Findings</span>
                  <span className="font-semibold text-ink-900">{riskReport.open_findings}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-ink-500">New (Period)</span>
                  <span className="font-semibold text-ink-900">{riskReport.new_findings}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-ink-500">Resolved (Period)</span>
                  <span className="font-semibold text-ink-900">{riskReport.resolved_findings}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-ink-500">Critical</span>
                  <span className="font-semibold text-danger-700">
                    {riskReport.critical_findings}
                  </span>
                </div>
              </div>
            </Panel>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Finding Trends" className="min-w-0">
              <TrendLineChart
                data={riskReport.finding_trends}
                title="New Findings"
                color={CHART.danger}
              />
            </Panel>
            <Panel title="Findings by Status" className="min-w-0">
              <NamedBarChart
                data={Object.entries(riskReport.status_distribution).map(([name, value]) => ({
                  name,
                  value,
                }))}
                emptyLabel="No finding status data"
              />
            </Panel>
          </div>

          <Panel title="Risk by AI System" className="min-w-0">
            <NamedBarChart
              layout="vertical"
              data={riskReport.risk_by_ai_system.slice(0, 8).map((item) => ({
                name: item.name,
                value: item.value,
                fill:
                  item.severity === "CRITICAL"
                    ? CHART.critical
                    : item.severity === "HIGH"
                      ? CHART.high
                      : CHART.accent,
              }))}
              emptyLabel="No system risk in this period"
            />
          </Panel>
        </div>
      )}

      {/* Policy Effectiveness */}
      {policyReport && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-ink-900">Policy Effectiveness</h2>
            <Link
              href="/governance/policies"
              className="text-sm font-semibold text-accent-700 hover:text-accent-500"
            >
              View policies →
            </Link>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Panel title="Policy Rates">
              <div className="space-y-5">
                <p className="text-sm text-ink-500">
                  {policyReport.evaluations.toLocaleString()} evaluations ·{" "}
                  {policyReport.triggers.toLocaleString()} triggers
                </p>
                <RateProgress label="Trigger rate" value={policyReport.trigger_rate} />
                <RateProgress
                  label="Intervention rate"
                  value={policyReport.intervention_rate}
                  tone={policyReport.intervention_rate >= 20 ? "warn" : "accent"}
                />
                <RateProgress
                  label="Deny rate"
                  value={policyReport.deny_rate}
                  tone={policyReport.deny_rate > 0 ? "danger" : "accent"}
                />
              </div>
            </Panel>

            <Panel title="Effect Distribution" className="min-w-0">
              <EffectDonutChart data={policyReport.effects} />
            </Panel>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Evaluation Trend" className="min-w-0">
              <TrendLineChart data={policyReport.evaluation_trends} title="Evaluations" />
            </Panel>
            <Panel title="Trigger Trend" className="min-w-0">
              <TrendLineChart
                data={policyReport.trigger_trends}
                title="Triggers"
                color={CHART.warn}
              />
            </Panel>
          </div>
        </div>
      )}

      {/* Budget & Cost */}
      {budgetReport && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-ink-900">Budget & Cost</h2>
            <Link
              href="/finops"
              className="text-sm font-semibold text-accent-700 hover:text-accent-500"
            >
              Open FinOps
            </Link>
            <Link
              href="/finops#usage"
              className="text-sm font-semibold text-accent-700 hover:text-accent-500"
            >
              Open cost breakdown
            </Link>
            <Link
              href="/risk/budgets"
              className="text-sm font-semibold text-accent-700 hover:text-accent-500"
            >
              Open budget management
            </Link>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <Panel title="Total Cost">
              <div className="space-y-2">
                <p className="text-3xl font-bold text-ink-900">
                  ${budgetReport.total_cost.toFixed(2)}
                </p>
                <p className="text-sm text-ink-500">Period total</p>
              </div>
            </Panel>

            <Panel title="Total Tokens">
              <div className="space-y-2">
                <p className="text-3xl font-bold text-ink-900">
                  {budgetReport.total_tokens.toLocaleString()}
                </p>
                <p className="text-sm text-ink-500">Period total</p>
              </div>
            </Panel>

            <Panel title="Budget Status">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-ink-500">Total Budgets</span>
                  <span className="font-semibold text-ink-900">{budgetReport.total_budgets}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-ink-500">Warning</span>
                  <Badge variant="warn">{budgetReport.budgets_warning}</Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-ink-500">Exceeded</span>
                  <Badge variant="danger">{budgetReport.budgets_exceeded}</Badge>
                </div>
              </div>
            </Panel>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Cost Trend" className="min-w-0">
              <TrendLineChart data={budgetReport.cost_trends} title="Cost" color={CHART.warn} />
            </Panel>
            <Panel title="Token Trend" className="min-w-0">
              <TrendLineChart data={budgetReport.token_trends} title="Tokens" />
            </Panel>
          </div>
          <Panel title="Budget Utilization">
            {budgetReport.budgets.length > 0 ? (
              <div className="space-y-3">
                {budgetReport.budgets.slice(0, 5).map((budget) => (
                  <BudgetProgressBar key={budget.id} budget={budget} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-ink-500">No active budgets in this period.</p>
            )}
          </Panel>
        </div>
      )}

      {runtimeReport && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-ink-900">Runtime Governance</h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Panel title="Governed Actions">
              <p className="text-3xl font-bold text-ink-900">
                {runtimeReport.governed_actions.toLocaleString()}
              </p>
            </Panel>
            <Panel title="Executions">
              <p className="text-3xl font-bold text-ink-900">
                {runtimeReport.executions.toLocaleString()}
              </p>
              <p className="text-sm text-ink-500">
                Success {runtimeReport.execution_success_rate.toFixed(1)}%
              </p>
            </Panel>
            <Panel title="Conversations">
              <p className="text-3xl font-bold text-ink-900">
                {runtimeReport.conversations.toLocaleString()}
              </p>
            </Panel>
            <Panel title="Interventions">
              <p className="text-3xl font-bold text-ink-900">
                {runtimeReport.interventions.toLocaleString()}
              </p>
              <p className="text-sm text-ink-500">
                Denied {runtimeReport.denied} · Approval {runtimeReport.approvals_required} ·
                Suspended {runtimeReport.runtime_suspensions}
              </p>
            </Panel>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Runtime Volume" className="min-w-0">
              <NamedBarChart
                data={[
                  { name: "Actions", value: runtimeReport.governed_actions },
                  { name: "Executions", value: runtimeReport.executions },
                  { name: "Conversations", value: runtimeReport.conversations },
                  {
                    name: "Evaluations",
                    value: runtimeReport.policy_evaluations,
                    fill: CHART.accentSoft,
                  },
                  { name: "Interventions", value: runtimeReport.interventions, fill: CHART.warn },
                  { name: "Denied", value: runtimeReport.denied, fill: CHART.danger },
                ]}
              />
            </Panel>
            <Panel title="Execution Success">
              <RateProgress
                label="Completed executions"
                value={runtimeReport.execution_success_rate}
                hint={`${runtimeReport.approvals_required} approvals required · ${runtimeReport.runtime_suspensions} suspensions`}
              />
            </Panel>
          </div>
        </div>
      )}

      {assuranceReport && (
        <div className="relative">
          <div className="pointer-events-none select-none space-y-4 blur-sm" aria-hidden="true">
            <h2 className="text-lg font-semibold text-ink-900">Assurance</h2>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <Panel title="Coverage">
                <p className="text-3xl font-bold text-ink-900">
                  {assuranceReport.assurance_coverage_pct.toFixed(1)}%
                </p>
                <p className="text-sm text-ink-500">
                  Valid {assuranceReport.valid_assurance} · Conditional{" "}
                  {assuranceReport.conditional_assurance}
                </p>
              </Panel>
              <Panel title="Expired / Failed">
                <p className="text-3xl font-bold text-ink-900">
                  {assuranceReport.expired_assurance + assuranceReport.failed_assurance}
                </p>
                <p className="text-sm text-ink-500">
                  Expired {assuranceReport.expired_assurance} · Failed{" "}
                  {assuranceReport.failed_assurance}
                </p>
              </Panel>
              <Panel title="Deployment Gates">
                <p className="text-3xl font-bold text-ink-900">
                  {assuranceReport.evaluation_pass_rate.toFixed(1)}%
                </p>
                <p className="text-sm text-ink-500">
                  Failed gates {assuranceReport.failed_deployment_gates}
                </p>
              </Panel>
              <Panel title="Waivers & Exceptions">
                <p className="text-3xl font-bold text-ink-900">{assuranceReport.active_waivers}</p>
                <p className="text-sm text-ink-500">
                  Expiring waivers {assuranceReport.expiring_waivers} · Open exceptions{" "}
                  {assuranceReport.open_exceptions}
                </p>
              </Panel>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Panel title="Assurance Status" className="min-w-0">
                <NamedBarChart
                  data={[
                    { name: "Valid", value: assuranceReport.valid_assurance, fill: CHART.accent },
                    {
                      name: "Conditional",
                      value: assuranceReport.conditional_assurance,
                      fill: CHART.warn,
                    },
                    { name: "Expired", value: assuranceReport.expired_assurance, fill: CHART.ink },
                    { name: "Failed", value: assuranceReport.failed_assurance, fill: CHART.danger },
                  ]}
                />
              </Panel>
              <Panel title="Assurance Rates">
                <div className="space-y-5">
                  <RateProgress label="Coverage" value={assuranceReport.assurance_coverage_pct} />
                  <RateProgress
                    label="Deployment gate pass rate"
                    value={assuranceReport.evaluation_pass_rate}
                    tone={assuranceReport.failed_deployment_gates > 0 ? "warn" : "accent"}
                    hint={`${assuranceReport.active_waivers} active waivers · ${assuranceReport.open_exceptions} open exceptions`}
                  />
                </div>
              </Panel>
            </div>
            <p className="text-sm text-ink-500">
              Control coverage is not a regulatory certification.
            </p>
          </div>
          <div className="absolute inset-0 z-10 flex items-center justify-center">
            <p className="rounded-lg border border-base-200 bg-white/90 px-4 py-2 text-sm font-semibold text-ink-900 shadow-sm">
              Assurance will be active soon
            </p>
          </div>
        </div>
      )}

      <div className="rounded-lg border border-accent-200 bg-accent-50 p-4">
        <p className="text-sm text-ink-600">
          <strong>Analytics Workspace:</strong> This reporting interface provides real-time
          aggregated metrics from authoritative governance data. All metrics are organization-scoped
          and default to the last 30 days. Use filters to refine the reporting period and scope.
        </p>
      </div>
    </div>
  );
}
