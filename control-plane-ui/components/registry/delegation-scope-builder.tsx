"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FormField } from "@/components/registry/form-field";
import { getDelegationResources } from "@/lib/api";
import type {
  DelegationResourceCatalog,
  DelegationScope,
  DelegationScopeSelection,
} from "@/lib/types";

const EMPTY_SCOPE: DelegationScopeSelection = {
  model_ids: [],
  data_source_ids: [],
  mcp_server_ids: [],
  tool_ids: [],
};

function scopeFromDelegation(scope?: DelegationScope): DelegationScopeSelection {
  return {
    model_ids: scope?.model_ids ?? [],
    data_source_ids: scope?.data_source_ids ?? [],
    mcp_server_ids: scope?.mcp_server_ids ?? [],
    tool_ids: scope?.tool_ids ?? [],
  };
}

function isAllowed(id: string, allowed: string[] | undefined, parentRestricted: boolean): boolean {
  if (!parentRestricted) return true;
  return (allowed ?? []).includes(id);
}

interface DelegationScopeBuilderProps {
  versionId: string;
  value: DelegationScopeSelection;
  onChange: (value: DelegationScopeSelection) => void;
  parentScope?: DelegationScope;
}

export function DelegationScopeBuilder({
  versionId,
  value,
  onChange,
  parentScope,
}: DelegationScopeBuilderProps) {
  const [catalog, setCatalog] = useState<DelegationResourceCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedMcps, setExpandedMcps] = useState<Set<string>>(new Set());

  const parentRestricted = Boolean(
    parentScope &&
    ((parentScope.model_ids?.length ?? 0) > 0 ||
      (parentScope.data_source_ids?.length ?? 0) > 0 ||
      (parentScope.mcp_server_ids?.length ?? 0) > 0 ||
      (parentScope.tool_ids?.length ?? 0) > 0),
  );

  const load = useCallback(() => {
    if (!versionId) return;
    setLoading(true);
    setError(null);
    getDelegationResources(versionId)
      .then((res) => {
        setCatalog(res.data);
        setExpandedMcps(new Set(res.data.mcp_servers.map((m) => m.id)));
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [versionId]);

  useEffect(() => {
    load();
  }, [load]);

  const toggleId = (field: keyof DelegationScopeSelection, id: string, allowed?: string[]) => {
    if (!isAllowed(id, allowed, parentRestricted)) return;
    const current = new Set(value[field]);
    if (current.has(id)) current.delete(id);
    else current.add(id);
    onChange({ ...value, [field]: Array.from(current) });
  };

  const mcpState = useMemo(() => {
    const states = new Map<string, "none" | "partial" | "all">();
    if (!catalog) return states;
    for (const mcp of catalog.mcp_servers) {
      const toolIds = mcp.tools.map((t) => t.id);
      const selected = toolIds.filter((id) => value.tool_ids.includes(id));
      if (selected.length === 0) states.set(mcp.id, "none");
      else if (selected.length === toolIds.length) states.set(mcp.id, "all");
      else states.set(mcp.id, "partial");
    }
    return states;
  }, [catalog, value.tool_ids]);

  const toggleMcp = (mcpId: string, toolIds: string[]) => {
    const allowedTools = parentRestricted
      ? toolIds.filter((id) => (parentScope?.tool_ids ?? []).includes(id))
      : toolIds;
    const state = mcpState.get(mcpId) ?? "none";
    const nextTools = new Set(value.tool_ids);
    const nextMcps = new Set(value.mcp_server_ids);

    if (state === "all") {
      for (const id of allowedTools) nextTools.delete(id);
      nextMcps.delete(mcpId);
    } else {
      for (const id of allowedTools) nextTools.add(id);
      if (allowedTools.length === toolIds.length) nextMcps.add(mcpId);
    }

    onChange({
      ...value,
      tool_ids: Array.from(nextTools),
      mcp_server_ids: Array.from(nextMcps),
    });
  };

  const toggleTool = (mcpId: string, toolId: string, allToolIds: string[]) => {
    if (!isAllowed(toolId, parentScope?.tool_ids, parentRestricted)) return;
    const nextTools = new Set(value.tool_ids);
    if (nextTools.has(toolId)) nextTools.delete(toolId);
    else nextTools.add(toolId);

    const nextMcps = new Set(value.mcp_server_ids);
    const selectedOnMcp = allToolIds.filter((id) => nextTools.has(id));
    if (selectedOnMcp.length === allToolIds.length && allToolIds.length > 0) {
      nextMcps.add(mcpId);
    } else {
      nextMcps.delete(mcpId);
    }

    onChange({
      ...value,
      tool_ids: Array.from(nextTools),
      mcp_server_ids: Array.from(nextMcps),
    });
  };

  if (loading) {
    return <p className="text-sm text-ink-500">Loading version resources...</p>;
  }

  if (error) {
    return (
      <div className="rounded-lg bg-danger-50 p-3 text-sm text-danger-600">
        {error}
        <button type="button" className="ml-2 underline" onClick={load}>
          Retry
        </button>
      </div>
    );
  }

  if (!catalog) {
    return <p className="text-sm text-ink-500">No version selected.</p>;
  }

  const noResources =
    catalog.models.length === 0 &&
    catalog.data_sources.length === 0 &&
    catalog.mcp_servers.length === 0 &&
    (catalog.standalone_tools?.length ?? 0) === 0;

  if (noResources) {
    return (
      <p className="text-sm text-ink-500">
        This agent version has no declared models, data sources, or MCP tools to delegate.
      </p>
    );
  }

  return (
    <div className="space-y-5">
      {catalog.models.length > 0 && (
        <FormField label="Models">
          <div className="flex flex-wrap gap-2">
            {catalog.models.map((model) => {
              const allowed = isAllowed(model.id, parentScope?.model_ids, parentRestricted);
              const selected = value.model_ids.includes(model.id);
              return (
                <button
                  key={model.id}
                  type="button"
                  disabled={!allowed}
                  onClick={() => toggleId("model_ids", model.id, parentScope?.model_ids)}
                  className={`rounded-full px-3 py-1 text-xs font-medium ${
                    selected
                      ? "bg-brand-100 text-brand-800"
                      : allowed
                        ? "bg-base-100 text-ink-600"
                        : "cursor-not-allowed bg-base-50 text-ink-300"
                  }`}
                  title={!allowed ? "Not in parent delegation scope" : undefined}
                >
                  {model.label}
                </button>
              );
            })}
          </div>
        </FormField>
      )}

      {catalog.data_sources.length > 0 && (
        <FormField label="Data Sources">
          <div className="flex flex-wrap gap-2">
            {catalog.data_sources.map((ds) => {
              const allowed = isAllowed(ds.id, parentScope?.data_source_ids, parentRestricted);
              const selected = value.data_source_ids.includes(ds.id);
              return (
                <button
                  key={ds.id}
                  type="button"
                  disabled={!allowed}
                  onClick={() => toggleId("data_source_ids", ds.id, parentScope?.data_source_ids)}
                  className={`rounded-full px-3 py-1 text-xs font-medium ${
                    selected
                      ? "bg-brand-100 text-brand-800"
                      : allowed
                        ? "bg-base-100 text-ink-600"
                        : "cursor-not-allowed bg-base-50 text-ink-300"
                  }`}
                >
                  {ds.label}
                </button>
              );
            })}
          </div>
        </FormField>
      )}

      {catalog.mcp_servers.length > 0 && (
        <FormField label="MCP & Tools">
          <div className="space-y-2 rounded-lg border border-base-200 p-3">
            {catalog.mcp_servers.map((mcp) => {
              const state = mcpState.get(mcp.id) ?? "none";
              const expanded = expandedMcps.has(mcp.id);
              const toolIds = mcp.tools.map((t) => t.id);
              const mcpAllowed =
                !parentRestricted ||
                (parentScope?.mcp_server_ids ?? []).includes(mcp.id) ||
                toolIds.some((id) => (parentScope?.tool_ids ?? []).includes(id));

              return (
                <div key={mcp.id} className="rounded-md border border-base-100">
                  <div className="flex items-center gap-2 px-3 py-2">
                    <button
                      type="button"
                      className="text-xs text-ink-500"
                      onClick={() => {
                        const next = new Set(expandedMcps);
                        if (expanded) next.delete(mcp.id);
                        else next.add(mcp.id);
                        setExpandedMcps(next);
                      }}
                    >
                      {expanded ? "▾" : "▸"}
                    </button>
                    <input
                      type="checkbox"
                      checked={state === "all"}
                      ref={(el) => {
                        if (el) el.indeterminate = state === "partial";
                      }}
                      disabled={!mcpAllowed || mcp.tools.length === 0}
                      onChange={() => toggleMcp(mcp.id, toolIds)}
                    />
                    <span className="text-sm font-medium text-ink-800">{mcp.name}</span>
                  </div>
                  {expanded && (
                    <div className="space-y-1 border-t border-base-100 px-8 py-2">
                      {mcp.tools.length === 0 ? (
                        <p className="text-xs text-ink-400">No tools declared on version</p>
                      ) : (
                        mcp.tools.map((tool) => {
                          const toolAllowed = isAllowed(
                            tool.id,
                            parentScope?.tool_ids,
                            parentRestricted,
                          );
                          return (
                            <label
                              key={tool.id}
                              className={`flex items-center gap-2 text-sm ${
                                toolAllowed ? "text-ink-700" : "text-ink-300"
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={value.tool_ids.includes(tool.id)}
                                disabled={!toolAllowed}
                                onChange={() => toggleTool(mcp.id, tool.id, toolIds)}
                              />
                              {tool.tool_key}
                            </label>
                          );
                        })
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </FormField>
      )}

      {(catalog.standalone_tools?.length ?? 0) > 0 && (
        <FormField label="Tools">
          <div className="space-y-1 rounded-lg border border-base-200 p-3">
            {catalog.standalone_tools!.map((tool) => {
              const toolAllowed = isAllowed(tool.id, parentScope?.tool_ids, parentRestricted);
              return (
                <label
                  key={tool.id}
                  className={`flex items-center gap-2 text-sm ${
                    toolAllowed ? "text-ink-700" : "text-ink-300"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={value.tool_ids.includes(tool.id)}
                    disabled={!toolAllowed}
                    onChange={() => toggleId("tool_ids", tool.id, parentScope?.tool_ids)}
                  />
                  {tool.tool_key}
                </label>
              );
            })}
          </div>
        </FormField>
      )}
    </div>
  );
}

export { EMPTY_SCOPE, scopeFromDelegation };
