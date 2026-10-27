"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { SideDrawer } from "@/components/ui/side-drawer";
import { Textarea } from "@/components/ui/textarea";
import { Table } from "@/components/ui/table";
import { Breadcrumbs } from "@/components/registry/breadcrumbs";
import { FormField } from "@/components/registry/form-field";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { createTool, getMCPServer, updateMCPServer, updateTool } from "@/lib/api";
import type { MCPServerSummary } from "@/lib/types";

function formatSourceType(sourceType?: string | null): string {
  if (sourceType === "SEEDED_TEMPLATE") return "Seeded Template";
  if (sourceType) return sourceType;
  return "—";
}

function formatAliases(aliases?: string[]): string {
  if (!aliases || aliases.length === 0) return "—";
  return aliases.join(", ");
}

function serverSubtitle(server: MCPServerSummary): string {
  const sourceLabel =
    server.source_type === "SEEDED_TEMPLATE"
      ? "seeded template"
      : server.source_type === "DISCOVERED" || server.endpoint_reference
        ? "connected"
        : "catalog entry";
  return `MCP server ${server.server_key} (${sourceLabel}) — manage server details and registered tools.`;
}

type McpTool = NonNullable<MCPServerSummary["tools"]>[number];

export default function MCPServerDetailPage() {
  const params = useParams();
  const mcpId = params.mcpId as string;
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
    if (!serverForm.name.trim()) return;
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
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Failed to update MCP server");
    } finally {
      setSaving(false);
    }
  };

  const handleCreateTool = async () => {
    if (!toolForm.tool_key.trim() || !toolForm.name.trim()) return;
    await createTool({
      ...toolForm,
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
    } catch (err) {
      setToolError(err instanceof Error ? err.message : "Failed to update tool");
    } finally {
      setToolSaving(false);
    }
  };

  if (loading) {
    return <div className="p-8 text-center text-sm text-ink-500">Loading MCP server...</div>;
  }

  if (error || !server) {
    return (
      <div className="rounded-xl bg-danger-50 p-6 text-sm text-danger-600">
        {error ?? "Not found"}
      </div>
    );
  }

  const toolRows = (server.tools ?? []).map((tool) => [
    tool.tool_key,
    tool.native_name ?? "—",
    tool.name,
    tool.capability_type ?? "—",
    tool.side_effect ?? "—",
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
      <Breadcrumbs
        items={[
          { label: "Resource Catalog", href: "/governance/registry/catalog" },
          { label: server.server_key },
        ]}
      />

      <SectionHeader
        title={server.name}
        subtitle={serverSubtitle(server)}
        actions={<StatusBadge status={server.status ?? "ACTIVE"} />}
      />

      <Panel title="Server Details">
        <div className="grid gap-4 md:grid-cols-2">
          <FormField label="Server Key">
            <Input value={server.server_key} disabled />
          </FormField>
          <FormField label="Name" required>
            <Input
              value={serverForm.name}
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
              onChange={(e) => setServerForm({ ...serverForm, environment: e.target.value })}
              placeholder="production"
            />
          </FormField>
          <FormField label="Trust Classification">
            <Input
              value={serverForm.trust_classification}
              onChange={(e) =>
                setServerForm({ ...serverForm, trust_classification: e.target.value })
              }
              placeholder="internal"
            />
          </FormField>
          <div className="md:col-span-2">
            <FormField label="Endpoint Reference">
              <Input
                value={serverForm.endpoint_reference}
                onChange={(e) =>
                  setServerForm({ ...serverForm, endpoint_reference: e.target.value })
                }
                placeholder="mcp://github-internal (non-secret)"
              />
            </FormField>
          </div>
          <div className="md:col-span-2">
            <FormField label="Description">
              <Textarea
                rows={2}
                value={serverForm.description}
                onChange={(e) => setServerForm({ ...serverForm, description: e.target.value })}
              />
            </FormField>
          </div>
        </div>

        <div className="mt-6 flex items-center justify-between gap-4">
          {saveMessage && (
            <p
              className={`text-sm ${saveMessage.includes("success") ? "text-accent-600" : "text-danger-600"}`}
            >
              {saveMessage}
            </p>
          )}
          <div className="ml-auto">
            <Button variant="primary" onClick={handleSaveServer} disabled={saving}>
              {saving ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </div>
      </Panel>

      <Panel
        title="Tools"
        actions={
          <Button variant="primary" onClick={() => setShowToolForm(!showToolForm)}>
            {showToolForm ? "Cancel" : "+ Add Tool"}
          </Button>
        }
      >
        {showToolForm && (
          <div className="mb-6 grid gap-4 md:grid-cols-2">
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
            <div className="md:col-span-2">
              <FormField label="Description">
                <Textarea
                  rows={2}
                  value={toolForm.description}
                  onChange={(e) => setToolForm({ ...toolForm, description: e.target.value })}
                />
              </FormField>
            </div>
            <div className="md:col-span-2 flex justify-end">
              <Button variant="primary" onClick={handleCreateTool}>
                Add Tool
              </Button>
            </div>
          </div>
        )}

        <Table
          columns={[
            "Key",
            "Native Name",
            "Name",
            "Capability",
            "Side Effect",
            "Risk",
            "Status",
            "",
          ]}
          rows={
            toolRows.length > 0 ? toolRows : [["No tools yet", "—", "—", "—", "—", "—", "—", "—"]]
          }
        />
      </Panel>

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
            <Button variant="primary" disabled={toolSaving} onClick={handleUpdateTool}>
              {toolSaving ? "Saving..." : "Save"}
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
