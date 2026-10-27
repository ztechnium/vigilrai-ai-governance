"use client";

import { useMemo, useState } from "react";
import { TechnicalValue } from "@/components/console/page-parts";
import { humanEventLabel } from "@/lib/evidence-content";
import { cn } from "@/lib/utils";
import type {
  EvidenceEvent,
  LifecycleStage,
  TrajectoryDetail,
  TrajectoryLifecycle,
} from "@/lib/types";

type SpanKind = "root" | "stage" | "phase" | "event";

type TimelineSpan = {
  id: string;
  kind: SpanKind;
  depth: number;
  name: string;
  subtitle?: string;
  status?: string;
  startMs: number;
  durationMs: number;
  eventId?: string;
  cost?: number | null;
  expandable?: boolean;
  children?: TimelineSpan[];
};

const ROW_H = 36;
const LABEL_W = 360;

function stageLabel(value: unknown, fallback = "Stage"): string {
  if (typeof value === "string" && value.trim()) return value;
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["tool_key", "tool_name", "name", "action", "label"]) {
      const candidate = record[key];
      if (typeof candidate === "string" && candidate.trim()) return candidate;
    }
  }
  return fallback;
}

function formatDurationMs(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  if (ms < 1) return "0ms";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)}s`;
  const totalSec = Math.round(ms / 1000);
  const minutes = Math.floor(totalSec / 60);
  const seconds = totalSec % 60;
  return `${minutes}m ${seconds}s`;
}

function formatAxisTick(ms: number): string {
  if (ms <= 0) return "0ms";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) {
    const s = ms / 1000;
    return Number.isInteger(s) ? `${s}s` : `${s.toFixed(2)}s`;
  }
  return formatDurationMs(ms);
}

function toEpoch(value?: string | null): number | null {
  if (!value) return null;
  const t = new Date(value).getTime();
  return Number.isNaN(t) ? null : t;
}

function eventDurationMs(event: EvidenceEvent): number {
  const payload = event.payload ?? {};
  for (const key of ["latency_ms", "duration_ms", "elapsed_ms"]) {
    const raw = payload[key];
    if (typeof raw === "number" && Number.isFinite(raw) && raw >= 0) return raw;
    if (typeof raw === "string" && raw.trim()) {
      const n = Number(raw);
      if (Number.isFinite(n) && n >= 0) return n;
    }
  }
  return 0;
}

function eventCost(event: EvidenceEvent): number | null {
  const payload = event.payload ?? {};
  for (const key of ["cost", "estimated_cost", "total_cost", "cost_usd"]) {
    const raw = payload[key];
    if (typeof raw === "number" && Number.isFinite(raw)) return raw;
    if (typeof raw === "string" && raw.trim()) {
      const n = Number(raw);
      if (Number.isFinite(n)) return n;
    }
  }
  return null;
}

function eventDisplayName(event: EvidenceEvent): string {
  const payload = event.payload ?? {};
  const tool =
    (typeof payload.tool_name === "string" && payload.tool_name) ||
    (typeof payload.tool === "string" && payload.tool) ||
    (typeof payload.tool_key === "string" && payload.tool_key);
  const model =
    (typeof payload.model === "string" && payload.model) ||
    (typeof payload.observed_model === "string" && payload.observed_model);
  const upper = event.event_type.toUpperCase();
  if (tool && (upper.includes("TOOL") || upper.includes("ACTION") || upper.includes("EXECUTION"))) {
    return `tool.${tool}`;
  }
  if (model && (upper.includes("MODEL") || upper.includes("LLM") || upper.includes("CHAT"))) {
    return `llm.${model}`;
  }
  return humanEventLabel(event.event_type);
}

function eventSubtitle(event: EvidenceEvent): string {
  const payload = event.payload ?? {};
  for (const key of ["summary", "decision", "enforcement_decision", "policy_decision"]) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return event.source_type.replace(/_/g, " ").toLowerCase();
}

function kindIcon(kind: SpanKind, name: string): string {
  const lower = name.toLowerCase();
  if (kind === "root") return "◆";
  if (kind === "stage") {
    if (lower.includes("input") || lower.includes("prompt")) return "◎";
    if (lower.includes("model")) return "✧";
    if (lower.includes("output") || lower.includes("complete")) return "✓";
    return "▸";
  }
  if (kind === "phase") return "◦";
  if (lower.includes("llm") || lower.includes("model") || lower.includes("chat")) return "✧";
  if (lower.includes("tool") || lower.includes("action")) return "⊚";
  return "•";
}

function barTone(kind: SpanKind, name: string): string {
  if (kind === "root" || kind === "stage") {
    return "bg-violet-400/70";
  }
  if (kind === "phase") {
    return "bg-violet-300/45";
  }
  const lower = name.toLowerCase();
  if (lower.includes("deny") || lower.includes("block") || lower.includes("fail")) {
    return "bg-rose-400/80";
  }
  if (lower.includes("approval") || lower.includes("human")) {
    return "bg-fuchsia-400/70";
  }
  if (lower.includes("policy") || lower.includes("authority")) {
    return "bg-amber-400/70";
  }
  return "bg-sky-400/80";
}

function flattenVisible(spans: TimelineSpan[], collapsed: Set<string>): TimelineSpan[] {
  const rows: TimelineSpan[] = [];
  const walk = (nodes: TimelineSpan[]) => {
    for (const node of nodes) {
      rows.push(node);
      if (node.children?.length && !collapsed.has(node.id)) {
        walk(node.children);
      }
    }
  };
  walk(spans);
  return rows;
}

function filterTree(spans: TimelineSpan[], query: string): TimelineSpan[] {
  const q = query.trim().toLowerCase();
  if (!q) return spans;

  const match = (span: TimelineSpan): TimelineSpan | null => {
    const selfHit =
      span.name.toLowerCase().includes(q) ||
      (span.subtitle?.toLowerCase().includes(q) ?? false) ||
      (span.status?.toLowerCase().includes(q) ?? false);
    const kids = (span.children ?? [])
      .map(match)
      .filter((child): child is TimelineSpan => Boolean(child));
    if (selfHit || kids.length) {
      return { ...span, children: kids.length ? kids : span.children };
    }
    return null;
  };

  return spans.map(match).filter((span): span is TimelineSpan => Boolean(span));
}

function buildActionPhases(
  stage: LifecycleStage,
  stageStart: number,
  stageDuration: number,
  depth: number,
): TimelineSpan[] {
  const phases: Array<{ key: string; label: string; status?: string; duration?: number | null }> =
    [];
  if (stage.authority?.status) {
    phases.push({ key: "authority", label: "authority.check", status: stage.authority.status });
  }
  if (stage.policy?.status) {
    phases.push({
      key: "policy",
      label: "policy.evaluate",
      status: stage.policy.decision ?? stage.policy.status,
    });
  }
  if (stage.approval?.required || stage.approval?.status) {
    phases.push({
      key: "approval",
      label: "approval.gate",
      status: stage.approval.status ?? (stage.approval.required ? "REQUIRED" : "NOT_REQUIRED"),
    });
  }
  if (stage.enforcement?.status || stage.enforcement?.decision) {
    phases.push({
      key: "enforcement",
      label: "enforcement.apply",
      status: stage.enforcement.decision ?? stage.enforcement.status,
    });
  }
  if (stage.execution?.status) {
    phases.push({
      key: "execution",
      label: "tool.execution",
      status: stage.execution.status,
      duration: stage.execution.duration_ms,
    });
  }

  if (!phases.length) return [];

  const slice = stageDuration / phases.length;
  return phases.map((phase, index) => {
    const duration = Math.max(phase.duration ?? slice, 0);
    const start =
      phase.duration != null && phase.key === "execution"
        ? stageStart + Math.max(stageDuration - duration, 0)
        : stageStart + index * slice;
    return {
      id: `${stage.id}:${phase.key}`,
      kind: "phase" as const,
      depth,
      name: phase.label,
      subtitle: phase.status,
      status: phase.status,
      startMs: start,
      durationMs: duration,
      expandable: false,
    };
  });
}

function buildSpans(
  trajectory: TrajectoryDetail,
  lifecycle: TrajectoryLifecycle | null,
  events: EvidenceEvent[],
): { spans: TimelineSpan[]; totalMs: number } {
  const eventById = new Map(events.map((event) => [event.id, event]));
  const sortedEvents = [...events].sort((a, b) => {
    const ta = toEpoch(a.occurred_at) ?? 0;
    const tb = toEpoch(b.occurred_at) ?? 0;
    if (ta !== tb) return ta - tb;
    return a.sequence_number - b.sequence_number;
  });

  const startEpoch =
    toEpoch(lifecycle?.summary.started_at) ??
    toEpoch(trajectory.started_at) ??
    toEpoch(sortedEvents[0]?.occurred_at) ??
    Date.now();

  const endEpoch =
    toEpoch(lifecycle?.summary.completed_at) ??
    toEpoch(trajectory.ended_at) ??
    toEpoch(trajectory.last_event_at) ??
    toEpoch(sortedEvents[sortedEvents.length - 1]?.occurred_at) ??
    startEpoch;

  let totalMs = lifecycle?.summary.duration_ms ?? Math.max(endEpoch - startEpoch, 0);

  if (totalMs <= 0 && sortedEvents.length) {
    totalMs = Math.max(
      ...sortedEvents.map((event) => {
        const offset = Math.max((toEpoch(event.occurred_at) ?? startEpoch) - startEpoch, 0);
        return offset + Math.max(eventDurationMs(event), 1);
      }),
      1,
    );
  }
  if (totalMs <= 0) totalMs = 1;

  const relative = (iso?: string | null) =>
    Math.max(0, Math.min(totalMs, (toEpoch(iso) ?? startEpoch) - startEpoch));

  const assigned = new Set<string>();
  const stages = lifecycle?.stages ?? [];

  const stageSpans: TimelineSpan[] = stages.map((stage, index) => {
    const stageEvents = (stage.event_ids ?? [])
      .map((id) => eventById.get(id))
      .filter((event): event is EvidenceEvent => Boolean(event));
    stageEvents.forEach((event) => assigned.add(event.id));

    const next = stages[index + 1];
    const stageStart = relative(stage.occurred_at);
    const inferredEnd = next?.occurred_at
      ? relative(next.occurred_at)
      : Math.max(
          stageStart + (stage.execution?.duration_ms ?? 0),
          ...stageEvents.map((event) => relative(event.occurred_at) + eventDurationMs(event)),
          stageStart + 1,
        );
    const stageDuration = Math.max(stage.execution?.duration_ms ?? 0, inferredEnd - stageStart, 1);

    const children: TimelineSpan[] = [];
    if (stage.type === "ACTION") {
      children.push(...buildActionPhases(stage, stageStart, stageDuration, 2));
    }

    for (const event of stageEvents) {
      const startMs = relative(event.occurred_at);
      const durationMs = Math.max(eventDurationMs(event), 0);
      children.push({
        id: `event:${event.id}`,
        kind: "event",
        depth: 2,
        name: eventDisplayName(event),
        subtitle: eventSubtitle(event),
        status: event.assurance_level,
        startMs,
        durationMs,
        eventId: event.id,
        cost: eventCost(event),
      });
    }

    return {
      id: `stage:${stage.id}`,
      kind: "stage" as const,
      depth: 1,
      name:
        stage.type === "ACTION"
          ? `action.${stageLabel(stage.label, "tool")}`
          : `${stage.type.toLowerCase()}.${stageLabel(stage.label, stage.type.toLowerCase())}`,
      subtitle: stage.status,
      status: stage.status,
      startMs: stageStart,
      durationMs: stageDuration,
      eventId: stage.event_ids?.[0],
      expandable: children.length > 0,
      children,
    };
  });

  const orphanEvents = sortedEvents.filter((event) => !assigned.has(event.id));
  if (orphanEvents.length && !stageSpans.length) {
    for (const event of orphanEvents) {
      stageSpans.push({
        id: `event:${event.id}`,
        kind: "event",
        depth: 1,
        name: eventDisplayName(event),
        subtitle: eventSubtitle(event),
        status: event.assurance_level,
        startMs: relative(event.occurred_at),
        durationMs: Math.max(eventDurationMs(event), 0),
        eventId: event.id,
        cost: eventCost(event),
      });
    }
  } else if (orphanEvents.length) {
    const lastOrphan = orphanEvents[orphanEvents.length - 1] ?? orphanEvents[0];
    stageSpans.push({
      id: "stage:other-events",
      kind: "stage",
      depth: 1,
      name: "other.events",
      subtitle: `${orphanEvents.length} events`,
      startMs: relative(orphanEvents[0]?.occurred_at),
      durationMs: Math.max(
        relative(lastOrphan?.occurred_at) -
          relative(orphanEvents[0]?.occurred_at) +
          (lastOrphan ? eventDurationMs(lastOrphan) : 0),
        1,
      ),
      expandable: true,
      children: orphanEvents.map((event) => ({
        id: `event:${event.id}`,
        kind: "event" as const,
        depth: 2,
        name: eventDisplayName(event),
        subtitle: eventSubtitle(event),
        status: event.assurance_level,
        startMs: relative(event.occurred_at),
        durationMs: Math.max(eventDurationMs(event), 0),
        eventId: event.id,
        cost: eventCost(event),
      })),
    });
  }

  const rootName = trajectory.agent_name
    ? `agent.${trajectory.agent_name.replace(/\s+/g, "_").toLowerCase()}`
    : "trajectory.run";

  const root: TimelineSpan = {
    id: "root",
    kind: "root",
    depth: 0,
    name: rootName,
    subtitle: trajectory.runtime_identity_name ?? trajectory.ai_system_name ?? undefined,
    status: trajectory.status,
    startMs: 0,
    durationMs: totalMs,
    expandable: stageSpans.length > 0,
    children: stageSpans,
  };

  return { spans: [root], totalMs };
}

function CostPill({ cost }: { cost: number }) {
  return (
    <span className="rounded-full bg-emerald-500/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-emerald-300">
      ${cost < 0.01 ? cost.toFixed(5) : cost.toFixed(4)}
    </span>
  );
}

export function LifecycleTimelineView({
  trajectory,
  lifecycle,
  events,
  selectedEventId,
  onSelectEvent,
}: {
  trajectory: TrajectoryDetail;
  lifecycle: TrajectoryLifecycle | null;
  events: EvidenceEvent[];
  selectedEventId?: string;
  onSelectEvent?: (eventId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());

  const { spans, totalMs } = useMemo(
    () => buildSpans(trajectory, lifecycle, events),
    [trajectory, lifecycle, events],
  );

  const filtered = useMemo(() => filterTree(spans, query), [spans, query]);
  const rows = useMemo(() => flattenVisible(filtered, collapsed), [filtered, collapsed]);

  const ticks = useMemo(() => {
    const count = 5;
    return Array.from({ length: count }, (_, i) => (totalMs * i) / (count - 1));
  }, [totalMs]);

  function toggle(id: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div
      className="overflow-hidden rounded-lg border border-base-200 bg-[#0b0f19] text-slate-100"
      data-testid="trajectory-lifecycle-timeline"
      data-timeline="span"
    >
      <div className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
            Span
          </p>
          <h3 className="text-sm font-semibold text-white">Trajectory lifecycle timeline</h3>
        </div>
        <label className="relative w-full max-w-xs">
          <span className="sr-only">Search spans</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search spans…"
            className="w-full rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-400/60 focus:outline-none"
            data-testid="timeline-span-search"
          />
        </label>
      </div>

      {!rows.length ? (
        <div className="flex min-h-48 items-center justify-center px-6 text-sm text-slate-400">
          No lifecycle spans available for this trajectory.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <div className="min-w-[720px]">
            <div
              className="sticky top-0 z-[1] grid border-b border-white/10 bg-[#0b0f19]/90 backdrop-blur"
              style={{ gridTemplateColumns: `${LABEL_W}px 1fr` }}
            >
              <div className="px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Name
              </div>
              <div className="relative h-8">
                {ticks.map((tick) => {
                  const left = (tick / totalMs) * 100;
                  return (
                    <div
                      key={tick}
                      className="absolute top-0 h-full border-l border-white/10"
                      style={{ left: `${left}%` }}
                    >
                      <span className="absolute left-1 top-1.5 font-mono text-[10px] text-slate-500">
                        {formatAxisTick(tick)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            <div>
              {rows.map((row) => {
                const selected = Boolean(row.eventId && row.eventId === selectedEventId);
                const hasKids = Boolean(row.children?.length);
                const isCollapsed = collapsed.has(row.id);
                const leftPct = (row.startMs / totalMs) * 100;
                const widthPct = Math.max(
                  (row.durationMs / totalMs) * 100,
                  row.durationMs <= 0 ? 0.15 : 0.4,
                );
                const indent = 12 + row.depth * 16;

                return (
                  <div
                    key={row.id}
                    className={cn(
                      "grid border-b border-white/[0.04] transition-colors",
                      selected ? "bg-sky-500/10" : "hover:bg-white/[0.03]",
                    )}
                    style={{ gridTemplateColumns: `${LABEL_W}px 1fr`, minHeight: ROW_H }}
                    data-testid={`timeline-span-${row.id}`}
                  >
                    <button
                      type="button"
                      className="flex min-w-0 items-center gap-1.5 px-2 py-1.5 text-left"
                      style={{ paddingLeft: indent }}
                      onClick={() => {
                        if (hasKids) toggle(row.id);
                        if (row.eventId && onSelectEvent) onSelectEvent(row.eventId);
                      }}
                    >
                      {hasKids ? (
                        <span className="inline-flex size-4 shrink-0 items-center justify-center text-[10px] text-slate-400">
                          {isCollapsed ? "▶" : "▼"}
                        </span>
                      ) : (
                        <span className="inline-flex size-4 shrink-0" />
                      )}
                      <span
                        className={cn(
                          "inline-flex size-5 shrink-0 items-center justify-center rounded text-[10px]",
                          row.kind === "root" || row.kind === "stage"
                            ? "bg-violet-500/20 text-violet-200"
                            : "bg-sky-500/15 text-sky-200",
                        )}
                        aria-hidden
                      >
                        {kindIcon(row.kind, row.name)}
                      </span>
                      <span className="min-w-0 flex-1 truncate">
                        <span className="block truncate font-mono text-[12px] text-slate-100">
                          {row.name}
                        </span>
                        {row.subtitle ? (
                          <span className="block truncate text-[10px] text-slate-500">
                            {row.subtitle}
                          </span>
                        ) : null}
                      </span>
                      {row.cost != null ? <CostPill cost={row.cost} /> : null}
                      <TechnicalValue className="shrink-0 text-[10px] text-slate-400">
                        {formatDurationMs(row.durationMs)}
                      </TechnicalValue>
                    </button>

                    <button
                      type="button"
                      className="relative px-2 py-1.5"
                      onClick={() => {
                        if (row.eventId && onSelectEvent) onSelectEvent(row.eventId);
                      }}
                      aria-label={`${row.name} ${formatDurationMs(row.durationMs)}`}
                    >
                      {ticks.map((tick) => (
                        <span
                          key={`${row.id}-${tick}`}
                          className="absolute inset-y-0 border-l border-white/[0.04]"
                          style={{ left: `${(tick / totalMs) * 100}%` }}
                        />
                      ))}
                      <span
                        className={cn(
                          "absolute top-1/2 h-3 -translate-y-1/2 rounded-sm",
                          barTone(row.kind, row.name),
                          selected && "ring-2 ring-sky-300/70",
                          row.durationMs <= 0 && "w-0.5",
                        )}
                        style={{
                          left: `${leftPct}%`,
                          width: row.durationMs <= 0 ? undefined : `${widthPct}%`,
                        }}
                        title={`${row.name} · ${formatDurationMs(row.durationMs)}`}
                      />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
