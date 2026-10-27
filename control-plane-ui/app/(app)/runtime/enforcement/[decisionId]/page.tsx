"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Breadcrumbs } from "@/components/registry/breadcrumbs";
import { Panel } from "@/components/registry/panel";
import { SectionHeader } from "@/components/section-header";
import { StatusBadge } from "@/components/registry/status-badge";
import { getEnforcementReceipt } from "@/lib/api";
import { formatEnforcementDecision, formatExecutionStatus } from "@/lib/format";
import type { EnforcementReceiptDetail } from "@/lib/types";

function formatParamValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return value.toLocaleString();
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function DlRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

export default function EnforcementDetailPage() {
  const params = useParams();
  const receiptId = params.decisionId as string;
  const [receipt, setReceipt] = useState<EnforcementReceiptDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getEnforcementReceipt(receiptId);
      setReceipt(res.data as EnforcementReceiptDetail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load receipt");
    } finally {
      setLoading(false);
    }
  }, [receiptId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading enforcement receipt...</p>;
  }

  if (error || !receipt) {
    return <p className="text-sm text-destructive">{error ?? "Receipt not found"}</p>;
  }

  const identity = receipt.identity;
  const client = receipt.client_context;
  const action = receipt.action;
  const policy = receipt.policy_evaluation;
  const approval = receipt.approval;
  const execution = receipt.execution;
  const assurance = receipt.assurance;
  const trace = receipt.trace;
  const parameters = (action?.parameters as Record<string, unknown> | undefined) ?? {};

  return (
    <div className="space-y-6" data-testid="enforcement-detail-page">
      <Breadcrumbs
        items={[
          { label: "Runtime Enforcement", href: "/runtime/enforcement" },
          { label: receipt.id.slice(0, 8) },
        ]}
      />
      <SectionHeader
        title="Runtime Action Detail"
        subtitle={receipt.reason ?? "Governance and execution receipt"}
        actions={<StatusBadge status={receipt.decision ?? "UNKNOWN"} />}
      />

      <Panel title="Summary" data-testid="receipt-section-summary">
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <DlRow label="Decision">{formatEnforcementDecision(receipt.decision)}</DlRow>
          <DlRow label="Reason">{receipt.reason ?? "—"}</DlRow>
          <DlRow label="Reason Code">{receipt.reason_code ?? "—"}</DlRow>
          <DlRow label="Execution">{formatExecutionStatus(execution?.status ?? "")}</DlRow>
          <DlRow label="Enforcement Mode">{assurance?.enforcement_mode ?? "—"}</DlRow>
          <DlRow label="Deployment Control">{assurance?.deployment_control ?? "—"}</DlRow>
          <DlRow label="Verification">{assurance?.verification_status ?? "—"}</DlRow>
          <DlRow label="Correlation ID">
            <span className="font-mono text-xs">{trace?.correlation_id ?? "—"}</span>
          </DlRow>
          <DlRow label="Started">
            {receipt.timestamps?.started_at
              ? new Date(receipt.timestamps.started_at).toLocaleString()
              : "—"}
          </DlRow>
        </dl>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Identity" data-testid="receipt-section-identity">
          <dl className="grid gap-2 text-sm">
            <DlRow label="AI System">
              <Link
                href={`/governance/registry/${identity?.ai_system_id}`}
                className="text-primary hover:underline"
              >
                {identity?.ai_system_name ?? identity?.ai_system_id}
              </Link>
            </DlRow>
            <DlRow label="Agent">{identity?.agent_name ?? identity?.agent_id}</DlRow>
            <DlRow label="Agent Version">
              {identity?.agent_version_number != null
                ? `v${identity.agent_version_number}`
                : identity?.agent_version_id}
            </DlRow>
            <DlRow label="Runtime Identity">
              <Link
                href={`/governance/runtime-identities/${identity?.runtime_identity_id}`}
                className="text-primary hover:underline"
              >
                {identity?.runtime_identity_name ?? identity?.runtime_identity_id}
              </Link>
            </DlRow>
            <DlRow label="Delegation">{identity?.delegation_id ?? "—"}</DlRow>
          </dl>
        </Panel>

        <Panel title="Client / Runtime Context" data-testid="receipt-section-client-context">
          <p className="mb-3 text-xs text-muted-foreground">
            Observed client context — not authoritative identity.
          </p>
          <dl className="grid gap-2 text-sm">
            <DlRow label="Client Type">{client?.client_type ?? "—"}</DlRow>
            <DlRow label="Client Version">{client?.client_version ?? "—"}</DlRow>
            <DlRow label="Hook Event">{client?.hook_event ?? "—"}</DlRow>
            <DlRow label="Session ID">
              <span className="font-mono text-xs">{client?.session_id ?? "—"}</span>
            </DlRow>
            <DlRow label="Conversation ID">
              <span className="font-mono text-xs">{client?.conversation_id ?? "—"}</span>
            </DlRow>
            <DlRow label="Generation ID">
              <span className="font-mono text-xs">{client?.generation_id ?? "—"}</span>
            </DlRow>
            <DlRow label="Observed Model">{client?.observed_model ?? "—"}</DlRow>
            <DlRow label="Observed User">{client?.observed_client_user ?? "—"}</DlRow>
          </dl>
        </Panel>

        <Panel title="Action" data-testid="receipt-section-action">
          <dl className="grid gap-2 text-sm">
            <DlRow label="Integration Type">{action?.integration_type ?? "—"}</DlRow>
            <DlRow label="MCP Server">
              {action?.integration_name ?? "—"}
              {action?.integration_id ? (
                <span className="ml-2 font-mono text-xs text-muted-foreground">
                  {action.integration_id}
                </span>
              ) : null}
            </DlRow>
            <DlRow label="Tool">
              {action?.tool_name ?? "—"}
              {action?.tool_id ? (
                <span className="ml-2 font-mono text-xs text-muted-foreground">
                  {action.tool_id}
                </span>
              ) : null}
            </DlRow>
            <DlRow label="Target">{formatParamValue(action?.target)}</DlRow>
            <DlRow label="Action Digest">
              <span className="font-mono text-xs">{action?.action_digest}</span>
            </DlRow>
            <DlRow label="Idempotency Key">{action?.idempotency_key ?? "—"}</DlRow>
          </dl>
          <div className="mt-4" data-testid="receipt-action-parameters">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Action Parameters
            </p>
            {Object.keys(parameters).length === 0 ? (
              <p className="text-sm text-muted-foreground">No parameters</p>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {Object.entries(parameters).map(([key, value]) => (
                  <div key={key} className="rounded-md border border-border px-3 py-2">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">{key}</p>
                    <p className="font-medium">{formatParamValue(value)}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Panel>

        <Panel title="Policy Evaluation" data-testid="receipt-section-policy">
          <dl className="grid gap-2 text-sm">
            <DlRow label="Final Effect">{policy?.final_effect ?? "—"}</DlRow>
            <DlRow label="Precedence">{policy?.precedence ?? "—"}</DlRow>
            <DlRow label="Tool Rules">
              {policy?.tool_rule_enforcement?.status ?? "ACTIVE"} /{" "}
              {policy?.tool_rule_enforcement?.mode ?? "DETERMINISTIC"}
            </DlRow>
            <DlRow label="Content Rules">
              {policy?.content_rule_enforcement?.status ?? "NOT_ACTIVE"}
              {policy?.content_rule_enforcement?.reason
                ? ` (${policy.content_rule_enforcement.reason})`
                : ""}
            </DlRow>
          </dl>
          <div className="mt-4" data-testid="receipt-matched-rules">
            {(policy?.matched_rules?.length ?? 0) > 0 ? (
              <div className="space-y-3">
                {policy?.matched_rules?.map((rule) => (
                  <div
                    key={rule.rule_id}
                    className="rounded-md border border-border p-3 text-sm"
                    data-testid={`matched-rule-${rule.rule_id}`}
                  >
                    <p className="font-medium">{rule.title ?? rule.rule_id}</p>
                    <p className="text-muted-foreground">
                      Effect: {rule.effect ?? "—"} · Matched: {rule.matched ? "true" : "false"}
                    </p>
                    {(rule.conditions?.length ?? 0) > 0 && (
                      <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                        {rule.conditions?.map((cond, idx) => (
                          <li key={`${rule.rule_id}-${idx}`}>
                            {cond.parameter_path} {cond.operator} · matched=
                            {String(cond.matched)}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No matched tool rules.</p>
            )}
          </div>
          {policy?.explanation && (
            <p className="mt-4 rounded-md border border-border bg-muted/30 p-3 text-sm">
              {policy.explanation}
            </p>
          )}
        </Panel>

        <Panel title="Approval" data-testid="receipt-section-approval">
          {!approval?.required ? (
            <p className="text-sm">Not Required</p>
          ) : (
            <dl className="grid gap-2 text-sm">
              <DlRow label="Request">
                <Link
                  href={`/governance/approvals/${approval.approval_request_id}`}
                  className="text-primary hover:underline"
                >
                  {approval.approval_request_id}
                </Link>
              </DlRow>
              <DlRow label="Status">{approval.status}</DlRow>
              <DlRow label="Approver Role">{approval.required_approver_role ?? "—"}</DlRow>
              <DlRow label="Requested">
                {approval.requested_at ? new Date(approval.requested_at).toLocaleString() : "—"}
              </DlRow>
              <DlRow label="Decision Time">
                {approval.decision_time ? new Date(approval.decision_time).toLocaleString() : "—"}
              </DlRow>
              <DlRow label="Approver">{approval.approver ?? "—"}</DlRow>
              <DlRow label="Action Digest">
                <span className="font-mono text-xs">{approval.action_digest ?? "—"}</span>
              </DlRow>
              <DlRow label="Consumed">
                {approval.consumed
                  ? `Yes${approval.consumed_at ? ` (${new Date(approval.consumed_at).toLocaleString()})` : ""}`
                  : "No"}
              </DlRow>
            </dl>
          )}
        </Panel>

        <Panel title="Execution" data-testid="receipt-section-execution">
          <dl className="grid gap-2 text-sm">
            <DlRow label="Status">{formatExecutionStatus(execution?.status ?? "")}</DlRow>
            <DlRow label="Source">{execution?.source ?? "—"}</DlRow>
            <DlRow label="Attempted">{execution?.attempted ? "Yes" : "No"}</DlRow>
            <DlRow label="Duration">
              {execution?.duration_ms != null ? `${execution.duration_ms} ms` : "—"}
            </DlRow>
            <DlRow label="Downstream Ref">
              <span className="font-mono text-xs">{execution?.downstream_reference ?? "—"}</span>
            </DlRow>
            <DlRow label="Reported">
              {execution?.reported_at ? new Date(execution.reported_at).toLocaleString() : "—"}
            </DlRow>
          </dl>
          {execution?.report && (
            <pre className="mt-3 overflow-auto rounded-md border border-border bg-muted/20 p-3 text-xs">
              {JSON.stringify(execution.report, null, 2)}
            </pre>
          )}
        </Panel>

        <Panel title="Assurance" data-testid="receipt-section-assurance">
          <dl className="grid gap-2 text-sm">
            <DlRow label="Enforcement">{assurance?.enforcement_mode ?? "—"}</DlRow>
            <DlRow label="Deployment Control">{assurance?.deployment_control ?? "—"}</DlRow>
            <DlRow label="Verification">{assurance?.verification_status ?? "—"}</DlRow>
            <DlRow label="Execution Evidence">{assurance?.execution_evidence ?? "—"}</DlRow>
          </dl>
          {assurance?.notes && (
            <p className="mt-3 text-sm text-muted-foreground">{assurance.notes}</p>
          )}
        </Panel>
      </div>

      <Panel title="Trace" data-testid="receipt-section-trace">
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <DlRow label="Receipt ID">
            <span className="font-mono text-xs">{trace?.receipt_id ?? receipt.id}</span>
          </DlRow>
          <DlRow label="Correlation ID">
            <span className="font-mono text-xs">{trace?.correlation_id ?? "—"}</span>
          </DlRow>
          <DlRow label="Trace ID">
            <span className="font-mono text-xs">{trace?.trace_id ?? "—"}</span>
          </DlRow>
          <DlRow label="Approval Request">
            {trace?.approval_request_id ? (
              <Link
                href={`/governance/approvals/${trace.approval_request_id}`}
                className="text-primary hover:underline"
              >
                {trace.approval_request_id}
              </Link>
            ) : (
              "—"
            )}
          </DlRow>
          <DlRow label="Session">
            <span className="font-mono text-xs">{trace?.session_id ?? "—"}</span>
          </DlRow>
          <DlRow label="Conversation">
            <span className="font-mono text-xs">{trace?.conversation_id ?? "—"}</span>
          </DlRow>
          <DlRow label="Started">
            {receipt.timestamps?.started_at
              ? new Date(receipt.timestamps.started_at).toLocaleString()
              : "—"}
          </DlRow>
          <DlRow label="Completed">
            {receipt.timestamps?.completed_at
              ? new Date(receipt.timestamps.completed_at).toLocaleString()
              : "—"}
          </DlRow>
        </dl>
      </Panel>
    </div>
  );
}
