"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/registry/status-badge";
import { TechnicalValue } from "@/components/console/page-parts";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { AISystemHierarchy, RuntimeIdentitySummary } from "@/lib/types";

function formatRelative(value?: string | null) {
  if (!value) return "—";
  const diff = Date.now() - new Date(value).getTime();
  if (Number.isNaN(diff)) return "—";
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} hr ago`;
  return new Date(value).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function AgentsVersionsTable({
  hierarchy,
  runtimes,
  onCreateAgent,
}: {
  hierarchy: AISystemHierarchy;
  runtimes: RuntimeIdentitySummary[];
  onCreateAgent?: () => void;
}) {
  const [expanded, setExpanded] = useState<string[]>(() =>
    hierarchy.agents.map((agent) => agent.id),
  );

  const runtimeByVersion = useMemo(() => {
    const map = new Map<string, RuntimeIdentitySummary[]>();
    for (const runtime of runtimes) {
      if (!runtime.agent_version_id) continue;
      const list = map.get(runtime.agent_version_id) ?? [];
      list.push(runtime);
      map.set(runtime.agent_version_id, list);
    }
    return map;
  }, [runtimes]);

  if (hierarchy.agents.length === 0) {
    return (
      <div className="flex min-h-48 flex-col items-center justify-center px-6 text-center">
        <h3 className="text-sm font-semibold text-ink-900">
          No agents registered for this system.
        </h3>
        <p className="mt-1 max-w-md text-xs text-ink-500">
          Agents are the governed workloads of an AI system. Each agent carries immutable,
          approvable versions.
        </p>
        {onCreateAgent ? (
          <div className="mt-4">
            <Button size="sm" variant="primary" onClick={onCreateAgent}>
              + Create Agent
            </Button>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[960px]">
        <thead>
          <tr className="border-b border-base-200 bg-base-100">
            {[
              "Agent",
              "Status",
              "Current Version",
              "Versions",
              "Runtime Identities",
              "Last Activity",
              "Actions",
            ].map((col) => (
              <th
                key={col}
                className={cn(
                  "px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wide text-ink-400",
                  col === "Actions" && "text-right",
                )}
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-base-200">
          {hierarchy.agents.map((agent) => {
            const open = expanded.includes(agent.id);
            const versions = [...agent.versions].sort(
              (a, b) => b.version_number - a.version_number,
            );
            const current =
              versions.find((version) => version.is_current) ??
              versions.find((version) => version.lifecycle_status === "APPROVED") ??
              versions[0];
            const agentRuntimes = runtimes.filter(
              (runtime) =>
                runtime.agent_id === agent.id ||
                versions.some((version) => version.id === runtime.agent_version_id),
            );
            const lastActivity = agentRuntimes
              .map((runtime) => runtime.last_authenticated_at)
              .filter(Boolean)
              .sort()
              .at(-1);

            return (
              <AgentBlock
                key={agent.id}
                agent={agent}
                open={open}
                versions={versions}
                current={current}
                agentRuntimes={agentRuntimes}
                lastActivity={lastActivity}
                runtimeByVersion={runtimeByVersion}
                onToggle={() =>
                  setExpanded((prev) =>
                    prev.includes(agent.id)
                      ? prev.filter((id) => id !== agent.id)
                      : [...prev, agent.id],
                  )
                }
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function AgentBlock({
  agent,
  open,
  versions,
  current,
  agentRuntimes,
  lastActivity,
  runtimeByVersion,
  onToggle,
}: {
  agent: AISystemHierarchy["agents"][number];
  open: boolean;
  versions: AISystemHierarchy["agents"][number]["versions"];
  current?: AISystemHierarchy["agents"][number]["versions"][number];
  agentRuntimes: RuntimeIdentitySummary[];
  lastActivity?: string | null;
  runtimeByVersion: Map<string, RuntimeIdentitySummary[]>;
  onToggle: () => void;
}) {
  return (
    <>
      <tr className="h-12 bg-base-50 hover:bg-base-100">
        <td className="px-3 py-2.5 text-xs">
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded p-0.5 text-ink-400 hover:bg-base-100 hover:text-ink-800"
              aria-expanded={open}
              aria-label={open ? "Collapse versions" : "Expand versions"}
              onClick={onToggle}
            >
              <span aria-hidden className="inline-block text-[10px]">
                {open ? "▾" : "▸"}
              </span>
            </button>
            <div>
              <Link
                href={`/governance/registry/agents/${agent.id}`}
                className="font-medium text-ink-900 hover:text-accent-600"
              >
                {agent.name}
              </Link>
              <TechnicalValue className="mt-0.5 block text-[11px] text-ink-400">
                {agent.agent_key}
              </TechnicalValue>
            </div>
          </div>
        </td>
        <td className="px-3 py-2.5 text-xs">
          <StatusBadge status={agent.status} />
        </td>
        <td className="px-3 py-2.5 text-xs">
          <TechnicalValue>{current ? `v${current.version_number}` : "—"}</TechnicalValue>
        </td>
        <td className="px-3 py-2.5 font-mono text-xs">{versions.length}</td>
        <td className="px-3 py-2.5 font-mono text-xs">{agentRuntimes.length}</td>
        <td className="px-3 py-2.5 text-xs text-ink-500">{formatRelative(lastActivity)}</td>
        <td className="px-3 py-2.5 text-right text-xs">
          <Link
            href={`/governance/registry/agents/${agent.id}`}
            className="font-semibold text-accent-600 hover:text-accent-500"
          >
            Open →
          </Link>
        </td>
      </tr>
      {open ? (
        versions.length === 0 ? (
          <tr className="bg-base-100">
            <td colSpan={7} className="px-3 py-6 pl-12 text-xs text-ink-500">
              This agent has no versions.
            </td>
          </tr>
        ) : (
          <>
            <tr className="bg-base-100">
              <td colSpan={7} className="px-3 pb-1 pt-2 pl-12">
                <div className="grid grid-cols-[80px_140px_1fr_1fr_110px_1fr] gap-3 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                  <span>Version</span>
                  <span>Lifecycle</span>
                  <span>Created</span>
                  <span>Approved</span>
                  <span>Runtime IDs</span>
                  <span>Configuration Change</span>
                </div>
              </td>
            </tr>
            {versions.map((version) => {
              const bound = runtimeByVersion.get(version.id) ?? [];
              return (
                <tr key={version.id} className="bg-base-100 hover:bg-base-50">
                  <td colSpan={7} className="px-3 py-2 pl-12 text-xs">
                    <Link
                      href={`/governance/registry/versions/${version.id}`}
                      className="grid grid-cols-[80px_140px_1fr_1fr_110px_1fr] items-center gap-3 hover:text-accent-600"
                    >
                      <span className="font-mono font-semibold">
                        v{version.version_number}
                        {current?.id === version.id ? (
                          <span className="ml-1 text-[10px] font-normal text-accent-600">
                            current
                          </span>
                        ) : null}
                      </span>
                      <span>
                        <StatusBadge status={version.lifecycle_status} />
                      </span>
                      <span className="text-ink-500">—</span>
                      <span className="text-ink-500">{formatRelative(version.approved_at)}</span>
                      <span className="font-mono">{bound.length}</span>
                      <span className="truncate text-ink-600">{version.change_summary || "—"}</span>
                    </Link>
                  </td>
                </tr>
              );
            })}
          </>
        )
      ) : null}
    </>
  );
}
