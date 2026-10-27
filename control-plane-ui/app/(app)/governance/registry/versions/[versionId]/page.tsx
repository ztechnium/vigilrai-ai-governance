"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tabs } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Table } from "@/components/ui/table";
import { Breadcrumbs } from "@/components/registry/breadcrumbs";
import { FormField } from "@/components/registry/form-field";
import { LifecycleActions } from "@/components/registry/lifecycle-actions";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { VersionDependencies } from "@/components/registry/version-dependencies";
import {
  createRiskAssessment,
  updateRiskAssessmentStatus,
  getAgent,
  getAgentVersion,
  getDeploymentReadiness,
  getMaterialChanges,
  getRuntimeIdentities,
  getVersionAssurance,
  getVersionDependencies,
  getVersionRiskAssessments,
  transitionAgentVersion,
  updateAgentVersion,
} from "@/lib/api";
import { RISK_TIERS } from "@/lib/registry-constants";
import type {
  AgentSummary,
  AgentVersionSummary,
  DeploymentReadiness,
  MaterialChange,
  RiskAssessmentSummary,
  RuntimeIdentitySummary,
  VersionAssurance,
  VersionDependency,
} from "@/lib/types";

/** Must stay aligned with backend ASSESSMENT_TRANSITIONS. */
const ASSESSMENT_TRANSITIONS: Record<string, string[]> = {
  DRAFT: ["SUBMITTED", "SUPERSEDED"],
  SUBMITTED: ["APPROVED", "DRAFT", "SUPERSEDED"],
  APPROVED: ["SUPERSEDED"],
  SUPERSEDED: [],
};

export default function VersionDetailPage() {
  const params = useParams();
  const versionId = params.versionId as string;
  const [version, setVersion] = useState<AgentVersionSummary | null>(null);
  const [agent, setAgent] = useState<AgentSummary | null>(null);
  const [dependencies, setDependencies] = useState<VersionDependency[]>([]);
  const [changes, setChanges] = useState<MaterialChange[]>([]);
  const [assessments, setAssessments] = useState<RiskAssessmentSummary[]>([]);
  const [runtimeIdentities, setRuntimeIdentities] = useState<RuntimeIdentitySummary[]>([]);
  const [assurance, setAssurance] = useState<VersionAssurance | null>(null);
  const [readiness, setReadiness] = useState<DeploymentReadiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [riskForm, setRiskForm] = useState({
    risk_tier: "MEDIUM",
    overall_score: 50,
    rationale: "",
  });
  const [riskError, setRiskError] = useState<string | null>(null);
  const [updatingAssessmentId, setUpdatingAssessmentId] = useState<string | null>(null);
  const [screen, setScreen] = useState("Overview");

  const isDraft =
    version?.lifecycle_status === "DRAFT" || version?.lifecycle_status === "REASSESSMENT_REQUIRED";

  const load = useCallback(() => {
    setLoading(true);
    getAgentVersion(versionId)
      .then(async (versionRes) => {
        const v = versionRes.data;
        setVersion(v);
        const agentRes = await getAgent(v.agent_id);
        setAgent(agentRes.data);
        const [deps, mats, risks, identities, assuranceRes, readinessRes] = await Promise.all([
          getVersionDependencies(versionId),
          getMaterialChanges(versionId),
          getVersionRiskAssessments(versionId),
          getRuntimeIdentities({ agent_version_id: versionId }),
          getVersionAssurance(versionId, { environment: "PRODUCTION" }).catch(() => null),
          getDeploymentReadiness(versionId).catch(() => null),
        ]);
        setDependencies(deps.data);
        setChanges(mats.data);
        setAssessments(risks.data);
        setRuntimeIdentities(Array.isArray(identities.data) ? identities.data : []);
        setAssurance(assuranceRes?.data ?? null);
        setReadiness(readinessRes?.data ?? null);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [versionId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreateRisk = async () => {
    if (!agent) return;
    setRiskError(null);
    try {
      await createRiskAssessment({
        ai_system_id: agent.ai_system_id,
        agent_version_id: versionId,
        risk_tier: riskForm.risk_tier,
        overall_score: riskForm.overall_score,
        rationale: riskForm.rationale || undefined,
      });
      load();
    } catch (err) {
      setRiskError(err instanceof Error ? err.message : "Failed to record assessment");
    }
  };

  const handleAssessmentStatus = async (assessmentId: string, status: string) => {
    setRiskError(null);
    setUpdatingAssessmentId(assessmentId);
    try {
      await updateRiskAssessmentStatus(assessmentId, status);
      setAssessments((current) =>
        current.map((assessment) =>
          assessment.id === assessmentId ? { ...assessment, status } : assessment,
        ),
      );
    } catch (err) {
      setRiskError(err instanceof Error ? err.message : "Failed to update assessment status");
    } finally {
      setUpdatingAssessmentId(null);
    }
  };

  if (loading) {
    return <div className="p-8 text-center text-sm text-ink-500">Loading version...</div>;
  }

  if (error || !version || !agent) {
    return (
      <div className="rounded-xl bg-danger-50 p-6 text-sm text-danger-600">
        {error ?? "Not found"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[
          { label: "Registry", href: "/governance/registry" },
          {
            label: "System",
            href: `/governance/registry/${agent.ai_system_id}`,
          },
          {
            label: agent.name,
            href: `/governance/registry/agents/${agent.id}`,
          },
          { label: `v${version.version_number}` },
        ]}
      />

      <SectionHeader
        title={`Version ${version.version_number}`}
        subtitle={version.change_summary ?? "Immutable governed version"}
        actions={
          <div className="flex gap-2">
            <StatusBadge status={version.lifecycle_status} />
            {version.material_change_status !== "NONE" && (
              <StatusBadge status={version.material_change_status} />
            )}
          </div>
        }
      />

      <Tabs tabs={["Overview", "Workflow"]} active={screen} onChange={setScreen} />

      {screen === "Workflow" ? (
        <div className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold text-ink-900">Workflow</h2>
            <p className="mt-1 text-sm text-ink-500">
              Current status is {version.lifecycle_status.replace(/_/g, " ").toLowerCase()}.
            </p>
          </div>
          <LifecycleActions
            entityKind="version"
            currentStatus={version.lifecycle_status}
            onTransition={async (status) => {
              await transitionAgentVersion(versionId, status);
              load();
            }}
          />
        </div>
      ) : (
        <div className="space-y-6">
          <Panel title="Version Configuration">
            {isDraft ? (
              <div className="space-y-4">
                <FormField label="Change Summary">
                  <Textarea
                    rows={2}
                    defaultValue={version.change_summary ?? ""}
                    onBlur={async (e) => {
                      await updateAgentVersion(versionId, { change_summary: e.target.value });
                      load();
                    }}
                  />
                </FormField>
                <FormField label="Risk Tier">
                  <Select
                    defaultValue={version.risk_tier ?? "MEDIUM"}
                    onChange={async (e) => {
                      await updateAgentVersion(versionId, { risk_tier: e.target.value });
                      load();
                    }}
                  >
                    {RISK_TIERS.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </Select>
                </FormField>
              </div>
            ) : (
              <dl className="grid gap-3 text-sm">
                <div>
                  <dt className="text-xs uppercase text-ink-400">Summary</dt>
                  <dd>{version.change_summary ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-ink-400">Risk Tier</dt>
                  <dd>{version.risk_tier ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-ink-400">Approved</dt>
                  <dd>
                    {version.approved_at ? new Date(version.approved_at).toLocaleString() : "—"}
                  </dd>
                </div>
              </dl>
            )}
          </Panel>

          <VersionDependencies
            versionId={versionId}
            dependencies={dependencies}
            editable={isDraft}
            onChanged={load}
          />

          <Panel
            title="Runtime Identities"
            description="Executable identities bound to this exact agent version."
            actions={
              <Link href={`/governance/runtime-identities?agent_version_id=${versionId}`}>
                <Button variant="secondary">Create Runtime Identity</Button>
              </Link>
            }
          >
            {version.lifecycle_status === "APPROVED" && runtimeIdentities.length === 0 && (
              <p className="mb-3 text-sm text-warning-700">
                This approved version has no runtime identity yet.
              </p>
            )}
            {runtimeIdentities.length === 0 ? (
              <p className="text-sm text-ink-500">No runtime identities bound to this version.</p>
            ) : (
              <Table
                columns={["Name", "Status", "Environment", "Last Auth", ""]}
                rows={runtimeIdentities.map((identity) => [
                  identity.name,
                  identity.status,
                  identity.environment ?? "—",
                  identity.last_authenticated_at
                    ? new Date(identity.last_authenticated_at).toLocaleString()
                    : "Never",
                  <Link
                    key={identity.id}
                    href={`/governance/runtime-identities/${identity.id}`}
                    className="text-sm font-medium text-brand-600 hover:underline"
                  >
                    View
                  </Link>,
                ])}
              />
            )}
          </Panel>

          <Panel
            title="Assurance"
            description="Deployment eligibility for this exact agent version."
          >
            <dl className="mb-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <dt className="text-xs uppercase text-ink-400">Target Environment</dt>
                <dd>PRODUCTION</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-ink-400">Deployment Eligibility</dt>
                <dd>
                  <StatusBadge
                    status={
                      assurance?.deployment_eligible || readiness?.eligible
                        ? "ELIGIBLE"
                        : "INELIGIBLE"
                    }
                  />
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-ink-400">Gate / Assurance Status</dt>
                <dd>
                  <StatusBadge status={assurance?.current?.status ?? "MISSING"} />
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-ink-400">Valid Until</dt>
                <dd>
                  {assurance?.current?.valid_until
                    ? new Date(assurance.current.valid_until).toLocaleString()
                    : "—"}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-ink-400">Reassessment Required</dt>
                <dd>{assurance?.reassessment_required ? "Yes" : "No"}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-ink-400">Config Digest</dt>
                <dd className="truncate font-mono text-xs">
                  {assurance?.current?.config_digest ?? version.configuration_digest ?? "—"}
                </dd>
              </div>
            </dl>
            {readiness && readiness.open_failures.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs uppercase text-ink-400">Open Failures</p>
                {readiness.open_failures.map((f) => (
                  <div
                    key={f.name}
                    className="rounded-lg border border-danger-100 bg-danger-50 px-3 py-2 text-sm text-danger-700"
                  >
                    <span className="font-medium">{f.name}</span>: {f.detail}
                  </div>
                ))}
              </div>
            )}
            {readiness && (
              <div className="mt-4 divide-y divide-base-100">
                {readiness.checks.map((c) => (
                  <div
                    key={c.name}
                    className="flex items-center justify-between gap-3 py-2 text-sm"
                  >
                    <span>{c.name}</span>
                    <StatusBadge status={c.result} />
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <div className="grid gap-4 lg:grid-cols-2">
            <Panel
              title="Material Changes"
              description="Compared to the previous governed version."
            >
              {changes.length === 0 ? (
                <p className="text-sm text-ink-500">No material changes detected.</p>
              ) : (
                <div className="space-y-3">
                  {changes.map((c, i) => (
                    <div
                      key={i}
                      className="rounded-lg border border-base-100 bg-base-50 p-3 text-sm"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-ink-800">{c.change_description}</span>
                        {c.is_material && <StatusBadge status="MATERIAL" />}
                      </div>
                      <p className="mt-1 text-ink-500">{c.reason}</p>
                    </div>
                  ))}
                </div>
              )}
            </Panel>

            <Panel title="Risk Assessment">
              <div className="mb-4 space-y-3">
                <FormField label="Risk Tier">
                  <Select
                    value={riskForm.risk_tier}
                    onChange={(e) => setRiskForm({ ...riskForm, risk_tier: e.target.value })}
                  >
                    {RISK_TIERS.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </Select>
                </FormField>
                <FormField label="Overall Score (0–100)">
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    value={riskForm.overall_score}
                    onChange={(e) =>
                      setRiskForm({ ...riskForm, overall_score: Number(e.target.value) })
                    }
                  />
                </FormField>
                <FormField label="Rationale">
                  <Textarea
                    rows={2}
                    value={riskForm.rationale}
                    onChange={(e) => setRiskForm({ ...riskForm, rationale: e.target.value })}
                  />
                </FormField>
                <Button variant="secondary" onClick={() => void handleCreateRisk()}>
                  Record Assessment
                </Button>
                {riskError ? <p className="text-sm text-danger-600">{riskError}</p> : null}
              </div>
              {assessments.length > 0 && (
                <Table
                  columns={["Status", "Risk Tier", "Score"]}
                  rows={assessments.map((a) => {
                    const nextStatuses = ASSESSMENT_TRANSITIONS[a.status] ?? [];
                    return [
                      <Select
                        key={a.id}
                        aria-label={`Risk assessment ${a.id}`}
                        className="h-8 min-w-36 text-xs"
                        value={a.status}
                        disabled={updatingAssessmentId === a.id || nextStatuses.length === 0}
                        onChange={(e) => void handleAssessmentStatus(a.id, e.target.value)}
                      >
                        <option value={a.status}>{a.status}</option>
                        {nextStatuses.map((status) => (
                          <option key={status} value={status}>
                            {status}
                          </option>
                        ))}
                      </Select>,
                      a.risk_tier ?? "—",
                      a.overall_score?.toString() ?? "—",
                    ];
                  })}
                />
              )}
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}
