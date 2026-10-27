"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { FilterToolbar, MetricStrip, PaginationBar } from "@/components/console/page-parts";
import { KpiCard } from "@/components/kpi-card";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table } from "@/components/ui/table";
import { FormField } from "@/components/registry/form-field";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import {
  createRuntimeIdentity,
  getAgents,
  getAgentVersions,
  getAISystems,
  getRuntimeIdentities,
} from "@/lib/api";
import type {
  AgentSummary,
  AgentVersionSummary,
  AISystemSummary,
  RuntimeIdentitySummary,
} from "@/lib/types";

const STATUS_OPTIONS = ["", "ACTIVE", "SUSPENDED", "REVOKED", "EXPIRED"];

export default function RuntimeIdentitiesPage() {
  const [identities, setIdentities] = useState<RuntimeIdentitySummary[]>([]);
  const [systems, setSystems] = useState<AISystemSummary[]>([]);
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [versions, setVersions] = useState<AgentVersionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    systemId: "",
    agentId: "",
    agentVersionId: "",
    name: "",
    environment: "",
    identity_type: "RAI_API_CREDENTIAL",
  });

  const load = () => {
    setLoading(true);
    setError(null);
    getRuntimeIdentities({
      search: search || undefined,
      status: statusFilter || undefined,
    })
      .then((res) => setIdentities(res.data))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    getAISystems()
      .then((res) => setSystems(res.data))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!form.systemId) {
      setAgents([]);
      setVersions([]);
      return;
    }
    getAgents(form.systemId)
      .then((res) => setAgents(res.data))
      .catch(() => {});
  }, [form.systemId]);

  useEffect(() => {
    if (!form.agentId) {
      setVersions([]);
      return;
    }
    getAgentVersions(form.agentId)
      .then((res) => setVersions(res.data))
      .catch(() => {});
  }, [form.agentId]);

  const stats = useMemo(
    () => ({
      total: identities.length,
      active: identities.filter((i) => i.status === "ACTIVE").length,
      suspended: identities.filter((i) => i.status === "SUSPENDED").length,
    }),
    [identities],
  );

  const pageSize = 10;
  const pageRows = identities.slice(page * pageSize, page * pageSize + pageSize);

  const handleCreate = async () => {
    if (!form.agentId || !form.agentVersionId || !form.name.trim()) return;
    setSaving(true);
    try {
      await createRuntimeIdentity({
        agent_id: form.agentId,
        agent_version_id: form.agentVersionId,
        name: form.name.trim(),
        identity_type: form.identity_type,
        environment: form.environment || undefined,
      });
      setShowCreate(false);
      setForm({
        systemId: "",
        agentId: "",
        agentVersionId: "",
        name: "",
        environment: "",
        identity_type: "RAI_API_CREDENTIAL",
      });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create identity");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Runtime"
        title="Runtime Identities"
        subtitle="Governed runtime identities bound to exact agent versions for secure authentication and delegation."
        actions={
          <Button variant="primary" onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? "Cancel" : "+ New Runtime Identity"}
          </Button>
        }
      />

      <MetricStrip>
        <KpiCard title="Total Identities" value={String(stats.total)} />
        <KpiCard title="Active" value={String(stats.active)} />
        <KpiCard title="Suspended" value={String(stats.suspended)} tone="warn" />
      </MetricStrip>

      {showCreate && (
        <Panel
          title="Create Runtime Identity"
          description="Bind to an exact agent version. Authority does not follow latest version automatically."
        >
          <div className="grid gap-4 md:grid-cols-2">
            <FormField label="AI System" required>
              <Select
                value={form.systemId}
                onChange={(e) =>
                  setForm({
                    ...form,
                    systemId: e.target.value,
                    agentId: "",
                    agentVersionId: "",
                  })
                }
              >
                <option value="">Select system...</option>
                {systems.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField label="Agent" required>
              <Select
                value={form.agentId}
                onChange={(e) => setForm({ ...form, agentId: e.target.value, agentVersionId: "" })}
                disabled={!form.systemId}
              >
                <option value="">Select agent...</option>
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField label="Agent Version" required>
              <Select
                value={form.agentVersionId}
                onChange={(e) => setForm({ ...form, agentVersionId: e.target.value })}
                disabled={!form.agentId}
              >
                <option value="">Select version...</option>
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    v{v.version_number} — {v.lifecycle_status}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField label="Identity Name" required>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Procurement Runtime"
              />
            </FormField>
            <FormField label="Environment">
              <Input
                value={form.environment}
                onChange={(e) => setForm({ ...form, environment: e.target.value })}
                placeholder="e.g. production"
              />
            </FormField>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleCreate}
              disabled={saving || !form.agentVersionId || !form.name.trim()}
            >
              {saving ? "Creating..." : "Create Identity"}
            </Button>
          </div>
        </Panel>
      )}

      <Panel title="Runtime Identities">
        <FilterToolbar
          value={search}
          onChange={setSearch}
          placeholder="Search by name or key..."
          filters={[
            {
              label: "Status",
              value: statusFilter,
              onChange: (value) => {
                setStatusFilter(value);
                setPage(0);
              },
              options: STATUS_OPTIONS.filter(Boolean).map((status) => ({
                value: status,
                label: status,
              })),
            },
          ]}
          action={
            <Button
              variant="secondary"
              onClick={() => {
                setPage(0);
                load();
              }}
            >
              Apply Filters
            </Button>
          }
        />

        {loading && (
          <p className="py-8 text-center text-sm text-ink-500">Loading runtime identities...</p>
        )}
        {error && (
          <div className="rounded-lg bg-danger-50 p-4 text-sm text-danger-600">{error}</div>
        )}
        {!loading && !error && identities.length === 0 && (
          <div className="py-12 text-center">
            <p className="text-sm text-ink-500">No runtime identities yet.</p>
            <Button variant="primary" className="mt-4" onClick={() => setShowCreate(true)}>
              Create your first runtime identity
            </Button>
          </div>
        )}
        {!loading && identities.length > 0 && (
          <Table
            columns={["Name", "Version", "Environment", "Type", "Status", "Last Auth", ""]}
            rows={pageRows.map((identity) => [
              <div key={`name-${identity.id}`}>
                <p className="font-medium text-ink-900">{identity.name}</p>
                <p className="text-xs text-ink-400">{identity.identity_key}</p>
              </div>,
              <span key={`ver-${identity.id}`} className="text-sm text-ink-600">
                {identity.agent_version_id.slice(0, 8)}…
              </span>,
              identity.environment ?? "—",
              identity.identity_type,
              <StatusBadge key={`st-${identity.id}`} status={identity.status} />,
              identity.last_authenticated_at
                ? new Date(identity.last_authenticated_at).toLocaleString()
                : "Never",
              <Link
                key={`link-${identity.id}`}
                href={`/governance/runtime-identities/${identity.id}`}
                className="text-sm font-medium text-accent-600 hover:underline"
              >
                View
              </Link>,
            ])}
          />
        )}
        <PaginationBar total={identities.length} page={page} pageSize={pageSize} onPage={setPage} />
      </Panel>
    </div>
  );
}
