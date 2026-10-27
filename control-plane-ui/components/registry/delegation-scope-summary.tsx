"use client";

import { useEffect, useState } from "react";
import { getDelegationResources } from "@/lib/api";
import type { DelegationResourceCatalog, DelegationScope } from "@/lib/types";

interface DelegationScopeSummaryProps {
  versionId: string;
  scope: DelegationScope;
}

export function DelegationScopeSummary({ versionId, scope }: DelegationScopeSummaryProps) {
  const [catalog, setCatalog] = useState<DelegationResourceCatalog | null>(null);

  useEffect(() => {
    if (!versionId) return;
    getDelegationResources(versionId)
      .then((res) => setCatalog(res.data))
      .catch(() => setCatalog(null));
  }, [versionId]);

  if (!catalog) {
    return <p className="text-xs text-ink-400">Loading scope...</p>;
  }

  const models = (scope.model_ids ?? [])
    .map((id) => catalog.models.find((m) => m.id === id)?.label)
    .filter(Boolean) as string[];

  const dataSources = (scope.data_source_ids ?? [])
    .map((id) => catalog.data_sources.find((d) => d.id === id)?.label)
    .filter(Boolean) as string[];

  const mcpBlocks = catalog.mcp_servers
    .map((mcp) => {
      const tools = mcp.tools.filter((t) => (scope.tool_ids ?? []).includes(t.id));
      const mcpSelected = (scope.mcp_server_ids ?? []).includes(mcp.id);
      if (!mcpSelected && tools.length === 0) return null;
      return { mcp, tools };
    })
    .filter(Boolean) as Array<{
    mcp: DelegationResourceCatalog["mcp_servers"][number];
    tools: DelegationResourceCatalog["mcp_servers"][number]["tools"];
  }>;

  const standaloneTools = (catalog.standalone_tools ?? []).filter((t) =>
    (scope.tool_ids ?? []).includes(t.id),
  );

  const legacyTools = scope.tool_keys ?? [];

  const empty =
    models.length === 0 &&
    dataSources.length === 0 &&
    mcpBlocks.length === 0 &&
    standaloneTools.length === 0 &&
    legacyTools.length === 0;

  if (empty) {
    return (
      <p className="text-sm text-ink-500">
        No resource scope restrictions (full version authority).
      </p>
    );
  }

  return (
    <div className="space-y-3 text-sm">
      {models.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase text-ink-400">Models</p>
          <ul className="mt-1 list-disc pl-5 text-ink-700">
            {models.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}

      {dataSources.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase text-ink-400">Data Sources</p>
          <ul className="mt-1 list-disc pl-5 text-ink-700">
            {dataSources.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </div>
      )}

      {mcpBlocks.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase text-ink-400">MCP & Tools</p>
          <div className="mt-2 space-y-2">
            {mcpBlocks.map(({ mcp, tools }) => (
              <div key={mcp.id}>
                <p className="font-medium text-ink-800">{mcp.name}</p>
                <ul className="mt-1 list-none pl-4 text-ink-600">
                  {tools.map((t) => (
                    <li key={t.id}>├── {t.tool_key}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      {standaloneTools.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase text-ink-400">Tools</p>
          <ul className="mt-1 list-disc pl-5 text-ink-700">
            {standaloneTools.map((t) => (
              <li key={t.id}>{t.tool_key}</li>
            ))}
          </ul>
        </div>
      )}

      {legacyTools.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase text-ink-400">Tools (legacy)</p>
          <div className="mt-1 flex flex-wrap gap-1">
            {legacyTools.map((tool) => (
              <span key={tool} className="rounded bg-base-100 px-2 py-0.5 text-xs">
                {tool}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
