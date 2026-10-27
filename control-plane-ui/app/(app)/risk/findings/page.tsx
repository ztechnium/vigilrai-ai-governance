"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { MetricStrip, PaginationBar } from "@/components/console/page-parts";
import { KpiCard } from "@/components/kpi-card";
import { SectionHeader } from "@/components/section-header";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { Table } from "@/components/ui/table";
import { getRiskFindings } from "@/lib/api";
import type { RuntimeRiskFinding } from "@/lib/types";

const PAGE_SIZE = 10;

const POLICY_NAMES: Record<string, string> = {
  POLICY_DENIAL: "Policy denial",
  AUTHORITY_DENIAL: "Authority denial",
  APPROVAL_MISMATCH: "Approval mismatch",
  UNUSUAL_TOOL_FREQUENCY: "Unusual tool frequency",
  UNUSUAL_TOOL_COMBINATION: "Unusual tool combination",
  REPEATED_DENIED_ACTION: "Repeated denied actions",
  REPEATED_APPROVAL_REQUIRED: "Repeated approval required",
  HIGH_VALUE_BURST: "High-value burst",
  RISK_SCORE_SPIKE: "Risk score spike",
  REPEATED_MODEL_MISMATCH: "Repeated model mismatch",
  CONTENT_POLICY_VIOLATION: "Content policy",
  FREQUENCY_THRESHOLD: "Frequency threshold",
  AMOUNT_THRESHOLD: "Amount threshold",
  BUDGET_WARNING: "Budget warning",
  BUDGET_EXCEEDED: "Budget exceeded",
};

function shortId(value?: string | null) {
  if (!value) return "—";
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

function humanizeCode(value: string) {
  return value
    .toLowerCase()
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function explanationField(finding: RuntimeRiskFinding, key: string) {
  const value = finding.explanation?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** Split a finding into the rule that fired and the action that triggered it. */
function policyAndAction(finding: RuntimeRiskFinding) {
  const policy =
    POLICY_NAMES[finding.finding_type] ?? humanizeCode(finding.finding_type || "Policy");
  const toolName = explanationField(finding, "tool_name");
  const ruleName = explanationField(finding, "rule");
  if (ruleName && toolName) return { policy: ruleName, action: toolName };
  if (toolName) return { policy, action: toolName };
  const subjectTypes = new Set([
    "CONTENT_POLICY_VIOLATION",
    "FREQUENCY_THRESHOLD",
    "AMOUNT_THRESHOLD",
  ]);
  if (subjectTypes.has(finding.finding_type) && ruleName) {
    return { policy: ruleName, action: null as string | null };
  }

  const title = finding.title?.trim() ?? "";
  const splitAt = title.indexOf(": ");
  if (splitAt > 0) {
    const subject = title.slice(splitAt + 2).trim();
    if (subjectTypes.has(finding.finding_type)) {
      return { policy: subject || policy, action: null as string | null };
    }
    if (subject) return { policy, action: subject };
  }

  return { policy, action: null as string | null };
}

export default function RiskFindingsPage() {
  const [items, setItems] = useState<RuntimeRiskFinding[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);

  const load = useCallback(async (pageIndex: number) => {
    setLoading(true);
    try {
      const res = await getRiskFindings({
        limit: PAGE_SIZE,
        offset: pageIndex * PAGE_SIZE,
      });
      setItems(res.data.items ?? []);
      setTotal(res.data.total ?? res.data.items?.length ?? 0);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load findings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(page);
  }, [load, page]);

  const openCount = items.filter((f) => f.status === "open" || f.status === "OPEN").length;
  const highCount = items.filter((f) => {
    const severity = f.severity?.toLowerCase();
    return severity === "high" || severity === "critical";
  }).length;

  const rows = useMemo(
    () =>
      items.map((f) => [
        f.created_at ? new Date(f.created_at).toLocaleString() : "—",
        <PolicyActionCell key={`${f.id}-policy`} finding={f} />,
        <StatusBadge key={`${f.id}-kind`} status={f.policy_kind ?? "governance"} />,
        <StatusBadge key={`${f.id}-sev`} status={f.severity} />,
        `${(f.confidence * 100).toFixed(0)}%`,
        f.status,
        <div key={`${f.id}-affected`} className="space-y-0.5 text-xs">
          <div>{f.ai_system_name ?? shortId(f.ai_system_id)}</div>
          <div className="text-muted-foreground">
            {f.agent_name ?? shortId(f.agent_id)}
            {f.agent_version_number != null ? ` · v${f.agent_version_number}` : ""}
          </div>
          <div className="text-muted-foreground">{f.model_name ?? "—"}</div>
        </div>,
        f.trajectory_id ? (
          <Link
            key={`${f.id}-traj`}
            className="font-mono text-xs text-primary underline"
            href={`/runtime/trajectories/${f.trajectory_id}`}
          >
            {shortId(f.trajectory_id)}
          </Link>
        ) : (
          "—"
        ),
      ]),
    [items],
  );

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Risk"
        title="Active Risk Findings"
        subtitle="Explainable runtime risk findings with severity, confidence, and intervention."
      />
      <MetricStrip>
        <KpiCard title="Findings" value={String(total)} />
        <KpiCard title="Open (page)" value={String(openCount)} tone="warn" />
        <KpiCard title="Critical / High (page)" value={String(highCount)} tone="danger" />
      </MetricStrip>
      <Panel title="Findings">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : error ? (
          <p className="text-sm text-red-600">{error}</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No risk findings yet.</p>
        ) : (
          <Table
            columns={[
              "Time",
              "Policy and action",
              "Kind",
              "Severity",
              "Confidence",
              "Status",
              "AI System / Agent / Model",
              "Trajectory",
            ]}
            rows={rows}
          />
        )}
        <PaginationBar total={total} page={page} pageSize={PAGE_SIZE} onPage={setPage} />
      </Panel>
    </div>
  );
}

function PolicyActionCell({ finding }: { finding: RuntimeRiskFinding }) {
  const { policy, action } = policyAndAction(finding);
  return (
    <div className="min-w-[220px] space-y-1.5">
      <div>
        <div className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">Policy</div>
        <div className="font-medium text-ink-900">{policy}</div>
      </div>
      <div>
        <div className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">Action</div>
        <div className="text-ink-800">{action ?? "—"}</div>
      </div>
      {finding.description ? (
        <p className="text-xs text-muted-foreground">{finding.description}</p>
      ) : null}
    </div>
  );
}
