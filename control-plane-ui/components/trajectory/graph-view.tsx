"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Panel } from "@/components/registry/panel";
import { Table } from "@/components/ui/table";
import { humanEventLabel } from "@/lib/evidence-content";
import type { TrajectoryGraph } from "@/lib/types";

function shortId(value?: string | null) {
  if (!value) return "—";
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

function SourceBadge({ source }: { source: string }) {
  const tone =
    source === "RAI_AUTHORITATIVE" || source === "RAI_EXECUTED"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
      : source === "CLIENT_REPORTED" || source === "CLIENT_OBSERVED"
        ? "border-amber-200 bg-amber-50 text-amber-950"
        : "border-base-200 bg-base-100 text-ink-700";
  return (
    <span className={`inline-flex rounded border px-2 py-0.5 text-[11px] font-semibold ${tone}`}>
      {source}
    </span>
  );
}

function AssuranceBadge({ level }: { level: string }) {
  const tone =
    level === "HIGH"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
      : level === "MEDIUM"
        ? "border-sky-200 bg-sky-50 text-sky-900"
        : level === "LOW"
          ? "border-amber-200 bg-amber-50 text-amber-950"
          : "border-base-200 bg-base-100 text-ink-700";
  return (
    <span className={`inline-flex rounded border px-2 py-0.5 text-[11px] font-semibold ${tone}`}>
      {level}
    </span>
  );
}

const ENTITY_ORDER = [
  "TRAJECTORY",
  "EVENT",
  "ARTIFACT",
  "RECEIPT",
  "APPROVAL_REQUEST",
  "APPROVAL_DECISION",
  "POLICY_RULE",
  "RUNTIME_IDENTITY",
  "TOOL",
  "EXECUTION",
  "FINDING",
];

function entityTone(entityType: string): string {
  switch (entityType) {
    case "EVENT":
      return "border-sky-200 bg-sky-50/70";
    case "RECEIPT":
    case "EXECUTION":
      return "border-emerald-200 bg-emerald-50/70";
    case "APPROVAL_REQUEST":
    case "APPROVAL_DECISION":
      return "border-amber-200 bg-amber-50/70";
    case "FINDING":
      return "border-red-200 bg-red-50/70";
    case "ARTIFACT":
      return "border-violet-200 bg-violet-50/40";
    default:
      return "border-base-200 bg-white";
  }
}

function humanEntityType(entityType: string): string {
  return entityType
    .toLowerCase()
    .split("_")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}

function humanRelation(relation: string): string {
  return relation
    .toLowerCase()
    .split("_")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}

function nodeLabel(node: TrajectoryGraph["nodes"][number]): string {
  if (node.entity_type === "EVENT") return humanEventLabel(node.label);
  if (node.title) return node.title;
  return node.label;
}

export function TrajectoryGraphView({
  graph,
  trajectoryId,
}: {
  graph: TrajectoryGraph | null;
  trajectoryId: string;
}) {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string>("ALL");

  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];

  const grouped = useMemo(() => {
    const map = new Map<string, typeof nodes>();
    for (const node of nodes) {
      const list = map.get(node.entity_type) ?? [];
      list.push(node);
      map.set(node.entity_type, list);
    }
    const types = Array.from(map.keys()).sort((a, b) => {
      const ia = ENTITY_ORDER.indexOf(a);
      const ib = ENTITY_ORDER.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });
    return types.map((type) => ({ type, nodes: map.get(type) ?? [] }));
  }, [nodes]);

  const typeOptions = useMemo(() => ["ALL", ...grouped.map((g) => g.type)], [grouped]);

  const visibleGroups = useMemo(
    () => (typeFilter === "ALL" ? grouped : grouped.filter((g) => g.type === typeFilter)),
    [grouped, typeFilter],
  );

  const selected = useMemo(() => {
    if (!selectedKey) return null;
    return nodes.find((n) => `${n.entity_type}:${n.id}` === selectedKey) ?? null;
  }, [nodes, selectedKey]);

  const relatedEdges = useMemo(() => {
    if (!selected) return [];
    return edges.filter(
      (e) =>
        (e.source_entity_type === selected.entity_type && e.source_entity_id === selected.id) ||
        (e.target_entity_type === selected.entity_type && e.target_entity_id === selected.id),
    );
  }, [edges, selected]);

  const evidenceHref = (eventId: string) =>
    `/runtime/trajectories/${trajectoryId}/evidence/${eventId}`;

  const relationRows = useMemo(() => {
    const list = selected ? relatedEdges : edges;
    return list.map((edge) => [
      <span key={`${edge.id}-from`} className="text-xs">
        <span className="font-semibold text-ink-800">
          {humanEntityType(edge.source_entity_type)}
        </span>
        <span className="mt-0.5 block font-mono text-[11px] text-ink-500">
          {shortId(edge.source_entity_id)}
        </span>
      </span>,
      <span
        key={`${edge.id}-rel`}
        className="inline-flex rounded-full border border-base-200 bg-base-100 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-ink-700"
      >
        {humanRelation(edge.relation_type)}
      </span>,
      <span key={`${edge.id}-to`} className="text-xs">
        <span className="font-semibold text-ink-800">
          {humanEntityType(edge.target_entity_type)}
        </span>
        <span className="mt-0.5 block font-mono text-[11px] text-ink-500">
          {shortId(edge.target_entity_id)}
        </span>
      </span>,
    ]);
  }, [edges, relatedEdges, selected]);

  if (!graph || nodes.length === 0) {
    return (
      <Panel title="Evidence graph" data-testid="trajectory-graph">
        <p className="text-sm text-ink-500">No graph relations yet.</p>
      </Panel>
    );
  }

  return (
    <div className="space-y-4" data-testid="trajectory-graph">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-base-200 bg-white px-4 py-3 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-500">Nodes</p>
          <p className="mt-1 text-2xl font-semibold text-ink-900">{nodes.length}</p>
        </div>
        <div className="rounded-xl border border-base-200 bg-white px-4 py-3 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-500">
            Relations
          </p>
          <p className="mt-1 text-2xl font-semibold text-ink-900">{edges.length}</p>
        </div>
        <div className="rounded-xl border border-base-200 bg-white px-4 py-3 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-500">
            Entity types
          </p>
          <p className="mt-1 text-2xl font-semibold text-ink-900">{grouped.length}</p>
        </div>
      </div>

      <Panel
        title="Provenance graph"
        description="Entity catalog and directed relations used for audit explainability."
        actions={
          <select
            className="rounded-md border border-base-200 bg-white px-2.5 py-1 text-xs font-semibold text-ink-700"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            {typeOptions.map((t) => (
              <option key={t} value={t}>
                {t === "ALL" ? "All entity types" : humanEntityType(t)}
              </option>
            ))}
          </select>
        }
      >
        <div className="mb-4 flex flex-wrap gap-2 text-[11px] text-ink-500">
          <span className="font-semibold uppercase tracking-wide">Legend</span>
          {["EVENT", "RECEIPT", "APPROVAL_REQUEST", "FINDING", "ARTIFACT"].map((t) => (
            <span key={t} className={`rounded border px-2 py-0.5 font-medium ${entityTone(t)}`}>
              {humanEntityType(t)}
            </span>
          ))}
        </div>

        <div className="space-y-5">
          {visibleGroups.map((group) => (
            <div key={group.type}>
              <div className="mb-2 flex items-center justify-between gap-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-500">
                  {humanEntityType(group.type)}
                  <span className="ml-2 font-normal text-ink-400">({group.nodes.length})</span>
                </h3>
              </div>
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {group.nodes.map((node) => {
                  const key = `${node.entity_type}:${node.id}`;
                  const isEvent = node.entity_type === "EVENT";
                  const selectedNode = selectedKey === key;
                  const card = (
                    <button
                      type="button"
                      onClick={() => setSelectedKey(selectedNode ? null : key)}
                      className={`w-full rounded-xl border p-3 text-left transition ${entityTone(
                        node.entity_type,
                      )} ${
                        selectedNode ? "ring-2 ring-ink-800 ring-offset-1" : "hover:border-ink-300"
                      }`}
                      data-testid={isEvent ? "graph-event-node" : undefined}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-500">
                            {humanEntityType(node.entity_type)}
                          </p>
                          <p className="mt-1 truncate text-sm font-semibold text-ink-900">
                            {nodeLabel(node)}
                          </p>
                          <p className="mt-1 font-mono text-[11px] text-ink-400">
                            {shortId(node.id)}
                          </p>
                        </div>
                        <div className="flex flex-col items-end gap-1">
                          {node.assurance_level && <AssuranceBadge level={node.assurance_level} />}
                          {node.source_type && <SourceBadge source={node.source_type} />}
                        </div>
                      </div>
                      {isEvent && (
                        <p className="mt-2 text-[11px] font-semibold text-accent-700">
                          Select to inspect relations · open details below
                        </p>
                      )}
                    </button>
                  );

                  if (!isEvent) {
                    return <div key={key}>{card}</div>;
                  }

                  return (
                    <div key={key} className="space-y-1">
                      {card}
                      <Link
                        href={evidenceHref(node.id)}
                        className="inline-block px-1 text-xs font-semibold text-accent-700 hover:underline"
                      >
                        View Details →
                      </Link>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <Panel title="Selection">
          {!selected ? (
            <p className="text-sm text-ink-500">
              Select a node to focus related edges and downstream evidence.
            </p>
          ) : (
            <div className="space-y-3 text-sm">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                  Entity
                </p>
                <p className="mt-1 font-semibold text-ink-900">
                  {humanEntityType(selected.entity_type)}
                </p>
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                  Label
                </p>
                <p className="mt-1 text-ink-800">{nodeLabel(selected)}</p>
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                  Identifier
                </p>
                <p className="mt-1 break-all font-mono text-xs text-ink-600">{selected.id}</p>
              </div>
              <p className="text-xs text-ink-500">
                {relatedEdges.length} related relation
                {relatedEdges.length === 1 ? "" : "s"}
              </p>
              {selected.entity_type === "EVENT" && (
                <Link
                  href={evidenceHref(selected.id)}
                  className="inline-block text-sm font-semibold text-accent-700 hover:underline"
                >
                  View Details →
                </Link>
              )}
              <button
                type="button"
                className="text-xs font-semibold text-ink-500 hover:text-ink-800"
                onClick={() => setSelectedKey(null)}
              >
                Clear selection
              </button>
            </div>
          )}
        </Panel>

        <Panel
          title={selected ? "Focused relations" : "All relations"}
          description="Directed provenance links between evidence entities."
        >
          {relationRows.length === 0 ? (
            <p className="text-sm text-ink-500">No relations to display.</p>
          ) : (
            <Table columns={["From", "Relation", "To"]} rows={relationRows} />
          )}
        </Panel>
      </div>
    </div>
  );
}
