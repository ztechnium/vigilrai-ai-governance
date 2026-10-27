"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { AgentAvatar } from "@/components/agent-avatar";
import { Breadcrumbs } from "@/components/registry/breadcrumbs";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { PostureStrip, TechnicalValue } from "@/components/console/page-parts";
import { Button } from "@/components/ui/button";
import { Tabs } from "@/components/ui/tabs";
import { Table } from "@/components/ui/table";
import {
  exportTrajectory,
  getTrajectory,
  getTrajectoryEconomics,
  getTrajectoryGraph,
  getTrajectoryLifecycle,
  getTrajectoryRiskFindings,
} from "@/lib/api";
import { FlowHierarchyView } from "@/components/trajectory/flow-hierarchy";
import { InvestigationWorkspace } from "@/components/trajectory/investigation-workspace";
import { LifecycleTimelineView } from "@/components/trajectory/lifecycle/lifecycle-timeline";
import { humanEventLabel } from "@/lib/evidence-content";
import type {
  TrajectoryDetail,
  TrajectoryEconomics,
  TrajectoryGraph,
  TrajectoryLifecycle,
  TrajectoryRiskFindings,
} from "@/lib/types";
import { formatCost, formatTokens, sourceLabel } from "@/lib/finops-format";

function formatTime(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatClock(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return `${date.toLocaleTimeString("en-GB", { hour12: false })}.${String(date.getMilliseconds()).padStart(3, "0")}`;
}

function formatDuration(
  startedAt?: string | null,
  endedAt?: string | null,
  options?: { inProgress?: boolean },
) {
  if (!startedAt) return "—";
  const start = new Date(startedAt).getTime();
  if (Number.isNaN(start)) return "—";

  if (options?.inProgress && !endedAt) {
    return "In progress";
  }

  const end = endedAt ? new Date(endedAt).getTime() : Date.now();
  if (Number.isNaN(end) || end < start) return "—";
  const ms = end - start;
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)}s`;
  const totalSec = Math.round(ms / 1000);
  const hours = Math.floor(totalSec / 3600);
  const minutes = Math.floor((totalSec % 3600) / 60);
  const seconds = totalSec % 60;
  if (hours > 48) return `${Math.floor(hours / 24)}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m ${seconds}s`;
}

function shortId(value?: string | null) {
  if (!value) return "—";
  return value.length > 14 ? `${value.slice(0, 12)}…` : value;
}

const GOVERNANCE_DECISIONS = new Set([
  "ALLOW",
  "ALLOWED",
  "DENY",
  "DENIED",
  "BLOCK",
  "BLOCKED",
  "APPROVAL_REQUIRED",
  "APPROVAL REQUIRED",
  "ESCALATE",
  "MONITOR",
  "WARN",
]);

function normalizeDecision(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const upper = trimmed.toUpperCase().replace(/-/g, "_");
  if (GOVERNANCE_DECISIONS.has(upper) || GOVERNANCE_DECISIONS.has(trimmed.toUpperCase())) {
    return upper.replace(/_/g, " ");
  }
  // Nested object stringifications / deployment modes are not decisions.
  if (
    upper.includes("HOOK") ||
    upper.includes("ENFORCE") ||
    upper.includes("OBSERVE") ||
    upper.includes("SHADOW") ||
    upper.includes("LOCAL")
  ) {
    return null;
  }
  return null;
}

function SourceBadge({ source }: { source: string }) {
  const tone = source.startsWith("RAI_")
    ? "border-accent-200 bg-accent-50 text-accent-700"
    : source === "DERIVED"
      ? "border-base-200 bg-base-100 text-ink-500"
      : "border-warn-100 bg-warn-50 text-warn-700";
  return (
    <span
      className={`inline-flex rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold ${tone}`}
    >
      {source}
    </span>
  );
}

function AssuranceBadge({ level }: { level: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-ink-600">
      <span
        className={`size-1.5 rounded-full ${
          level === "HIGH" ? "bg-accent-600" : level === "LOW" ? "bg-warn-600" : "bg-ink-400"
        }`}
      />
      {level.toLowerCase()}
    </span>
  );
}

export default function TrajectoryDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const trajectoryId = params.trajectoryId as string;
  const focusEventId = searchParams.get("event");
  const [trajectory, setTrajectory] = useState<TrajectoryDetail | null>(null);
  const [economics, setEconomics] = useState<TrajectoryEconomics | null>(null);
  const [graph, setGraph] = useState<TrajectoryGraph | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [graphLoaded, setGraphLoaded] = useState(false);
  const [lifecycle, setLifecycle] = useState<TrajectoryLifecycle | null>(null);
  const [lifecycleLoading, setLifecycleLoading] = useState(false);
  const [lifecycleError, setLifecycleError] = useState<string | null>(null);
  const [lifecycleLoaded, setLifecycleLoaded] = useState(false);
  const [riskFindings, setRiskFindings] = useState<TrajectoryRiskFindings | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const [riskError, setRiskError] = useState<string | null>(null);
  const [tab, setTab] = useState<string>("Investigation");
  const [selectedEventId, setSelectedEventId] = useState("");
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const detailRes = await getTrajectory(trajectoryId);
      setTrajectory(detailRes.data);
      const econ = await getTrajectoryEconomics(trajectoryId).catch(() => null);
      setEconomics(econ?.data ?? null);
      const events = detailRes.data.events ?? [];
      const preferred =
        focusEventId && events.some((event) => event.id === focusEventId)
          ? focusEventId
          : events.find((event) => event.event_type.toUpperCase().includes("POLICY"))?.id ||
            events[0]?.id ||
            "";
      setSelectedEventId(preferred);
      setGraph(null);
      setGraphLoaded(false);
      setGraphError(null);
      setLifecycle(null);
      setLifecycleLoaded(false);
      setLifecycleError(null);
      setRiskFindings(null);
      setRiskError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load trajectory");
    } finally {
      setLoading(false);
    }
  }, [trajectoryId, focusEventId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (tab !== "Timeline" || lifecycleLoaded) return;
    let cancelled = false;
    void (async () => {
      setLifecycleLoading(true);
      setLifecycleError(null);
      try {
        const res = await getTrajectoryLifecycle(trajectoryId);
        if (!cancelled) {
          setLifecycle(res.data);
          setLifecycleLoaded(true);
        }
      } catch (err) {
        if (!cancelled) {
          setLifecycle(null);
          setLifecycleError(
            err instanceof Error ? err.message : "Failed to load lifecycle timeline",
          );
          setLifecycleLoaded(true);
        }
      } finally {
        if (!cancelled) setLifecycleLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tab, trajectoryId, lifecycleLoaded]);

  useEffect(() => {
    if (tab !== "Findings") return;
    let cancelled = false;
    setRiskLoading(true);
    setRiskError(null);
    void (async () => {
      try {
        const res = await getTrajectoryRiskFindings(trajectoryId);
        if (cancelled) return;
        setRiskFindings(res.data);
      } catch (err) {
        if (cancelled) return;
        setRiskFindings(null);
        setRiskError(err instanceof Error ? err.message : "Failed to load risk findings");
      } finally {
        if (!cancelled) setRiskLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tab, trajectoryId]);

  useEffect(() => {
    if (tab !== "Flow" || graphLoaded) return;
    let cancelled = false;
    void (async () => {
      setGraphLoading(true);
      setGraphError(null);
      try {
        const res = await getTrajectoryGraph(trajectoryId);
        if (!cancelled) {
          setGraph(res.data);
          setGraphLoaded(true);
        }
      } catch (err) {
        if (!cancelled) {
          setGraph(null);
          setGraphError(err instanceof Error ? err.message : "Failed to load flow graph");
          setGraphLoaded(true);
        }
      } finally {
        if (!cancelled) setGraphLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tab, trajectoryId, graphLoaded]);

  async function handleExport() {
    setExporting(true);
    try {
      const res = await exportTrajectory(trajectoryId);
      const blob = new Blob([JSON.stringify(res.data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${trajectoryId}-evidence.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  const events = useMemo(() => trajectory?.events ?? [], [trajectory]);
  const decision = useMemo(() => {
    if (!trajectory) return "—";
    for (const event of [...events].reverse()) {
      const payload = event.payload ?? {};
      for (const key of ["decision", "enforcement_decision", "policy_decision", "effect"]) {
        const value = payload[key];
        if (typeof value === "string") {
          const normalized = normalizeDecision(value);
          if (normalized) return normalized;
        }
        if (value && typeof value === "object" && "final_effect" in value) {
          const effect = (value as { final_effect?: unknown }).final_effect;
          if (typeof effect === "string") {
            const normalized = normalizeDecision(effect);
            if (normalized) return normalized;
          }
        }
      }
    }
    for (const candidate of [
      trajectory.deployment_control,
      trajectory.enforcement_mode,
      trajectory.status,
    ]) {
      if (typeof candidate === "string") {
        const normalized = normalizeDecision(candidate);
        if (normalized) return normalized;
      }
    }
    // Active trajectories without a recorded governance decision.
    if (String(trajectory.status).toUpperCase() === "ACTIVE") return "OBSERVED";
    if (String(trajectory.status).toUpperCase() === "COMPLETED") return "ALLOW";
    return "—";
  }, [events, trajectory]);
  const findings = useMemo(() => {
    const evidence = riskFindings?.evidence_findings ?? [];
    const risk = riskFindings?.risk?.findings ?? [];
    const trajectoryFindings = trajectory?.findings ?? [];
    return { evidence, risk, trajectoryFindings };
  }, [riskFindings, trajectory]);

  const evidenceStats = useMemo(() => {
    const authoritative = events.filter((event) => event.source_type.startsWith("RAI_")).length;
    const contentTypes = new Set([
      "PROMPT_OBSERVED",
      "MODEL_REQUEST_OBSERVED",
      "MODEL_RESPONSE_OBSERVED",
      "AGENT_OUTPUT_OBSERVED",
    ]);
    const missing = events.filter(
      (event) => contentTypes.has(event.event_type) && !event.content_preview,
    ).length;
    return { authoritative, missing, observed: events.length - authoritative };
  }, [events]);

  if (loading) {
    return <p className="text-sm text-ink-500">Loading trajectory...</p>;
  }

  if (error || !trajectory) {
    return <p className="text-sm text-danger-600">{error ?? "Trajectory not found"}</p>;
  }

  const riskLevel =
    riskFindings?.highest_risk_level ?? trajectory.assurance_summary?.highest ?? null;
  const findingCount =
    findings.evidence.length + findings.risk.length + findings.trajectoryFindings.length;

  const tabLabels = [
    "Investigation",
    "Timeline",
    "Evidence",
    `Findings (${findingCount})`,
    "Flow",
  ] as const;

  const activeTabLabel = tab === "Findings" ? `Findings (${findingCount})` : tab;

  return (
    <div className="space-y-4" data-testid="trajectory-detail-page">
      <div className="flex flex-col gap-4 border-b border-base-200 pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <div className="mb-2 text-xs text-ink-500">
            <Breadcrumbs
              items={[
                { label: "Trajectories", href: "/runtime/trajectories" },
                { label: shortId(trajectory.id) },
              ]}
            />
          </div>
          <h1 className="text-[28px] font-semibold leading-tight text-ink-900">
            Runtime Trajectory
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-500">
            <span className="inline-flex items-center gap-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                ID
              </span>
              <TechnicalValue className="text-ink-700">{trajectory.id}</TechnicalValue>
            </span>
            {trajectory.session_key || trajectory.conversation_id ? (
              <span className="inline-flex items-center gap-1.5">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                  Session
                </span>
                <TechnicalValue className="text-ink-700">
                  {shortId(trajectory.session_key || trajectory.conversation_id)}
                </TechnicalValue>
              </span>
            ) : null}
            {trajectory.event_count != null ? (
              <span className="inline-flex items-center gap-1.5">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                  Events
                </span>
                <span className="font-mono text-ink-700">{trajectory.event_count}</span>
              </span>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <StatusBadge status={trajectory.status} />
          {riskLevel ? <StatusBadge status={riskLevel} /> : null}
          <Button variant="secondary" size="sm" onClick={() => void load()}>
            Refresh
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={exporting}
            onClick={() => void handleExport()}
          >
            {exporting ? "Exporting…" : "Export Evidence"}
          </Button>
        </div>
      </div>

      <div className="sticky top-12 z-10 space-y-2 bg-base-100/95 py-1 backdrop-blur">
        <PostureStrip
          items={[
            { label: "Decision", value: <StatusBadge status={String(decision)} /> },
            {
              label: "Risk",
              value: riskLevel ? <StatusBadge status={riskLevel} /> : "—",
            },
            {
              label: "Cost",
              value: (
                <span title={sourceLabel(economics?.summary.metering_source)}>
                  {formatCost(
                    economics?.summary.total_cost,
                    economics?.summary.cost_state,
                    economics?.summary.currency,
                  )}
                </span>
              ),
            },
            { label: "Tokens", value: formatTokens(economics?.summary.total_tokens) },
            { label: "Model calls", value: String(economics?.summary.model_calls ?? 0) },
            {
              label: "AI System",
              value: (
                <Link
                  href={`/governance/registry/${trajectory.ai_system_id}`}
                  className="truncate text-sm text-accent-600 hover:text-accent-500"
                >
                  {trajectory.ai_system_name ?? shortId(trajectory.ai_system_id)}
                </Link>
              ),
            },
            {
              label: "Agent",
              value: (
                <span className="inline-flex min-w-0 items-center gap-2">
                  <AgentAvatar
                    name={trajectory.agent_name}
                    avatar={trajectory.agent_avatar}
                    size={28}
                    placeholder
                  />
                  <span className="truncate text-sm">
                    {trajectory.agent_name ?? shortId(trajectory.agent_id)}
                  </span>
                </span>
              ),
            },
            {
              label: "Version",
              value: (
                <span className="font-mono text-sm">
                  {trajectory.agent_version_number != null
                    ? `v${trajectory.agent_version_number}`
                    : shortId(trajectory.agent_version_id)}
                </span>
              ),
            },
            {
              label: "Runtime",
              value: (
                <Link
                  href={`/governance/runtime-identities/${trajectory.runtime_identity_id}`}
                  className="truncate text-sm text-accent-600 hover:text-accent-500"
                >
                  {trajectory.runtime_identity_name ?? shortId(trajectory.runtime_identity_id)}
                </Link>
              ),
            },
            {
              label: "Client",
              value: <span className="truncate text-sm">{trajectory.client_type ?? "—"}</span>,
            },
            {
              label: "Started",
              value: <span className="truncate text-sm">{formatTime(trajectory.started_at)}</span>,
            },
            {
              label: "Duration",
              value: (
                <span className="truncate font-mono text-sm">
                  {formatDuration(
                    trajectory.started_at,
                    trajectory.ended_at ??
                      (String(trajectory.status).toUpperCase() === "ACTIVE"
                        ? null
                        : trajectory.last_event_at),
                    { inProgress: String(trajectory.status).toUpperCase() === "ACTIVE" },
                  )}
                </span>
              ),
            },
          ]}
        />
        {(trajectory.delegation || trajectory.delegation_id || trajectory.enforcement_mode) && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-base-200 bg-base-50 px-4 py-2 text-xs text-ink-500">
            {trajectory.delegation || trajectory.delegation_id ? (
              <span className="inline-flex min-w-0 items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                  Delegation
                </span>
                <Link
                  href={`/governance/runtime-identities/${trajectory.runtime_identity_id}`}
                  className="truncate font-mono text-accent-600 hover:text-accent-500"
                  title={
                    trajectory.delegation
                      ? `${trajectory.delegation.delegator_type}:${trajectory.delegation.delegator_id} · ${trajectory.delegation.status}`
                      : (trajectory.delegation_id ?? undefined)
                  }
                >
                  {trajectory.delegation
                    ? `${trajectory.delegation.delegator_type}:${shortId(trajectory.delegation.delegator_id)}`
                    : shortId(trajectory.delegation_id)}
                </Link>
                {trajectory.delegation?.status ? (
                  <StatusBadge status={trajectory.delegation.status} />
                ) : null}
              </span>
            ) : null}
            {trajectory.enforcement_mode ? (
              <span className="inline-flex items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                  Mode
                </span>
                <TechnicalValue>{trajectory.enforcement_mode}</TechnicalValue>
              </span>
            ) : null}
            {trajectory.deployment_control ? (
              <span className="inline-flex items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                  Control
                </span>
                <TechnicalValue>{trajectory.deployment_control}</TechnicalValue>
              </span>
            ) : null}
          </div>
        )}
      </div>

      <Tabs
        tabs={[...tabLabels]}
        active={activeTabLabel}
        onChange={(label) => {
          if (label.startsWith("Findings")) setTab("Findings");
          else setTab(label);
        }}
      />

      {tab === "Investigation" && (
        <div data-testid="trajectory-overview">
          <InvestigationWorkspace
            trajectory={trajectory}
            selectedId={selectedEventId}
            onSelect={setSelectedEventId}
          />
        </div>
      )}

      {tab === "Timeline" && (
        <div className="space-y-3" data-testid="trajectory-timeline-tab">
          {lifecycleLoading ? (
            <p className="text-sm text-ink-500">Loading lifecycle timeline…</p>
          ) : null}
          {lifecycleError ? (
            <p className="text-xs text-warn-700">
              Lifecycle projection unavailable ({lifecycleError}). Showing event timing hierarchy.
            </p>
          ) : null}
          <LifecycleTimelineView
            trajectory={trajectory}
            lifecycle={lifecycle}
            events={events}
            selectedEventId={selectedEventId}
            onSelectEvent={setSelectedEventId}
          />
        </div>
      )}

      {tab === "Evidence" && (
        <div className="space-y-4" data-testid="trajectory-raw-audit">
          <PostureStrip
            items={[
              {
                label: "Evidence Coverage",
                value:
                  trajectory.completeness_pct != null
                    ? `${Math.round(trajectory.completeness_pct)}%`
                    : events.length
                      ? `${Math.round(((events.length - evidenceStats.missing) / events.length) * 100)}%`
                      : "—",
              },
              {
                label: "Authoritative Events",
                value: evidenceStats.authoritative,
                tone: "text-accent-600",
              },
              {
                label: "Observed / Reported",
                value: evidenceStats.observed,
              },
              {
                label: "Missing Content",
                value: evidenceStats.missing,
                tone: evidenceStats.missing ? "text-warn-700" : undefined,
              },
              {
                label: "Evidence Integrity",
                value: (
                  <span className="text-sm text-accent-600">
                    {events.some((event) => event.payload_digest) ? "DIGESTS RECORDED" : "—"}
                  </span>
                ),
              },
            ]}
          />
          <div className="overflow-hidden rounded-lg border border-base-200 bg-base-50">
            <div className="flex items-center justify-between border-b border-base-200 px-4 py-2">
              <span className="text-sm font-semibold">Evidence Records</span>
              <Button
                size="sm"
                variant="secondary"
                disabled={exporting}
                onClick={() => void handleExport()}
              >
                Export Evidence Package
              </Button>
            </div>
            <Table
              columns={[
                "Event",
                "Evidence Type",
                "Source",
                "Assurance",
                "Captured",
                "Integrity",
                "Details",
              ]}
              rows={
                events.length > 0
                  ? events.map((event) => [
                      <TechnicalValue key={`${event.id}-id`}>{shortId(event.id)}</TechnicalValue>,
                      humanEventLabel(event.event_type),
                      <SourceBadge key={`${event.id}-src`} source={event.source_type} />,
                      <AssuranceBadge key={`${event.id}-asr`} level={event.assurance_level} />,
                      <span key={`${event.id}-ts`} className="font-mono">
                        {formatClock(event.occurred_at)}
                      </span>,
                      <TechnicalValue key={`${event.id}-dig`} className="text-[11px]">
                        {event.payload_digest ? `${event.payload_digest.slice(0, 23)}…` : "—"}
                      </TechnicalValue>,
                      <Button
                        key={`${event.id}-inspect`}
                        size="sm"
                        variant="ghost"
                        className="h-7"
                        onClick={() => {
                          setSelectedEventId(event.id);
                          setTab("Investigation");
                        }}
                      >
                        Inspect
                      </Button>,
                    ])
                  : [["No evidence events", "—", "—", "—", "—", "—", "—"]]
              }
            />
          </div>
        </div>
      )}

      {tab === "Findings" && (
        <div className="space-y-4" data-testid="trajectory-risk-findings">
          {riskError ? <p className="text-sm text-danger-600">{riskError}</p> : null}
          {riskLoading && !riskFindings ? (
            <p className="text-sm text-ink-500">Loading risk and findings...</p>
          ) : null}
          {!riskLoading || riskFindings || findings.trajectoryFindings.length > 0 ? (
            <>
              {riskLoading && riskFindings ? (
                <p className="text-xs text-ink-400">Refreshing risk findings…</p>
              ) : null}
              <PostureStrip
                items={[
                  {
                    label: "Critical",
                    value: [
                      ...findings.evidence,
                      ...findings.risk,
                      ...findings.trajectoryFindings,
                    ].filter((f) => String(f.severity).toUpperCase() === "CRITICAL").length,
                    tone: "text-danger-600",
                  },
                  {
                    label: "High",
                    value: [
                      ...findings.evidence,
                      ...findings.risk,
                      ...findings.trajectoryFindings,
                    ].filter((f) => String(f.severity).toUpperCase() === "HIGH").length,
                    tone: "text-danger-500",
                  },
                  {
                    label: "Medium",
                    value: [
                      ...findings.evidence,
                      ...findings.risk,
                      ...findings.trajectoryFindings,
                    ].filter((f) => String(f.severity).toUpperCase() === "MEDIUM").length,
                    tone: "text-warn-700",
                  },
                  {
                    label: "Low / Info",
                    value: [
                      ...findings.evidence,
                      ...findings.risk,
                      ...findings.trajectoryFindings,
                    ].filter((f) => {
                      const severity = String(f.severity).toUpperCase();
                      return severity === "LOW" || severity === "INFO";
                    }).length,
                  },
                ]}
              />
              <div className="overflow-hidden rounded-lg border border-base-200 bg-base-50">
                {findingCount === 0 ? (
                  <div className="flex min-h-48 flex-col items-center justify-center px-6 text-center">
                    <h3 className="text-sm font-semibold text-ink-900">
                      No governance or runtime findings were recorded for this trajectory.
                    </h3>
                    <p className="mt-1 max-w-md text-xs text-ink-500">
                      All authorization decisions in this trajectory were within delegated
                      authority.
                    </p>
                  </div>
                ) : (
                  <ul className="divide-y divide-base-200">
                    {[...findings.evidence, ...findings.risk, ...findings.trajectoryFindings].map(
                      (finding) => {
                        const expanded = selectedFindingId === finding.id;
                        return (
                          <li key={finding.id} className="p-4">
                            <button
                              type="button"
                              className="w-full text-left"
                              onClick={() => setSelectedFindingId(expanded ? null : finding.id)}
                              aria-expanded={expanded}
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <StatusBadge status={finding.severity} />
                                <span className="text-[11px] font-semibold uppercase text-ink-400">
                                  {"finding_type" in finding
                                    ? String(finding.finding_type)
                                    : "Finding"}
                                </span>
                                <TechnicalValue>{finding.id}</TechnicalValue>
                                {"status" in finding && finding.status ? (
                                  <StatusBadge status={String(finding.status)} />
                                ) : null}
                                <span className="ml-auto text-[10px] font-semibold uppercase text-ink-400">
                                  {expanded ? "Hide" : "Details"}
                                </span>
                              </div>
                              <h3 className="mt-2 text-sm font-semibold text-ink-900">
                                {finding.title}
                              </h3>
                              {"description" in finding && finding.description ? (
                                <p className="mt-1 text-xs text-ink-600">{finding.description}</p>
                              ) : null}
                            </button>
                            {expanded ? (
                              <div className="mt-3 space-y-2 rounded-md border border-base-200 bg-base-50 p-3 text-xs text-ink-600">
                                {"trajectory_id" in finding && finding.trajectory_id ? (
                                  <div>
                                    Trajectory:{" "}
                                    <Link
                                      href={`/runtime/trajectories/${finding.trajectory_id}`}
                                      className="font-mono text-accent-600 underline"
                                    >
                                      {String(finding.trajectory_id).slice(0, 8)}…
                                    </Link>
                                  </div>
                                ) : null}
                                {"explanation" in finding && finding.explanation ? (
                                  <pre className="overflow-x-auto font-mono text-[10px] text-ink-500">
                                    {JSON.stringify(finding.explanation, null, 2)}
                                  </pre>
                                ) : null}
                                {"source_event_ids" in finding &&
                                Array.isArray(finding.source_event_ids) &&
                                finding.source_event_ids.length > 0 ? (
                                  <div>
                                    Source events:{" "}
                                    {finding.source_event_ids.map((id) => (
                                      <span key={String(id)} className="mr-2 font-mono">
                                        {String(id).slice(0, 8)}…
                                      </span>
                                    ))}
                                  </div>
                                ) : null}
                                <pre className="overflow-x-auto font-mono text-[10px] text-ink-500">
                                  {JSON.stringify(finding, null, 2)}
                                </pre>
                              </div>
                            ) : null}
                          </li>
                        );
                      },
                    )}
                  </ul>
                )}
              </div>

              {(riskFindings?.risk?.interventions?.length ?? 0) > 0 ? (
                <Panel title="Interventions">
                  <ul className="space-y-2 text-sm">
                    {riskFindings!.risk!.interventions.map((intervention) => (
                      <li key={intervention.id} className="flex flex-wrap items-center gap-2">
                        <StatusBadge status={intervention.effect} />
                        <span>{intervention.status}</span>
                        <span className="text-ink-500">{intervention.reason}</span>
                      </li>
                    ))}
                  </ul>
                </Panel>
              ) : null}
            </>
          ) : null}
        </div>
      )}

      {tab === "Flow" && (
        <div className="space-y-3" data-testid="trajectory-flow-tab">
          {graphLoading ? <p className="text-sm text-ink-500">Building flow hierarchy…</p> : null}
          {graphError ? (
            <p className="text-xs text-warn-700">
              Flow edges unavailable ({graphError}). Showing event sequence hierarchy.
            </p>
          ) : null}
          <FlowHierarchyView
            trajectory={trajectory}
            graph={graph}
            selectedId={selectedEventId}
            onSelect={(eventId) => {
              setSelectedEventId(eventId);
            }}
          />
        </div>
      )}
    </div>
  );
}
