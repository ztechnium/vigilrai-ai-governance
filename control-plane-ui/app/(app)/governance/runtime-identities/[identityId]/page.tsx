"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ClientIntegrationsPanel } from "@/components/client-integrations-panel";
import { SdkIntegrationsPanel } from "@/components/sdk-integrations-panel";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table } from "@/components/ui/table";
import { Breadcrumbs } from "@/components/registry/breadcrumbs";
import {
  DelegationScopeBuilder,
  EMPTY_SCOPE,
  scopeFromDelegation,
} from "@/components/registry/delegation-scope-builder";
import { DelegationScopeSummary } from "@/components/registry/delegation-scope-summary";
import { FormField } from "@/components/registry/form-field";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import {
  activateRuntimeIdentity,
  createDelegation,
  getAgent,
  getAgentVersion,
  getDelegations,
  getRuntimeCredentials,
  getRuntimeIdentity,
  issueRuntimeCredential,
  revokeDelegation,
  revokeRuntimeCredential,
  revokeRuntimeIdentity,
  rotateRuntimeCredential,
  suspendRuntimeIdentity,
  updateDelegation,
} from "@/lib/api";
import type {
  AgentSummary,
  AgentVersionSummary,
  DelegationSummary,
  DelegationScopeSelection,
  RuntimeCredentialSummary,
  RuntimeIdentitySummary,
} from "@/lib/types";

export default function RuntimeIdentityDetailPage() {
  const params = useParams();
  const identityId = params.identityId as string;
  const [identity, setIdentity] = useState<RuntimeIdentitySummary | null>(null);
  const [agent, setAgent] = useState<AgentSummary | null>(null);
  const [version, setVersion] = useState<AgentVersionSummary | null>(null);
  const [credentials, setCredentials] = useState<RuntimeCredentialSummary[]>([]);
  const [delegations, setDelegations] = useState<DelegationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [issuedSecret, setIssuedSecret] = useState<string | null>(null);
  const [secretAcknowledged, setSecretAcknowledged] = useState(false);
  const [showDelegationForm, setShowDelegationForm] = useState(false);
  const [editingDelegationId, setEditingDelegationId] = useState<string | null>(null);
  const [delegationForm, setDelegationForm] = useState({
    delegator_type: "HUMAN",
    delegator_id: "",
    expires_at: "",
    scope: EMPTY_SCOPE,
  });
  const [editDelegationForm, setEditDelegationForm] = useState({
    delegator_type: "HUMAN",
    delegator_id: "",
    expires_at: "",
    scope: EMPTY_SCOPE,
  });

  const toDatetimeLocal = (iso: string | null | undefined) => {
    if (!iso) return "";
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  const load = useCallback(() => {
    setLoading(true);
    getRuntimeIdentity(identityId)
      .then(async (identityRes) => {
        const id = identityRes.data;
        setIdentity(id);
        const [agentRes, versionRes, credsRes, delegRes] = await Promise.all([
          getAgent(id.agent_id),
          getAgentVersion(id.agent_version_id),
          getRuntimeCredentials(identityId),
          getDelegations({ delegate_runtime_identity_id: identityId }),
        ]);
        setAgent(agentRes.data);
        setVersion(versionRes.data);
        setCredentials(credsRes.data);
        setDelegations(delegRes.data);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [identityId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleIssueCredential = async () => {
    const res = await issueRuntimeCredential(identityId);
    setIssuedSecret(res.data.plaintext_secret ?? null);
    setSecretAcknowledged(false);
    load();
  };

  const handleRotate = async (credentialId: string) => {
    if (!confirm("Rotate this credential? The old secret will be revoked immediately.")) return;
    const res = await rotateRuntimeCredential(identityId, credentialId);
    setIssuedSecret(res.data.plaintext_secret ?? null);
    setSecretAcknowledged(false);
    load();
  };

  const handleRevokeCredential = async (credentialId: string) => {
    if (!confirm("Revoke this credential? Applications using it will immediately lose access."))
      return;
    await revokeRuntimeCredential(identityId, credentialId);
    load();
  };

  const handleSuspend = async () => {
    if (!confirm("Suspend this runtime identity? Authentication will fail until reactivated."))
      return;
    await suspendRuntimeIdentity(identityId);
    load();
  };

  const handleActivate = async () => {
    await activateRuntimeIdentity(identityId);
    load();
  };

  const handleRevokeIdentity = async () => {
    if (
      !confirm(
        "Revoke this runtime identity? It will immediately fail authentication and all credentials will be revoked.",
      )
    )
      return;
    await revokeRuntimeIdentity(identityId);
    load();
  };

  const handleCreateDelegation = async () => {
    if (!delegationForm.delegator_id.trim()) return;
    await createDelegation({
      delegator_type: delegationForm.delegator_type,
      delegator_id: delegationForm.delegator_id.trim(),
      delegate_runtime_identity_id: identityId,
      scope: delegationForm.scope,
      expires_at: delegationForm.expires_at || undefined,
    });
    setShowDelegationForm(false);
    setDelegationForm({
      delegator_type: "HUMAN",
      delegator_id: "",
      expires_at: "",
      scope: EMPTY_SCOPE,
    });
    load();
  };

  const handleRevokeDelegation = async (delegationId: string) => {
    if (
      !confirm(
        "Revoke this delegation? Dependent authority through this chain will be invalidated.",
      )
    )
      return;
    await revokeDelegation(delegationId);
    load();
  };

  const startEditDelegation = (delegation: DelegationSummary) => {
    setEditingDelegationId(delegation.id);
    setShowDelegationForm(false);
    setEditDelegationForm({
      delegator_type: delegation.delegator_type,
      delegator_id: delegation.delegator_id,
      scope: scopeFromDelegation(delegation.scope),
      expires_at: toDatetimeLocal(delegation.expires_at),
    });
  };

  const cancelEditDelegation = () => {
    setEditingDelegationId(null);
    setEditDelegationForm({
      delegator_type: "HUMAN",
      delegator_id: "",
      expires_at: "",
      scope: EMPTY_SCOPE,
    });
  };

  const handleUpdateDelegation = async () => {
    if (!editingDelegationId || !editDelegationForm.delegator_id.trim()) return;
    await updateDelegation(editingDelegationId, {
      delegator_type: editDelegationForm.delegator_type,
      delegator_id: editDelegationForm.delegator_id.trim(),
      scope: editDelegationForm.scope,
      expires_at: editDelegationForm.expires_at
        ? new Date(editDelegationForm.expires_at).toISOString()
        : null,
      clear_expires_at: !editDelegationForm.expires_at,
    });
    cancelEditDelegation();
    load();
  };

  if (loading) {
    return <div className="p-8 text-center text-sm text-ink-500">Loading identity...</div>;
  }

  if (error || !identity) {
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
          { label: "Runtime Identities", href: "/governance/runtime-identities" },
          { label: identity.name },
        ]}
      />

      <SectionHeader
        title={identity.name}
        subtitle={`Bound to ${agent?.name ?? "Agent"} v${version?.version_number ?? "?"}`}
        actions={
          <div className="flex flex-wrap gap-2">
            {identity.status === "ACTIVE" && (
              <Button variant="secondary" onClick={handleSuspend}>
                Suspend
              </Button>
            )}
            {identity.status === "SUSPENDED" && (
              <Button variant="secondary" onClick={handleActivate}>
                Activate
              </Button>
            )}
            {identity.status !== "REVOKED" && (
              <Button variant="danger" onClick={handleRevokeIdentity}>
                Revoke Identity
              </Button>
            )}
          </div>
        }
      />

      <Panel title="Overview">
        <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[
            ["Status", <StatusBadge key="st" status={identity.status} />],
            ["Identity Key", identity.identity_key],
            ["Type", identity.identity_type],
            ["Environment", identity.environment ?? "—"],
            [
              "Agent Version",
              version ? `v${version.version_number} (${version.lifecycle_status})` : "—",
            ],
            [
              "Last Authenticated",
              identity.last_authenticated_at
                ? new Date(identity.last_authenticated_at).toLocaleString()
                : "Never",
            ],
            [
              "Expires",
              identity.expires_at ? new Date(identity.expires_at).toLocaleString() : "No expiry",
            ],
          ].map(([label, value]) => (
            <div key={String(label)}>
              <dt className="text-xs font-semibold uppercase text-ink-400">{label}</dt>
              <dd className="mt-1 text-sm text-ink-800">{value}</dd>
            </div>
          ))}
        </dl>
      </Panel>

      {issuedSecret && !secretAcknowledged && (
        <Panel
          title="Credential Secret — Shown Once"
          description="Copy this secret now. It cannot be retrieved again."
        >
          <div className="rounded-lg border border-warning-200 bg-warning-50 p-4">
            <code className="break-all text-sm text-ink-900">{issuedSecret}</code>
          </div>
          <div className="mt-4 flex gap-2">
            <Button variant="secondary" onClick={() => navigator.clipboard.writeText(issuedSecret)}>
              Copy
            </Button>
            <Button variant="primary" onClick={() => setSecretAcknowledged(true)}>
              I have saved this secret
            </Button>
          </div>
        </Panel>
      )}

      <Panel
        title="Credentials"
        description="Issue, rotate, and revoke runtime authentication credentials."
        actions={
          identity.status === "ACTIVE" ? (
            <Button variant="primary" onClick={handleIssueCredential}>
              Create Credential
            </Button>
          ) : undefined
        }
      >
        {credentials.length === 0 ? (
          <p className="text-sm text-ink-500">No credentials issued yet.</p>
        ) : (
          <Table
            columns={["Key", "Status", "Issued", "Last Used", "Actions"]}
            rows={credentials.map((cred) => [
              <span key={`k-${cred.id}`} className="font-mono text-sm">
                {cred.credential_key}
              </span>,
              <StatusBadge key={`s-${cred.id}`} status={cred.status} />,
              cred.issued_at ? new Date(cred.issued_at).toLocaleString() : "—",
              cred.last_used_at ? new Date(cred.last_used_at).toLocaleString() : "Never",
              cred.status === "ACTIVE" ? (
                <div key={`a-${cred.id}`} className="flex gap-2">
                  <button
                    type="button"
                    className="text-sm text-brand-600 hover:underline"
                    onClick={() => handleRotate(cred.id)}
                  >
                    Rotate
                  </button>
                  <button
                    type="button"
                    className="text-sm text-danger-600 hover:underline"
                    onClick={() => handleRevokeCredential(cred.id)}
                  >
                    Revoke
                  </button>
                </div>
              ) : (
                "—"
              ),
            ])}
          />
        )}
      </Panel>

      <Panel
        title="Delegations"
        description="Bounded authority grants acting on behalf of a principal."
        actions={
          <Button variant="primary" onClick={() => setShowDelegationForm(!showDelegationForm)}>
            {showDelegationForm ? "Cancel" : "Create Delegation"}
          </Button>
        }
      >
        {showDelegationForm && (
          <div className="mb-6 space-y-4 rounded-lg border border-base-200 p-4">
            <div className="grid gap-4 md:grid-cols-2">
              <FormField label="Delegator ID" required hint="e.g. user email or service account">
                <Input
                  value={delegationForm.delegator_id}
                  onChange={(e) =>
                    setDelegationForm({ ...delegationForm, delegator_id: e.target.value })
                  }
                  placeholder="mohamed@example.com"
                />
              </FormField>
              <FormField label="Expires At">
                <Input
                  type="datetime-local"
                  value={delegationForm.expires_at}
                  onChange={(e) =>
                    setDelegationForm({ ...delegationForm, expires_at: e.target.value })
                  }
                />
              </FormField>
            </div>
            {identity && (
              <DelegationScopeBuilder
                versionId={identity.agent_version_id}
                value={delegationForm.scope}
                onChange={(scope) => setDelegationForm({ ...delegationForm, scope })}
              />
            )}
            <Button variant="primary" onClick={handleCreateDelegation}>
              Create Delegation
            </Button>
          </div>
        )}

        {delegations.length === 0 ? (
          <p className="text-sm text-ink-500">No delegations for this identity.</p>
        ) : (
          <div className="space-y-4">
            {delegations.map((d) => (
              <div key={d.id} className="rounded-lg border border-base-200 p-4">
                {editingDelegationId === d.id ? (
                  <div className="space-y-4">
                    <p className="text-sm font-medium text-ink-900">Edit Delegation</p>
                    <div className="grid gap-4 md:grid-cols-2">
                      <FormField label="Delegator Type">
                        <Input
                          value={editDelegationForm.delegator_type}
                          onChange={(e) =>
                            setEditDelegationForm({
                              ...editDelegationForm,
                              delegator_type: e.target.value,
                            })
                          }
                        />
                      </FormField>
                      <FormField label="Delegator ID" required>
                        <Input
                          value={editDelegationForm.delegator_id}
                          onChange={(e) =>
                            setEditDelegationForm({
                              ...editDelegationForm,
                              delegator_id: e.target.value,
                            })
                          }
                        />
                      </FormField>
                      <FormField label="Expires At">
                        <Input
                          type="datetime-local"
                          value={editDelegationForm.expires_at}
                          onChange={(e) =>
                            setEditDelegationForm({
                              ...editDelegationForm,
                              expires_at: e.target.value,
                            })
                          }
                        />
                      </FormField>
                    </div>
                    {identity && (
                      <DelegationScopeBuilder
                        versionId={identity.agent_version_id}
                        value={editDelegationForm.scope}
                        onChange={(scope) =>
                          setEditDelegationForm({ ...editDelegationForm, scope })
                        }
                      />
                    )}
                    <div className="flex gap-2">
                      <Button variant="primary" onClick={handleUpdateDelegation}>
                        Save Changes
                      </Button>
                      <Button variant="secondary" onClick={cancelEditDelegation}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="font-medium text-ink-900">
                        {d.delegator_type}: {d.delegator_id}
                      </p>
                      <p className="mt-1 text-xs text-ink-500">
                        Valid {d.valid_from ? new Date(d.valid_from).toLocaleString() : "now"}
                        {d.expires_at
                          ? ` → ${new Date(d.expires_at).toLocaleString()}`
                          : " (no expiry)"}
                      </p>
                      <div className="mt-3">
                        <DelegationScopeSummary
                          versionId={identity.agent_version_id}
                          scope={d.scope}
                        />
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={d.status} />
                      {d.status === "ACTIVE" && (
                        <>
                          <button
                            type="button"
                            className="text-sm text-brand-600 hover:underline"
                            onClick={() => startEditDelegation(d)}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            className="text-sm text-danger-600 hover:underline"
                            onClick={() => handleRevokeDelegation(d.id)}
                          >
                            Revoke
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>

      <SdkIntegrationsPanel runtimeIdentityId={identityId} />

      <ClientIntegrationsPanel
        identityId={identityId}
        onCredentialNeeded={() => setSecretAcknowledged(false)}
      />

      {agent && version && (
        <p className="text-sm text-ink-500">
          <Link
            href={`/governance/registry/versions/${version.id}`}
            className="text-brand-600 hover:underline"
          >
            View agent version detail
          </Link>
        </p>
      )}
    </div>
  );
}
