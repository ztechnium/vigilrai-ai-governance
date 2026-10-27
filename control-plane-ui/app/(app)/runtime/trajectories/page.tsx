"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AgentNameCell } from "@/components/agent-avatar";
import { FilterToolbar, MetricStrip, PaginationBar } from "@/components/console/page-parts";
import { KpiCard } from "@/components/kpi-card";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Table } from "@/components/ui/table";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { getTrajectories } from "@/lib/api";
import { formatCost, formatTokens, sourceLabel } from "@/lib/finops-format";
import type { TrajectorySummary } from "@/lib/types";

const STATUS_OPTIONS = ["", "ACTIVE", "COMPLETED", "INCOMPLETE", "FAILED"];
const PAGE_SIZE = 10;

function formatTime(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function shortId(value?: string | null) {
  if (!value) return "—";
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

function formatDuration(started?: string | null, ended?: string | null) {
  if (!started || !ended) return "—";
  const ms = new Date(ended).getTime() - new Date(started).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms / 60_000)}m`;
}

export default function TrajectoriesPage() {
  const router = useRouter();
  const [items, setItems] = useState<TrajectorySummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);

  const load = useCallback(
    async (pageIndex: number) => {
      setLoading(true);
      setError(null);
      try {
        const res = await getTrajectories({
          status: statusFilter || undefined,
          limit: PAGE_SIZE,
          offset: pageIndex * PAGE_SIZE,
        });
        setItems(res.data.items ?? []);
        setTotal(res.data.total ?? res.data.items?.length ?? 0);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load trajectories");
      } finally {
        setLoading(false);
      }
    },
    [statusFilter],
  );

  useEffect(() => {
    void load(page);
  }, [load, page]);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.toLowerCase();
    return items.filter(
      (t) =>
        t.ai_system_name?.toLowerCase().includes(q) ||
        t.agent_name?.toLowerCase().includes(q) ||
        t.runtime_identity_name?.toLowerCase().includes(q) ||
        t.conversation_id?.toLowerCase().includes(q) ||
        t.client_session_id?.toLowerCase().includes(q) ||
        t.correlation_id?.toLowerCase().includes(q) ||
        t.client_type?.toLowerCase().includes(q) ||
        t.id.toLowerCase().includes(q),
    );
  }, [items, search]);

  const stats = useMemo(
    () => ({
      total,
      active: filtered.filter((t) => t.status === "ACTIVE").length,
      incomplete: filtered.filter((t) => t.status === "INCOMPLETE").length,
      withFindings: filtered.filter((t) => (t.finding_count ?? 0) > 0).length,
    }),
    [filtered, total],
  );

  return (
    <div className="space-y-6" data-testid="trajectories-page">
      <SectionHeader
        eyebrow="Runtime"
        title="Trajectories"
        subtitle="Correlated runtime evidence across prompts, tools, policy, approval, and execution"
        actions={
          <Button variant="outline" onClick={() => void load(page)}>
            Refresh
          </Button>
        }
      />

      <MetricStrip>
        <KpiCard title="Total" value={String(stats.total)} />
        <KpiCard title="Active (page)" value={String(stats.active)} />
        <KpiCard title="Incomplete (page)" value={String(stats.incomplete)} tone="warn" />
        <KpiCard title="With Findings (page)" value={String(stats.withFindings)} tone="danger" />
      </MetricStrip>

      <Panel title="Recent Trajectories">
        <FilterToolbar
          value={search}
          onChange={(value) => {
            setSearch(value);
          }}
          placeholder="Search system, agent, session, correlation..."
          filters={[
            {
              label: "Status",
              value: statusFilter,
              onChange: (value) => {
                setStatusFilter(value);
                setPage(0);
              },
              options: STATUS_OPTIONS.filter(Boolean).map((opt) => ({ value: opt, label: opt })),
            },
          ]}
          action={
            <Button
              variant="secondary"
              onClick={() => {
                setPage(0);
                void load(0);
              }}
            >
              Apply
            </Button>
          }
        />
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading trajectories...</p>
        ) : error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-muted-foreground">No trajectories yet.</p>
        ) : (
          <Table
            columns={[
              "Started",
              "AI System",
              "Agent",
              "Version",
              "Runtime Identity",
              "Client",
              "Session",
              "Events",
              "Findings",
              "Completeness",
              "Status",
              "Duration",
              "Tokens",
              "Cost",
            ]}
            rows={filtered.map((t) => [
              formatTime(t.started_at),
              <Link
                key={`${t.id}-sys`}
                href={`/governance/registry/${t.ai_system_id}`}
                className="text-primary hover:underline"
                onClick={(e) => e.stopPropagation()}
              >
                {t.ai_system_name ?? shortId(t.ai_system_id)}
              </Link>,
              <AgentNameCell
                key={`${t.id}-agent`}
                name={t.agent_name}
                avatar={t.agent_avatar}
                fallback={shortId(t.agent_id)}
                size={32}
              />,
              <span key={`${t.id}-ver`} className="font-mono text-xs">
                {t.agent_version_number != null
                  ? `v${t.agent_version_number}`
                  : shortId(t.agent_version_id)}
              </span>,
              <Link
                key={`${t.id}-ri`}
                href={`/governance/runtime-identities/${t.runtime_identity_id}`}
                className="text-primary hover:underline"
                onClick={(e) => e.stopPropagation()}
              >
                {t.runtime_identity_name ?? shortId(t.runtime_identity_id)}
              </Link>,
              t.client_type ?? "—",
              <span key={`${t.id}-sess`} className="font-mono text-xs">
                {t.conversation_id ??
                  t.client_session_id ??
                  (t.session_key?.startsWith("corr:")
                    ? `corr:${shortId(t.correlation_id)}`
                    : shortId(t.session_key))}
              </span>,
              String(t.event_count ?? 0),
              String(t.finding_count ?? 0),
              t.completeness_pct != null ? `${t.completeness_pct}%` : "—",
              <StatusBadge key={`${t.id}-status`} status={t.status} />,
              formatDuration(t.started_at, t.ended_at ?? t.last_event_at),
              formatTokens(t.economics?.total_tokens),
              <span key={`${t.id}-cost`} title={sourceLabel(t.economics?.metering_source)}>
                {formatCost(
                  t.economics?.total_cost,
                  t.economics?.cost_state,
                  t.economics?.currency,
                )}
              </span>,
            ])}
            rowTestIds={filtered.map((t) => `trajectory-row-${t.id}`)}
            onRowClick={(idx) => {
              const row = filtered[idx];
              if (row) router.push(`/runtime/trajectories/${row.id}`);
            }}
          />
        )}
        <PaginationBar
          total={search.trim() ? filtered.length : total}
          page={page}
          pageSize={PAGE_SIZE}
          onPage={setPage}
        />
      </Panel>
    </div>
  );
}
