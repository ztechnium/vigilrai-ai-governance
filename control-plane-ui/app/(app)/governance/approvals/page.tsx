"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { FilterToolbar, MetricStrip } from "@/components/console/page-parts";
import { KpiCard } from "@/components/kpi-card";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table } from "@/components/ui/table";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { getApprovalRequests } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ApprovalRequestSummary } from "@/lib/types";

type InboxView = "needs_my_decision" | "waiting" | "approved_awaiting_execution" | "resolved";

const VIEWS: {
  id: InboxView;
  label: string;
  hint: string;
}[] = [
  {
    id: "needs_my_decision",
    label: "Needs decision",
    hint: "Pending requests you can approve or reject",
  },
  {
    id: "waiting",
    label: "Waiting",
    hint: "Pending, but waiting on another approver or stage",
  },
  {
    id: "approved_awaiting_execution",
    label: "Awaiting execution",
    hint: "Approved once — runtime has not consumed the grant yet",
  },
  {
    id: "resolved",
    label: "Resolved",
    hint: "Consumed, rejected, expired, or cancelled",
  },
];

const RISK_OPTIONS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

function formatExpiry(expiresAt?: string | null): {
  label: string;
  urgency: "ok" | "soon" | "expired" | "none";
} {
  if (!expiresAt) return { label: "—", urgency: "none" };
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (!Number.isFinite(ms)) {
    return { label: new Date(expiresAt).toLocaleString(), urgency: "none" };
  }
  if (ms <= 0) return { label: "Expired", urgency: "expired" };
  const mins = Math.round(ms / 60000);
  if (mins < 60) return { label: `in ${mins} min`, urgency: "soon" };
  const hours = Math.round(mins / 60);
  if (hours < 24) {
    return {
      label: `in ${hours}h`,
      urgency: hours < 2 ? "soon" : "ok",
    };
  }
  return { label: `in ${Math.round(hours / 24)}d`, urgency: "ok" };
}

function formatCreated(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function stageLabel(r: ApprovalRequestSummary) {
  const plan = r.plan;
  if (!plan?.stages?.length) return null;
  const current = plan.stages.find((s) => s.stage_index === plan.current_stage_index);
  const total = plan.stages.length;
  const index = (plan.current_stage_index ?? 0) + 1;
  return {
    name: current?.name ?? "Stage",
    progress: `${index}/${total}`,
  };
}

function requestTitle(r: ApprovalRequestSummary) {
  return r.human_summary ?? `${r.tool_name ?? r.action_type} · ${r.target_identifier ?? "—"}`;
}

function emptyCopy(view: InboxView) {
  switch (view) {
    case "needs_my_decision":
      return {
        title: "Nothing waiting on you",
        body: "When an agent action needs your approval, it will land here with risk context and a clear one-time decision.",
      };
    case "waiting":
      return {
        title: "No requests in flight",
        body: "Multi-stage approvals waiting on other roles will appear in this queue.",
      };
    case "approved_awaiting_execution":
      return {
        title: "No approved grants outstanding",
        body: "Approved requests stay here until the runtime consumes the one-time execution grant.",
      };
    default:
      return {
        title: "No resolved requests yet",
        body: "Consumed, rejected, expired, and cancelled approvals will collect here for audit.",
      };
  }
}

export default function ApprovalsPage() {
  const router = useRouter();
  const [view, setView] = useState<InboxView>("needs_my_decision");
  const [requests, setRequests] = useState<ApprovalRequestSummary[]>([]);
  const [allForStats, setAllForStats] = useState<ApprovalRequestSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [riskTier, setRiskTier] = useState("");

  useEffect(() => {
    const handle = window.setTimeout(() => setSearch(searchInput.trim()), 280);
    return () => window.clearTimeout(handle);
  }, [searchInput]);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      getApprovalRequests({
        view,
        search: search || undefined,
        risk_tier: riskTier || undefined,
      }),
      getApprovalRequests({}),
    ])
      .then(([viewRes, allRes]) => {
        setRequests(viewRes.data);
        setAllForStats(allRes.data);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [view, search, riskTier]);

  useEffect(() => {
    load();
  }, [load]);

  const stats = useMemo(() => {
    const now = Date.now();
    const hour = 60 * 60 * 1000;
    const needsDecision = allForStats.filter(
      (r) => r.status === "PENDING" && Boolean(r.viewer_capabilities?.can_approve),
    ).length;
    const waiting = allForStats.filter(
      (r) => r.status === "PENDING" && !r.viewer_capabilities?.can_approve,
    ).length;
    const expiringSoon = allForStats.filter((r) => {
      if (r.status !== "PENDING" || !r.expires_at) return false;
      const ms = new Date(r.expires_at).getTime() - now;
      return Number.isFinite(ms) && ms > 0 && ms < hour;
    }).length;
    const awaitingExecution = allForStats.filter((r) => r.status === "APPROVED").length;
    return { needsDecision, waiting, expiringSoon, awaitingExecution };
  }, [allForStats]);

  const viewCounts = useMemo(
    () => ({
      needs_my_decision: stats.needsDecision,
      waiting: stats.waiting,
      approved_awaiting_execution: stats.awaitingExecution,
      resolved: allForStats.filter((r) =>
        ["CONSUMED", "REJECTED", "EXPIRED", "CANCELLED"].includes(r.status),
      ).length,
    }),
    [allForStats, stats],
  );

  const activeView = VIEWS.find((tab) => tab.id === view) ?? VIEWS[0];
  const empty = emptyCopy(view);

  return (
    <div className="space-y-6" data-testid="approvals-page">
      <SectionHeader
        eyebrow="Governance"
        title="Approvals"
        subtitle="One-time human decisions for consequential agent actions — review risk, decide, then let runtime execute once."
        actions={
          <Button variant="outline" onClick={load} disabled={loading}>
            Refresh
          </Button>
        }
      />

      <MetricStrip>
        <button
          type="button"
          className="text-left transition hover:bg-base-100"
          onClick={() => setView("needs_my_decision")}
        >
          <KpiCard
            title="Needs my decision"
            value={String(stats.needsDecision)}
            tone={stats.needsDecision > 0 ? "warn" : "neutral"}
            trend={stats.needsDecision > 0 ? "Action required" : "Queue clear"}
          />
        </button>
        <button
          type="button"
          className="text-left transition hover:bg-base-100"
          onClick={() => setView("needs_my_decision")}
        >
          <KpiCard
            title="Expiring < 1h"
            value={String(stats.expiringSoon)}
            tone={stats.expiringSoon > 0 ? "danger" : "neutral"}
            trend={stats.expiringSoon > 0 ? "Decide soon" : "None urgent"}
          />
        </button>
        <button
          type="button"
          className="text-left transition hover:bg-base-100"
          onClick={() => setView("approved_awaiting_execution")}
        >
          <KpiCard
            title="Awaiting execution"
            value={String(stats.awaitingExecution)}
            tone={stats.awaitingExecution > 0 ? "warn" : "neutral"}
            trend="Approved, not consumed"
          />
        </button>
        <button
          type="button"
          className="text-left transition hover:bg-base-100"
          onClick={() => setView("waiting")}
        >
          <KpiCard
            title="Waiting on others"
            value={String(stats.waiting)}
            trend="Other stage / role"
          />
        </button>
      </MetricStrip>

      <Panel title="Approval inbox" description={activeView.hint}>
        <div className="-m-4">
          <div className="border-b border-base-200 bg-base-50 px-3 pt-3">
            <div
              className="flex flex-wrap gap-1 rounded-lg border border-base-200 bg-base-100 p-1"
              role="tablist"
              aria-label="Approval views"
            >
              {VIEWS.map((tab) => {
                const active = view === tab.id;
                const count = viewCounts[tab.id];
                return (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => setView(tab.id)}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition",
                      active
                        ? "bg-ink-900 text-base-100 shadow-sm"
                        : "text-ink-600 hover:bg-base-200 hover:text-ink-900",
                    )}
                  >
                    <span>{tab.label}</span>
                    <span
                      className={cn(
                        "rounded-md px-1.5 py-0.5 font-mono text-[10px] font-semibold",
                        active ? "bg-base-100/20 text-base-100" : "bg-base-200 text-ink-500",
                      )}
                    >
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <FilterToolbar
            value={searchInput}
            onChange={setSearchInput}
            placeholder="Search tool, target, policy, reason…"
            filters={[
              {
                label: "Risk",
                value: riskTier,
                onChange: setRiskTier,
                options: RISK_OPTIONS.map((opt) => ({ value: opt, label: opt })),
              },
            ]}
            action={
              <Button variant="secondary" onClick={load} disabled={loading}>
                Apply
              </Button>
            }
          />

          <div className="p-4">
            {loading ? (
              <div className="space-y-2 rounded-lg border border-dashed border-base-200 bg-base-50 px-4 py-10 text-center">
                <p className="text-sm font-medium text-ink-700">Loading approval requests…</p>
                <p className="text-xs text-ink-400">Fetching the selected inbox view.</p>
              </div>
            ) : error ? (
              <div className="rounded-lg border border-danger-500/30 bg-danger-100/40 px-4 py-6">
                <p className="text-sm font-medium text-danger-700">Could not load approvals</p>
                <p className="mt-1 text-sm text-danger-700/80">{error}</p>
                <Button className="mt-3" variant="outline" size="sm" onClick={load}>
                  Retry
                </Button>
              </div>
            ) : requests.length === 0 ? (
              <div className="space-y-2 rounded-lg border border-dashed border-base-200 bg-base-50 px-4 py-10 text-center">
                <p className="text-sm font-medium text-ink-800">{empty.title}</p>
                <p className="mx-auto max-w-md text-sm text-ink-500">{empty.body}</p>
              </div>
            ) : (
              <Table
                columns={["Request", "Risk", "Stage", "Status", "Expires", "Created"]}
                rowTestIds={requests.map((r) => `approval-row-${r.id}`)}
                onRowClick={(index) => {
                  const request = requests[index];
                  if (request) router.push(`/governance/approvals/${request.id}`);
                }}
                rows={requests.map((r) => {
                  const expiry = formatExpiry(r.expires_at);
                  const stage = stageLabel(r);
                  const canDecide = Boolean(r.viewer_capabilities?.can_approve);
                  return [
                    <div key={`summary-${r.id}`} className="max-w-xl space-y-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-ink-900">{requestTitle(r)}</span>
                        {canDecide && r.status === "PENDING" ? (
                          <Badge variant="warn">Your decision</Badge>
                        ) : null}
                      </div>
                      <div className="text-[11px] leading-relaxed text-ink-400">
                        {[
                          r.integration_name ?? r.integration_type,
                          r.tool_key ?? r.tool_name,
                          r.approval_policy_reference
                            ? `Required by ${r.approval_policy_reference}`
                            : null,
                          r.business_reason ? r.business_reason.slice(0, 80) : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </div>
                    </div>,
                    r.risk_tier ? (
                      <StatusBadge key={`risk-${r.id}`} status={r.risk_tier} />
                    ) : (
                      <span key={`risk-${r.id}`} className="text-ink-400">
                        —
                      </span>
                    ),
                    stage ? (
                      <div key={`stage-${r.id}`} className="space-y-0.5">
                        <div className="text-xs font-medium text-ink-700">{stage.name}</div>
                        <div className="font-mono text-[10px] uppercase tracking-wide text-ink-400">
                          Stage {stage.progress}
                        </div>
                      </div>
                    ) : (
                      <span key={`stage-${r.id}`} className="text-ink-400">
                        Single stage
                      </span>
                    ),
                    <StatusBadge key={`status-${r.id}`} status={r.status} />,
                    <span
                      key={`exp-${r.id}`}
                      className={cn(
                        "font-mono text-xs",
                        expiry.urgency === "expired" && "font-semibold text-danger-700",
                        expiry.urgency === "soon" && "font-semibold text-warn-700",
                        expiry.urgency === "ok" && "text-ink-600",
                        expiry.urgency === "none" && "text-ink-400",
                      )}
                    >
                      {expiry.label}
                    </span>,
                    <span key={`created-${r.id}`} className="whitespace-nowrap text-ink-500">
                      {formatCreated(r.created_at)}
                    </span>,
                  ];
                })}
              />
            )}
          </div>
        </div>
      </Panel>
    </div>
  );
}
