"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/registry/status-badge";
import { TechnicalValue } from "@/components/console/page-parts";
import { contentStatusMessage, eventContentPreview } from "@/lib/evidence-content";
import { cn } from "@/lib/utils";
import type { EvidenceEvent, TrajectoryDetail } from "@/lib/types";

function formatClock(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  const base = date.toLocaleTimeString("en-GB", { hour12: false });
  return `${base}.${String(date.getMilliseconds()).padStart(3, "0")}`;
}

function formatIso(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toISOString();
}

function categoryFor(eventType: string): string {
  const upper = eventType.toUpperCase();
  if (upper.includes("PROMPT")) return "prompt";
  if (upper.includes("MODEL_REQUEST") || upper.includes("MODEL REQUEST")) return "model_request";
  if (upper.includes("MODEL_RESPONSE") || upper.includes("MODEL RESPONSE")) return "model_response";
  if (upper.includes("POLICY") || upper.includes("BUDGET")) return "policy";
  if (upper.includes("DATA_SOURCE") || upper.includes("DATA_ACCESS")) return "data_source";
  if (upper.includes("APPROVAL")) return "approval";
  if (
    upper.includes("TOOL_REQUEST") ||
    upper.includes("ACTION_REQUEST") ||
    upper.includes("TOOL_ATTEMPTED") ||
    upper.includes("TOOL_CALL")
  ) {
    return "tool_request";
  }
  if (upper.includes("AUTHORIZ")) return "authorization";
  if (
    upper.includes("EXECUTION") ||
    upper.includes("ACTION_EXECUTED") ||
    upper.includes("TOOL_EXEC")
  ) {
    return "execution";
  }
  if (upper.includes("TOOL_RESULT") || upper.includes("ACTION_RESULT")) return "tool_result";
  if (upper.includes("OUTPUT")) return "output";
  return "other";
}

function eventTypeLabel(eventType: string): string {
  return eventType.replace(/_/g, " ").toUpperCase();
}

function decisionFromEvent(event: EvidenceEvent): string | undefined {
  const payload = event.payload ?? {};
  const candidates = [
    payload.decision,
    payload.enforcement_decision,
    payload.policy_decision,
    payload.effect,
  ];
  for (const value of candidates) {
    if (typeof value === "string" && value.trim()) return value;
    if (value && typeof value === "object" && "final_effect" in value) {
      const effect = (value as { final_effect?: unknown }).final_effect;
      if (typeof effect === "string") return effect;
    }
  }
  return undefined;
}

function toolLabel(payload: Record<string, unknown>): string | null {
  for (const key of ["tool_name", "tool_key", "tool"]) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  const toolId = payload.tool_id;
  if (typeof toolId === "string" && toolId.trim()) {
    return `tool ${toolId.slice(0, 8)}…`;
  }
  return null;
}

function summaryFor(event: EvidenceEvent): string {
  const payload = event.payload ?? {};
  const tool = toolLabel(payload);
  if (tool && /TOOL_|ACTION_ALLOWED|ACTION_DENIED|POLICY_EVALUATED/i.test(event.event_type)) {
    for (const key of ["summary", "human_explanation", "reason", "message"]) {
      const value = payload[key];
      if (typeof value === "string" && value.trim()) {
        return `${tool}: ${value}`;
      }
    }
    return tool;
  }
  for (const key of ["summary", "human_explanation", "reason", "message"]) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  const preview = eventContentPreview(event);
  if (preview) return preview;
  const status = contentStatusMessage(event);
  if (status) return status.split("\n")[0];
  return eventTypeLabel(event.event_type);
}

function latencyMs(event: EvidenceEvent): number | undefined {
  const payload = event.payload ?? {};
  for (const key of ["latency_ms", "duration_ms"]) {
    const value = payload[key];
    if (typeof value === "number") return value;
    if (typeof value === "string" && value.trim() && !Number.isNaN(Number(value))) {
      return Number(value);
    }
  }
  return undefined;
}

function SourceBadge({ source }: { source: string }) {
  const tone = source.startsWith("RAI_")
    ? "border-accent-200 bg-accent-50 text-accent-700"
    : source === "DERIVED"
      ? "border-base-200 bg-base-100 text-ink-500"
      : "border-warn-100 bg-warn-50 text-warn-700";
  return (
    <span
      className={cn(
        "inline-flex rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold",
        tone,
      )}
    >
      {source}
    </span>
  );
}

function AssuranceDot({ value }: { value: string }) {
  const tone =
    value === "HIGH" || value === "authoritative" || value === "executed"
      ? "bg-accent-600"
      : value === "DERIVED" || value === "derived"
        ? "bg-ink-400"
        : "bg-warn-600";
  return (
    <span className="inline-flex items-center gap-1 text-xs text-ink-600">
      <span className={cn("size-1.5 rounded-full", tone)} />
      {value.toLowerCase()}
    </span>
  );
}

function EventIcon({ category, decision }: { category: string; decision?: string }) {
  const ring =
    decision && /deny|denied|fail/i.test(decision)
      ? "border-danger-500 text-danger-600"
      : decision && /approval|warn/i.test(decision)
        ? "border-warn-600 text-warn-700"
        : decision
          ? "border-accent-600 text-accent-600"
          : "border-base-300 text-accent-600";
  return (
    <span
      className={cn(
        "relative z-10 flex size-7 items-center justify-center rounded-full border bg-base-50",
        ring,
      )}
    >
      <svg
        aria-hidden
        viewBox="0 0 16 16"
        className="size-3.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      >
        {category === "prompt" ? (
          <circle cx="8" cy="8" r="3.5" />
        ) : category === "model_request" || category === "model_response" ? (
          <>
            <rect x="3" y="4" width="10" height="8" rx="1.5" />
            <path d="M6 7h4M6 9.5h2.5" />
          </>
        ) : category === "policy" || category === "authorization" ? (
          <path d="M8 2.5 12.5 4.5v3.2c0 2.7-1.9 4.8-4.5 5.8-2.6-1-4.5-3.1-4.5-5.8V4.5L8 2.5Z" />
        ) : category === "approval" ? (
          <>
            <circle cx="8" cy="6" r="2.2" />
            <path d="M3.8 13c.7-2 2.2-3 4.2-3s3.5 1 4.2 3" />
          </>
        ) : category === "data_source" ? (
          <>
            <path d="M3.5 5.5c0-1.4 2-2.5 4.5-2.5s4.5 1.1 4.5 2.5-2 2.5-4.5 2.5-4.5-1.1-4.5-2.5Z" />
            <path d="M3.5 5.5v5c0 1.4 2 2.5 4.5 2.5s4.5-1.1 4.5-2.5v-5" />
          </>
        ) : category === "tool_request" ? (
          <path d="M5 4.5h6v2H5v-2Zm0 5h6v2H5v-2Z" />
        ) : category === "execution" || category === "tool_result" ? (
          <path d="M5 3.5 12 8 5 12.5v-9Z" />
        ) : category === "output" ? (
          <path d="M3.5 8h9M9.5 5l3 3-3 3" />
        ) : (
          <circle cx="8" cy="8" r="2" fill="currentColor" stroke="none" />
        )}
      </svg>
    </span>
  );
}

function detailEntries(
  event: EvidenceEvent,
  trajectory: TrajectoryDetail,
): { label: string; value: string; mono?: boolean }[] {
  const rows: { label: string; value: string; mono?: boolean }[] = [
    { label: "Timestamp", value: formatIso(event.occurred_at) },
    { label: "Source", value: event.source_type },
    { label: "Assurance", value: event.assurance_level.toLowerCase() },
  ];
  const latency = latencyMs(event);
  if (latency != null) rows.push({ label: "Latency", value: `${latency} ms` });
  const decision = decisionFromEvent(event);
  if (decision) rows.push({ label: "Decision", value: decision.toUpperCase() });

  rows.push(
    { label: "AI System", value: trajectory.ai_system_name ?? trajectory.ai_system_id },
    { label: "Agent", value: trajectory.agent_name ?? trajectory.agent_id },
    {
      label: "Version",
      value:
        trajectory.agent_version_number != null
          ? `v${trajectory.agent_version_number}`
          : trajectory.agent_version_id,
      mono: true,
    },
    {
      label: "Runtime Identity",
      value: trajectory.runtime_identity_name ?? trajectory.runtime_identity_id,
    },
  );

  if (trajectory.delegation_id || trajectory.delegation) {
    const grant = trajectory.delegation;
    rows.push({
      label: "Delegation",
      value: grant
        ? `${grant.delegator_type}:${grant.delegator_id} (${grant.status})`
        : String(trajectory.delegation_id),
      mono: true,
    });
  }

  if (event.correlation_id) {
    rows.push({ label: "Correlation ID", value: event.correlation_id, mono: true });
  }
  if (event.payload_digest) {
    rows.push({ label: "Payload Digest", value: event.payload_digest, mono: true });
  }

  const payload = event.payload ?? {};
  for (const [key, value] of Object.entries(payload)) {
    if (value == null) continue;
    if (typeof value === "object") continue;
    const label = key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    if (rows.some((row) => row.label.toLowerCase() === label.toLowerCase())) continue;
    rows.push({
      label,
      value: String(value),
      mono: /id|digest|tool|key/i.test(key),
    });
  }
  return rows;
}

function TimelineList({
  events,
  selectedId,
  onSelect,
}: {
  events: EvidenceEvent[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="p-4" role="list" aria-label="Trajectory event timeline">
      {events.map((event, index) => {
        const category = categoryFor(event.event_type);
        const decision = decisionFromEvent(event);
        const selected = selectedId === event.id;
        return (
          <button
            key={event.id}
            type="button"
            role="listitem"
            onClick={() => onSelect(event.id)}
            className={cn(
              "relative grid w-full grid-cols-[84px_28px_1fr] gap-2 rounded-md p-2 text-left transition-colors hover:bg-base-100",
              selected && "bg-accent-50 ring-1 ring-accent-600/40",
            )}
          >
            <TechnicalValue className="pt-1 text-[10px]">
              {formatClock(event.occurred_at)}
            </TechnicalValue>
            <EventIcon category={category} decision={decision} />
            {index < events.length - 1 ? (
              <span className="absolute bottom-[-12px] left-[107px] top-9 w-px bg-base-200" />
            ) : null}
            <span className="min-w-0 pb-5">
              <span className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-900">
                  {eventTypeLabel(event.event_type)}
                </span>
                {decision ? <StatusBadge status={decision} /> : null}
              </span>
              <span className="mt-1 block text-sm text-ink-600">{summaryFor(event)}</span>
              <span className="mt-2 flex flex-wrap items-center gap-3">
                <SourceBadge source={event.source_type} />
                <AssuranceDot value={event.assurance_level} />
                {latencyMs(event) != null ? (
                  <span className="font-mono text-[10px] text-ink-400">{latencyMs(event)} ms</span>
                ) : null}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

function DecisionGraph({
  events,
  selectedId,
  onSelect,
}: {
  events: EvidenceEvent[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="overflow-x-auto p-6">
      <div
        className="mx-auto flex min-w-[520px] max-w-xl flex-col items-center"
        role="list"
        aria-label="Decision graph"
      >
        {events.map((event, index) => {
          const decision = decisionFromEvent(event);
          const selected = selectedId === event.id;
          return (
            <div className="contents" key={event.id}>
              <button
                type="button"
                role="listitem"
                onClick={() => onSelect(event.id)}
                className={cn(
                  "grid w-full grid-cols-[120px_1fr_auto] items-center gap-3 rounded-md border p-3 text-left",
                  selected
                    ? "border-accent-600 bg-accent-50"
                    : "border-base-200 bg-base-100 hover:border-base-300",
                )}
              >
                <span className="font-mono text-[10px] text-ink-400">
                  {formatClock(event.occurred_at)}
                </span>
                <span>
                  <span className="block text-xs font-semibold uppercase tracking-wide">
                    {eventTypeLabel(event.event_type)}
                  </span>
                  <span className="mt-1 block text-xs text-ink-500">{summaryFor(event)}</span>
                </span>
                {decision ? (
                  <StatusBadge status={decision} />
                ) : (
                  <span className="font-mono text-[10px] text-ink-400">OBSERVED</span>
                )}
              </button>
              {index < events.length - 1 ? <div className="h-7 w-px bg-base-300" /> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EventInspector({
  event,
  trajectory,
}: {
  event: EvidenceEvent;
  trajectory: TrajectoryDetail;
}) {
  const [raw, setRaw] = useState(false);
  const preview = eventContentPreview(event);
  const unavailable = contentStatusMessage(event);
  const contentCategory = ["prompt", "model_request", "model_response", "output"].includes(
    categoryFor(event.event_type),
  );

  return (
    <aside className="min-w-0 bg-base-100" aria-label="Selected event inspector">
      <header className="border-b border-base-200 p-4">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
          Selected Event
        </div>
        <div className="mt-1 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-900">
            {eventTypeLabel(event.event_type)}
          </h2>
          <TechnicalValue>{event.id.slice(0, 12)}</TechnicalValue>
        </div>
      </header>
      <div className="max-h-[760px] overflow-y-auto p-4">
        <dl className="space-y-3">
          {detailEntries(event, trajectory).map((row) => (
            <div
              key={row.label}
              className="grid grid-cols-[112px_1fr] gap-3 border-b border-base-200 pb-2"
            >
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                {row.label}
              </dt>
              <dd
                className={cn("min-w-0 break-words text-xs text-ink-700", row.mono && "font-mono")}
              >
                {row.value}
              </dd>
            </div>
          ))}
        </dl>

        {preview ? (
          <div className="mt-4">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
              Retained redacted content
            </div>
            <div className="rounded-md border border-base-200 bg-base-50 p-3 font-mono text-xs leading-5 text-ink-700">
              {preview}
            </div>
          </div>
        ) : contentCategory ? (
          <div className="mt-4 rounded-md border border-base-200 bg-base-50 p-3">
            <div className="text-xs font-semibold text-ink-900">Content not retained</div>
            <p className="mt-1 text-xs text-ink-500">
              {unavailable ??
                "The event was recorded, but prompt/output content was not retained under the current evidence retention configuration."}
            </p>
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2">
          <Link
            href={`/runtime/trajectories/${trajectory.id}/evidence/${event.id}`}
            className="text-xs font-semibold text-accent-600 hover:text-accent-500"
          >
            Open full evidence →
          </Link>
        </div>

        <Button
          variant="ghost"
          size="sm"
          className="mt-4 w-full justify-between"
          onClick={() => setRaw((value) => !value)}
        >
          <span>View Raw Event</span>
          <span aria-hidden>{raw ? "▴" : "▾"}</span>
        </Button>
        {raw ? (
          <pre className="mt-2 overflow-x-auto rounded-md border border-base-200 bg-base-50 p-3 font-mono text-[10px] text-ink-500">
            {JSON.stringify(event, null, 2)}
          </pre>
        ) : null}
      </div>
    </aside>
  );
}

export function InvestigationWorkspace({
  trajectory,
  selectedId,
  onSelect,
}: {
  trajectory: TrajectoryDetail;
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const events = useMemo(
    () =>
      [...(trajectory.events ?? [])].sort(
        (a, b) =>
          (a.sequence_number ?? 0) - (b.sequence_number ?? 0) ||
          String(a.occurred_at ?? "").localeCompare(String(b.occurred_at ?? "")),
      ),
    [trajectory.events],
  );
  const selected = events.find((event) => event.id === selectedId) ?? events[0];
  const [mode, setMode] = useState<"timeline" | "graph">("timeline");

  if (!selected) {
    return (
      <div className="rounded-lg border border-base-200 bg-base-50 p-8 text-center text-sm text-ink-500">
        No evidence events recorded for this trajectory.
      </div>
    );
  }

  return (
    <div
      className="grid min-h-[640px] overflow-hidden rounded-lg border border-base-200 bg-base-50 xl:grid-cols-[minmax(0,7fr)_minmax(360px,3fr)]"
      data-testid="investigation-workspace"
    >
      <div className="min-w-0 border-b border-base-200 xl:border-b-0 xl:border-r">
        <div className="flex h-12 items-center justify-between border-b border-base-200 px-3">
          <div
            className="flex rounded-md bg-base-100 p-1"
            role="group"
            aria-label="Visualization mode"
          >
            <Button
              size="sm"
              variant={mode === "timeline" ? "secondary" : "ghost"}
              aria-pressed={mode === "timeline"}
              onClick={() => setMode("timeline")}
            >
              Timeline
            </Button>
            <Button
              size="sm"
              variant={mode === "graph" ? "secondary" : "ghost"}
              aria-pressed={mode === "graph"}
              onClick={() => setMode("graph")}
            >
              Decision Graph
            </Button>
          </div>
          <span className="font-mono text-[10px] text-ink-400">{events.length} EVENTS</span>
        </div>
        {mode === "timeline" ? (
          <TimelineList events={events} selectedId={selected.id} onSelect={onSelect} />
        ) : (
          <DecisionGraph events={events} selectedId={selected.id} onSelect={onSelect} />
        )}
      </div>
      <EventInspector key={selected.id} event={selected} trajectory={trajectory} />
    </div>
  );
}
