"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Breadcrumbs } from "@/components/registry/breadcrumbs";
import {
  ContentRuleForm,
  EMPTY_CONTENT_RULE_FORM,
  contentRuleFormFromSummary,
} from "@/components/registry/content-rule-form";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import {
  EMPTY_TOOL_RULE_FORM,
  ToolRuleForm,
  toolRuleFormFromSummary,
} from "@/components/registry/tool-rule-form";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  createContentRule,
  createToolRule,
  deleteContentRule,
  deleteToolRule,
  getAISystem,
  getMCPServers,
  getSystemPolicies,
  getTools,
  updateContentRule,
  updateToolRule,
} from "@/lib/api";
import type {
  ContentRuleSummary,
  MCPServerSummary,
  PolicyCollectionDetail,
  ToolResourceSummary,
  ToolRuleSummary,
} from "@/lib/types";

type Tab = "content" | "tool";

function effectLabel(effect: string): string {
  switch (effect) {
    case "ALLOW":
      return "Allow";
    case "MONITOR":
      return "Monitor";
    case "REQUIRE_APPROVAL":
      return "Require Approval";
    case "DENY":
      return "Block";
    default:
      return effect;
  }
}

export default function SystemPoliciesPage() {
  const params = useParams();
  const systemId = params.systemId as string;

  const [systemName, setSystemName] = useState("");
  const [policies, setPolicies] = useState<PolicyCollectionDetail | null>(null);
  const [mcps, setMcps] = useState<MCPServerSummary[]>([]);
  const [tools, setTools] = useState<ToolResourceSummary[]>([]);
  const [tab, setTab] = useState<Tab>("tool");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [effectFilter, setEffectFilter] = useState("");
  const [enabledFilter, setEnabledFilter] = useState("all");

  const [showContentForm, setShowContentForm] = useState(false);
  const [contentForm, setContentForm] = useState(EMPTY_CONTENT_RULE_FORM);
  const [editingContentId, setEditingContentId] = useState<string | null>(null);

  const [showToolForm, setShowToolForm] = useState(false);
  const [toolForm, setToolForm] = useState(EMPTY_TOOL_RULE_FORM);
  const [editingToolId, setEditingToolId] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([getAISystem(systemId), getSystemPolicies(systemId), getMCPServers(), getTools()])
      .then(([sysRes, policyRes, mcpRes, toolRes]) => {
        setSystemName(sysRes.data.name);
        setPolicies(policyRes.data);
        setMcps(mcpRes.data);
        setTools(toolRes.data);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [systemId]);

  useEffect(() => {
    load();
  }, [load]);

  const toolNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const tool of tools) {
      map.set(tool.id, tool.name);
    }
    for (const mcp of mcps) {
      for (const tool of mcp.tools ?? []) {
        map.set(tool.id, tool.name);
      }
    }
    return map;
  }, [tools, mcps]);

  const filteredContentRules = useMemo(() => {
    if (!policies) return [];
    return policies.content_rules.filter((rule) => {
      if (search && !rule.title.toLowerCase().includes(search.toLowerCase())) return false;
      if (effectFilter && rule.effect !== effectFilter) return false;
      if (enabledFilter === "enabled" && !rule.enabled) return false;
      if (enabledFilter === "disabled" && rule.enabled) return false;
      return true;
    });
  }, [policies, search, effectFilter, enabledFilter]);

  const filteredToolRules = useMemo(() => {
    if (!policies) return [];
    return policies.tool_rules.filter((rule) => {
      if (search && !rule.title.toLowerCase().includes(search.toLowerCase())) return false;
      if (effectFilter && rule.effect !== effectFilter) return false;
      if (enabledFilter === "enabled" && !rule.enabled) return false;
      if (enabledFilter === "disabled" && rule.enabled) return false;
      return true;
    });
  }, [policies, search, effectFilter, enabledFilter]);

  const resetContentForm = () => {
    setContentForm(EMPTY_CONTENT_RULE_FORM);
    setEditingContentId(null);
    setShowContentForm(false);
  };

  const resetToolForm = () => {
    setToolForm(EMPTY_TOOL_RULE_FORM);
    setEditingToolId(null);
    setShowToolForm(false);
  };

  const handleSaveContentRule = async () => {
    if (!contentForm.title.trim() || !contentForm.content.trim()) return;
    const payload = {
      title: contentForm.title,
      content: contentForm.content,
      effect: contentForm.effect,
      enabled: contentForm.enabled,
      applies_to: contentForm.applies_to,
      category: contentForm.category || undefined,
      severity: contentForm.severity || undefined,
      required_approver_role:
        contentForm.effect === "REQUIRE_APPROVAL" ? contentForm.required_approver_role : undefined,
    };
    if (editingContentId) {
      await updateContentRule(editingContentId, payload);
    } else {
      await createContentRule(systemId, payload);
    }
    resetContentForm();
    load();
  };

  const handleSaveToolRule = async () => {
    if (!toolForm.title.trim() || !toolForm.tool_id) return;
    const payload = {
      title: toolForm.title,
      description: toolForm.description || undefined,
      mcp_server_id: toolForm.mcp_server_id || undefined,
      tool_id: toolForm.tool_id,
      match_mode: toolForm.match_mode,
      effect: toolForm.effect,
      enabled: toolForm.enabled,
      severity: toolForm.severity || undefined,
      category: toolForm.category || undefined,
      required_approver_role:
        toolForm.effect === "REQUIRE_APPROVAL" ? toolForm.required_approver_role : undefined,
      conditions: toolForm.conditions,
    };
    if (editingToolId) {
      await updateToolRule(editingToolId, payload);
    } else {
      await createToolRule(systemId, payload);
    }
    resetToolForm();
    load();
  };

  const startEditContent = (rule: ContentRuleSummary) => {
    setTab("content");
    setContentForm(contentRuleFormFromSummary(rule));
    setEditingContentId(rule.id);
    setShowContentForm(true);
  };

  const startEditTool = (rule: ToolRuleSummary) => {
    setTab("tool");
    setToolForm(toolRuleFormFromSummary(rule));
    setEditingToolId(rule.id);
    setShowToolForm(true);
  };

  if (loading) {
    return <div className="p-8 text-center text-sm text-ink-500">Loading policies...</div>;
  }

  if (error || !policies) {
    return (
      <div className="rounded-xl bg-danger-50 p-6 text-sm text-danger-600">
        {error ?? "Failed to load policies"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[
          { label: "AI Systems", href: "/governance/registry" },
          { label: systemName, href: `/governance/registry/${systemId}` },
          { label: "Policies" },
        ]}
      />

      <SectionHeader
        title={`Policies — ${systemName}`}
        subtitle="Content rules for governance; tool rules for machine-enforceable runtime decisions."
        actions={
          <Link href={`/governance/registry/${systemId}`}>
            <Button variant="secondary">Back to system</Button>
          </Link>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <Input
          className="max-w-xs"
          placeholder="Search rules..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Select value={effectFilter} onChange={(e) => setEffectFilter(e.target.value)}>
          <option value="">All effects</option>
          <option value="ALLOW">Allow</option>
          <option value="MONITOR">Monitor</option>
          <option value="REQUIRE_APPROVAL">Require Approval</option>
          <option value="DENY">Block</option>
        </Select>
        <Select value={enabledFilter} onChange={(e) => setEnabledFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="enabled">Enabled only</option>
          <option value="disabled">Disabled only</option>
        </Select>
      </div>

      <div className="flex gap-2 border-b border-base-200">
        <button
          type="button"
          className={`px-4 py-2 text-sm font-medium ${
            tab === "content" ? "border-b-2 border-brand-600 text-brand-700" : "text-ink-500"
          }`}
          onClick={() => setTab("content")}
        >
          Content Rules ({policies.content_rules.length})
        </button>
        <button
          type="button"
          className={`px-4 py-2 text-sm font-medium ${
            tab === "tool" ? "border-b-2 border-brand-600 text-brand-700" : "text-ink-500"
          }`}
          onClick={() => setTab("tool")}
        >
          Tool Rules ({policies.tool_rules.length})
        </button>
      </div>

      {tab === "content" && (
        <div className="space-y-4">
          <Panel title="Content Rule Enforcement Status">
            <dl className="grid gap-2 text-sm sm:grid-cols-2">
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Tool Rule Enforcement</dt>
                <dd>ACTIVE / DETERMINISTIC</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Content Rule Enforcement</dt>
                <dd>NOT_ACTIVE</dd>
              </div>
              <div className="flex justify-between gap-4 sm:col-span-2">
                <dt className="text-muted-foreground">Reason</dt>
                <dd>CONTENT_EVALUATOR_NOT_CONFIGURED</dd>
              </div>
            </dl>
            <p className="mt-3 text-sm text-muted-foreground">
              Content rules are stored as governance guidance. Semantic/LLM evaluation is not active
              in WP4; a future ContentPolicyEvaluator seam will classify findings for the Policy
              Engine.
            </p>
          </Panel>
          <div className="flex justify-end">
            <Button
              variant="primary"
              onClick={() => {
                resetContentForm();
                setShowContentForm(true);
              }}
            >
              + New Content Rule
            </Button>
          </div>

          {showContentForm && (
            <Panel title={editingContentId ? "Edit Content Rule" : "New Content Rule"}>
              <ContentRuleForm value={contentForm} onChange={setContentForm} />
              <div className="mt-4 flex justify-end gap-2">
                <Button variant="secondary" onClick={resetContentForm}>
                  Cancel
                </Button>
                <Button variant="primary" onClick={handleSaveContentRule}>
                  Save
                </Button>
              </div>
            </Panel>
          )}

          {filteredContentRules.length === 0 ? (
            <div className="rounded-xl border border-dashed border-base-300 p-8 text-center text-sm text-ink-500">
              No content rules yet. Add governance guidance for operators and reviewers.
            </div>
          ) : (
            filteredContentRules.map((rule) => (
              <Panel key={rule.id} title={rule.title}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <StatusBadge status={rule.enabled ? "ACTIVE" : "DISABLED"} />
                      <span className="text-xs text-ink-500">{effectLabel(rule.effect)}</span>
                    </div>
                    <p className="whitespace-pre-wrap text-sm text-ink-700">{rule.content}</p>
                    {rule.required_approver_role && (
                      <p className="text-xs text-ink-500">
                        Approver role: {rule.required_approver_role}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Button variant="secondary" size="sm" onClick={() => startEditContent(rule)}>
                      Edit
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={async () => {
                        await updateContentRule(rule.id, { enabled: !rule.enabled });
                        load();
                      }}
                    >
                      {rule.enabled ? "Disable" : "Enable"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={async () => {
                        await deleteContentRule(rule.id);
                        load();
                      }}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              </Panel>
            ))
          )}
        </div>
      )}

      {tab === "tool" && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <Button
              variant="primary"
              onClick={() => {
                resetToolForm();
                setShowToolForm(true);
              }}
            >
              + New Tool Rule
            </Button>
          </div>

          {showToolForm && (
            <Panel title={editingToolId ? "Edit Tool Rule" : "New Tool Rule"}>
              <ToolRuleForm value={toolForm} onChange={setToolForm} mcps={mcps} tools={tools} />
              <div className="mt-4 flex justify-end gap-2">
                <Button variant="secondary" onClick={resetToolForm}>
                  Cancel
                </Button>
                <Button variant="primary" onClick={handleSaveToolRule}>
                  Save
                </Button>
              </div>
            </Panel>
          )}

          {filteredToolRules.length === 0 ? (
            <div className="rounded-xl border border-dashed border-base-300 p-8 text-center text-sm text-ink-500">
              No tool rules yet. Create machine-enforceable rules for MCP tool invocations.
            </div>
          ) : (
            filteredToolRules.map((rule) => (
              <Panel key={rule.id} title={rule.title}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center gap-2">
                      <StatusBadge status={rule.enabled ? "ACTIVE" : "DISABLED"} />
                      <span className="text-xs text-ink-500">{effectLabel(rule.effect)}</span>
                      <span className="text-xs text-ink-400">· {rule.match_mode}</span>
                    </div>
                    {rule.description && <p className="text-ink-600">{rule.description}</p>}
                    <p className="text-ink-700">
                      Tool: <strong>{toolNameById.get(rule.tool_id) ?? rule.tool_id}</strong>
                    </p>
                    {rule.conditions.length > 0 && (
                      <ul className="list-inside list-disc text-xs text-ink-500">
                        {rule.conditions.map((c, i) => (
                          <li key={i}>
                            {c.parameter_path} {c.operator}{" "}
                            {c.operator !== "exists" && c.operator !== "not_exists"
                              ? JSON.stringify(c.value)
                              : ""}
                          </li>
                        ))}
                      </ul>
                    )}
                    {rule.required_approver_role && (
                      <p className="text-xs text-ink-500">
                        Approver role: {rule.required_approver_role}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Button variant="secondary" size="sm" onClick={() => startEditTool(rule)}>
                      Edit
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={async () => {
                        await updateToolRule(rule.id, { enabled: !rule.enabled });
                        load();
                      }}
                    >
                      {rule.enabled ? "Disable" : "Enable"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={async () => {
                        await deleteToolRule(rule.id);
                        load();
                      }}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              </Panel>
            ))
          )}
        </div>
      )}
    </div>
  );
}
