"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { FormField } from "@/components/registry/form-field";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { getRuntimeIdentities } from "@/lib/api";
import {
  ACTIVE_ORG_STORAGE_KEY,
  createSdkIntegration,
  listSdkIntegrations,
  PublicApiError,
  type SdkIntegrationSummary,
} from "@/lib/public-api";
import type { RuntimeIdentitySummary } from "@/lib/types";

function slugifyKey(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

export function SdkIntegrationsPanel({
  runtimeIdentityId,
}: {
  /** When set, list/create is scoped to this runtime identity. */
  runtimeIdentityId?: string;
}) {
  const [orgId, setOrgId] = useState<string | null>(null);
  const [items, setItems] = useState<SdkIntegrationSummary[]>([]);
  const [identities, setIdentities] = useState<RuntimeIdentitySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [created, setCreated] = useState<SdkIntegrationSummary | null>(null);
  const [form, setForm] = useState({
    name: "",
    integration_key: "",
    runtime_identity_id: runtimeIdentityId ?? "",
    environment: "production",
    enforcement_mode: "HOOK_ENFORCED",
    fail_closed: true,
  });

  useEffect(() => {
    setOrgId(window.localStorage.getItem(ACTIVE_ORG_STORAGE_KEY));
  }, []);

  useEffect(() => {
    if (runtimeIdentityId) {
      setForm((prev) => ({ ...prev, runtime_identity_id: runtimeIdentityId }));
    }
  }, [runtimeIdentityId]);

  const load = useCallback(async () => {
    const activeOrg = window.localStorage.getItem(ACTIVE_ORG_STORAGE_KEY);
    setOrgId(activeOrg);
    if (!activeOrg) {
      setItems([]);
      setLoading(false);
      setError("No active organization. Complete registration to provision integrations.");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const [integrationsRes, identitiesRes] = await Promise.all([
        listSdkIntegrations(activeOrg),
        runtimeIdentityId
          ? Promise.resolve({ data: [] as RuntimeIdentitySummary[] })
          : getRuntimeIdentities({ status: "ACTIVE" }).catch(() => ({
              data: [] as RuntimeIdentitySummary[],
            })),
      ]);
      const all = integrationsRes.items ?? [];
      setItems(
        runtimeIdentityId
          ? all.filter((item) => item.runtime_identity_id === runtimeIdentityId)
          : all,
      );
      if (!runtimeIdentityId) {
        setIdentities(identitiesRes.data ?? []);
      }
    } catch (err) {
      setError(
        err instanceof PublicApiError || err instanceof Error
          ? err.message
          : "Failed to load SDK integrations",
      );
    } finally {
      setLoading(false);
    }
  }, [runtimeIdentityId]);

  useEffect(() => {
    void load();
  }, [load]);

  const activeIdentities = useMemo(
    () => identities.filter((identity) => identity.status === "ACTIVE"),
    [identities],
  );

  const handleNameChange = (name: string) => {
    setForm((prev) => {
      const autoKey = !prev.integration_key || prev.integration_key === slugifyKey(prev.name);
      return {
        ...prev,
        name,
        integration_key: autoKey ? slugifyKey(name) : prev.integration_key,
      };
    });
  };

  const handleCreate = async () => {
    if (!orgId) {
      setError("No active organization selected.");
      return;
    }
    if (!form.name.trim() || !form.integration_key.trim() || !form.runtime_identity_id) {
      setError("Name, integration key, and runtime identity are required.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const integration = await createSdkIntegration({
        organization_id: orgId,
        name: form.name.trim(),
        integration_key: form.integration_key.trim(),
        runtime_identity_id: form.runtime_identity_id,
        environment: form.environment,
        enforcement_mode: form.enforcement_mode,
        fail_closed: form.fail_closed,
      });
      setCreated(integration);
      setItems((prev) => {
        const withoutDup = prev.filter((item) => item.id !== integration.id);
        return [integration, ...withoutDup];
      });
      setShowForm(false);
      setForm({
        name: "",
        integration_key: "",
        runtime_identity_id: runtimeIdentityId ?? "",
        environment: "production",
        enforcement_mode: "HOOK_ENFORCED",
        fail_closed: true,
      });
      await load();
    } catch (err) {
      setError(
        err instanceof PublicApiError || err instanceof Error
          ? err.message
          : "Failed to create SDK integration",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Panel
      title="SDK Integrations"
      description="Provision Node/TypeScript or Python SDK connections for this organization. Use the integration ID and a runtime credential in your application."
      actions={
        <Button
          size="sm"
          variant={showForm ? "secondary" : "primary"}
          onClick={() => {
            setShowForm((open) => !open);
            setError(null);
          }}
          disabled={!orgId}
        >
          {showForm ? "Cancel" : "Create SDK integration"}
        </Button>
      }
    >
      {created && (
        <div className="mb-4 rounded-lg border border-accent-500/30 bg-accent-600/5 p-4 text-sm text-ink-800">
          <p className="font-medium text-ink-900">SDK integration created</p>
          <p className="mt-1 text-ink-600">
            Copy <code className="font-mono text-xs">RAI_INTEGRATION_ID</code> into your app env,
            then issue a runtime credential for{" "}
            <code className="font-mono text-xs">RAI_AGENT_KEY</code>.
          </p>
          <div className="mt-3 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold uppercase text-ink-400">Integration ID</span>
              <code className="break-all font-mono text-xs text-ink-900">{created.id}</code>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => void navigator.clipboard.writeText(created.id)}
              >
                Copy
              </Button>
            </div>
            <p className="text-xs text-ink-500">
              Key: <span className="font-mono">{created.integration_key}</span>
              {" · "}
              <Link
                href={`/governance/runtime-identities/${created.runtime_identity_id}`}
                className="text-brand-600 hover:underline"
              >
                Open runtime identity
              </Link>
            </p>
          </div>
        </div>
      )}

      {showForm && (
        <div className="mb-6 space-y-4 rounded-lg border border-base-200 bg-base-100/40 p-4">
          <div className="grid gap-4 md:grid-cols-2">
            <FormField label="Name" required hint="Human-readable label, e.g. Qaabot Support">
              <Input
                value={form.name}
                onChange={(e) => handleNameChange(e.target.value)}
                placeholder="Qaabot Support Inbox"
              />
            </FormField>
            <FormField
              label="Integration key"
              required
              hint="Stable unique key within the organization"
            >
              <Input
                value={form.integration_key}
                onChange={(e) => {
                  const raw = e.target.value;
                  setForm((prev) => ({
                    ...prev,
                    integration_key: slugifyKey(raw) || raw,
                  }));
                }}
                placeholder="qaabot-support"
              />
            </FormField>
            {!runtimeIdentityId && (
              <FormField
                label="Runtime identity"
                required
                hint="Must already exist. Create one under Governance → Runtime Identities."
              >
                <Select
                  value={form.runtime_identity_id}
                  onChange={(e) =>
                    setForm((prev) => ({ ...prev, runtime_identity_id: e.target.value }))
                  }
                >
                  <option value="">Select runtime identity…</option>
                  {activeIdentities.map((identity) => (
                    <option key={identity.id} value={identity.id}>
                      {identity.name} ({identity.environment ?? "n/a"}) — {identity.identity_key}
                    </option>
                  ))}
                </Select>
              </FormField>
            )}
            {runtimeIdentityId && (
              <FormField label="Runtime identity">
                <Input value={runtimeIdentityId} disabled />
              </FormField>
            )}
            <FormField label="Environment">
              <Select
                value={form.environment}
                onChange={(e) => setForm((prev) => ({ ...prev, environment: e.target.value }))}
              >
                <option value="production">production</option>
                <option value="staging">staging</option>
                <option value="development">development</option>
              </Select>
            </FormField>
            <FormField label="Enforcement mode">
              <Select
                value={form.enforcement_mode}
                onChange={(e) => setForm((prev) => ({ ...prev, enforcement_mode: e.target.value }))}
              >
                <option value="HOOK_ENFORCED">HOOK_ENFORCED</option>
                <option value="OBSERVE_ONLY">OBSERVE_ONLY</option>
              </Select>
            </FormField>
            <FormField label="Fail closed" hint="When RAI is unavailable, deny side effects">
              <Select
                value={form.fail_closed ? "true" : "false"}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, fail_closed: e.target.value === "true" }))
                }
              >
                <option value="true">Yes (recommended)</option>
                <option value="false">No</option>
              </Select>
            </FormField>
          </div>
          {!runtimeIdentityId && activeIdentities.length === 0 && (
            <p className="text-sm text-ink-500">
              No active runtime identities found.{" "}
              <Link
                href="/governance/runtime-identities"
                className="text-brand-600 hover:underline"
              >
                Create a runtime identity
              </Link>{" "}
              first, then return here.
            </p>
          )}
          <Button
            variant="primary"
            disabled={
              submitting ||
              !form.name.trim() ||
              !form.integration_key.trim() ||
              !form.runtime_identity_id
            }
            onClick={() => void handleCreate()}
          >
            {submitting ? "Creating…" : "Create SDK integration"}
          </Button>
        </div>
      )}

      {loading ? (
        <p className="text-sm text-ink-500">Loading SDK integrations…</p>
      ) : error && items.length === 0 && !showForm ? (
        <div className="rounded-lg border border-danger-600/20 bg-danger-100 p-3 text-sm text-danger-600">
          {error}
        </div>
      ) : (
        <>
          {error && (
            <div className="mb-3 rounded-lg border border-danger-600/20 bg-danger-100 p-3 text-sm text-danger-600">
              {error}
            </div>
          )}
          {items.length === 0 ? (
            <p className="text-sm text-ink-500">
              No SDK integrations yet. Create one to connect Node/TypeScript or Python apps via{" "}
              <code className="font-mono text-xs">/sdk/v1</code>.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-base-200">
              <table className="min-w-full text-left text-sm">
                <thead className="border-b border-base-200 bg-base-100 text-ink-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">Name</th>
                    <th className="px-4 py-3 font-medium">Integration ID</th>
                    <th className="px-4 py-3 font-medium">Type</th>
                    <th className="px-4 py-3 font-medium">Environment</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Enforcement</th>
                    <th className="px-4 py-3 font-medium">Last heartbeat</th>
                    {!runtimeIdentityId && (
                      <th className="px-4 py-3 font-medium">Runtime identity</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id} className="border-b border-base-200 last:border-0">
                      <td className="px-4 py-3">
                        <div className="font-medium text-ink-900">{item.name}</div>
                        <div className="font-mono text-xs text-ink-400">{item.integration_key}</div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <code
                            className="max-w-[10rem] truncate font-mono text-xs"
                            title={item.id}
                          >
                            {item.id}
                          </code>
                          <button
                            type="button"
                            className="text-xs text-brand-600 hover:underline"
                            onClick={() => void navigator.clipboard.writeText(item.id)}
                          >
                            Copy
                          </button>
                        </div>
                      </td>
                      <td className="px-4 py-3">{item.integration_type}</td>
                      <td className="px-4 py-3">{item.environment}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={item.status} />
                      </td>
                      <td className="px-4 py-3">{item.enforcement_mode}</td>
                      <td className="px-4 py-3">
                        {item.last_heartbeat_at
                          ? new Date(item.last_heartbeat_at).toLocaleString()
                          : "Never — not yet connected"}
                      </td>
                      {!runtimeIdentityId && (
                        <td className="px-4 py-3">
                          <Link
                            href={`/governance/runtime-identities/${item.runtime_identity_id}`}
                            className="text-brand-600 hover:underline"
                          >
                            View
                          </Link>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
