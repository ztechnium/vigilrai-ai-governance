"use client";

import { useEffect, useState } from "react";
import { Panel } from "@/components/registry/panel";
import { Badge } from "@/components/ui/badge";
import { NamedBarChart } from "@/components/reporting/named-bar-chart";
import { RateProgress } from "@/components/reporting/rate-progress";
import { CHART } from "@/components/reporting/chart-colors";
import { getAiSystemReport } from "@/lib/api";
import type { AISystemReport } from "@/lib/types";

interface AISystemReportTabProps {
  systemId: string;
}

export function AISystemReportTab({ systemId }: AISystemReportTabProps) {
  const [report, setReport] = useState<AISystemReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    getAiSystemReport(systemId)
      .then((response) => {
        if (!active) return;
        setReport(response.data);
      })
      .catch((err) => {
        if (!active) return;
        console.error("Failed to load AI system report:", err);
        setError(err instanceof Error ? err.message : "Failed to load report");
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [systemId]);

  if (loading) {
    return <p className="text-sm text-ink-500">Loading report data...</p>;
  }

  if (error || !report) {
    return (
      <div className="rounded-lg border border-warn-200 bg-warn-50 p-4">
        <p className="text-sm text-ink-700">
          {error || "Unable to load report data. The system may not have sufficient activity yet."}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Executive Metrics */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Panel title="Governed Actions">
          <div className="space-y-2">
            <p className="text-3xl font-bold text-ink-900">
              {report.governed_actions.toLocaleString()}
            </p>
            <p className="text-sm text-ink-500">Period total</p>
          </div>
        </Panel>

        <Panel title="Conversations">
          <div className="space-y-2">
            <p className="text-3xl font-bold text-ink-900">
              {report.conversations.toLocaleString()}
            </p>
            <p className="text-sm text-ink-500">Period total</p>
          </div>
        </Panel>

        <Panel title="Open Findings">
          <div className="space-y-2">
            <p className="text-3xl font-bold text-danger-700">{report.open_findings}</p>
            <p className="text-sm text-ink-500">{report.critical_findings} critical</p>
          </div>
        </Panel>

        <Panel title="Execution Success Rate">
          <div className="space-y-2">
            <p className="text-3xl font-bold text-ink-900">
              {report.execution_success_rate.toFixed(1)}%
            </p>
            <p className="text-sm text-ink-500">Of {report.executions} executions</p>
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Activity" className="min-w-0">
          <NamedBarChart
            data={[
              { name: "Actions", value: report.governed_actions },
              { name: "Executions", value: report.executions },
              { name: "Conversations", value: report.conversations },
              { name: "Findings", value: report.open_findings, fill: CHART.danger },
            ]}
          />
        </Panel>
        <Panel title="Rates">
          <div className="space-y-5">
            <RateProgress label="Execution success" value={report.execution_success_rate} />
            <RateProgress label="Policy trigger" value={report.policy_trigger_rate} />
            <RateProgress
              label="Deny"
              value={report.deny_rate}
              tone={report.deny_rate > 0 ? "danger" : "accent"}
            />
            <RateProgress label="Approval" value={report.approval_rate} tone="warn" />
          </div>
        </Panel>
      </div>

      {/* Risk Metrics */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-ink-900">Risk Metrics</h3>
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title="Risk Overview">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-ink-500">Open Findings</span>
                <span className="font-semibold text-ink-900">{report.open_findings}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-ink-500">Critical</span>
                <Badge variant="danger">{report.critical_findings}</Badge>
              </div>
              {report.risk_score !== null && report.risk_score !== undefined && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-ink-500">Risk Score</span>
                  <span className="font-semibold text-ink-900">{report.risk_score.toFixed(1)}</span>
                </div>
              )}
              {report.risk_trend && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-ink-500">Trend</span>
                  <span className="text-sm text-ink-700">{report.risk_trend}</span>
                </div>
              )}
            </div>
          </Panel>

          {report.risk_by_agent.length > 0 && (
            <Panel title="Risk by Agent">
              <div className="space-y-2">
                {report.risk_by_agent.slice(0, 5).map((item) => (
                  <div key={item.id} className="flex items-center justify-between">
                    <span className="text-sm text-ink-700">{item.name}</span>
                    <span className="font-mono text-sm font-semibold text-ink-900">
                      {item.value}
                    </span>
                  </div>
                ))}
              </div>
            </Panel>
          )}
        </div>
      </div>

      {/* Policy Metrics */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-ink-900">Policy Metrics</h3>
        <div className="grid gap-4 md:grid-cols-3">
          <Panel title="Policy Trigger Rate">
            <div className="space-y-2">
              <p className="text-3xl font-bold text-ink-900">
                {report.policy_trigger_rate.toFixed(1)}%
              </p>
            </div>
          </Panel>

          <Panel title="Deny Rate">
            <div className="space-y-2">
              <p className="text-3xl font-bold text-danger-700">{report.deny_rate.toFixed(1)}%</p>
            </div>
          </Panel>

          <Panel title="Approval Rate">
            <div className="space-y-2">
              <p className="text-3xl font-bold text-ink-900">{report.approval_rate.toFixed(1)}%</p>
            </div>
          </Panel>
        </div>
      </div>

      {/* Budget & Cost */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-ink-900">Budget & Cost</h3>
        <div className="grid gap-4 md:grid-cols-3">
          <Panel title="Total Cost">
            <div className="space-y-2">
              <p className="text-3xl font-bold text-ink-900">${report.cost.toFixed(2)}</p>
              <p className="text-sm text-ink-500">Period total</p>
            </div>
          </Panel>

          <Panel title="Token Usage">
            <div className="space-y-2">
              <p className="text-3xl font-bold text-ink-900">
                {report.token_usage.toLocaleString()}
              </p>
              <p className="text-sm text-ink-500">Period total</p>
            </div>
          </Panel>

          <Panel title="Budget Usage">
            <div className="space-y-2">
              <p className="text-3xl font-bold text-ink-900">${report.budget_usage.toFixed(2)}</p>
              <p className="text-sm text-ink-500">Against budgets</p>
            </div>
          </Panel>
        </div>
      </div>

      {/* Governance Status */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-ink-900">Governance Status</h3>
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title="Assurance & Evidence">
            <div className="space-y-3">
              {report.assurance_status && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-ink-500">Assurance Status</span>
                  <Badge variant={report.assurance_status === "VALID" ? "neutral" : "warn"}>
                    {report.assurance_status}
                  </Badge>
                </div>
              )}
              {report.evidence_completeness_pct !== null &&
                report.evidence_completeness_pct !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-ink-500">Evidence Completeness</span>
                    <span className="font-semibold text-ink-900">
                      {report.evidence_completeness_pct.toFixed(1)}%
                    </span>
                  </div>
                )}
            </div>
          </Panel>

          <Panel title="Incidents & Exceptions">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-ink-500">Open Incidents</span>
                <Badge variant={report.incidents > 0 ? "danger" : "neutral"}>
                  {report.incidents}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-ink-500">Active Exceptions</span>
                <span className="font-semibold text-ink-900">{report.exceptions}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-ink-500">Evaluation Waivers</span>
                <span className="font-semibold text-ink-900">{report.evaluation_waivers}</span>
              </div>
            </div>
          </Panel>
        </div>
      </div>

      <div className="rounded-lg border border-accent-200 bg-accent-50 p-4">
        <p className="text-sm text-ink-600">
          <strong>Reporting Period:</strong> This report aggregates metrics for the last 30 days.
          All data is derived from live governance records.
        </p>
      </div>
    </div>
  );
}
