"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Breadcrumbs } from "@/components/registry/breadcrumbs";
import { Panel } from "@/components/registry/panel";
import { MetaGrid, PostureStrip, TechnicalValue } from "@/components/console/page-parts";
import { Button } from "@/components/ui/button";
import { getTrajectoryEvent } from "@/lib/api";
import { contentStatusMessage, extractEventContent, humanEventLabel } from "@/lib/evidence-content";
import { cn } from "@/lib/utils";
import type { EvidenceArtifact, EvidenceEventDetail } from "@/lib/types";

const CONTENT_KEYS = new Set(["prompt", "output", "content", "text", "result"]);

type TrajectoryContext = NonNullable<EvidenceEventDetail["trajectory"]> & {
  delegation?: {
    delegator_type?: string;
    delegator_id?: string;
    status?: string;
  } | null;
};

function formatTime(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatBytes(value?: number | null) {
  if (value == null) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function humanizeKey(key: string) {
  return key
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function sourceTone(source: string) {
  if (source.startsWith("RAI_")) return "border-accent-200 bg-accent-50 text-accent-700";
  if (source === "DERIVED") return "border-base-200 bg-base-100 text-ink-500";
  return "border-warn-100 bg-warn-50 text-warn-700";
}

function Token({ value, className }: { value: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full truncate rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold",
        className,
      )}
    >
      {value}
    </span>
  );
}

function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <Button
      type="button"
      size="sm"
      variant="ghost"
      className="h-7"
      onClick={() => {
        void navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1400);
        });
      }}
    >
      {copied ? "Copied" : label}
    </Button>
  );
}

function payloadAttributes(payload?: Record<string, unknown> | null) {
  if (!payload) return [];
  return Object.entries(payload).filter(([key, value]) => {
    if (CONTENT_KEYS.has(key)) return false;
    if (value == null || value === "") return false;
    return true;
  });
}

function AttributeValue({ value }: { value: unknown }) {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return <span className="break-all">{String(value)}</span>;
  }
  return (
    <pre className="overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-5 text-ink-600">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function ArtifactCard({ artifact }: { artifact: EvidenceArtifact }) {
  return (
    <li className="rounded-md border border-base-200 bg-base-100 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-ink-900">
            {humanEventLabel(artifact.artifact_type)}
          </p>
          <p className="mt-1 font-mono text-[11px] text-ink-400">
            {[artifact.mime_type, formatBytes(artifact.size_bytes), artifact.source_type]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Token
            value={artifact.content_handling_mode}
            className={sourceTone(artifact.source_type)}
          />
          {artifact.sensitivity_classification ? (
            <Token
              value={artifact.sensitivity_classification}
              className="border-base-200 bg-base-50 text-ink-600"
            />
          ) : null}
          {artifact.encrypted ? (
            <Token value="ENCRYPTED" className="border-accent-200 bg-accent-50 text-accent-700" />
          ) : null}
        </div>
      </div>
      {artifact.content_digest ? (
        <p className="mt-2 break-all font-mono text-[11px] text-ink-500">
          {artifact.content_digest}
        </p>
      ) : null}
      {artifact.inline_content ? (
        <pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap rounded-md border border-base-200 bg-base-50 p-3 font-mono text-xs leading-5 text-ink-700">
          {artifact.inline_content}
        </pre>
      ) : null}
    </li>
  );
}

export default function EvidenceEventDetailPage() {
  const params = useParams();
  const trajectoryId = params.trajectoryId as string;
  const eventId = params.eventId as string;
  const [detail, setDetail] = useState<EvidenceEventDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getTrajectoryEvent(trajectoryId, eventId);
      setDetail(res.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load evidence event");
    } finally {
      setLoading(false);
    }
  }, [trajectoryId, eventId]);

  useEffect(() => {
    void load();
  }, [load]);

  const content = detail ? extractEventContent(detail) : null;
  const unavailable = detail ? contentStatusMessage(detail) : null;
  const attributes = useMemo(() => payloadAttributes(detail?.payload), [detail]);

  if (loading) {
    return (
      <div className="space-y-4" data-testid="evidence-event-detail-page">
        <div className="h-4 w-48 animate-pulse rounded bg-base-200" />
        <div className="h-8 w-72 animate-pulse rounded bg-base-200" />
        <div className="h-16 animate-pulse rounded-lg bg-base-200" />
        <div className="h-64 animate-pulse rounded-lg bg-base-200" />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="space-y-4" data-testid="evidence-event-detail-page">
        <Breadcrumbs
          items={[
            { label: "Trajectories", href: "/runtime/trajectories" },
            { label: trajectoryId.slice(0, 8), href: `/runtime/trajectories/${trajectoryId}` },
            { label: "Evidence" },
          ]}
        />
        <Panel title="Evidence unavailable">
          <p className="text-sm text-danger-600">{error ?? "Evidence event not found"}</p>
          <Button className="mt-4" size="sm" variant="secondary" onClick={() => void load()}>
            Retry
          </Button>
        </Panel>
      </div>
    );
  }

  const trajectory = detail.trajectory as TrajectoryContext | undefined;
  const client =
    typeof detail.payload?.client_type === "string"
      ? detail.payload.client_type
      : trajectory?.client_type;
  const observedModel =
    typeof detail.payload?.observed_model === "string" ? detail.payload.observed_model : null;
  const contentAccess =
    "content_access" in detail && typeof detail.content_access === "string"
      ? detail.content_access
      : null;
  const related = [...(detail.related_events ?? [])].sort(
    (a, b) => a.sequence_number - b.sequence_number,
  );
  const backHref = `/runtime/trajectories/${trajectoryId}?event=${eventId}`;

  return (
    <div className="space-y-4" data-testid="evidence-event-detail-page">
      <div className="flex flex-col gap-4 border-b border-base-200 pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <div className="mb-2 text-xs text-ink-500">
            <Breadcrumbs
              items={[
                { label: "Trajectories", href: "/runtime/trajectories" },
                {
                  label: trajectoryId.slice(0, 8),
                  href: `/runtime/trajectories/${trajectoryId}`,
                },
                { label: humanEventLabel(detail.event_type) },
              ]}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-[28px] font-semibold leading-tight text-ink-900">
              {humanEventLabel(detail.event_type)}
            </h1>
            <span className="rounded-md border border-base-200 bg-base-50 px-2 py-0.5 font-mono text-xs text-ink-500">
              seq {String(detail.sequence_number).padStart(2, "0")}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-500">
            <span className="inline-flex min-w-0 items-center gap-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                Event
              </span>
              <TechnicalValue className="text-ink-700">{detail.id}</TechnicalValue>
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                Observed
              </span>
              <span>{formatTime(detail.occurred_at)}</span>
            </span>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Link
            href={backHref}
            className="inline-flex h-7 items-center rounded-md border border-base-200 bg-base-50 px-3 text-xs font-semibold text-ink-700 hover:bg-base-700"
          >
            Back to trajectory
          </Link>
        </div>
      </div>

      <PostureStrip
        items={[
          {
            label: "Source",
            value: <Token value={detail.source_type} className={sourceTone(detail.source_type)} />,
          },
          {
            label: "Assurance",
            value: (
              <span className="inline-flex items-center gap-1.5 text-sm font-semibold">
                <span
                  className={cn(
                    "size-1.5 rounded-full",
                    detail.assurance_level === "HIGH"
                      ? "bg-accent-600"
                      : detail.assurance_level === "LOW"
                        ? "bg-warn-600"
                        : "bg-ink-400",
                  )}
                />
                {detail.assurance_level}
              </span>
            ),
          },
          {
            label: "Handling",
            value: (
              <Token
                value={detail.content_handling_mode}
                className="border-base-200 bg-base-100 text-ink-700"
              />
            ),
          },
          {
            label: "Redaction",
            value: (
              <Token
                value={detail.redaction_status}
                className={
                  detail.redaction_status === "FAILED"
                    ? "border-danger-500/30 bg-danger-100 text-danger-700"
                    : "border-base-200 bg-base-100 text-ink-700"
                }
              />
            ),
          },
          {
            label: "Content",
            value: (
              <Token
                value={detail.content_status ?? "UNKNOWN"}
                className={
                  detail.content_status === "AVAILABLE"
                    ? "border-accent-200 bg-accent-50 text-accent-700"
                    : "border-warn-100 bg-warn-50 text-warn-700"
                }
              />
            ),
          },
          ...(contentAccess
            ? [
                {
                  label: "Access",
                  value: (
                    <Token
                      value={contentAccess}
                      className="border-accent-200 bg-accent-50 text-accent-700"
                    />
                  ),
                },
              ]
            : []),
        ]}
      />

      {(trajectory?.ai_system_name ||
        trajectory?.agent_name ||
        client ||
        trajectory?.conversation_id ||
        trajectory?.runtime_identity_name) && (
        <Panel title="Trajectory context">
          <MetaGrid
            items={[
              { label: "AI system", value: trajectory?.ai_system_name ?? "—" },
              {
                label: "Agent",
                value: trajectory?.agent_name
                  ? `${trajectory.agent_name}${
                      trajectory.agent_version_number != null
                        ? ` · v${trajectory.agent_version_number}`
                        : ""
                    }`
                  : "—",
              },
              { label: "Runtime", value: trajectory?.runtime_identity_name ?? "—" },
              { label: "Client", value: client ?? "—" },
              {
                label: "Conversation",
                value: (
                  <TechnicalValue className="text-ink-700">
                    {trajectory?.conversation_id ?? "—"}
                  </TechnicalValue>
                ),
              },
              {
                label: "Control",
                value: (
                  <TechnicalValue className="text-ink-700">
                    {trajectory?.deployment_control ?? "—"}
                  </TechnicalValue>
                ),
              },
            ]}
          />
          {trajectory?.delegation?.delegator_id ? (
            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-base-200 pt-3 text-xs text-ink-500">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                Delegation
              </span>
              <TechnicalValue className="text-ink-700">
                {trajectory.delegation.delegator_type}:{trajectory.delegation.delegator_id}
              </TechnicalValue>
              {trajectory.delegation.status ? (
                <Token
                  value={trajectory.delegation.status}
                  className="border-accent-200 bg-accent-50 text-accent-700"
                />
              ) : null}
            </div>
          ) : null}
        </Panel>
      )}

      <div className={cn("grid gap-4", related.length > 0 && "xl:grid-cols-[minmax(0,1fr)_320px]")}>
        <Panel
          title="Content"
          description="Retained evidence for this event."
          data-testid="evidence-event-content"
          actions={
            content ? (
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-ink-400">
                  {content.length.toLocaleString()} chars
                </span>
                <CopyButton value={content} />
              </div>
            ) : null
          }
        >
          {(observedModel || client) && (
            <div className="mb-3 flex flex-wrap gap-2">
              {observedModel ? (
                <span className="inline-flex items-center gap-1.5 rounded-md border border-base-200 bg-base-100 px-2 py-1 text-xs text-ink-600">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                    Model
                  </span>
                  {observedModel}
                </span>
              ) : null}
              {client ? (
                <span className="inline-flex items-center gap-1.5 rounded-md border border-base-200 bg-base-100 px-2 py-1 text-xs text-ink-600">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                    Client
                  </span>
                  {client}
                </span>
              ) : null}
            </div>
          )}
          {content ? (
            <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-md border border-base-200 bg-base-100 p-4 font-mono text-[13px] leading-6 text-ink-800">
              {content}
            </pre>
          ) : (
            <div
              className="flex min-h-40 flex-col items-center justify-center rounded-md border border-dashed border-base-200 bg-base-100 px-6 py-8 text-center"
              data-testid="evidence-content-unavailable"
            >
              <p className="whitespace-pre-line text-sm text-ink-600">{unavailable}</p>
              {observedModel && detail.event_type === "MODEL_REQUEST_OBSERVED" ? (
                <p className="mt-3 text-xs text-ink-500">Observed Model: {observedModel}</p>
              ) : null}
            </div>
          )}
        </Panel>

        {related.length > 0 ? (
          <Panel title="Related events" description={`${related.length} in this trajectory`}>
            <ul className="max-h-[36rem] space-y-1.5 overflow-auto">
              {related.map((relatedEvent) => {
                const current = relatedEvent.id === detail.id;
                return (
                  <li key={relatedEvent.id}>
                    <Link
                      href={`/runtime/trajectories/${trajectoryId}/evidence/${relatedEvent.id}`}
                      aria-current={current ? "page" : undefined}
                      className={cn(
                        "flex items-start gap-3 rounded-md border px-2.5 py-2 transition",
                        current
                          ? "border-accent-200 bg-accent-50"
                          : "border-transparent hover:border-base-200 hover:bg-base-100",
                      )}
                    >
                      <span className="mt-0.5 w-6 shrink-0 font-mono text-[11px] text-ink-400">
                        {String(relatedEvent.sequence_number).padStart(2, "0")}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-ink-800">
                          {humanEventLabel(relatedEvent.event_type)}
                        </span>
                        <span className="mt-1 flex flex-wrap items-center gap-1.5">
                          <Token
                            value={relatedEvent.source_type}
                            className={sourceTone(relatedEvent.source_type)}
                          />
                          <span className="text-[11px] text-ink-400">
                            {relatedEvent.assurance_level.toLowerCase()}
                          </span>
                        </span>
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </Panel>
        ) : null}
      </div>

      <Panel title="Integrity">
        <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <div className="min-w-0 sm:col-span-2 xl:col-span-3">
            <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
              Digest
            </dt>
            <dd className="mt-1 flex items-start justify-between gap-3">
              <TechnicalValue className="break-all text-ink-700">
                {detail.payload_digest ?? "—"}
              </TechnicalValue>
              {detail.payload_digest ? <CopyButton value={detail.payload_digest} /> : null}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
              Recorded
            </dt>
            <dd className="mt-1 text-sm text-ink-700">{formatTime(detail.recorded_at)}</dd>
          </div>
          <div className="min-w-0">
            <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
              Correlation
            </dt>
            <dd className="mt-1">
              <TechnicalValue className="break-all text-ink-700">
                {detail.correlation_id ?? "—"}
              </TechnicalValue>
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
              Trace
            </dt>
            <dd className="mt-1">
              <TechnicalValue className="break-all text-ink-700">
                {detail.trace_id ?? "—"}
              </TechnicalValue>
            </dd>
          </div>
          <div className="min-w-0 sm:col-span-2 xl:col-span-3">
            <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
              Source reference
            </dt>
            <dd className="mt-1">
              <TechnicalValue className="break-all text-ink-700">
                {detail.source_reference || "—"}
              </TechnicalValue>
            </dd>
          </div>
        </dl>
      </Panel>

      {detail.artifacts?.length > 0 ? (
        <Panel title="Artifacts" description={`${detail.artifacts.length} attached`}>
          <ul className="grid gap-3 lg:grid-cols-2">
            {detail.artifacts.map((artifact) => (
              <ArtifactCard key={artifact.id} artifact={artifact} />
            ))}
          </ul>
        </Panel>
      ) : null}

      {attributes.length > 0 || detail.payload ? (
        <Panel
          title="Recorded attributes"
          actions={
            detail.payload ? (
              <Button size="sm" variant="ghost" onClick={() => setShowRaw((value) => !value)}>
                {showRaw ? "Hide raw payload" : "View raw payload"}
              </Button>
            ) : null
          }
        >
          {attributes.length > 0 ? (
            <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {attributes.map(([key, value]) => (
                <div key={key} className="min-w-0">
                  <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                    {humanizeKey(key)}
                  </dt>
                  <dd className="mt-1 text-sm text-ink-700">
                    <AttributeValue value={value} />
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-sm text-ink-500">No additional attributes were recorded.</p>
          )}
          {showRaw && detail.payload ? (
            <pre className="mt-4 max-h-80 overflow-auto whitespace-pre-wrap rounded-md border border-base-200 bg-base-100 p-3 font-mono text-[11px] leading-5 text-ink-600">
              {JSON.stringify(detail.payload, null, 2)}
            </pre>
          ) : null}
        </Panel>
      ) : null}
    </div>
  );
}
