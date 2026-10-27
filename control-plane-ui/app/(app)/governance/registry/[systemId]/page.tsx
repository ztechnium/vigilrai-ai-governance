"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  AssetHierarchy,
  MetaGrid,
  PaginationBar,
  TechnicalValue,
} from "@/components/console/page-parts";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { SideDrawer } from "@/components/ui/side-drawer";
import { Table } from "@/components/ui/table";
import { Breadcrumbs } from "@/components/registry/breadcrumbs";
import { FormField } from "@/components/registry/form-field";
import { AgentsVersionsTable } from "@/components/registry/agents-versions-table";
import { LifecycleActions } from "@/components/registry/lifecycle-actions";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { AISystemReportTab } from "@/components/reporting/ai-system-report-tab";
import {
  createAgent,
  getAISystem,
  getAISystemConfigurationProvenance,
  getAISystemHierarchy,
  getRuntimeIdentities,
  getTrajectories,
  transitionAISystem,
  updateAISystem,
} from "@/lib/api";
import { BUSINESS_UNITS, RISK_TIERS } from "@/lib/registry-constants";
import { slugifyKey } from "@/lib/slugify";
import type {
  AISystemConfigurationProvenance,
  AISystemHierarchy,
  AISystemSummary,
  RuntimeIdentitySummary,
  TrajectorySummary,
} from "@/lib/types";

const TABS = [
  "Overview",
  "Agents & Versions",
  "Runtime Access",
  "Activity",
  "Report Summary",
] as const;
type Tab = (typeof TABS)[number];

const EMPTY_AGENT = {
  agent_key: "",
  name: "",
  business_purpose: "",
  owner_id: "",
};

function formatDate(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatRelative(value?: string | null) {
  if (!value) return "Never";
  const diff = Date.now() - new Date(value).getTime();
  if (Number.isNaN(diff)) return "—";
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} hr ago`;
  return formatDate(value);
}

export default function AISystemDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const systemId = params.systemId as string;
  const tabParam = searchParams.get("tab");
  const tab: Tab = TABS.includes(tabParam as Tab) ? (tabParam as Tab) : "Overview";

  const [system, setSystem] = useState<AISystemSummary | null>(null);
  const [hierarchy, setHierarchy] = useState<AISystemHierarchy | null>(null);
  const [provenance, setProvenance] = useState<AISystemConfigurationProvenance | null>(null);
  const [runtimes, setRuntimes] = useState<RuntimeIdentitySummary[]>([]);
  const [trajectories, setTrajectories] = useState<TrajectorySummary[]>([]);
  const [trajectoriesTotal, setTrajectoriesTotal] = useState(0);
  const [trajectoriesPage, setTrajectoriesPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAgentForm, setShowAgentForm] = useState(false);
  const [showEditSystem, setShowEditSystem] = useState(false);
  const [agentForm, setAgentForm] = useState(EMPTY_AGENT);
  const [savingAgent, setSavingAgent] = useState(false);

  const setTab = (next: Tab) => {
    const query = new URLSearchParams(searchParams.toString());
    if (next === "Overview") query.delete("tab");
    else query.set("tab", next);
    const suffix = query.toString();
    router.replace(
      suffix ? `/governance/registry/${systemId}?${suffix}` : `/governance/registry/${systemId}`,
    );
  };

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      getAISystem(systemId),
      getAISystemHierarchy(systemId),
      getAISystemConfigurationProvenance(systemId).catch(() => null),
      getTrajectories({
        ai_system_id: systemId,
        limit: 10,
        offset: 0,
      }).catch(() => ({
        data: { items: [] as TrajectorySummary[], total: 0 },
      })),
    ])
      .then(async ([sysRes, hierRes, provRes, trajRes]) => {
        setSystem(sysRes.data);
        setHierarchy(hierRes.data);
        setProvenance(provRes?.data ?? null);
        setTrajectories(trajRes.data.items ?? []);
        setTrajectoriesTotal(trajRes.data.total ?? trajRes.data.items?.length ?? 0);
        setTrajectoriesPage(0);
        setError(null);

        const agentIds = hierRes.data.agents.map((agent) => agent.id);
        if (agentIds.length === 0) {
          setRuntimes([]);
          return;
        }
        const identityLists = await Promise.all(
          agentIds.map((agentId) =>
            getRuntimeIdentities({ agent_id: agentId }).catch(() => ({
              data: [] as RuntimeIdentitySummary[],
            })),
          ),
        );
        const byId = new Map<string, RuntimeIdentitySummary>();
        for (const list of identityLists) {
          for (const identity of list.data) byId.set(identity.id, identity);
        }
        setRuntimes([...byId.values()]);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [systemId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleUpdateSystem = async (field: string, value: string) => {
    await updateAISystem(systemId, { [field]: value });
    load();
  };

  const handleAgentNameChange = (name: string) => {
    setAgentForm((prev) => {
      const autoKey = !prev.agent_key || prev.agent_key === slugifyKey(prev.name);
      return {
        ...prev,
        name,
        agent_key: autoKey ? slugifyKey(name) : prev.agent_key,
      };
    });
  };

  const handleCreateAgent = async () => {
    if (!agentForm.agent_key.trim() || !agentForm.name.trim()) return;
    setSavingAgent(true);
    try {
      await createAgent(systemId, {
        agent_key: agentForm.agent_key.trim(),
        name: agentForm.name.trim(),
        business_purpose: agentForm.business_purpose || undefined,
        owner_id: agentForm.owner_id || undefined,
      });
      setShowAgentForm(false);
      setAgentForm(EMPTY_AGENT);
      setTab("Agents & Versions");
      load();
    } finally {
      setSavingAgent(false);
    }
  };

  const versionStats = useMemo(() => {
    const versions = hierarchy?.agents.flatMap((agent) => agent.versions) ?? [];
    return {
      total: versions.length,
      approved: versions.filter((version) => version.lifecycle_status === "APPROVED").length,
      review: versions.filter((version) => version.lifecycle_status === "UNDER_REVIEW").length,
    };
  }, [hierarchy]);

  if (loading) {
    return <div className="p-8 text-center text-sm text-ink-500">Loading system...</div>;
  }

  if (error || !system || !hierarchy) {
    return (
      <div className="rounded-xl border border-danger-200 bg-danger-50 p-6 text-sm text-danger-600">
        {error ?? "Not found"}
      </div>
    );
  }

  const activeCredentials = runtimes.filter((runtime) => runtime.status === "ACTIVE").length;

  return (
    <div className="space-y-5">
      <SectionHeader
        eyebrow={
          <Breadcrumbs
            items={[{ label: "AI Systems", href: "/governance/registry" }, { label: system.name }]}
          />
        }
        title={system.name}
        subtitle={system.business_purpose ?? "No business purpose recorded."}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              disabled={system.status === "RETIRED"}
              onClick={() => setShowEditSystem(true)}
            >
              Edit System
            </Button>
            <Button
              variant="primary"
              disabled={system.status === "RETIRED"}
              onClick={() => setShowAgentForm(true)}
            >
              + Create Agent
            </Button>
          </div>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <TechnicalValue>{system.system_key}</TechnicalValue>
        <StatusBadge status={system.status} />
        {system.risk_tier ? <StatusBadge status={system.risk_tier} /> : null}
      </div>

      <div className="mb-4 rounded-lg border border-base-200 bg-base-50 p-4">
        <MetaGrid
          items={[
            { label: "Owner", value: system.owner_id ?? "—" },
            { label: "Business Unit", value: system.business_unit ?? "—" },
            { label: "Updated", value: formatDate(system.updated_at) },
            {
              label: "Last Runtime Activity",
              value: formatRelative(trajectories[0]?.started_at ?? provenance?.last_seen_at),
            },
          ]}
        />
      </div>

      <AssetHierarchy
        nodes={[
          ["AI SYSTEM", system.system_key],
          ["AGENTS", hierarchy.agents.length],
          ["AGENT VERSIONS", versionStats.total],
          ["RUNTIME IDENTITIES", runtimes.length],
          ["ACTIVE CREDENTIALS", activeCredentials],
        ]}
      />

      <div role="tablist" className="mt-5 flex gap-1 overflow-x-auto border-b border-base-200">
        {TABS.map((item) => (
          <button
            key={item}
            type="button"
            role="tab"
            aria-selected={tab === item}
            onClick={() => setTab(item)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              tab === item
                ? "border-accent-600 font-semibold text-ink-900"
                : "border-transparent text-ink-500 hover:text-ink-800"
            }`}
          >
            {item}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {tab === "Overview" && (
          <div className="grid gap-4 xl:grid-cols-2">
            <Panel title="System Information">
              <MetaGrid
                items={[
                  { label: "Display name", value: system.name },
                  {
                    label: "System key",
                    value: <TechnicalValue>{system.system_key}</TechnicalValue>,
                  },
                  { label: "Business unit", value: system.business_unit ?? "—" },
                  { label: "Updated", value: formatDate(system.updated_at) },
                ]}
              />
            </Panel>

            <Panel title="Governance State">
              <MetaGrid
                items={[
                  {
                    label: "Risk",
                    value: system.risk_tier ? <StatusBadge status={system.risk_tier} /> : "—",
                  },
                  {
                    label: "Lifecycle",
                    value: <StatusBadge status={system.status} />,
                  },
                  { label: "Approved versions", value: versionStats.approved },
                  { label: "Awaiting review", value: versionStats.review },
                  { label: "Runtime identities", value: runtimes.length },
                  { label: "Active credentials", value: activeCredentials },
                  {
                    label: "Open findings",
                    value: trajectories.reduce((sum, t) => sum + t.finding_count, 0),
                  },
                  { label: "Trajectories", value: trajectories.length },
                ]}
              />
            </Panel>

            <Panel title="AI Architecture" className="xl:col-span-2">
              {hierarchy.agents.length === 0 ? (
                <p className="text-xs text-ink-500">No agents registered for this system.</p>
              ) : (
                <ul className="space-y-3">
                  {hierarchy.agents.map((agent) => (
                    <li
                      key={agent.id}
                      className="rounded-md border border-base-200 bg-base-100 p-3"
                    >
                      <div className="text-xs font-semibold text-ink-900">
                        {agent.name}{" "}
                        <TechnicalValue className="ml-2 text-ink-400">
                          {agent.agent_key}
                        </TechnicalValue>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {agent.versions.length === 0 ? (
                          <span className="text-xs text-ink-400">No versions</span>
                        ) : (
                          agent.versions.map((version) => {
                            const boundRuntimes = runtimes.filter(
                              (runtime) => runtime.agent_version_id === version.id,
                            );
                            return (
                              <Link
                                key={version.id}
                                href={`/governance/registry/versions/${version.id}`}
                                className="flex items-center gap-2 rounded border border-base-200 px-2 py-1 text-xs hover:border-accent-600"
                              >
                                <span className="font-mono">v{version.version_number}</span>
                                <StatusBadge status={version.lifecycle_status} />
                                <span className="text-ink-400">
                                  →{" "}
                                  {boundRuntimes.map((runtime) => runtime.name).join(", ") ||
                                    "no runtime"}
                                </span>
                              </Link>
                            );
                          })
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>
        )}

        {tab === "Agents & Versions" && (
          <div className="overflow-hidden rounded-lg border border-base-200 bg-base-50">
            <div className="flex items-center justify-between border-b border-base-200 px-4 py-2">
              <span className="text-sm font-semibold text-ink-900">Agents & Versions</span>
              <Button size="sm" variant="primary" onClick={() => setShowAgentForm(true)}>
                + Create Agent
              </Button>
            </div>
            <AgentsVersionsTable
              hierarchy={hierarchy}
              runtimes={runtimes}
              onCreateAgent={() => setShowAgentForm(true)}
            />
          </div>
        )}

        {tab === "Runtime Access" && (
          <div className="overflow-hidden rounded-lg border border-base-200 bg-base-50">
            <div className="flex items-center justify-between border-b border-base-200 px-4 py-2">
              <span className="text-sm font-semibold text-ink-900">Runtime Identities</span>
              <Link href="/governance/runtime-identities">
                <Button size="sm" variant="secondary">
                  + Create Runtime Identity
                </Button>
              </Link>
            </div>
            {runtimes.length === 0 ? (
              <div className="flex min-h-48 flex-col items-center justify-center px-6 text-center">
                <h3 className="text-sm font-semibold">No runtime access configured.</h3>
                <p className="mt-1 max-w-md text-xs text-ink-500">
                  Create a runtime identity to connect an Agent Version to a running application.
                </p>
              </div>
            ) : (
              <Table
                columns={[
                  "Runtime Identity",
                  "Environment",
                  "Type",
                  "Status",
                  "Last Auth",
                  "Actions",
                ]}
                rows={runtimes.map((runtime) => [
                  <div key={`${runtime.id}-name`}>
                    <div className="font-mono font-medium">{runtime.name}</div>
                    <TechnicalValue className="text-[11px] text-ink-400">
                      {runtime.identity_key}
                    </TechnicalValue>
                  </div>,
                  runtime.environment ?? "—",
                  runtime.identity_type,
                  <StatusBadge key={`${runtime.id}-status`} status={runtime.status} />,
                  formatRelative(runtime.last_authenticated_at),
                  <Link
                    key={runtime.id}
                    href={`/governance/runtime-identities/${runtime.id}`}
                    className="text-sm font-semibold text-accent-600 hover:text-accent-500"
                  >
                    Open →
                  </Link>,
                ])}
              />
            )}
          </div>
        )}

        {tab === "Report Summary" && <AISystemReportTab systemId={systemId} />}

        {tab === "Activity" && (
          <div className="overflow-hidden rounded-lg border border-base-200 bg-base-50">
            <div className="border-b border-base-200 px-4 py-2">
              <span className="text-sm font-semibold text-ink-900">Recent Trajectories</span>
            </div>
            {trajectories.length === 0 ? (
              <div className="flex min-h-48 flex-col items-center justify-center px-6 text-center">
                <h3 className="text-sm font-semibold">Waiting for runtime activity.</h3>
                <p className="mt-1 max-w-md text-xs text-ink-500">
                  Connect your application using a runtime credential. Incoming governed activity
                  will appear here automatically.
                </p>
              </div>
            ) : (
              <>
                <Table
                  columns={[
                    "Trajectory",
                    "Time",
                    "Agent",
                    "Version",
                    "Runtime Identity",
                    "Decision",
                    "Risk",
                  ]}
                  rows={trajectories.map((trajectory) => [
                    <Link
                      key={`${trajectory.id}-id`}
                      href={`/runtime/trajectories/${trajectory.id}`}
                      className="font-mono text-xs text-accent-600 hover:underline"
                    >
                      <TechnicalValue>{trajectory.id}</TechnicalValue>
                    </Link>,
                    formatDate(trajectory.started_at),
                    trajectory.agent_name ?? "—",
                    trajectory.agent_version_number != null
                      ? `v${trajectory.agent_version_number}`
                      : "—",
                    <TechnicalValue key={`${trajectory.id}-rt`}>
                      {trajectory.runtime_identity_name ?? "—"}
                    </TechnicalValue>,
                    <StatusBadge
                      key={`${trajectory.id}-status`}
                      status={trajectory.deployment_control ?? trajectory.status}
                    />,
                    trajectory.assurance_summary?.highest ? (
                      <StatusBadge
                        key={`${trajectory.id}-risk`}
                        status={trajectory.assurance_summary.highest}
                      />
                    ) : (
                      "—"
                    ),
                  ])}
                />
                <PaginationBar
                  total={trajectoriesTotal}
                  page={trajectoriesPage}
                  pageSize={10}
                  onPage={(next) => {
                    setTrajectoriesPage(next);
                    void getTrajectories({
                      ai_system_id: systemId,
                      limit: 10,
                      offset: next * 10,
                    })
                      .then((res) => {
                        setTrajectories(res.data.items ?? []);
                        setTrajectoriesTotal(res.data.total ?? res.data.items?.length ?? 0);
                      })
                      .catch(() => undefined);
                  }}
                />
              </>
            )}
            {provenance?.trajectory_id ? (
              <div className="border-t border-base-200 px-4 py-3 text-xs text-ink-500">
                Last observed provenance trajectory:{" "}
                <Link
                  href={`/runtime/trajectories/${provenance.trajectory_id}`}
                  className="font-semibold text-accent-600 hover:text-accent-500"
                >
                  {provenance.trajectory_id}
                </Link>
              </div>
            ) : null}
          </div>
        )}
      </div>

      <SideDrawer
        open={showEditSystem}
        onClose={() => setShowEditSystem(false)}
        title="Edit AI System"
        description="Ownership, business context, and lifecycle controls."
        width="lg"
        data-testid="edit-ai-system-drawer"
        footer={
          <Button variant="secondary" onClick={() => setShowEditSystem(false)}>
            Close
          </Button>
        }
      >
        <div className="grid gap-4">
          <FormField label="System Name" required>
            <Input
              defaultValue={system.name}
              onBlur={(e) => {
                const value = e.target.value.trim();
                if (value && value !== system.name) void handleUpdateSystem("name", value);
              }}
            />
          </FormField>
          <FormField label="Business Unit">
            <Input
              list="bu-list-edit"
              defaultValue={system.business_unit ?? ""}
              onBlur={(e) => {
                if (e.target.value !== (system.business_unit ?? "")) {
                  void handleUpdateSystem("business_unit", e.target.value);
                }
              }}
            />
            <datalist id="bu-list-edit">
              {BUSINESS_UNITS.map((unit) => (
                <option key={unit} value={unit} />
              ))}
            </datalist>
          </FormField>
          <FormField label="Owner ID">
            <Input
              defaultValue={system.owner_id ?? ""}
              onBlur={(e) => {
                if (e.target.value !== (system.owner_id ?? "")) {
                  void handleUpdateSystem("owner_id", e.target.value);
                }
              }}
            />
          </FormField>
          <FormField label="Risk Tier">
            <Select
              defaultValue={system.risk_tier ?? "MEDIUM"}
              onChange={(e) => void handleUpdateSystem("risk_tier", e.target.value)}
            >
              {RISK_TIERS.map((tier) => (
                <option key={tier} value={tier}>
                  {tier}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Business Purpose">
            <Textarea
              rows={3}
              defaultValue={system.business_purpose ?? ""}
              onBlur={(e) => {
                if (e.target.value !== (system.business_purpose ?? "")) {
                  void handleUpdateSystem("business_purpose", e.target.value);
                }
              }}
            />
          </FormField>
          <div className="rounded-lg border border-base-200 p-3">
            <p className="mb-3 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
              Lifecycle Management
            </p>
            <LifecycleActions
              entityKind="system"
              currentStatus={system.status}
              onTransition={async (status) => {
                await transitionAISystem(systemId, status);
                load();
              }}
            />
          </div>
          {provenance?.found ? (
            <div className="rounded-lg border border-base-200 p-3">
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                External Configuration Provenance
              </p>
              <MetaGrid
                items={[
                  {
                    label: "Configuration ID",
                    value: <TechnicalValue>{provenance.configuration_id ?? "—"}</TechnicalValue>,
                  },
                  {
                    label: "Observed Model",
                    value: <TechnicalValue>{provenance.observed_model ?? "—"}</TechnicalValue>,
                  },
                  {
                    label: "Environment",
                    value: (
                      <TechnicalValue>{provenance.configuration_environment ?? "—"}</TechnicalValue>
                    ),
                  },
                  { label: "Last Seen", value: formatDate(provenance.last_seen_at) },
                ]}
              />
            </div>
          ) : null}
        </div>
      </SideDrawer>

      <SideDrawer
        open={showAgentForm}
        onClose={() => {
          setShowAgentForm(false);
          setAgentForm(EMPTY_AGENT);
        }}
        title="Create Agent"
        description="Register an agent under this AI system."
        width="md"
        data-testid="create-agent-drawer"
        footer={
          <>
            <Button
              variant="secondary"
              disabled={savingAgent}
              onClick={() => {
                setShowAgentForm(false);
                setAgentForm(EMPTY_AGENT);
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={savingAgent}
              onClick={() => void handleCreateAgent()}
            >
              {savingAgent ? "Creating..." : "Create Agent"}
            </Button>
          </>
        }
      >
        <div className="grid gap-4">
          <FormField label="Name" required>
            <Input value={agentForm.name} onChange={(e) => handleAgentNameChange(e.target.value)} />
          </FormField>
          <FormField label="Agent Key" required hint="Filled from the name. Edit to override.">
            <Input
              value={agentForm.agent_key}
              onChange={(e) => setAgentForm({ ...agentForm, agent_key: e.target.value })}
              placeholder="po-assistant"
              className="font-mono"
            />
          </FormField>
          <FormField label="Owner ID">
            <Input
              value={agentForm.owner_id}
              onChange={(e) => setAgentForm({ ...agentForm, owner_id: e.target.value })}
            />
          </FormField>
          <FormField label="Business Purpose">
            <Textarea
              rows={3}
              value={agentForm.business_purpose}
              onChange={(e) => setAgentForm({ ...agentForm, business_purpose: e.target.value })}
            />
          </FormField>
        </div>
      </SideDrawer>
    </div>
  );
}
