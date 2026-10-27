"use client";

import { useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/registry/status-badge";
import type { AISystemHierarchy } from "@/lib/types";

function Chevron({ open }: { open: boolean }) {
  return (
    <span className={`inline-block text-ink-400 transition-transform ${open ? "rotate-90" : ""}`}>
      ▸
    </span>
  );
}

export function HierarchyTree({ hierarchy }: { hierarchy: AISystemHierarchy }) {
  const [openAgents, setOpenAgents] = useState<Record<string, boolean>>({});
  const [openVersions, setOpenVersions] = useState<Record<string, boolean>>({});

  const toggleAgent = (id: string) => setOpenAgents((prev) => ({ ...prev, [id]: !prev[id] }));
  const toggleVersion = (id: string) => setOpenVersions((prev) => ({ ...prev, [id]: !prev[id] }));

  if (hierarchy.agents.length === 0) {
    return (
      <p className="text-sm text-ink-500">
        No agents registered yet. Add an agent to build the governance hierarchy.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {/* System root */}
      <div className="rounded-lg border border-accent-200 bg-accent-50/40 px-4 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-xs font-semibold uppercase tracking-wide text-accent-700">
            AI System
          </span>
          <span className="font-semibold text-ink-900">{hierarchy.system.name}</span>
          <StatusBadge status={hierarchy.system.status} />
          {hierarchy.system.risk_tier && <StatusBadge status={hierarchy.system.risk_tier} />}
          <span className="text-xs text-ink-400">
            {hierarchy.agents.length} agent{hierarchy.agents.length !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* Agents */}
      <div className="ml-4 space-y-2 border-l-2 border-base-200 pl-4">
        {hierarchy.agents.map((agent) => {
          const agentOpen = openAgents[agent.id] ?? true;
          return (
            <div key={agent.id} className="space-y-1">
              <button
                type="button"
                onClick={() => toggleAgent(agent.id)}
                className="flex w-full items-center gap-2 rounded-lg border border-base-200 bg-white px-3 py-2 text-left hover:bg-base-50"
              >
                <Chevron open={agentOpen} />
                <span className="text-xs font-semibold uppercase text-ink-400">Agent</span>
                <span className="font-medium text-ink-800">{agent.name}</span>
                <StatusBadge status={agent.status} />
                <span className="ml-auto text-xs text-ink-400">{agent.agent_key}</span>
              </button>

              {agentOpen && (
                <div className="ml-6 space-y-1 border-l-2 border-dashed border-base-200 pl-4">
                  {agent.versions.length === 0 ? (
                    <p className="py-2 text-xs text-ink-400">No versions yet</p>
                  ) : (
                    agent.versions.map((version) => {
                      const versionOpen = openVersions[version.id] ?? false;
                      const depTotal = Object.values(version.dependency_counts).reduce(
                        (a, b) => a + b,
                        0,
                      );
                      return (
                        <div key={version.id}>
                          <button
                            type="button"
                            onClick={() => toggleVersion(version.id)}
                            className="flex w-full flex-wrap items-center gap-2 rounded-md border border-base-100 bg-base-50 px-3 py-2 text-left text-sm hover:bg-base-100"
                          >
                            <Chevron open={versionOpen} />
                            <span className="font-semibold text-ink-800">
                              v{version.version_number}
                            </span>
                            <StatusBadge status={version.lifecycle_status} />
                            {version.is_current && (
                              <span className="rounded bg-accent-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-accent-700">
                                Current
                              </span>
                            )}
                            {version.material_change_status !== "NONE" && (
                              <StatusBadge status={version.material_change_status} />
                            )}
                            {version.model ? (
                              <span className="text-xs text-ink-500">
                                Model: {version.model.label}
                              </span>
                            ) : (
                              <span className="text-xs text-warn-600">No model declared</span>
                            )}
                            <Link
                              href={`/governance/registry/versions/${version.id}`}
                              onClick={(e) => e.stopPropagation()}
                              className="ml-auto text-xs font-semibold text-accent-600 hover:text-accent-500"
                            >
                              Configure →
                            </Link>
                          </button>

                          {versionOpen && (
                            <div className="ml-8 mt-1 space-y-1 rounded-md bg-white p-3 text-xs text-ink-600">
                              {version.change_summary && (
                                <p>
                                  <span className="font-semibold text-ink-500">Change: </span>
                                  {version.change_summary}
                                </p>
                              )}
                              <p>
                                <span className="font-semibold text-ink-500">Dependencies: </span>
                                {depTotal === 0
                                  ? "None"
                                  : Object.entries(version.dependency_counts)
                                      .filter(([, c]) => c > 0)
                                      .map(([k, c]) => `${c} ${k.replace("_", " ")}`)
                                      .join(", ")}
                              </p>
                              {version.model && (
                                <p>
                                  <span className="font-semibold text-ink-500">Model: </span>
                                  {version.model.provider} / {version.model.model_name}
                                </p>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                  <Link
                    href={`/governance/registry/agents/${agent.id}`}
                    className="inline-block py-1 text-xs font-semibold text-accent-600"
                  >
                    + Manage agent & versions
                  </Link>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
