"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Panel } from "@/components/registry/panel";
import { contentStatusMessage, eventContentPreview, humanEventLabel } from "@/lib/evidence-content";
import type { EvidenceEvent } from "@/lib/types";

type SourceFilter = "ALL" | "AUTHORITATIVE" | "CLIENT" | "DERIVED";

function formatTime(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function formatClock(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function SourceBadge({ source }: { source: string }) {
  const tone =
    source === "RAI_AUTHORITATIVE" || source === "RAI_EXECUTED"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
      : source === "CLIENT_REPORTED" || source === "CLIENT_OBSERVED"
        ? "border-amber-200 bg-amber-50 text-amber-950"
        : source === "DERIVED"
          ? "border-slate-200 bg-slate-50 text-slate-800"
          : "border-base-200 bg-base-100 text-ink-700";
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-[11px] font-semibold tracking-wide ${tone}`}
    >
      {source}
    </span>
  );
}

function AssuranceBadge({ level }: { level: string }) {
  const tone =
    level === "HIGH"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
      : level === "MEDIUM"
        ? "border-sky-200 bg-sky-50 text-sky-900"
        : level === "LOW"
          ? "border-amber-200 bg-amber-50 text-amber-950"
          : "border-base-200 bg-base-100 text-ink-700";
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-[11px] font-semibold ${tone}`}
    >
      {level}
    </span>
  );
}

function eventCategory(eventType: string): string {
  if (eventType.includes("PROMPT") || eventType.includes("MODEL") || eventType.includes("OUTPUT")) {
    return "Content";
  }
  if (eventType.includes("POLICY") || eventType.includes("AUTHORITY")) {
    return "Policy";
  }
  if (eventType.includes("APPROVAL")) {
    return "Approval";
  }
  if (
    eventType.includes("ACTION") ||
    eventType.includes("TOOL") ||
    eventType.includes("EXECUTION")
  ) {
    return "Execution";
  }
  if (eventType.includes("FINDING") || eventType.includes("EVIDENCE")) {
    return "Assurance";
  }
  if (eventType.includes("SESSION")) {
    return "Session";
  }
  if (eventType.includes("CONTENT_EVALUATION")) {
    return "Risk";
  }
  return "Other";
}

function railTone(eventType: string): string {
  if (eventType.includes("DENIED") || eventType.includes("FAILED")) {
    return "bg-red-500";
  }
  if (
    eventType.includes("ALLOWED") ||
    eventType.includes("SUCCEEDED") ||
    eventType.includes("APPROVED")
  ) {
    return "bg-emerald-500";
  }
  if (eventType.includes("APPROVAL") || eventType.includes("REQUIRE")) {
    return "bg-amber-500";
  }
  if (eventType.includes("POLICY") || eventType.includes("AUTHORITY")) {
    return "bg-sky-500";
  }
  return "bg-slate-400";
}

function eventDrilldown(event: EvidenceEvent): { href: string; label: string } | null {
  const payload = event.payload ?? {};
  if (typeof payload.approval_request_id === "string") {
    return {
      href: `/governance/approvals/${payload.approval_request_id}`,
      label: "Open approval",
    };
  }
  if (typeof payload.receipt_id === "string") {
    return {
      href: `/runtime/enforcement/${payload.receipt_id}`,
      label: "Open enforcement receipt",
    };
  }
  const ref = event.source_reference;
  if (ref.startsWith("receipt:") && ref.includes(":")) {
    const receiptId = ref.split(":")[1];
    if (receiptId) {
      return { href: `/runtime/enforcement/${receiptId}`, label: "Open enforcement receipt" };
    }
  }
  if (ref.startsWith("approval:")) {
    const approvalId = ref.split(":")[1];
    if (approvalId) {
      return { href: `/governance/approvals/${approvalId}`, label: "Open approval" };
    }
  }
  return null;
}

function EventContentHint({ event }: { event: EvidenceEvent }) {
  const contentEvents = new Set([
    "PROMPT_OBSERVED",
    "MODEL_REQUEST_OBSERVED",
    "MODEL_RESPONSE_OBSERVED",
    "AGENT_OUTPUT_OBSERVED",
  ]);
  if (!contentEvents.has(event.event_type)) return null;

  const preview = eventContentPreview(event);
  if (preview) {
    return (
      <p className="mt-2 line-clamp-2 text-sm text-ink-700" data-testid="event-content-preview">
        “{preview}”
      </p>
    );
  }
  const status = contentStatusMessage(event);
  if (!status) return null;
  return (
    <p className="mt-2 text-xs text-ink-500" data-testid="event-content-status">
      {status.split("\n")[0]}
    </p>
  );
}

function matchesSourceFilter(source: string, filter: SourceFilter): boolean {
  if (filter === "ALL") return true;
  if (filter === "AUTHORITATIVE") {
    return source === "RAI_AUTHORITATIVE" || source === "RAI_EXECUTED";
  }
  if (filter === "CLIENT") {
    return source === "CLIENT_REPORTED" || source === "CLIENT_OBSERVED";
  }
  return source === "DERIVED" || source === "EXTERNAL_PROVIDER";
}

export function TrajectoryTimelineView({
  events,
  trajectoryId,
}: {
  events: EvidenceEvent[];
  trajectoryId: string;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("ALL");
  const [categoryFilter, setCategoryFilter] = useState<string>("ALL");

  const categories = useMemo(() => {
    const set = new Set(events.map((e) => eventCategory(e.event_type)));
    return ["ALL", ...Array.from(set).sort()];
  }, [events]);

  const filtered = useMemo(
    () =>
      events.filter(
        (e) =>
          matchesSourceFilter(e.source_type, sourceFilter) &&
          (categoryFilter === "ALL" || eventCategory(e.event_type) === categoryFilter),
      ),
    [events, sourceFilter, categoryFilter],
  );

  const evidenceHref = (eventId: string) =>
    `/runtime/trajectories/${trajectoryId}/evidence/${eventId}`;

  const counts = useMemo(() => {
    const authoritative = events.filter((e) =>
      matchesSourceFilter(e.source_type, "AUTHORITATIVE"),
    ).length;
    const client = events.filter((e) => matchesSourceFilter(e.source_type, "CLIENT")).length;
    const derived = events.filter((e) => matchesSourceFilter(e.source_type, "DERIVED")).length;
    return { total: events.length, authoritative, client, derived };
  }, [events]);

  if (events.length === 0) {
    return (
      <div data-testid="trajectory-timeline">
        <Panel title="Audit timeline">
          <p className="text-sm text-ink-500">No events recorded.</p>
        </Panel>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="trajectory-timeline">
      <div className="grid gap-3 sm:grid-cols-4">
        {[
          { label: "Events", value: counts.total },
          { label: "RAI authoritative", value: counts.authoritative },
          { label: "Client observed", value: counts.client },
          { label: "Derived", value: counts.derived },
        ].map((stat) => (
          <div
            key={stat.label}
            className="rounded-xl border border-base-200 bg-white px-4 py-3 shadow-sm"
          >
            <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-500">
              {stat.label}
            </p>
            <p className="mt-1 text-2xl font-semibold text-ink-900">{stat.value}</p>
          </div>
        ))}
      </div>

      <Panel
        title="Audit timeline"
        description="Chronological evidence stream with provenance and assurance."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {(
              [
                ["ALL", "All sources"],
                ["AUTHORITATIVE", "RAI"],
                ["CLIENT", "Client"],
                ["DERIVED", "Derived"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setSourceFilter(value)}
                className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                  sourceFilter === value
                    ? "bg-ink-900 text-white"
                    : "border border-base-200 bg-white text-ink-600 hover:bg-base-100"
                }`}
              >
                {label}
              </button>
            ))}
            <select
              className="rounded-md border border-base-200 bg-white px-2.5 py-1 text-xs font-semibold text-ink-700"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
            >
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c === "ALL" ? "All categories" : c}
                </option>
              ))}
            </select>
          </div>
        }
      >
        {filtered.length === 0 ? (
          <p className="text-sm text-ink-500">No events match the current filters.</p>
        ) : (
          <ol className="relative ml-2 space-y-0 border-l border-base-200 pl-6">
            {filtered.map((event, index) => {
              const open = expanded === event.id;
              const drill = eventDrilldown(event);
              const category = eventCategory(event.event_type);
              return (
                <li key={event.id} className="relative pb-6 last:pb-0" data-testid="timeline-event">
                  <span
                    className={`absolute -left-[1.9rem] top-3 h-3 w-3 rounded-full ring-4 ring-white ${railTone(
                      event.event_type,
                    )}`}
                    aria-hidden
                  />
                  <div
                    className={`rounded-xl border bg-white shadow-sm transition ${
                      open ? "border-ink-300" : "border-base-200 hover:border-base-300"
                    }`}
                  >
                    <button
                      type="button"
                      className="flex w-full items-start gap-4 px-4 py-3 text-left"
                      onClick={() => setExpanded(open ? null : event.id)}
                    >
                      <div className="w-24 shrink-0 pt-0.5">
                        <p className="font-mono text-xs font-semibold text-ink-800">
                          {formatClock(event.occurred_at)}
                        </p>
                        <p className="mt-1 text-[11px] text-ink-400">
                          #{event.sequence_number}
                          {index === 0 ? " · start" : ""}
                        </p>
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-semibold text-ink-900">
                            {humanEventLabel(event.event_type)}
                          </p>
                          <span className="rounded bg-base-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-500">
                            {category}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-ink-500">{formatTime(event.occurred_at)}</p>
                        <EventContentHint event={event} />
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1.5">
                        <SourceBadge source={event.source_type} />
                        <AssuranceBadge level={event.assurance_level} />
                        <span className="text-[11px] font-medium text-ink-400">
                          {open ? "Collapse" : "Expand"}
                        </span>
                      </div>
                    </button>

                    {open && (
                      <div className="space-y-3 border-t border-base-100 bg-base-50/60 px-4 py-3 text-sm">
                        <div className="grid gap-3 sm:grid-cols-3">
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                              Content handling
                            </p>
                            <p className="mt-1 text-ink-800">
                              {event.content_handling_mode} · {event.redaction_status}
                            </p>
                          </div>
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                              Source reference
                            </p>
                            <p className="mt-1 break-all font-mono text-xs text-ink-700">
                              {event.source_reference}
                            </p>
                          </div>
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                              Payload digest
                            </p>
                            <p className="mt-1 break-all font-mono text-xs text-ink-700">
                              {event.payload_digest ?? "—"}
                            </p>
                          </div>
                        </div>
                        <details className="rounded-lg border border-base-200 bg-white">
                          <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-ink-600">
                            Structured payload
                          </summary>
                          <pre className="max-h-64 overflow-auto border-t border-base-100 p-3 text-xs text-ink-700">
                            {JSON.stringify(event.payload ?? {}, null, 2)}
                          </pre>
                        </details>
                        <div className="flex flex-wrap gap-4">
                          <Link
                            href={evidenceHref(event.id)}
                            className="text-sm font-semibold text-accent-700 hover:underline"
                            data-testid="view-evidence-details"
                          >
                            View evidence details
                          </Link>
                          {drill && (
                            <Link
                              href={drill.href}
                              className="text-sm font-semibold text-accent-700 hover:underline"
                            >
                              {drill.label}
                            </Link>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </Panel>
    </div>
  );
}
