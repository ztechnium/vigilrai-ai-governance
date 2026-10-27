"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { getTrajectoryEvent } from "@/lib/api";
import { contentStatusMessage, extractEventContent, humanEventLabel } from "@/lib/evidence-content";
import type { EvidenceEventDetail, LifecycleStage } from "@/lib/types";

function formatTime(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function DlRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] gap-2 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="break-all">{children}</dd>
    </div>
  );
}

function provenanceFromPayload(payload?: Record<string, unknown> | null) {
  if (!payload) return null;
  const keys = [
    "configuration_id",
    "configuration_version",
    "configuration_digest",
    "configuration_source",
    "configuration_environment",
    "deployment_id",
    "release_id",
  ] as const;
  const found: Record<string, string> = {};
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) found[key] = value;
  }
  return Object.keys(found).length ? found : null;
}

function viewLabelForStage(stage: LifecycleStage): string {
  switch (stage.type) {
    case "INPUT":
      return "View User Input";
    case "MODEL":
      return "View Model Request";
    case "OUTPUT":
      return "View AI Output";
    case "ACTION":
      return "View Action Details";
    default:
      return "View Content";
  }
}

export function EvidenceContentDrawer({
  trajectoryId,
  stage,
  onClose,
}: {
  trajectoryId: string;
  stage: LifecycleStage | null;
  onClose: () => void;
}) {
  const eventId = stage?.event_ids?.[0] ?? null;
  const [detail, setDetail] = useState<EvidenceEventDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!stage || !eventId) {
      setDetail(null);
      setError(null);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    getTrajectoryEvent(trajectoryId, eventId)
      .then((res) => {
        if (!active) return;
        setDetail(res.data);
      })
      .catch((err: Error) => {
        if (!active) return;
        setError(err.message);
        setDetail(null);
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [trajectoryId, eventId, stage]);

  if (!stage) return null;

  const content = detail ? extractEventContent(detail) : null;
  const unavailable = detail ? contentStatusMessage(detail) : null;
  const provenance = provenanceFromPayload(detail?.payload);
  const observedModel =
    typeof detail?.payload?.observed_model === "string"
      ? detail.payload.observed_model
      : (stage.model?.observed_model ?? null);
  const title = stage.type === "MODEL" ? "View Model Request" : viewLabelForStage(stage);

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-black/20"
      data-testid="evidence-content-drawer"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
    >
      <aside
        className="flex h-full w-full max-w-lg flex-col border-l border-border bg-background shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{stage.type}</p>
            <h2 className="text-lg font-semibold">{title}</h2>
            <p className="text-xs text-muted-foreground">{stageLabelSafe(stage)}</p>
          </div>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {loading && <p className="text-sm text-muted-foreground">Loading content…</p>}
          {error && <p className="text-sm text-destructive">{error}</p>}

          {!loading && !error && (
            <>
              <section className="space-y-2">
                <h3 className="text-sm font-semibold">Content</h3>
                {content ? (
                  <pre className="whitespace-pre-wrap break-words rounded border border-border bg-base-50 p-3 text-sm">
                    {content}
                  </pre>
                ) : unavailable ? (
                  <p
                    className="text-sm text-muted-foreground"
                    data-testid="drawer-content-unavailable"
                  >
                    {unavailable}
                  </p>
                ) : stage.content?.preview ? (
                  <p className="text-sm">&ldquo;{stage.content.preview}&rdquo;</p>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    {stage.content?.availability ?? "Content not available"}
                    {stage.content?.reason ? ` — ${stage.content.reason}` : ""}
                  </p>
                )}
              </section>

              <section className="space-y-2">
                <h3 className="text-sm font-semibold">Metadata</h3>
                <dl className="space-y-2">
                  <DlRow label="Source">
                    {detail?.source_type ?? stage.evidence?.source ?? "—"}
                  </DlRow>
                  <DlRow label="Assurance">
                    {detail?.assurance_level ?? stage.evidence?.assurance ?? "—"}
                  </DlRow>
                  <DlRow label="Observed At">
                    {formatTime(detail?.occurred_at ?? stage.occurred_at)}
                  </DlRow>
                  <DlRow label="Handling Mode">
                    {detail?.content_handling_mode ?? stage.content?.availability ?? "—"}
                  </DlRow>
                  <DlRow label="Redaction">{detail?.redaction_status ?? "—"}</DlRow>
                  <DlRow label="Digest">{detail?.payload_digest ?? "—"}</DlRow>
                  <DlRow label="Model">{observedModel ?? "—"}</DlRow>
                  <DlRow label="Correlation ID">{detail?.correlation_id ?? "—"}</DlRow>
                  <DlRow label="Event Type">
                    {detail ? humanEventLabel(detail.event_type) : "—"}
                  </DlRow>
                </dl>
              </section>

              {provenance && (
                <section className="space-y-2">
                  <h3 className="text-sm font-semibold">External Configuration</h3>
                  <p className="text-xs text-muted-foreground">
                    Application-reported provenance (not RAI-owned prompt/persona content).
                  </p>
                  <dl className="space-y-2">
                    {Object.entries(provenance).map(([key, value]) => (
                      <DlRow key={key} label={key.replace(/_/g, " ")}>
                        <span className="font-mono text-xs">{value}</span>
                      </DlRow>
                    ))}
                  </dl>
                </section>
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

function stageLabelSafe(stage: LifecycleStage): string {
  if (typeof stage.label === "string") return stage.label;
  return stage.type;
}
