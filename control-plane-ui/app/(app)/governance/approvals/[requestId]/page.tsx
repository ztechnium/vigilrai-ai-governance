"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { MetaGrid, PostureStrip, TechnicalValue } from "@/components/console/page-parts";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Breadcrumbs } from "@/components/registry/breadcrumbs";
import { DelegationScopeSummary } from "@/components/registry/delegation-scope-summary";
import { FormField } from "@/components/registry/form-field";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import {
  approveApprovalRequest,
  cancelApprovalRequest,
  getApprovalRequest,
  rejectApprovalRequest,
} from "@/lib/api";
import { pickActingMembershipId } from "@/lib/acting-membership";
import { useOrganization } from "@/lib/hooks/use-auth";
import type { ApprovalRequestDetail } from "@/lib/types";

function formatTime(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function shortId(value?: string | null) {
  if (!value) return "—";
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

function formatParamValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return value.toLocaleString();
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function DlRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-base-200 py-2 last:border-0">
      <dt className="shrink-0 text-xs font-semibold uppercase tracking-wide text-ink-400">
        {label}
      </dt>
      <dd className="min-w-0 text-right text-sm text-ink-800">{children}</dd>
    </div>
  );
}

function HumanReadableParameters({ parameters }: { parameters: Record<string, unknown> }) {
  const entries = Object.entries(parameters ?? {});
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No parameters</p>;
  }
  return (
    <dl className="grid gap-2 sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="rounded-md border border-base-200 bg-base-50 px-3 py-2">
          <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">{key}</dt>
          <dd className="mt-1 break-words text-sm font-medium text-ink-800">
            {formatParamValue(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default function ApprovalDetailPage() {
  const params = useParams();
  const router = useRouter();
  const requestId = params.requestId as string;
  const [request, setRequest] = useState<ApprovalRequestDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [showApproveConfirm, setShowApproveConfirm] = useState(false);
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [decisionReason, setDecisionReason] = useState("");
  const [acting, setActing] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const { activeOrganization } = useOrganization();

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getApprovalRequest(requestId)
      .then((res) => setRequest(res.data))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [requestId]);

  useEffect(() => {
    load();
  }, [load]);

  const caps = request?.viewer_capabilities;
  const canApprove = Boolean(caps?.can_approve);
  const canReject = Boolean(caps?.can_reject);
  const canCancel = Boolean(caps?.can_cancel);
  const canDecide = canApprove || canReject;
  const isTerminal = Boolean(
    request && ["REJECTED", "EXPIRED", "CANCELLED", "CONSUMED"].includes(request.status),
  );
  const awaitingExecution = request?.status === "APPROVED" && !request.consumed_at;
  const isConsumed = request?.status === "CONSUMED";
  const latestDecision = request?.decisions?.[request.decisions.length - 1];
  const expiresSoon = useMemo(() => {
    if (!request?.expires_at || request.status !== "PENDING") return false;
    const ms = new Date(request.expires_at).getTime() - Date.now();
    return Number.isFinite(ms) && ms > 0 && ms < 60 * 60 * 1000;
  }, [request]);

  const actingMembershipId = () => {
    const stage = request?.plan?.stages?.find(
      (item) => item.stage_index === request.plan?.current_stage_index,
    );
    return pickActingMembershipId(activeOrganization?.memberships, stage?.required_roles);
  };

  const handleApprove = async () => {
    const membershipId = actingMembershipId();
    if (!membershipId) {
      setActionError("Your organization membership is missing. Sign in again, then retry.");
      return;
    }
    setActing(true);
    setActionError(null);
    try {
      const res = await approveApprovalRequest(requestId, {
        acting_membership_id: membershipId,
        decision_reason: decisionReason || undefined,
      });
      setRequest(res.data);
      setShowApproveConfirm(false);
      setDecisionReason("");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Approval failed");
      load();
    } finally {
      setActing(false);
    }
  };

  const handleReject = async () => {
    const requiresReason = request?.risk_tier === "HIGH" || request?.risk_tier === "CRITICAL";
    if (requiresReason && !decisionReason.trim()) {
      setActionError("Decision reason is required for HIGH/CRITICAL risk actions");
      return;
    }
    const membershipId = actingMembershipId();
    if (!membershipId) {
      setActionError("Your organization membership is missing. Sign in again, then retry.");
      return;
    }
    setActing(true);
    setActionError(null);
    try {
      const res = await rejectApprovalRequest(requestId, {
        acting_membership_id: membershipId,
        decision_reason: decisionReason || undefined,
      });
      setRequest(res.data);
      setShowRejectForm(false);
      setDecisionReason("");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Rejection failed");
      load();
    } finally {
      setActing(false);
    }
  };

  const handleCancel = async () => {
    setActing(true);
    setActionError(null);
    try {
      const res = await cancelApprovalRequest(requestId);
      setRequest(res.data);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Cancel failed");
      load();
    } finally {
      setActing(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading approval request…</p>;
  }

  if (error || !request) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-destructive">{error ?? "Approval request not found"}</p>
        <Button variant="secondary" onClick={() => router.push("/governance/approvals")}>
          Back to inbox
        </Button>
      </div>
    );
  }

  const identity = request.identity;
  const toolLabel = request.tool_name ?? request.tool_key ?? "—";
  const targetLabel = request.target_type
    ? `${request.target_type}${request.target_identifier ? ` · ${request.target_identifier}` : ""}`
    : "—";

  return (
    <div className="space-y-6" data-testid="approval-detail-page">
      <Breadcrumbs
        items={[
          { label: "Approvals", href: "/governance/approvals" },
          { label: shortId(request.id) },
        ]}
      />
      <SectionHeader
        title={request.human_summary ?? "Approval Detail"}
        subtitle={
          request.business_reason ||
          request.requirement_reason ||
          "Review the exact action, authority context, and governance metadata."
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={request.status} />
            {request.risk_tier ? <StatusBadge status={request.risk_tier} /> : null}
            <Button variant="secondary" size="sm" onClick={() => void load()}>
              Refresh
            </Button>
          </div>
        }
      />

      {awaitingExecution ? (
        <Panel title="Approved — awaiting execution">
          <p className="text-sm text-muted-foreground">
            Human approval is complete. The AI system has not redeemed this approval yet. It must
            retry the exact action through VigilRAI before expiry ({formatTime(request.expires_at)}
            ).
          </p>
        </Panel>
      ) : null}

      {isConsumed ? (
        <Panel title="Consumed">
          <p className="text-sm text-muted-foreground">
            This one-time approval was consumed. Related enforcement receipts are linked below.
          </p>
        </Panel>
      ) : null}

      <PostureStrip
        items={[
          { label: "Status", value: <StatusBadge status={request.status} /> },
          {
            label: "Risk",
            value: request.risk_tier ? <StatusBadge status={request.risk_tier} /> : "—",
            tone:
              request.risk_tier === "HIGH" || request.risk_tier === "CRITICAL"
                ? "text-warn-700"
                : undefined,
          },
          { label: "Tool", value: <span className="text-xs">{toolLabel}</span> },
          {
            label: "Integration",
            value: (
              <span className="text-xs">
                {request.integration_name ?? request.integration_type ?? "—"}
              </span>
            ),
          },
          {
            label: "Created",
            value: <span className="text-xs">{formatTime(request.created_at)}</span>,
          },
          {
            label: "Expires",
            value: (
              <span className={`text-xs ${expiresSoon ? "font-semibold text-warn-700" : ""}`}>
                {formatTime(request.expires_at)}
                {expiresSoon ? " · soon" : ""}
              </span>
            ),
          },
        ]}
      />

      {actionError ? (
        <Panel title="Action conflict">
          <p className="text-sm text-destructive">{actionError}</p>
        </Panel>
      ) : null}

      {request.identity_unavailable ? (
        <Panel title="Authority unavailable">
          <p className="text-sm text-destructive">
            {request.identity_unavailable}
            {request.identity_unavailable_reason ? ` (${request.identity_unavailable_reason})` : ""}
          </p>
        </Panel>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Identity">
          <dl>
            <DlRow label="AI System">
              <Link
                href={`/governance/registry/${request.ai_system_id}`}
                className="text-primary hover:underline"
              >
                {identity?.ai_system.name ?? shortId(request.ai_system_id)}
              </Link>
            </DlRow>
            <DlRow label="Agent">
              {identity?.agent.name ?? shortId(request.agent_id)}
              {identity?.agent_version ? ` · v${identity.agent_version.version_number}` : ""}
            </DlRow>
            <DlRow label="Runtime Identity">
              <Link
                href={`/governance/runtime-identities/${request.runtime_identity_id}`}
                className="text-primary hover:underline"
              >
                {identity?.runtime_identity.name ?? shortId(request.runtime_identity_id)}
              </Link>
            </DlRow>
            <DlRow label="Environment">{identity?.runtime_identity.environment ?? "—"}</DlRow>
            <DlRow label="Initiating Principal">
              {request.initiating_principal ?? identity?.initiating_principal ?? "—"}
            </DlRow>
            <DlRow label="Created By">{request.created_by ?? "—"}</DlRow>
            <DlRow label="Delegation">
              {request.delegation_id ? (
                <TechnicalValue>{shortId(request.delegation_id)}</TechnicalValue>
              ) : (
                "—"
              )}
            </DlRow>
          </dl>
        </Panel>

        <Panel title="Risk & Governance">
          <dl>
            <DlRow label="Risk Tier">
              {request.risk_tier ? <StatusBadge status={request.risk_tier} /> : "—"}
            </DlRow>
            <DlRow label="Risk Score">
              {request.risk_score != null ? String(request.risk_score) : "—"}
            </DlRow>
            <DlRow label="Requirement">{request.requirement_reason ?? "—"}</DlRow>
            <DlRow label="Policy Ref">{request.approval_policy_reference ?? "—"}</DlRow>
            <DlRow label="Action Type">{request.action_type ?? "—"}</DlRow>
            <DlRow label="Decided">{formatTime(request.decided_at)}</DlRow>
            <DlRow label="Consumed">{formatTime(request.consumed_at)}</DlRow>
            <DlRow label="Correlation">
              <TechnicalValue>{request.correlation_id ?? "—"}</TechnicalValue>
            </DlRow>
          </dl>
        </Panel>
      </div>

      <Panel title="Proposed Action">
        <MetaGrid
          items={[
            { label: "Tool", value: toolLabel },
            {
              label: "Tool Key",
              value: <TechnicalValue>{request.tool_key ?? "—"}</TechnicalValue>,
            },
            {
              label: "Integration",
              value: request.integration_name ?? request.integration_type ?? "—",
            },
            { label: "Target", value: targetLabel },
            {
              label: "Business Reason",
              value: request.business_reason ?? "—",
            },
            {
              label: "Action Digest",
              value: <TechnicalValue>{shortId(request.action_digest)}</TechnicalValue>,
            },
          ]}
        />
        <div className="mt-4">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">
            Parameters
          </h4>
          <HumanReadableParameters parameters={request.parameters} />
        </div>
        {request.canonical_action_payload ? (
          <div className="mt-4">
            <Button variant="ghost" size="sm" onClick={() => setShowRaw((value) => !value)}>
              {showRaw ? "Hide" : "Show"} canonical action payload
            </Button>
            {showRaw ? (
              <pre className="mt-2 overflow-x-auto rounded-md border border-base-200 bg-base-50 p-3 font-mono text-[10px] text-ink-500">
                {JSON.stringify(request.canonical_action_payload, null, 2)}
              </pre>
            ) : null}
          </div>
        ) : null}
      </Panel>

      {(identity?.delegation_chain?.length ?? 0) > 0 ? (
        <Panel title="Delegation Chain">
          <ol className="space-y-2">
            {identity?.delegation_chain.map((entry, index) => (
              <li
                key={`${entry.delegation_id}-${index}`}
                className="flex flex-wrap items-center gap-2 rounded-md border border-base-200 bg-base-50 px-3 py-2 text-sm"
              >
                <span className="text-[10px] font-semibold uppercase text-ink-400">
                  #{index + 1}
                </span>
                <StatusBadge status={entry.delegator_type} />
                <span>{entry.delegator_id}</span>
                <TechnicalValue>{shortId(entry.delegation_id)}</TechnicalValue>
              </li>
            ))}
          </ol>
        </Panel>
      ) : null}

      {request.effective_scope ? (
        <Panel title="Effective Authority">
          <DelegationScopeSummary
            versionId={request.agent_version_id}
            scope={{
              model_ids: request.effective_scope.model_ids ?? [],
              data_source_ids: request.effective_scope.data_source_ids ?? [],
              mcp_server_ids: request.effective_scope.mcp_server_ids ?? [],
              tool_ids: request.effective_scope.tool_ids ?? [],
            }}
          />
        </Panel>
      ) : null}

      {request.plan ? (
        <Panel title="Approval Plan">
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            <StatusBadge status={request.plan.status} />
            <span className="text-muted-foreground">
              Current stage #{request.plan.current_stage_index}
            </span>
          </div>
          <ol className="space-y-3">
            {(request.plan.stages ?? []).map((stage) => (
              <li key={stage.id} className="rounded-md border border-base-200 bg-base-50 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold uppercase text-ink-400">
                    Stage {stage.stage_index}
                  </span>
                  <span className="text-sm font-medium">{stage.name ?? "—"}</span>
                  <StatusBadge status={stage.status} />
                  {stage.mode ? <StatusBadge status={stage.mode} /> : null}
                </div>
                {(stage.required_roles?.length ?? 0) > 0 ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Roles: {stage.required_roles?.join(", ")}
                    {stage.quorum_count != null ? ` · quorum ${stage.quorum_count}` : ""}
                  </p>
                ) : null}
                {(stage.decisions?.length ?? 0) > 0 ? (
                  <ul className="mt-2 space-y-1 text-xs">
                    {stage.decisions?.map((decision) => (
                      <li key={decision.id} className="flex flex-wrap gap-2">
                        <StatusBadge status={decision.decision} />
                        <span>{decision.decided_by}</span>
                        <span className="text-muted-foreground">
                          {formatTime(decision.decided_at)}
                        </span>
                        {decision.decision_reason ? (
                          <span className="text-muted-foreground">
                            — {decision.decision_reason}
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ol>
        </Panel>
      ) : null}

      {(request.decisions?.length ?? 0) > 0 ? (
        <Panel title="Decision History">
          <ol className="space-y-3">
            {request.decisions.map((decision, index) => (
              <li key={decision.id} className="rounded-md border border-base-200 bg-base-50 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[10px] font-semibold uppercase text-ink-400">
                    #{index + 1}
                  </span>
                  <StatusBadge status={decision.decision} />
                  <span className="text-sm">{decision.decided_by}</span>
                  <span className="text-xs text-muted-foreground">
                    {formatTime(decision.decided_at)}
                  </span>
                </div>
                <dl className="mt-2 grid gap-1 text-xs sm:grid-cols-2">
                  <div>
                    <span className="text-muted-foreground">Reason: </span>
                    {decision.decision_reason ?? "—"}
                  </div>
                  <div>
                    <span className="text-muted-foreground">Assurance: </span>
                    {decision.authentication_assurance ?? "—"}
                  </div>
                </dl>
              </li>
            ))}
          </ol>
        </Panel>
      ) : latestDecision ? (
        <Panel title="Decision">
          <dl>
            <DlRow label="Status">
              <StatusBadge status={latestDecision.decision} />
            </DlRow>
            <DlRow label="Decided By">{latestDecision.decided_by}</DlRow>
            <DlRow label="Decided At">{formatTime(latestDecision.decided_at)}</DlRow>
            <DlRow label="Reason">{latestDecision.decision_reason ?? "—"}</DlRow>
          </dl>
        </Panel>
      ) : null}

      {(request.related_enforcement_receipts?.length ?? 0) > 0 ? (
        <Panel title="Related Enforcement">
          <ul className="divide-y divide-base-200">
            {request.related_enforcement_receipts?.map((receipt) => (
              <li
                key={receipt.id}
                className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm"
              >
                <div className="space-y-1">
                  <Link
                    href={receipt.href}
                    className="font-mono text-xs text-primary hover:underline"
                  >
                    {shortId(receipt.id)}
                  </Link>
                  <div className="text-xs text-muted-foreground">
                    {formatTime(receipt.started_at)}
                    {receipt.execution_source ? ` · ${receipt.execution_source}` : ""}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <StatusBadge status={receipt.enforcement_decision} />
                  <StatusBadge status={receipt.execution_status} />
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      {canDecide ? (
        <div className="sticky bottom-0 z-10 border-t border-base-200 bg-background/95 p-4 backdrop-blur">
          <Panel title="Decision Actions">
            {!showApproveConfirm && !showRejectForm ? (
              <div className="space-y-3">
                {caps?.decision_block_reason && !canApprove ? (
                  <p className="text-sm text-muted-foreground">
                    You cannot approve yet ({caps.decision_block_reason}).
                  </p>
                ) : null}
                <div className="flex flex-wrap gap-3">
                  {canApprove ? (
                    <Button onClick={() => setShowApproveConfirm(true)}>
                      Approve this action once
                    </Button>
                  ) : null}
                  {canReject ? (
                    <Button variant="secondary" onClick={() => setShowRejectForm(true)}>
                      Reject
                    </Button>
                  ) : null}
                  {canCancel ? (
                    <Button variant="ghost" disabled={acting} onClick={() => void handleCancel()}>
                      Cancel request
                    </Button>
                  ) : null}
                </div>
              </div>
            ) : null}

            {showApproveConfirm ? (
              <div className="space-y-4">
                <p className="text-sm">
                  Approve this exact action once for{" "}
                  <strong>
                    {identity?.agent.name ?? "agent"}
                    {identity?.agent_version ? ` v${identity.agent_version.version_number}` : ""}
                  </strong>
                  ?
                </p>
                <p className="text-sm text-muted-foreground">
                  Tool: {toolLabel} · Target: {targetLabel}
                </p>
                <p className="text-sm text-muted-foreground">
                  Expires: {formatTime(request.expires_at)}
                </p>
                <p className="text-sm font-medium text-amber-700">
                  This approval authorizes one exact action digest. It is not permission for future
                  similar actions.
                </p>
                <FormField label="Optional note">
                  <Textarea
                    value={decisionReason}
                    onChange={(e) => setDecisionReason(e.target.value)}
                    rows={3}
                  />
                </FormField>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setShowApproveConfirm(false);
                      setDecisionReason("");
                    }}
                  >
                    Back
                  </Button>
                  <Button onClick={() => void handleApprove()} disabled={acting}>
                    {acting ? "Approving…" : "Confirm — approve once"}
                  </Button>
                </div>
              </div>
            ) : null}

            {showRejectForm ? (
              <div className="space-y-4">
                <FormField label="Decision reason">
                  <Textarea
                    value={decisionReason}
                    onChange={(e) => setDecisionReason(e.target.value)}
                    rows={3}
                    placeholder={
                      request.risk_tier === "HIGH" || request.risk_tier === "CRITICAL"
                        ? "Required for HIGH/CRITICAL risk"
                        : "Optional"
                    }
                  />
                </FormField>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setShowRejectForm(false);
                      setDecisionReason("");
                    }}
                  >
                    Back
                  </Button>
                  <Button variant="secondary" onClick={() => void handleReject()} disabled={acting}>
                    {acting ? "Rejecting…" : "Confirm Reject"}
                  </Button>
                </div>
              </div>
            ) : null}
          </Panel>
        </div>
      ) : null}

      {isTerminal ? (
        <Panel title="Read-only">
          <p className="text-sm text-muted-foreground">
            This request is in a terminal state ({request.status}) and cannot be modified.
          </p>
        </Panel>
      ) : null}
    </div>
  );
}
