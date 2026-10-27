"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table } from "@/components/ui/table";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { getAgents, getAISystems, getConversations, searchRuntimeAudit } from "@/lib/api";
import type { AgentSummary, AISystemSummary, AuditRecord } from "@/lib/types";

const ENTITY_OPTIONS = [
  { value: "ENFORCEMENT,EXECUTION,EVIDENCE_EVENT", label: "All" },
  { value: "ENFORCEMENT", label: "Enforcement" },
  { value: "EXECUTION", label: "Executions" },
  { value: "EVIDENCE_EVENT", label: "Evidence Events" },
];

const RECORD_KIND_OPTIONS = [
  { value: "", label: "Any observation" },
  { value: "INPUT", label: "Input" },
  { value: "OUTPUT", label: "Output" },
  { value: "MODEL_REQUEST", label: "Model Request" },
  { value: "MODEL_RESPONSE", label: "Model Response" },
];

function toLocalInputValue(date: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

function defaultWindow() {
  const end = new Date();
  const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
  return { from: toLocalInputValue(start), to: toLocalInputValue(end) };
}

function formatTime(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function shortId(value?: string | null) {
  if (!value) return "—";
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

/** Enforcement outcome shown in the Action column. DENY is presented as Block. */
function outcomeStatus(row: AuditRecord): string | null {
  const raw = (row.decision || "").trim().toUpperCase();
  if (!raw) return null;
  if (raw === "ALLOW" || raw === "ALLOWED") return "ALLOW";
  if (raw === "DENY" || raw === "DENIED" || raw === "BLOCK" || raw === "BLOCKED") {
    return "BLOCK";
  }
  if (raw === "REQUIRE_APPROVAL" || raw === "APPROVAL_REQUIRED") return "REQUIRE_APPROVAL";
  return raw;
}

function trajectoryHref(row: AuditRecord) {
  if (row.trajectory_id) {
    const event = row.detail_reference?.includes("event=")
      ? row.detail_reference.split("event=")[1]
      : null;
    const focus = event ? `?event=${encodeURIComponent(event)}` : "";
    return `/runtime/trajectories/${row.trajectory_id}${focus}`;
  }
  return row.detail_reference ?? "#";
}

function AuditExplorerInner() {
  const searchParams = useSearchParams();
  const initialType = searchParams.get("type");
  const mappedType =
    initialType === "execution"
      ? "EXECUTION"
      : initialType === "evidence" || initialType === "evidence_event"
        ? "EVIDENCE_EVENT"
        : initialType === "all"
          ? "ENFORCEMENT,EXECUTION,EVIDENCE_EVENT"
          : "ENFORCEMENT";

  const defaults = useMemo(() => defaultWindow(), []);
  const [dateFrom, setDateFrom] = useState(defaults.from);
  const [dateTo, setDateTo] = useState(defaults.to);
  const [entityTypes, setEntityTypes] = useState(mappedType);
  const [recordKind, setRecordKind] = useState("");
  const [decision, setDecision] = useState("");
  const [executionStatus, setExecutionStatus] = useState("");
  const [assurance, setAssurance] = useState("");
  const [aiSystemId, setAiSystemId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [principal, setPrincipal] = useState("");
  const [channel, setChannel] = useState("");
  const [correlationId, setCorrelationId] = useState("");
  const [conversationId, setConversationId] = useState("");
  const [trajectoryId, setTrajectoryId] = useState("");
  const [contentSearch, setContentSearch] = useState("");
  const [items, setItems] = useState<AuditRecord[]>([]);
  const [searched, setSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [systems, setSystems] = useState<AISystemSummary[]>([]);
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [principals, setPrincipals] = useState<string[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);

  useEffect(() => {
    void getAISystems()
      .then((res) => setSystems(res.data ?? []))
      .catch(() => setSystems([]));
    void getConversations({ limit: 100 })
      .then((res) => {
        const values = [
          ...new Set(
            (res.data.items ?? [])
              .map((row) => row.principal_reference?.trim())
              .filter((value): value is string => Boolean(value)),
          ),
        ].sort((a, b) => a.localeCompare(b));
        setPrincipals(values);
      })
      .catch(() => setPrincipals([]));
  }, []);

  useEffect(() => {
    setAgentId("");
    if (!aiSystemId) {
      setAgents([]);
      return;
    }
    void getAgents(aiSystemId)
      .then((res) => setAgents(res.data ?? []))
      .catch(() => setAgents([]));
  }, [aiSystemId]);

  const runSearch = useCallback(
    async (cursor?: string | null, append = false) => {
      setLoading(true);
      setError(null);
      try {
        const res = await searchRuntimeAudit({
          date_from: new Date(dateFrom).toISOString(),
          date_to: new Date(dateTo).toISOString(),
          entity_types: recordKind ? "EVIDENCE_EVENT" : entityTypes,
          record_kind: recordKind || undefined,
          decision: decision || undefined,
          execution_status: executionStatus || undefined,
          assurance: assurance || undefined,
          ai_system_id: aiSystemId.trim() || undefined,
          agent_id: agentId.trim() || undefined,
          principal: principal.trim() || undefined,
          channel: channel.trim() || undefined,
          correlation_id: correlationId.trim() || undefined,
          conversation_id: conversationId.trim() || undefined,
          trajectory_id: trajectoryId.trim() || undefined,
          content_search: contentSearch.trim() || undefined,
          cursor: cursor || undefined,
          limit: 50,
        });
        const rows = res.data.items ?? [];
        setItems((prev) => (append ? [...prev, ...rows] : rows));
        setNextCursor(res.data.next_cursor ?? null);
        setHasMore(Boolean(res.data.has_more));
        setSearched(true);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Search failed");
      } finally {
        setLoading(false);
      }
    },
    [
      dateFrom,
      dateTo,
      entityTypes,
      recordKind,
      decision,
      executionStatus,
      assurance,
      aiSystemId,
      agentId,
      principal,
      channel,
      correlationId,
      conversationId,
      trajectoryId,
      contentSearch,
    ],
  );

  useEffect(() => {
    void runSearch(null, false);
    // Load the default Enforcement window once. Later searches stay on the button.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-6" data-testid="audit-explorer-page">
      <SectionHeader
        title="Audit Explorer"
        subtitle="Forensic search over enforcement, executions, and observed input/output — results open Conversation / Trajectory context"
      />

      <Panel
        title="Filters"
        actions={
          <Button
            variant="secondary"
            aria-expanded={filtersOpen}
            data-testid="audit-filters-toggle"
            onClick={() => setFiltersOpen((open) => !open)}
          >
            {filtersOpen ? "Hide filters" : "Show filters"}
          </Button>
        }
      >
        {filtersOpen && (
          <>
            <p className="mb-3 text-sm text-muted-foreground">
              Date range is required. The page loads Enforcement records for the last 24 hours.
              Content search requires <code className="text-xs">evidence:content:read</code> and
              never dumps raw content in the result table.
            </p>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">From *</span>
                <Input
                  type="datetime-local"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">To *</span>
                <Input
                  type="datetime-local"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Record type</span>
                <Select
                  value={entityTypes}
                  onChange={(e) => setEntityTypes(e.target.value)}
                  disabled={Boolean(recordKind)}
                >
                  {ENTITY_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Observation kind</span>
                <Select value={recordKind} onChange={(e) => setRecordKind(e.target.value)}>
                  {RECORD_KIND_OPTIONS.map((opt) => (
                    <option key={opt.value || "any"} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">AI System</span>
                <Select value={aiSystemId} onChange={(e) => setAiSystemId(e.target.value)}>
                  <option value="">Any system</option>
                  {systems.map((system) => (
                    <option key={system.id} value={system.id}>
                      {system.name}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Agent</span>
                <Select
                  value={agentId}
                  onChange={(e) => setAgentId(e.target.value)}
                  disabled={!aiSystemId}
                >
                  <option value="">Any agent</option>
                  {agents.map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.name}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Principal</span>
                <Select value={principal} onChange={(e) => setPrincipal(e.target.value)}>
                  <option value="">Any principal</option>
                  {principals.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Channel</span>
                <Input
                  value={channel}
                  onChange={(e) => setChannel(e.target.value)}
                  placeholder="WhatsApp"
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Decision</span>
                <Select value={decision} onChange={(e) => setDecision(e.target.value)}>
                  <option value="">Any</option>
                  <option value="ALLOW">Allow</option>
                  <option value="DENY">Block</option>
                  <option value="REQUIRE_APPROVAL">Require approval</option>
                  <option value="MONITOR">MONITOR</option>
                </Select>
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Execution status</span>
                <Select
                  value={executionStatus}
                  onChange={(e) => setExecutionStatus(e.target.value)}
                >
                  <option value="">Any</option>
                  <option value="SUCCEEDED">SUCCEEDED</option>
                  <option value="FAILED">FAILED</option>
                  <option value="STARTED">STARTED</option>
                  <option value="NOT_ATTEMPTED">NOT_ATTEMPTED</option>
                </Select>
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Assurance</span>
                <Select value={assurance} onChange={(e) => setAssurance(e.target.value)}>
                  <option value="">Any</option>
                  <option value="HIGH">HIGH</option>
                  <option value="MEDIUM">MEDIUM</option>
                  <option value="LOW">LOW</option>
                </Select>
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Correlation ID</span>
                <Input
                  value={correlationId}
                  onChange={(e) => setCorrelationId(e.target.value)}
                  placeholder="corr-…"
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Conversation ID</span>
                <Input
                  value={conversationId}
                  onChange={(e) => setConversationId(e.target.value)}
                  placeholder="external conversation id"
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Trajectory ID</span>
                <Input
                  value={trajectoryId}
                  onChange={(e) => setTrajectoryId(e.target.value)}
                  placeholder="uuid"
                />
              </label>
              <label className="space-y-1 text-sm md:col-span-2 lg:col-span-3">
                <span className="text-muted-foreground">Content search</span>
                <Input
                  value={contentSearch}
                  onChange={(e) => setContentSearch(e.target.value)}
                  placeholder="Search stored input/output text (permission-gated)"
                  data-testid="audit-content-search"
                />
              </label>
            </div>
            <div className="mt-4">
              <Button onClick={() => void runSearch(null, false)} disabled={loading}>
                {loading ? "Searching…" : "Search"}
              </Button>
            </div>
          </>
        )}
      </Panel>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {!searched ? (
        <Panel>
          <p className="text-sm text-muted-foreground" data-testid="audit-empty-prompt">
            {loading ? "Loading enforcement records…" : "No records loaded."}
          </p>
        </Panel>
      ) : (
        <Panel title={`Results (${items.length}${hasMore ? "+" : ""})`}>
          <Table
            columns={[
              "Time",
              "Type",
              "Action",
              "Tool",
              "AI System",
              "Agent",
              "Conversation",
              "Assurance",
              "Detail",
            ]}
            rows={items.map((row) => [
              formatTime(row.occurred_at),
              <StatusBadge key={`t-${row.id}`} status={row.record_type} />,
              outcomeStatus(row) ? (
                <StatusBadge key={`a-${row.id}`} status={outcomeStatus(row)} />
              ) : (
                "—"
              ),
              row.action ?? "—",
              row.ai_system_name ?? shortId(row.ai_system_id),
              row.agent_name ?? shortId(row.agent_id),
              row.conversation_id ? (
                <span key={`c-${row.id}`} title={row.conversation_id}>
                  {shortId(row.conversation_id)}
                </span>
              ) : (
                "—"
              ),
              row.assurance ?? "—",
              <Link
                key={`d-${row.id}`}
                href={trajectoryHref(row)}
                className="text-primary hover:underline"
              >
                Open
              </Link>,
            ])}
          />
          {items.length === 0 && (
            <p className="mt-3 text-sm text-muted-foreground">No records matched.</p>
          )}
          {hasMore && (
            <div className="mt-4">
              <Button
                variant="secondary"
                disabled={loading}
                onClick={() => void runSearch(nextCursor, true)}
              >
                Load more
              </Button>
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}

export default function AuditExplorerPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Loading…</p>}>
      <AuditExplorerInner />
    </Suspense>
  );
}
