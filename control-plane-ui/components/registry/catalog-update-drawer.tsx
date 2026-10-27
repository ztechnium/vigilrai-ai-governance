"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { SideDrawer } from "@/components/ui/side-drawer";
import { Textarea } from "@/components/ui/textarea";
import { Table } from "@/components/ui/table";
import { FormField } from "@/components/registry/form-field";
import { StatusBadge } from "@/components/registry/status-badge";
import {
  createTool,
  getMCPServer,
  getModel,
  updateMCPServer,
  updateModel,
  updateTool,
} from "@/lib/api";
import type { MCPServerSummary, ModelResourceSummary, ResourceCatalogItem } from "@/lib/types";

type McpTool = NonNullable<MCPServerSummary["tools"]>[number];

function formatSourceType(sourceType?: string | null): string {
  if (sourceType === "SEEDED_TEMPLATE") return "Seeded Template";
  if (sourceType) return sourceType;
  return "—";
}

function formatAliases(aliases?: string[]): string {
  if (!aliases || aliases.length === 0) return "—";
  return aliases.join(", ");
}

function ModelEditor({
  modelId,
  onSaved,
}: {
  modelId: string;
  onSaved: () => Promise<void> | void;
}) {
  const [model, setModel] = useState<ModelResourceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [form, setForm] = useState({
    provider: "",
    model_name: "",
    model_version: "",
    deployment_reference: "",
    hosting_type: "",
  });

  const load = useCallback(() => {
    setLoading(true);
    getModel(modelId)
      .then((res) => {
        setModel(res.data);
        setForm({
          provider: res.data.provider,
          model_name: res.data.model_name,
          model_version: res.data.model_version ?? "",
          deployment_reference: res.data.deployment_reference ?? "",
          hosting_type: res.data.hosting_type ?? "",
        });
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [modelId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async () => {
    if (!form.provider.trim() || !form.model_name.trim() || saving) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      await updateModel(modelId, {
        provider: form.provider.trim(),
        model_name: form.model_name.trim(),
        model_version: form.model_version.trim() || undefined,
        deployment_reference: form.deployment_reference.trim() || undefined,
        hosting_type: form.hosting_type.trim() || undefined,
      });
      setSaveMessage("Model updated successfully.");
      load();
      await onSaved();
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Failed to update model");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-ink-500">Loading model…</p>;
  }
  if (error || !model) {
    return <p className="text-sm text-danger-600">{error ?? "Not found"}</p>;
  }

  const succeeded = saveMessage?.includes("success");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-ink-500">Update model metadata used by agent versions.</p>
        <StatusBadge status={model.status} />
      </div>
      <FormField label="Provider" required>
        <Input
          value={form.provider}
          disabled={saving}
          onChange={(e) => setForm({ ...form, provider: e.target.value })}
        />
      </FormField>
      <FormField label="Model Name" required>
        <Input
          value={form.model_name}
          disabled={saving}
          onChange={(e) => setForm({ ...form, model_name: e.target.value })}
        />
      </FormField>
      <FormField label="Model Version">
        <Input
          value={form.model_version}
          disabled={saving}
          onChange={(e) => setForm({ ...form, model_version: e.target.value })}
          placeholder="2024-08-06"
        />
      </FormField>
      <FormField label="Hosting Type">
        <Input
          value={form.hosting_type}
          disabled={saving}
          onChange={(e) => setForm({ ...form, hosting_type: e.target.value })}
          placeholder="managed"
        />
      </FormField>
      <FormField label="Deployment Reference">
        <Input
          value={form.deployment_reference}
          disabled={saving}
          onChange={(e) => setForm({ ...form, deployment_reference: e.target.value })}
          placeholder="azure-openai://eastus/gpt-4o"
        />
      </FormField>
      {saveMessage ? (
        <p className={`text-sm ${succeeded ? "text-accent-600" : "text-danger-600"}`}>
          {saveMessage}
        </p>
      ) : null}
      <div className="flex justify-end">
        <Button
          variant="primary"
          disabled={saving || !form.provider.trim() || !form.model_name.trim()}
          onClick={() => void handleSave()}
        >
          {saving ? "Saving…" : "Save changes"}
        </Button>
      </div>
    </div>
  );
}

function McpEditor({ mcpId, onSaved }: { mcpId: string; onSaved: () => Promise<void> | void }) {
  const [server, setServer] = useState<MCPServerSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [showToolForm, setShowToolForm] = useState(false);
  const [serverForm, setServerForm] = useState({
    name: "",
    description: "",
    environment: "",
    endpoint_reference: "",
    trust_classification: "",
  });
  const [toolForm, setToolForm] = useState({
    tool_key: "",
    name: "",
    description: "",
    category: "",
    consequential_action: false,
  });
  const [editingTool, setEditingTool] = useState<McpTool | null>(null);
  const [editForm, setEditForm] = useState({
    name: "",
    description: "",
    category: "",
    consequential_action: false,
    status: "ACTIVE",
    capability_type: "",
    side_effect: "",
    default_risk: "",
  });
  const [toolSaving, setToolSaving] = useState(false);
  const [toolError, setToolError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    getMCPServer(mcpId)
      .then((res) => {
        setServer(res.data);
        setServerForm({
          name: res.data.name,
          description: res.data.description ?? "",
          environment: res.data.environment ?? "",
          endpoint_reference: res.data.endpoint_reference ?? "",
          trust_classification: res.data.trust_classification ?? "",
        });
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [mcpId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleSaveServer = async () => {
    if (!serverForm.name.trim() || saving) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      await updateMCPServer(mcpId, {
        name: serverForm.name.trim(),
        description: serverForm.description.trim() || undefined,
        environment: serverForm.environment.trim() || undefined,
        endpoint_reference: serverForm.endpoint_reference.trim() || undefined,
        trust_classification: serverForm.trust_classification.trim() || undefined,
      });
      setSaveMessage("MCP server updated successfully.");
      load();
      await onSaved();
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Failed to update MCP server");
    } finally {
      setSaving(false);
    }
  };

  const handleCreateTool = async () => {
    if (!toolForm.tool_key.trim() || !toolForm.name.trim()) return;
    setToolError(null);
    try {
      await createTool({
        ...toolForm,
        tool_key: toolForm.tool_key.trim(),
        name: toolForm.name.trim(),
        mcp_server_id: mcpId,
      });
      setToolForm({
        tool_key: "",
        name: "",
        description: "",
        category: "",
        consequential_action: false,
      });
      setShowToolForm(false);
      load();
      await onSaved();
    } catch (err) {
      setToolError(err instanceof Error ? err.message : "Failed to add tool");
    }
  };

  const openEditTool = (tool: McpTool) => {
    setToolError(null);
    setEditingTool(tool);
    setEditForm({
      name: tool.name,
      description: tool.description ?? "",
      category: tool.category ?? "",
      consequential_action: Boolean(tool.consequential_action),
      status: tool.status ?? "ACTIVE",
      capability_type: tool.capability_type ?? "",
      side_effect: tool.side_effect ?? "",
      default_risk: tool.default_risk ?? "",
    });
  };

  const handleUpdateTool = async () => {
    if (!editingTool || !editForm.name.trim()) return;
    setToolSaving(true);
    setToolError(null);
    try {
      await updateTool(editingTool.id, {
        name: editForm.name.trim(),
        description: editForm.description.trim(),
        category: editForm.category.trim(),
        consequential_action: editForm.consequential_action,
        status: editForm.status,
        ...(editForm.capability_type ? { capability_type: editForm.capability_type } : {}),
        ...(editForm.side_effect ? { side_effect: editForm.side_effect } : {}),
        ...(editForm.default_risk ? { default_risk: editForm.default_risk } : {}),
      });
      setEditingTool(null);
      load();
      await onSaved();
    } catch (err) {
      setToolError(err instanceof Error ? err.message : "Failed to update tool");
    } finally {
      setToolSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-ink-500">Loading MCP server…</p>;
  }
  if (error || !server) {
    return <p className="text-sm text-danger-600">{error ?? "Not found"}</p>;
  }

  const succeeded = saveMessage?.includes("success");
  const toolRows = (server.tools ?? []).map((tool) => [
    tool.tool_key,
    tool.name,
    tool.default_risk ?? "—",
    <StatusBadge key={tool.id} status={tool.status ?? "ACTIVE"} />,
    <Button
      key={`${tool.id}-edit`}
      variant="secondary"
      size="sm"
      onClick={() => openEditTool(tool)}
    >
      Update
    </Button>,
  ]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-ink-500">Server {server.server_key}</p>
        <StatusBadge status={server.status ?? "ACTIVE"} />
      </div>

      <div className="space-y-3">
        <FormField label="Server Key">
          <Input value={server.server_key} disabled />
        </FormField>
        <FormField label="Name" required>
          <Input
            value={serverForm.name}
            disabled={saving}
            onChange={(e) => setServerForm({ ...serverForm, name: e.target.value })}
          />
        </FormField>
        <FormField label="Vendor">
          <Input value={server.vendor ?? server.provider ?? "—"} disabled />
        </FormField>
        <FormField label="Source">
          <Input value={formatSourceType(server.source_type)} disabled />
        </FormField>
        <FormField label="Aliases">
          <Input value={formatAliases(server.native_aliases)} disabled />
        </FormField>
        <FormField label="Environment">
          <Input
            value={serverForm.environment}
            disabled={saving}
            onChange={(e) => setServerForm({ ...serverForm, environment: e.target.value })}
            placeholder="production"
          />
        </FormField>
        <FormField label="Trust Classification">
          <Input
            value={serverForm.trust_classification}
            disabled={saving}
            onChange={(e) => setServerForm({ ...serverForm, trust_classification: e.target.value })}
            placeholder="internal"
          />
        </FormField>
        <FormField label="Endpoint Reference">
          <Input
            value={serverForm.endpoint_reference}
            disabled={saving}
            onChange={(e) => setServerForm({ ...serverForm, endpoint_reference: e.target.value })}
            placeholder="mcp://github-internal (non-secret)"
          />
        </FormField>
        <FormField label="Description">
          <Textarea
            rows={2}
            value={serverForm.description}
            disabled={saving}
            onChange={(e) => setServerForm({ ...serverForm, description: e.target.value })}
          />
        </FormField>
        {saveMessage ? (
          <p className={`text-sm ${succeeded ? "text-accent-600" : "text-danger-600"}`}>
            {saveMessage}
          </p>
        ) : null}
        <div className="flex justify-end">
          <Button
            variant="primary"
            disabled={saving || !serverForm.name.trim()}
            onClick={() => void handleSaveServer()}
          >
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </div>

      <div className="space-y-3 border-t border-base-200 pt-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-ink-900">Tools</h3>
          <Button variant="secondary" size="sm" onClick={() => setShowToolForm((value) => !value)}>
            {showToolForm ? "Cancel" : "+ Add tool"}
          </Button>
        </div>
        {toolError && !editingTool ? <p className="text-sm text-danger-600">{toolError}</p> : null}
        {showToolForm && (
          <div className="grid gap-3">
            <FormField label="Tool Key" required>
              <Input
                value={toolForm.tool_key}
                onChange={(e) => setToolForm({ ...toolForm, tool_key: e.target.value })}
                placeholder="github.create_issue"
              />
            </FormField>
            <FormField label="Name" required>
              <Input
                value={toolForm.name}
                onChange={(e) => setToolForm({ ...toolForm, name: e.target.value })}
              />
            </FormField>
            <FormField label="Category">
              <Input
                value={toolForm.category}
                onChange={(e) => setToolForm({ ...toolForm, category: e.target.value })}
              />
            </FormField>
            <FormField label="Consequential Action">
              <Select
                value={toolForm.consequential_action ? "yes" : "no"}
                onChange={(e) =>
                  setToolForm({ ...toolForm, consequential_action: e.target.value === "yes" })
                }
              >
                <option value="no">No</option>
                <option value="yes">Yes — triggers material change review</option>
              </Select>
            </FormField>
            <FormField label="Description">
              <Textarea
                rows={2}
                value={toolForm.description}
                onChange={(e) => setToolForm({ ...toolForm, description: e.target.value })}
              />
            </FormField>
            <div className="flex justify-end">
              <Button variant="primary" onClick={() => void handleCreateTool()}>
                Add tool
              </Button>
            </div>
          </div>
        )}
        <Table
          columns={["Key", "Name", "Risk", "Status", ""]}
          rows={toolRows.length > 0 ? toolRows : [["No tools yet", "—", "—", "—", "—"]]}
        />
      </div>

      <SideDrawer
        open={editingTool != null}
        onClose={() => setEditingTool(null)}
        title="Update tool"
        description={editingTool?.tool_key}
        width="lg"
        data-testid="update-tool-drawer"
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditingTool(null)}>
              Cancel
            </Button>
            <Button variant="primary" disabled={toolSaving} onClick={() => void handleUpdateTool()}>
              {toolSaving ? "Saving…" : "Save"}
            </Button>
          </>
        }
      >
        <div className="grid gap-4">
          {toolError ? <p className="text-sm text-danger-600">{toolError}</p> : null}
          <FormField label="Tool Key" hint="Stable identifier — cannot be changed">
            <Input value={editingTool?.tool_key ?? ""} disabled />
          </FormField>
          <FormField label="Name" required>
            <Input
              value={editForm.name}
              onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
            />
          </FormField>
          <FormField label="Category">
            <Input
              value={editForm.category}
              onChange={(e) => setEditForm({ ...editForm, category: e.target.value })}
            />
          </FormField>
          <FormField label="Status">
            <Select
              value={editForm.status}
              onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}
            >
              <option value="ACTIVE">ACTIVE</option>
              <option value="DISABLED">DISABLED</option>
            </Select>
          </FormField>
          <FormField label="Capability">
            <Select
              value={editForm.capability_type}
              onChange={(e) => setEditForm({ ...editForm, capability_type: e.target.value })}
            >
              <option value="">Unchanged</option>
              {["READ", "SEARCH", "CREATE", "UPDATE", "DELETE", "EXECUTE", "ADMIN"].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Side Effect">
            <Select
              value={editForm.side_effect}
              onChange={(e) => setEditForm({ ...editForm, side_effect: e.target.value })}
            >
              <option value="">Unchanged</option>
              <option value="NONE">NONE</option>
              <option value="REVERSIBLE">REVERSIBLE</option>
              <option value="CONSEQUENTIAL">CONSEQUENTIAL</option>
            </Select>
          </FormField>
          <FormField label="Risk">
            <Select
              value={editForm.default_risk}
              onChange={(e) => setEditForm({ ...editForm, default_risk: e.target.value })}
            >
              <option value="">Unchanged</option>
              {["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Consequential Action">
            <Select
              value={editForm.consequential_action ? "yes" : "no"}
              onChange={(e) =>
                setEditForm({ ...editForm, consequential_action: e.target.value === "yes" })
              }
            >
              <option value="no">No</option>
              <option value="yes">Yes — triggers material change review</option>
            </Select>
          </FormField>
          <FormField label="Description">
            <Textarea
              rows={3}
              value={editForm.description}
              onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
            />
          </FormField>
        </div>
      </SideDrawer>
    </div>
  );
}

function isEditable(item: ResourceCatalogItem | null): item is ResourceCatalogItem {
  return item != null && (item.resource_type === "MCP" || item.resource_type === "MODEL");
}

export function CatalogUpdateDrawer({
  item,
  onClose,
  onSaved,
}: {
  item: ResourceCatalogItem | null;
  onClose: () => void;
  onSaved: () => Promise<void> | void;
}) {
  const editable = isEditable(item);
  const title = item?.resource_type === "MCP" ? "Update MCP server" : "Update model";

  return (
    <SideDrawer
      open={editable}
      onClose={onClose}
      title={title}
      description={item ? `${item.name} · ${item.key}` : undefined}
      width="2xl"
      data-testid="resource-update-drawer"
    >
      {item?.resource_type === "MCP" ? (
        <McpEditor key={item.id} mcpId={item.id} onSaved={onSaved} />
      ) : item?.resource_type === "MODEL" ? (
        <ModelEditor key={item.id} modelId={item.id} onSaved={onSaved} />
      ) : null}
    </SideDrawer>
  );
}
