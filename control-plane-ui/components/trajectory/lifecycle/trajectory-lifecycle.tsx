"use client";

import Link from "next/link";
import type { LifecycleStage, TrajectoryLifecycle } from "@/lib/types";
import { StatusBadge } from "@/components/registry/status-badge";

function formatTime(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

/** Coerce lifecycle labels that may arrive as objects (e.g. action_summary). */
function stageLabel(value: unknown, fallback = "Stage"): string {
  if (typeof value === "string" && value.trim()) return value;
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["tool_key", "tool_name", "name", "action", "label"]) {
      const candidate = record[key];
      if (typeof candidate === "string" && candidate.trim()) return candidate;
    }
    const target = record.target;
    if (target && typeof target === "object") {
      const t = target as Record<string, unknown>;
      for (const key of ["tool_key", "name", "resource"]) {
        const candidate = t[key];
        if (typeof candidate === "string" && candidate.trim()) return candidate;
      }
    }
  }
  return fallback;
}

function StageStatus({ status }: { status: string }) {
  return <StatusBadge status={status} />;
}

function AssuranceLine({ evidence }: { evidence?: { source?: string; assurance?: string } }) {
  if (!evidence) return null;
  return (
    <p className="text-xs text-muted-foreground">
      Evidence: {evidence.source ?? "—"} · Assurance: {evidence.assurance ?? "—"}
    </p>
  );
}

function contentViewLabel(stage: LifecycleStage): string {
  const availability = (stage.content?.availability ?? "").toUpperCase();
  if (availability === "HASH_ONLY") return "View Digest";
  if (availability === "REDACTED") {
    return stage.type === "OUTPUT" ? "View Redacted Output" : "View Redacted Input";
  }
  if (availability === "METADATA_ONLY" || availability === "DO_NOT_STORE") {
    return "View Content Status";
  }
  switch (stage.type) {
    case "INPUT":
      return "View User Input";
    case "MODEL":
      return "View Model Request";
    case "OUTPUT":
      return "View AI Output";
    default:
      return "View Details";
  }
}

function ContentBlock({
  content,
  onView,
  viewLabel,
}: {
  content?: { availability?: string; preview?: string | null; reason?: string | null };
  onView?: () => void;
  viewLabel?: string;
}) {
  if (!content) return null;
  return (
    <div className="mt-2 space-y-1">
      {content.preview ? (
        <p className="text-sm text-ink-700">&ldquo;{content.preview}&rdquo;</p>
      ) : (
        <p className="text-xs text-muted-foreground">
          {content.availability}
          {content.reason ? ` — ${content.reason}` : ""}
        </p>
      )}
      {onView && (
        <button
          type="button"
          className="text-sm text-primary hover:underline"
          onClick={onView}
          data-testid="lifecycle-view-content"
        >
          {viewLabel ?? "View details"}
        </button>
      )}
    </div>
  );
}

function ActionStage({
  stage,
  trajectoryId,
  onSelect,
}: {
  stage: LifecycleStage;
  trajectoryId: string;
  onSelect?: (stage: LifecycleStage) => void;
}) {
  const firstEvent = stage.event_ids?.[0];
  return (
    <div
      className="rounded border border-border bg-base-100 p-4"
      data-testid={`lifecycle-action-${stage.id}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Action</p>
          <h3 className="text-base font-semibold">{stageLabel(stage.label, "Action")}</h3>
        </div>
        <StageStatus status={stage.status} />
      </div>
      <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs text-muted-foreground">Authority</dt>
          <dd>{stage.authority?.status ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Delegation</dt>
          <dd>
            {stage.authority?.delegation
              ? `${stage.authority.delegation.delegator_type ?? "Delegation"} · ${
                  stage.authority.delegation.status ?? ""
                }`
              : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Policy</dt>
          <dd>
            {stage.policy?.status === "EVALUATED"
              ? `${stage.policy.matched_rules?.[0]?.name ?? "Policy"} → ${
                  stage.policy.decision ?? "—"
                }`
              : (stage.policy?.status ?? "—")}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Approval</dt>
          <dd>
            {stage.approval?.required ? (stage.approval.status ?? "REQUIRED") : "NOT REQUIRED"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Enforcement</dt>
          <dd>
            {stage.enforcement?.decision ?? "—"}
            {stage.enforcement?.mode ? ` · ${stage.enforcement.mode}` : ""}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Execution</dt>
          <dd>
            {stage.execution?.status ?? "—"}
            {stage.execution?.duration_ms != null ? ` · ${stage.execution.duration_ms} ms` : ""}
          </dd>
        </div>
      </dl>
      {stage.result && (
        <div className="mt-2">
          <p className="text-xs text-muted-foreground">Result</p>
          <ContentBlock
            content={stage.result}
            onView={onSelect ? () => onSelect(stage) : undefined}
            viewLabel="View Tool Result"
          />
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-3">
        {onSelect && (
          <button
            type="button"
            className="text-sm text-primary hover:underline"
            onClick={() => onSelect(stage)}
          >
            View details
          </button>
        )}
        {firstEvent && (
          <Link
            href={`/runtime/trajectories/${trajectoryId}/evidence/${firstEvent}`}
            className="text-sm text-primary hover:underline"
          >
            Open evidence
          </Link>
        )}
      </div>
    </div>
  );
}

function GenericStage({
  stage,
  trajectoryId,
  index,
  onSelect,
  highlighted,
}: {
  stage: LifecycleStage;
  trajectoryId: string;
  index: number;
  onSelect?: (stage: LifecycleStage) => void;
  highlighted?: boolean;
}) {
  const firstEvent = stage.event_ids?.[0];
  const canOpenDrawer = Boolean(onSelect && firstEvent);
  return (
    <div
      className={`rounded border p-4 ${
        highlighted ? "border-primary ring-2 ring-primary/30" : "border-border"
      }`}
      data-testid={`lifecycle-stage-${stage.type.toLowerCase()}`}
      id={firstEvent ? `lifecycle-event-${firstEvent}` : undefined}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            [{index}] {stage.type}
          </p>
          <h3 className="text-base font-semibold">{stageLabel(stage.label)}</h3>
          <p className="text-xs text-muted-foreground">{formatTime(stage.occurred_at)}</p>
        </div>
        <StageStatus status={stage.status} />
      </div>
      {stage.type === "MODEL" && stage.model?.observed_model && (
        <div className="mt-2 space-y-1">
          <p className="font-mono text-sm">{stage.model.observed_model}</p>
          {stage.model.observational && (
            <p className="text-xs text-muted-foreground">
              Observed model (client-reported — not RAI-verified)
            </p>
          )}
        </div>
      )}
      <ContentBlock
        content={stage.content}
        onView={canOpenDrawer ? () => onSelect!(stage) : undefined}
        viewLabel={contentViewLabel(stage)}
      />
      <AssuranceLine evidence={stage.evidence} />
      {firstEvent && (
        <div className="mt-2">
          <Link
            href={`/runtime/trajectories/${trajectoryId}/evidence/${firstEvent}`}
            className="text-xs text-muted-foreground hover:underline"
          >
            Open full evidence page
          </Link>
        </div>
      )}
    </div>
  );
}

export function TrajectoryLifecycleView({
  lifecycle,
  trajectoryId,
  onSelectStage,
  highlightEventId,
}: {
  lifecycle: TrajectoryLifecycle;
  trajectoryId: string;
  onSelectStage?: (stage: LifecycleStage) => void;
  highlightEventId?: string | null;
}) {
  return (
    <div className="space-y-4" data-testid="trajectory-lifecycle">
      <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
        <span>Started: {formatTime(lifecycle.summary.started_at)}</span>
        <span>Duration: {lifecycle.summary.duration_ms ?? "—"} ms</span>
        <span>Assurance: {lifecycle.summary.assurance ?? "—"}</span>
        <span>
          Coverage:{" "}
          {lifecycle.summary.completeness_pct != null
            ? `${lifecycle.summary.completeness_pct}%`
            : "—"}
        </span>
      </div>
      {lifecycle.stages.map((stage, index) =>
        stage.type === "ACTION" ? (
          <ActionStage
            key={stage.id}
            stage={stage}
            trajectoryId={trajectoryId}
            onSelect={onSelectStage}
          />
        ) : (
          <GenericStage
            key={stage.id}
            stage={stage}
            trajectoryId={trajectoryId}
            index={index + 1}
            onSelect={onSelectStage}
            highlighted={Boolean(highlightEventId && stage.event_ids?.includes(highlightEventId))}
          />
        ),
      )}
    </div>
  );
}
