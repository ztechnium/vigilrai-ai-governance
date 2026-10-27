"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { FormField } from "@/components/registry/form-field";
import { Panel } from "@/components/registry/panel";
import {
  addVersionDependency,
  getDataSources,
  getExternalServices,
  getMCPServers,
  getModels,
  getTools,
  removeVersionDependency,
} from "@/lib/api";
import type {
  DataSourceSummary,
  ExternalServiceSummary,
  MCPServerSummary,
  ModelResourceSummary,
  ToolResourceSummary,
  VersionDependency,
} from "@/lib/types";

type ManageSection = "models" | "mcp" | "data_sources" | "external_services" | null;

interface VersionDependenciesProps {
  versionId: string;
  dependencies: VersionDependency[];
  editable: boolean;
  onChanged: () => void;
}

function groupDependencies(dependencies: VersionDependency[]) {
  return {
    models: dependencies.filter((d) => d.resource_type === "model"),
    mcpServers: dependencies.filter((d) => d.resource_type === "mcp_server"),
    tools: dependencies.filter((d) => d.resource_type === "tool"),
    dataSources: dependencies.filter((d) => d.resource_type === "data_source"),
    externalServices: dependencies.filter((d) => d.resource_type === "external_service"),
  };
}

export function VersionDependencies({
  versionId,
  dependencies,
  editable,
  onChanged,
}: VersionDependenciesProps) {
  const [manageSection, setManageSection] = useState<ManageSection>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [models, setModels] = useState<ModelResourceSummary[]>([]);
  const [mcpServers, setMcpServers] = useState<MCPServerSummary[]>([]);
  const [tools, setTools] = useState<ToolResourceSummary[]>([]);
  const [dataSources, setDataSources] = useState<DataSourceSummary[]>([]);
  const [externalServices, setExternalServices] = useState<ExternalServiceSummary[]>([]);
  const [pickerValue, setPickerValue] = useState("");

  const grouped = useMemo(() => groupDependencies(dependencies), [dependencies]);

  const loadCatalog = useCallback(async () => {
    const [modelRes, mcpRes, toolRes, dsRes, svcRes] = await Promise.all([
      getModels(),
      getMCPServers(),
      getTools(),
      getDataSources(),
      getExternalServices(),
    ]);
    setModels(modelRes.data);
    setMcpServers(mcpRes.data);
    setTools(toolRes.data);
    setDataSources(dsRes.data);
    setExternalServices(svcRes.data);
  }, []);

  useEffect(() => {
    loadCatalog().catch((err: Error) => setError(err.message));
  }, [loadCatalog]);

  const modelMap = useMemo(() => new Map(models.map((m) => [m.id, m])), [models]);
  const mcpMap = useMemo(() => new Map(mcpServers.map((m) => [m.id, m])), [mcpServers]);
  const toolMap = useMemo(() => new Map(tools.map((t) => [t.id, t])), [tools]);
  const dataSourceMap = useMemo(() => new Map(dataSources.map((d) => [d.id, d])), [dataSources]);
  const externalServiceMap = useMemo(
    () => new Map(externalServices.map((s) => [s.id, s])),
    [externalServices],
  );

  const toolsByMcp = useMemo(() => {
    const map = new Map<string, ToolResourceSummary[]>();
    for (const tool of tools) {
      if (!tool.mcp_server_id) continue;
      const list = map.get(tool.mcp_server_id) ?? [];
      list.push(tool);
      map.set(tool.mcp_server_id, list);
    }
    return map;
  }, [tools]);

  const selectedToolIds = useMemo(
    () => new Set(grouped.tools.map((d) => d.resource_id)),
    [grouped.tools],
  );

  const runMutation = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dependency update failed");
    } finally {
      setBusy(false);
    }
  };

  const handleAdd = async (resourceType: string, resourceId: string) => {
    if (!resourceId) return;
    await runMutation(() =>
      addVersionDependency(versionId, {
        resource_type: resourceType,
        resource_id: resourceId,
      }),
    );
    setPickerValue("");
  };

  const handleRemove = async (dependencyId: string) => {
    await runMutation(() => removeVersionDependency(versionId, dependencyId));
  };

  const handleToggleTool = async (tool: ToolResourceSummary, selected: boolean) => {
    if (selected) {
      const dep = grouped.tools.find((d) => d.resource_id === tool.id);
      if (dep) await handleRemove(dep.id);
      return;
    }
    await handleAdd("tool", tool.id);
  };

  const toggleManage = (section: ManageSection) => {
    setManageSection((current) => (current === section ? null : section));
    setPickerValue("");
    setError(null);
  };

  const renderManageButton = (section: ManageSection) =>
    editable ? (
      <Button variant="secondary" onClick={() => toggleManage(section)} disabled={busy}>
        {manageSection === section ? "Close" : "Manage"}
      </Button>
    ) : null;

  const renderModelLabel = (dep: VersionDependency) => {
    const model = modelMap.get(dep.resource_id);
    if (!model) return dep.resource_id;
    const version = model.model_version ? ` / ${model.model_version}` : "";
    return `${model.provider} ${model.model_name}${version}`;
  };

  const renderDataSourceMeta = (dep: VersionDependency) => {
    const ds = dataSourceMap.get(dep.resource_id);
    if (!ds) return null;
    const parts = [ds.classification, ds.contains_sensitive_data ? "sensitive" : null]
      .filter(Boolean)
      .join(" · ");
    return parts || null;
  };

  const renderExternalServiceMeta = (dep: VersionDependency) => {
    const svc = externalServiceMap.get(dep.resource_id);
    if (!svc) return null;
    return [svc.provider, svc.environment, svc.sensitivity].filter(Boolean).join(" · ") || null;
  };

  return (
    <Panel
      title="Dependencies"
      description={
        editable
          ? "Declare models, MCP servers with selected tools, data sources, and external services for this version."
          : "Immutable snapshot of declared dependencies."
      }
    >
      {error && (
        <div className="mb-4 rounded-lg bg-danger-50 px-3 py-2 text-sm text-danger-600">
          {error}
        </div>
      )}

      <div className="space-y-6">
        <section>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-ink-800">Models</h3>
            {renderManageButton("models")}
          </div>
          {grouped.models.length === 0 ? (
            <p className="text-sm text-ink-500">No models declared.</p>
          ) : (
            <ul className="space-y-2">
              {grouped.models.map((dep) => {
                const model = modelMap.get(dep.resource_id);
                return (
                  <li
                    key={dep.id}
                    className="flex items-start justify-between gap-3 rounded-lg border border-base-100 bg-base-50 px-3 py-2 text-sm"
                  >
                    <div>
                      <div className="font-medium text-ink-800">{renderModelLabel(dep)}</div>
                      {model?.status && (
                        <div className="text-xs text-ink-500">Status: {model.status}</div>
                      )}
                    </div>
                    {editable && (
                      <Button variant="ghost" disabled={busy} onClick={() => handleRemove(dep.id)}>
                        Remove
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {manageSection === "models" && (
            <div className="mt-3 rounded-lg border border-base-100 bg-white p-4">
              <FormField label="Add model from catalog">
                <div className="flex gap-2">
                  <Select
                    value={pickerValue}
                    onChange={(e) => setPickerValue(e.target.value)}
                    className="flex-1"
                  >
                    <option value="">Select model...</option>
                    {models
                      .filter((m) => !grouped.models.some((d) => d.resource_id === m.id))
                      .map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.provider}/{m.model_name}
                          {m.model_version ? ` (${m.model_version})` : ""} — {m.status}
                        </option>
                      ))}
                  </Select>
                  <Button
                    variant="primary"
                    disabled={busy || !pickerValue}
                    onClick={() => handleAdd("model", pickerValue)}
                  >
                    Add
                  </Button>
                </div>
              </FormField>
            </div>
          )}
        </section>

        <section>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-ink-800">MCP Servers &amp; Tools</h3>
            {renderManageButton("mcp")}
          </div>
          {grouped.mcpServers.length === 0 ? (
            <p className="text-sm text-ink-500">No MCP servers declared.</p>
          ) : (
            <ul className="space-y-3">
              {grouped.mcpServers.map((mcpDep) => {
                const server = mcpMap.get(mcpDep.resource_id);
                const serverTools = toolsByMcp.get(mcpDep.resource_id) ?? [];
                const selectedForMcp = grouped.tools.filter((dep) => {
                  const tool = toolMap.get(dep.resource_id);
                  return tool?.mcp_server_id === mcpDep.resource_id;
                });
                return (
                  <li
                    key={mcpDep.id}
                    className="rounded-lg border border-base-100 bg-base-50 px-3 py-3 text-sm"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="font-medium text-ink-800">
                          {server?.name ?? mcpDep.resource_id}
                        </div>
                        {server?.server_key && (
                          <div className="text-xs text-ink-500">{server.server_key}</div>
                        )}
                      </div>
                      {editable && (
                        <Button
                          variant="ghost"
                          disabled={busy}
                          onClick={() => handleRemove(mcpDep.id)}
                        >
                          Remove
                        </Button>
                      )}
                    </div>
                    <ul className="mt-2 space-y-1 pl-1">
                      {serverTools.map((tool) => {
                        const selected = selectedToolIds.has(tool.id);
                        return (
                          <li key={tool.id} className="flex items-center gap-2 text-ink-700">
                            <span aria-hidden>{selected ? "✓" : "✗"}</span>
                            <span>{tool.tool_key}</span>
                            {manageSection === "mcp" && editable && (
                              <Button
                                variant="ghost"
                                disabled={busy}
                                onClick={() => handleToggleTool(tool, selected)}
                              >
                                {selected ? "Deselect" : "Select"}
                              </Button>
                            )}
                          </li>
                        );
                      })}
                      {selectedForMcp.length === 0 && manageSection !== "mcp" && (
                        <li className="text-xs text-ink-500">No tools selected.</li>
                      )}
                    </ul>
                  </li>
                );
              })}
            </ul>
          )}
          {manageSection === "mcp" && (
            <div className="mt-3 space-y-4 rounded-lg border border-base-100 bg-white p-4">
              <FormField label="Add MCP server from catalog">
                <div className="flex gap-2">
                  <Select
                    value={pickerValue}
                    onChange={(e) => setPickerValue(e.target.value)}
                    className="flex-1"
                  >
                    <option value="">Select MCP server...</option>
                    {mcpServers
                      .filter((m) => !grouped.mcpServers.some((d) => d.resource_id === m.id))
                      .map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.server_key} — {m.name}
                        </option>
                      ))}
                  </Select>
                  <Button
                    variant="primary"
                    disabled={busy || !pickerValue}
                    onClick={() => handleAdd("mcp_server", pickerValue)}
                  >
                    Add
                  </Button>
                </div>
              </FormField>
              <p className="text-xs text-ink-500">
                Adding an MCP server does not authorize its tools. Select only the tools this
                version declares.
              </p>
            </div>
          )}
        </section>

        <section>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-ink-800">Data Sources</h3>
            {renderManageButton("data_sources")}
          </div>
          {grouped.dataSources.length === 0 ? (
            <p className="text-sm text-ink-500">No data sources declared.</p>
          ) : (
            <ul className="space-y-2">
              {grouped.dataSources.map((dep) => {
                const ds = dataSourceMap.get(dep.resource_id);
                const meta = renderDataSourceMeta(dep);
                return (
                  <li
                    key={dep.id}
                    className="flex items-start justify-between gap-3 rounded-lg border border-base-100 bg-base-50 px-3 py-2 text-sm"
                  >
                    <div>
                      <div className="font-medium text-ink-800">{ds?.name ?? dep.resource_id}</div>
                      {meta && <div className="text-xs text-ink-500">{meta}</div>}
                    </div>
                    {editable && (
                      <Button variant="ghost" disabled={busy} onClick={() => handleRemove(dep.id)}>
                        Remove
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {manageSection === "data_sources" && (
            <div className="mt-3 rounded-lg border border-base-100 bg-white p-4">
              <FormField label="Add data source from catalog">
                <div className="flex gap-2">
                  <Select
                    value={pickerValue}
                    onChange={(e) => setPickerValue(e.target.value)}
                    className="flex-1"
                  >
                    <option value="">Select data source...</option>
                    {dataSources
                      .filter((d) => !grouped.dataSources.some((dep) => dep.resource_id === d.id))
                      .map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.data_source_key} — {d.name}
                          {d.classification ? ` (${d.classification})` : ""}
                        </option>
                      ))}
                  </Select>
                  <Button
                    variant="primary"
                    disabled={busy || !pickerValue}
                    onClick={() => handleAdd("data_source", pickerValue)}
                  >
                    Add
                  </Button>
                </div>
              </FormField>
            </div>
          )}
        </section>

        <section>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-ink-800">External Services</h3>
            {renderManageButton("external_services")}
          </div>
          {grouped.externalServices.length === 0 ? (
            <p className="text-sm text-ink-500">No external services declared.</p>
          ) : (
            <ul className="space-y-2">
              {grouped.externalServices.map((dep) => {
                const svc = externalServiceMap.get(dep.resource_id);
                const meta = renderExternalServiceMeta(dep);
                return (
                  <li
                    key={dep.id}
                    className="flex items-start justify-between gap-3 rounded-lg border border-base-100 bg-base-50 px-3 py-2 text-sm"
                  >
                    <div>
                      <div className="font-medium text-ink-800">{svc?.name ?? dep.resource_id}</div>
                      {meta && <div className="text-xs text-ink-500">{meta}</div>}
                    </div>
                    {editable && (
                      <Button variant="ghost" disabled={busy} onClick={() => handleRemove(dep.id)}>
                        Remove
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {manageSection === "external_services" && (
            <div className="mt-3 rounded-lg border border-base-100 bg-white p-4">
              <FormField label="Add external service from catalog">
                <div className="flex gap-2">
                  <Select
                    value={pickerValue}
                    onChange={(e) => setPickerValue(e.target.value)}
                    className="flex-1"
                  >
                    <option value="">Select external service...</option>
                    {externalServices
                      .filter(
                        (s) => !grouped.externalServices.some((dep) => dep.resource_id === s.id),
                      )
                      .map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.service_key} — {s.name}
                        </option>
                      ))}
                  </Select>
                  <Button
                    variant="primary"
                    disabled={busy || !pickerValue}
                    onClick={() => handleAdd("external_service", pickerValue)}
                  >
                    Add
                  </Button>
                </div>
              </FormField>
            </div>
          )}
        </section>
      </div>

      {editable && (
        <div className="mt-6 border-t border-base-100 pt-4">
          <Link href="/governance/registry/catalog" className="text-sm text-accent-600">
            Manage resource catalog →
          </Link>
        </div>
      )}
    </Panel>
  );
}
