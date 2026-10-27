"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Plus } from "lucide-react";
import {
  ContentRuleForm,
  EMPTY_CONTENT_RULE_FORM,
  contentRuleFormFromSummary,
} from "@/components/registry/content-rule-form";
import { FormField } from "@/components/registry/form-field";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import {
  EMPTY_TOOL_RULE_FORM,
  ToolRuleForm,
  toolRuleFormFromSummary,
} from "@/components/registry/tool-rule-form";
import { SectionHeader } from "@/components/section-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { SideDrawer } from "@/components/ui/side-drawer";
import { Table } from "@/components/ui/table";
import {
  createContentRule,
  createToolRule,
  getAISystems,
  getMCPServers,
  getPolicyLibrary,
  getRaiRulesUnified,
  getTools,
  updateContentRule,
  updateToolRule,
} from "@/lib/api";
import type {
  AISystemSummary,
  ContentRuleSummary,
  MCPServerSummary,
  PolicySourceSummary,
  ToolResourceSummary,
  ToolRuleSummary,
  UnifiedRaiRuleItem,
} from "@/lib/types";

const PAGE_SIZE = 50;
const EFFECT_OPTIONS = ["", "MONITOR", "REQUIRE_APPROVAL", "DENY", "MARK", "ALLOW"];
const STATUS_OPTIONS = ["", "ACTIVE", "DISABLED"];
const SEVERITY_OPTIONS = ["", "INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"];

function effectLabel(effect: string): string {
  switch (effect) {
    case "ALLOW":
      return "Allow";
    case "MARK":
      return "Mark";
    case "MONITOR":
      return "Monitor";
    case "REQUIRE_APPROVAL":
      return "Approval";
    case "DENY":
      return "Block";
    default:
      return effect;
  }
}

export default function RaiRulesPage() {
  const [items, setItems] = useState<UnifiedRaiRuleItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [systems, setSystems] = useState<AISystemSummary[]>([]);
  const [mcps, setMcps] = useState<MCPServerSummary[]>([]);
  const [tools, setTools] = useState<ToolResourceSummary[]>([]);
  const [policySources, setPolicySources] = useState<PolicySourceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [filterSystemId, setFilterSystemId] = useState("");
  const [ruleType, setRuleType] = useState("");
  const [toolId, setToolId] = useState("");
  const [mcpServerId, setMcpServerId] = useState("");
  const [effect, setEffect] = useState("");
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");

  const [formSystemId, setFormSystemId] = useState("");
  const [originalSystemId, setOriginalSystemId] = useState("");
  const [showContentForm, setShowContentForm] = useState(false);
  const [contentForm, setContentForm] = useState(EMPTY_CONTENT_RULE_FORM);
  const [editingContentId, setEditingContentId] = useState<string | null>(null);
  const [showToolForm, setShowToolForm] = useState(false);
  const [toolForm, setToolForm] = useState(EMPTY_TOOL_RULE_FORM);
  const [editingToolId, setEditingToolId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<UnifiedRaiRuleItem | null>(null);

  const load = useCallback(
    async (pageOffset = 0, append = false) => {
      setLoading(true);
      setError(null);
      try {
        const res = await getRaiRulesUnified({
          search: search.trim() || undefined,
          ai_system_id: filterSystemId || undefined,
          rule_type: ruleType || undefined,
          tool_id: toolId || undefined,
          mcp_server_id: mcpServerId || undefined,
          effect: effect || undefined,
          severity: severity || undefined,
          status: status || undefined,
          limit: PAGE_SIZE,
          offset: pageOffset,
        });
        const rows = res.data.items ?? [];
        setItems((prev) => (append ? [...prev, ...rows] : rows));
        setTotal(res.data.total ?? 0);
        setOffset(pageOffset);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load rules");
      } finally {
        setLoading(false);
      }
    },
    [search, filterSystemId, ruleType, toolId, mcpServerId, effect, severity, status],
  );

  useEffect(() => {
    Promise.all([getAISystems(), getMCPServers(), getTools(), getPolicyLibrary({ limit: 200 })])
      .then(([systemsRes, mcpRes, toolRes, policyRes]) => {
        setSystems(systemsRes.data ?? []);
        setMcps(mcpRes.data ?? []);
        setTools(toolRes.data ?? []);
        setPolicySources(policyRes.data.items ?? []);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    void load(0, false);
  }, [load]);

  const resetForms = () => {
    setShowContentForm(false);
    setShowToolForm(false);
    setEditingContentId(null);
    setEditingToolId(null);
    setContentForm(EMPTY_CONTENT_RULE_FORM);
    setToolForm(EMPTY_TOOL_RULE_FORM);
    setFormSystemId("");
    setOriginalSystemId("");
    setSaveError(null);
  };

  const startCreateContent = () => {
    resetForms();
    setShowContentForm(true);
  };

  const startCreateTool = () => {
    resetForms();
    setShowToolForm(true);
  };

  const startEdit = (rule: UnifiedRaiRuleItem) => {
    resetForms();
    setDrawer(null);
    const sid = rule.ai_system_id ?? "";
    setFormSystemId(sid);
    setOriginalSystemId(sid);
    if (rule.rule_type === "CONTENT") {
      setContentForm(
        contentRuleFormFromSummary({
          id: rule.id,
          policy_collection_id: "",
          title: rule.title,
          content: rule.content ?? "",
          effect: rule.effect as ContentRuleSummary["effect"],
          enabled: rule.enabled,
          applies_to: rule.applies_to ?? undefined,
          category: rule.category ?? undefined,
          severity: rule.severity ?? undefined,
          required_approver_role: rule.required_approver_role ?? undefined,
        }),
      );
      setEditingContentId(rule.id);
      setShowContentForm(true);
    } else {
      setToolForm(
        toolRuleFormFromSummary({
          id: rule.id,
          policy_collection_id: "",
          title: rule.title,
          description: rule.description,
          mcp_server_id: rule.mcp_server_id,
          tool_id: rule.tool_id ?? "",
          match_mode: (rule.match_mode as "ALL" | "ANY") || "ALL",
          effect: rule.effect as ToolRuleSummary["effect"],
          enabled: rule.enabled,
          required_approver_role: rule.required_approver_role,
          severity: rule.severity,
          category: rule.category,
          conditions: rule.conditions ?? [],
        }),
      );
      setEditingToolId(rule.id);
      setShowToolForm(true);
    }
  };

  const handleSaveContent = async () => {
    if (!contentForm.title.trim() || !contentForm.content.trim() || !formSystemId) return;
    setSaving(true);
    setSaveError(null);
    try {
      const payload = {
        title: contentForm.title,
        content: contentForm.content,
        effect: contentForm.effect,
        enabled: contentForm.enabled,
        applies_to: contentForm.applies_to,
        category: contentForm.category || undefined,
        severity: contentForm.severity || undefined,
        required_approver_role:
          contentForm.effect === "REQUIRE_APPROVAL"
            ? contentForm.required_approver_role
            : undefined,
        source_policy_id: contentForm.source_policy_id || undefined,
      };
      if (editingContentId) {
        await updateContentRule(editingContentId, {
          ...payload,
          ...(formSystemId !== originalSystemId ? { ai_system_id: formSystemId } : {}),
        });
      } else {
        await createContentRule(formSystemId, payload);
      }
      resetForms();
      await load(0, false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save content rule");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveTool = async () => {
    if (!toolForm.title.trim() || !toolForm.tool_id || !formSystemId) return;
    setSaving(true);
    setSaveError(null);
    try {
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
        source_policy_id: toolForm.source_policy_id || undefined,
        conditions: toolForm.conditions,
      };
      if (editingToolId) {
        await updateToolRule(editingToolId, {
          ...payload,
          clear_mcp_server_id: !toolForm.mcp_server_id,
          ...(formSystemId !== originalSystemId ? { ai_system_id: formSystemId } : {}),
        });
      } else {
        await createToolRule(formSystemId, payload);
      }
      resetForms();
      await load(0, false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save tool rule");
    } finally {
      setSaving(false);
    }
  };

  const filteredTools = mcpServerId ? tools.filter((t) => t.mcp_server_id === mcpServerId) : tools;
  const hasMore = offset + items.length < total;
  const showToolFilter = ruleType !== "CONTENT";

  return (
    <div className="space-y-6" data-testid="rai-rules-page">
      <SectionHeader
        title="RAI Rules"
        subtitle="Executable runtime controls for content and tool actions."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => void load(0, false)}>
              Refresh
            </Button>
            <Button variant="secondary" onClick={startCreateContent}>
              <Plus className="size-4" aria-hidden />
              Content Rule
            </Button>
            <Button onClick={startCreateTool}>
              <Plus className="size-4" aria-hidden />
              Tool Rule
            </Button>
          </div>
        }
      />

      <Panel>
        <div className="flex flex-wrap gap-3">
          <Input
            placeholder="Search rules…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-xs"
          />
          <Select
            value={filterSystemId}
            onChange={(e) => setFilterSystemId(e.target.value)}
            className="w-48"
          >
            <option value="">All AI Systems</option>
            {systems.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
          <Select
            value={ruleType}
            onChange={(e) => {
              setRuleType(e.target.value);
              if (e.target.value === "CONTENT") {
                setToolId("");
                setMcpServerId("");
              }
            }}
            className="w-36"
          >
            <option value="">All types</option>
            <option value="CONTENT">Content</option>
            <option value="TOOL">Tool</option>
          </Select>
          {showToolFilter && (
            <>
              <Select
                value={mcpServerId}
                onChange={(e) => {
                  setMcpServerId(e.target.value);
                  setToolId("");
                }}
                className="w-44"
              >
                <option value="">Any MCP</option>
                {mcps.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </Select>
              <Select value={toolId} onChange={(e) => setToolId(e.target.value)} className="w-48">
                <option value="">Any tool</option>
                {filteredTools.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            </>
          )}
          <Select value={effect} onChange={(e) => setEffect(e.target.value)} className="w-40">
            {EFFECT_OPTIONS.map((opt) => (
              <option key={opt || "all-effect"} value={opt}>
                {opt ? effectLabel(opt) : "All effects"}
              </option>
            ))}
          </Select>
          <Select value={severity} onChange={(e) => setSeverity(e.target.value)} className="w-36">
            {SEVERITY_OPTIONS.map((opt) => (
              <option key={opt || "all-sev"} value={opt}>
                {opt || "All severities"}
              </option>
            ))}
          </Select>
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-36">
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt || "all-status"} value={opt}>
                {opt || "All statuses"}
              </option>
            ))}
          </Select>
          <Button onClick={() => void load(0, false)}>Apply</Button>
        </div>
      </Panel>

      <SideDrawer
        open={showContentForm || showToolForm}
        onClose={() => {
          if (!saving) resetForms();
        }}
        title={
          showContentForm
            ? editingContentId
              ? "Edit Content Rule"
              : "Create Content Rule"
            : editingToolId
              ? "Edit Tool Rule"
              : "Create Tool Rule"
        }
        description="Configure an enforceable runtime rule without introducing synthetic risk entities."
        width="2xl"
        data-testid="create-rule-drawer"
        footer={
          <>
            <Button
              variant="secondary"
              disabled={saving}
              onClick={() => {
                if (!saving) resetForms();
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={
                saving ||
                !formSystemId ||
                (showContentForm
                  ? !contentForm.title.trim() || !contentForm.content.trim()
                  : !toolForm.title.trim() || !toolForm.tool_id)
              }
              onClick={() => void (showContentForm ? handleSaveContent() : handleSaveTool())}
            >
              {saving
                ? "Saving…"
                : showContentForm
                  ? editingContentId
                    ? "Save Content Rule"
                    : "Create Content Rule"
                  : editingToolId
                    ? "Save Tool Rule"
                    : "Create Tool Rule"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <FormField label="AI System" required>
            <Select
              value={formSystemId}
              disabled={saving}
              onChange={(e) => setFormSystemId(e.target.value)}
            >
              <option value="">Select AI System…</option>
              {systems.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </FormField>
          {showContentForm ? (
            <ContentRuleForm
              value={contentForm}
              onChange={setContentForm}
              policySources={policySources}
            />
          ) : (
            <ToolRuleForm
              value={toolForm}
              onChange={setToolForm}
              mcps={mcps}
              tools={tools}
              policySources={policySources}
            />
          )}
          {saveError ? <p className="text-sm text-danger-600">{saveError}</p> : null}
        </div>
      </SideDrawer>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading && items.length === 0 ? (
        <p className="text-sm text-muted-foreground">Loading rules…</p>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            Showing {items.length} of {total} rules
          </p>
          <Table
            columns={[
              "Rule",
              "AI System",
              "Type",
              "Applies To / Target",
              "Effect",
              "Severity",
              "Status",
              "Source Policy",
              "Actions",
            ]}
            rows={items.map((rule) => {
              const cells: ReactNode[] = [
                rule.title,
                rule.ai_system_name ?? "—",
                <Badge key={`${rule.id}-type`} variant="neutral">
                  {rule.rule_type === "CONTENT" ? "Content" : "Tool"}
                </Badge>,
                rule.target ?? rule.applies_to ?? "—",
                effectLabel(rule.effect),
                rule.severity ?? "—",
                <StatusBadge key={`${rule.id}-status`} status={rule.status} />,
                rule.source_policy?.title ?? "—",
                <Button
                  key={`${rule.id}-edit`}
                  variant="ghost"
                  size="sm"
                  onClick={() => startEdit(rule)}
                >
                  Edit
                </Button>,
              ];
              return cells;
            })}
            onRowClick={(idx) => setDrawer(items[idx] ?? null)}
          />
          {hasMore && (
            <div className="flex justify-center">
              <Button
                variant="secondary"
                disabled={loading}
                onClick={() => void load(offset + PAGE_SIZE, true)}
              >
                {loading ? "Loading…" : "Load more"}
              </Button>
            </div>
          )}
        </>
      )}

      <SideDrawer
        open={!!drawer}
        onClose={() => setDrawer(null)}
        title={drawer?.title ?? "Rule detail"}
        description={
          drawer?.rule_type === "CONTENT" ? "Content rule" : drawer ? "Tool rule" : undefined
        }
        width="md"
        data-testid="rule-detail-drawer"
        footer={
          drawer ? (
            <>
              <Button variant="secondary" onClick={() => setDrawer(null)}>
                Close
              </Button>
              <Button
                onClick={() => {
                  startEdit(drawer);
                }}
              >
                Edit rule
              </Button>
            </>
          ) : null
        }
      >
        {drawer ? (
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-[11px] font-semibold uppercase text-ink-400">AI System</dt>
              <dd className="mt-1">{drawer.ai_system_name ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-semibold uppercase text-ink-400">Effect</dt>
              <dd className="mt-1">{effectLabel(drawer.effect)}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-semibold uppercase text-ink-400">Severity</dt>
              <dd className="mt-1">{drawer.severity ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-semibold uppercase text-ink-400">Status</dt>
              <dd className="mt-1">
                <StatusBadge status={drawer.status} />
              </dd>
            </div>
            <div>
              <dt className="text-[11px] font-semibold uppercase text-ink-400">
                Applies to / Target
              </dt>
              <dd className="mt-1">{drawer.target ?? drawer.applies_to ?? "—"}</dd>
            </div>
            {drawer.content ? (
              <div>
                <dt className="text-[11px] font-semibold uppercase text-ink-400">Instruction</dt>
                <dd className="mt-1 whitespace-pre-wrap">{drawer.content}</dd>
              </div>
            ) : null}
            {drawer.source_policy ? (
              <div>
                <dt className="text-[11px] font-semibold uppercase text-ink-400">Source policy</dt>
                <dd className="mt-1">{drawer.source_policy.title}</dd>
              </div>
            ) : null}
          </dl>
        ) : null}
      </SideDrawer>
    </div>
  );
}
