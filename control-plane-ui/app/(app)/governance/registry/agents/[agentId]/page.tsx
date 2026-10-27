"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AgentAvatar } from "@/components/agent-avatar";
import { MetaGrid } from "@/components/console/page-parts";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { SideDrawer } from "@/components/ui/side-drawer";
import { Tabs } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Table } from "@/components/ui/table";
import { Breadcrumbs } from "@/components/registry/breadcrumbs";
import { FormField } from "@/components/registry/form-field";
import { LifecycleActions } from "@/components/registry/lifecycle-actions";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import {
  createAgentVersion,
  getAgent,
  getAgentVersions,
  getAISystem,
  transitionAgent,
  updateAgent,
} from "@/lib/api";
import { RISK_TIERS } from "@/lib/registry-constants";
import type { AgentSummary, AgentVersionSummary, AISystemSummary } from "@/lib/types";

export default function AgentDetailPage() {
  const params = useParams();
  const agentId = params.agentId as string;
  const [agent, setAgent] = useState<AgentSummary | null>(null);
  const [system, setSystem] = useState<AISystemSummary | null>(null);
  const [versions, setVersions] = useState<AgentVersionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showVersionForm, setShowVersionForm] = useState(false);
  const [showUpdate, setShowUpdate] = useState(false);
  const [screen, setScreen] = useState("Overview");
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [agentForm, setAgentForm] = useState({
    name: "",
    owner_id: "",
    business_purpose: "",
    description: "",
    avatar: "",
  });
  const [versionForm, setVersionForm] = useState({
    change_summary: "",
    risk_tier: "MEDIUM",
  });

  const load = useCallback(() => {
    setLoading(true);
    getAgent(agentId)
      .then(async (agentRes) => {
        const agentData = agentRes.data;
        setAgent(agentData);
        setAgentForm({
          name: agentData.name,
          owner_id: agentData.owner_id ?? "",
          business_purpose: agentData.business_purpose ?? "",
          description: agentData.description ?? "",
          avatar: agentData.avatar ?? "",
        });
        const [sysRes, versionsRes] = await Promise.all([
          getAISystem(agentData.ai_system_id),
          getAgentVersions(agentId),
        ]);
        setSystem(sysRes.data);
        setVersions(versionsRes.data);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [agentId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreateVersion = async () => {
    await createAgentVersion(agentId, {
      change_summary: versionForm.change_summary || undefined,
      risk_tier: versionForm.risk_tier,
    });
    setShowVersionForm(false);
    setVersionForm({ change_summary: "", risk_tier: "MEDIUM" });
    load();
  };

  const handleUpdateAgent = async () => {
    if (!agentForm.name.trim()) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      await updateAgent(agentId, {
        name: agentForm.name.trim(),
        owner_id: agentForm.owner_id.trim() || undefined,
        business_purpose: agentForm.business_purpose.trim() || undefined,
        description: agentForm.description.trim() || undefined,
        avatar: agentForm.avatar.trim(),
      });
      setSaveMessage("Agent updated successfully.");
      setShowUpdate(false);
      load();
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Failed to update agent");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="p-8 text-center text-sm text-ink-500">Loading agent...</div>;
  }

  if (error || !agent) {
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
            label: system?.name ?? "System",
            href: `/governance/registry/${agent.ai_system_id}`,
          },
          { label: agent.name },
        ]}
      />

      <SectionHeader
        title={agent.name}
        subtitle={agent.business_purpose ?? agent.agent_key}
        actions={
          <>
            <StatusBadge status={agent.status} />
            <Button variant="secondary" onClick={() => setShowUpdate(true)}>
              Update
            </Button>
          </>
        }
      />

      <div className="flex items-center gap-3">
        <AgentAvatar name={agent.name} avatar={agent.avatar} size={40} />
        <p className="font-mono text-xs text-ink-500">{agent.agent_key}</p>
      </div>

      <Tabs tabs={["Overview", "Workflow"]} active={screen} onChange={setScreen} />

      {screen === "Overview" ? (
        <div className="space-y-6">
          <Panel title="Agent">
            <MetaGrid
              items={[
                { label: "Name", value: agent.name },
                { label: "Owner", value: agent.owner_id || "—" },
                { label: "Status", value: <StatusBadge status={agent.status} /> },
                {
                  label: "Parent system",
                  value: (
                    <Link
                      href={`/governance/registry/${agent.ai_system_id}`}
                      className="font-medium text-accent-600"
                    >
                      {system?.name ?? agent.ai_system_id}
                    </Link>
                  ),
                },
                { label: "Business purpose", value: agent.business_purpose || "—" },
                { label: "Description", value: agent.description || "—" },
              ]}
            />
          </Panel>

          <Panel
            title="Version History"
            description="Each version is immutable once approved. Changes create a new version."
            actions={
              <Button variant="primary" onClick={() => setShowVersionForm(!showVersionForm)}>
                {showVersionForm ? "Cancel" : "+ New Version"}
              </Button>
            }
          >
            {showVersionForm && (
              <div className="mb-6 grid gap-4 rounded-lg border border-base-100 bg-base-50 p-4 md:grid-cols-2">
                <FormField label="Risk Tier">
                  <Select
                    value={versionForm.risk_tier}
                    onChange={(e) => setVersionForm({ ...versionForm, risk_tier: e.target.value })}
                  >
                    {RISK_TIERS.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </Select>
                </FormField>
                <div className="md:col-span-2">
                  <FormField label="Change Summary">
                    <Textarea
                      rows={2}
                      value={versionForm.change_summary}
                      onChange={(e) =>
                        setVersionForm({ ...versionForm, change_summary: e.target.value })
                      }
                      placeholder="What changed in this version?"
                    />
                  </FormField>
                </div>
                <div className="md:col-span-2 flex justify-end">
                  <Button variant="primary" onClick={handleCreateVersion}>
                    Create Version
                  </Button>
                </div>
              </div>
            )}

            <Table
              columns={["Version", "Status", "Risk", "Material Change", "Approved", ""]}
              rows={
                versions.length > 0
                  ? versions.map((v) => [
                      `v${v.version_number}`,
                      <StatusBadge key={`${v.id}-s`} status={v.lifecycle_status} />,
                      v.risk_tier ? <StatusBadge key={`${v.id}-r`} status={v.risk_tier} /> : "—",
                      v.material_change_status !== "NONE" ? (
                        <StatusBadge key={`${v.id}-m`} status={v.material_change_status} />
                      ) : (
                        "—"
                      ),
                      v.approved_at ? new Date(v.approved_at).toLocaleDateString() : "—",
                      <Link
                        key={v.id}
                        href={`/governance/registry/versions/${v.id}`}
                        className="text-sm font-semibold text-accent-600"
                      >
                        Configure →
                      </Link>,
                    ])
                  : [["No versions — create v1 above", "—", "—", "—", "—", "—"]]
              }
            />
          </Panel>
        </div>
      ) : (
        <div className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold text-ink-900">Workflow</h2>
            <p className="mt-1 text-sm text-ink-500">
              Move this agent through review, approval, suspension, or retirement.
            </p>
          </div>
          <LifecycleActions
            entityKind="agent"
            currentStatus={agent.status}
            onTransition={async (status) => {
              await transitionAgent(agentId, status);
              load();
            }}
          />
        </div>
      )}

      <SideDrawer
        open={showUpdate}
        onClose={() => setShowUpdate(false)}
        title="Update agent"
        description={agent.agent_key}
        width="lg"
        data-testid="update-agent-drawer"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowUpdate(false)}>
              Cancel
            </Button>
            <Button variant="primary" disabled={saving} onClick={handleUpdateAgent}>
              {saving ? "Saving..." : "Save"}
            </Button>
          </>
        }
      >
        <div className="grid gap-4">
          {saveMessage ? (
            <p
              className={`text-sm ${saveMessage.includes("success") ? "text-accent-600" : "text-danger-600"}`}
            >
              {saveMessage}
            </p>
          ) : null}
          <FormField label="Agent Key" hint="Stable identifier — cannot be changed">
            <Input value={agent.agent_key} disabled className="bg-base-50 text-ink-500" />
          </FormField>
          <FormField label="Agent Name" required>
            <Input
              value={agentForm.name}
              onChange={(e) => setAgentForm({ ...agentForm, name: e.target.value })}
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
              rows={2}
              value={agentForm.business_purpose}
              onChange={(e) => setAgentForm({ ...agentForm, business_purpose: e.target.value })}
            />
          </FormField>
          <FormField label="Description">
            <Textarea
              rows={2}
              value={agentForm.description}
              onChange={(e) => setAgentForm({ ...agentForm, description: e.target.value })}
            />
          </FormField>
          <FormField label="Avatar URL" hint="Shown in Enforcement and Trajectories">
            <div className="flex items-center gap-3">
              <Input
                value={agentForm.avatar}
                onChange={(e) => setAgentForm({ ...agentForm, avatar: e.target.value })}
                placeholder="https://… or data:image/…"
              />
              <AgentAvatar name={agentForm.name} avatar={agentForm.avatar || null} size={36} />
            </div>
          </FormField>
        </div>
      </SideDrawer>
    </div>
  );
}
