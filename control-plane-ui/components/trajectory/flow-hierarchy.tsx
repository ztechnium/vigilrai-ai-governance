"use client";

import { useMemo, useState } from "react";
import { TechnicalValue } from "@/components/console/page-parts";
import { StatusBadge } from "@/components/registry/status-badge";
import { cn } from "@/lib/utils";
import type { EvidenceEvent, TrajectoryDetail, TrajectoryGraph } from "@/lib/types";

type FlowKind = "trigger" | "agent" | "condition" | "action" | "human" | "output" | "other";

type FlowNode = {
  id: string;
  title: string;
  subtitle: string;
  kind: FlowKind;
  decision?: string;
  eventId?: string;
  hash?: string;
};

type FlowEdge = {
  id: string;
  from: string;
  to: string;
  label?: string;
};

const KIND_STYLE: Record<FlowKind, { border: string; glow: string; iconBg: string; icon: string }> =
  {
    trigger: {
      border: "border-emerald-400/70",
      glow: "shadow-[0_0_24px_rgba(52,211,153,0.35)]",
      iconBg: "bg-emerald-500/20 text-emerald-300",
      icon: "bolt",
    },
    agent: {
      border: "border-violet-400/70",
      glow: "shadow-[0_0_24px_rgba(167,139,250,0.4)]",
      iconBg: "bg-violet-500/20 text-violet-300",
      icon: "spark",
    },
    condition: {
      border: "border-amber-400/70",
      glow: "shadow-[0_0_24px_rgba(251,191,36,0.35)]",
      iconBg: "bg-amber-500/20 text-amber-300",
      icon: "branch",
    },
    action: {
      border: "border-sky-400/70",
      glow: "shadow-[0_0_24px_rgba(56,189,248,0.35)]",
      iconBg: "bg-sky-500/20 text-sky-300",
      icon: "send",
    },
    human: {
      border: "border-fuchsia-400/70",
      glow: "shadow-[0_0_24px_rgba(232,121,249,0.35)]",
      iconBg: "bg-fuchsia-500/20 text-fuchsia-300",
      icon: "user",
    },
    output: {
      border: "border-lime-400/70",
      glow: "shadow-[0_0_24px_rgba(163,230,53,0.3)]",
      iconBg: "bg-lime-500/20 text-lime-300",
      icon: "check",
    },
    other: {
      border: "border-base-300",
      glow: "shadow-[0_0_16px_rgba(148,163,184,0.2)]",
      iconBg: "bg-base-200 text-ink-400",
      icon: "dot",
    },
  };

function eventTypeLabel(eventType: string) {
  return eventType.replace(/_/g, " ").toUpperCase();
}

function kindFor(eventType: string): FlowKind {
  const upper = eventType.toUpperCase();
  if (upper.includes("PROMPT") || upper.includes("SESSION") || upper.includes("START")) {
    return "trigger";
  }
  if (upper.includes("MODEL") || upper.includes("AGENT") || upper.includes("INFERENCE")) {
    return "agent";
  }
  if (
    upper.includes("POLICY") ||
    upper.includes("BUDGET") ||
    upper.includes("CONDITION") ||
    upper.includes("AUTHORIZ")
  ) {
    return "condition";
  }
  if (upper.includes("APPROVAL") || upper.includes("HUMAN") || upper.includes("REVIEW")) {
    return "human";
  }
  if (
    upper.includes("TOOL") ||
    upper.includes("ACTION") ||
    upper.includes("EXECUTION") ||
    upper.includes("SEND")
  ) {
    return "action";
  }
  if (upper.includes("OUTPUT") || upper.includes("COMPLETE") || upper.includes("RESULT")) {
    return "output";
  }
  return "other";
}

function decisionFromEvent(event: EvidenceEvent): string | undefined {
  const payload = event.payload ?? {};
  for (const key of ["decision", "enforcement_decision", "policy_decision", "effect", "outcome"]) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value;
    if (value && typeof value === "object" && "final_effect" in value) {
      const effect = (value as { final_effect?: unknown }).final_effect;
      if (typeof effect === "string") return effect;
    }
  }
  return undefined;
}

function subtitleFor(event: EvidenceEvent): string {
  const payload = event.payload ?? {};
  for (const key of ["summary", "tool_name", "tool", "model", "reason", "message"]) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  const latency = payload.latency_ms ?? payload.duration_ms;
  const parts = [event.source_type.replace(/_/g, " ").toLowerCase()];
  if (typeof latency === "number") parts.push(`${latency} ms`);
  else if (typeof latency === "string" && latency.trim()) parts.push(`${latency} ms`);
  return parts.join(" · ");
}

function NodeIcon({ name }: { name: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      className="size-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
    >
      {name === "bolt" ? (
        <path d="M9 1.5 4.5 9h3.2L7 14.5 12.5 7H9.2L9 1.5Z" />
      ) : name === "spark" ? (
        <path d="M8 1.5 9.2 6.2 14 7.5 9.2 8.8 8 14.5 6.8 8.8 2 7.5 6.8 6.2 8 1.5Z" />
      ) : name === "branch" ? (
        <path d="M4 2.5v5.5c0 1.5 1.2 2.5 2.8 2.5H9m0 0 2-2m-2 2 2 2M12 3v3" />
      ) : name === "send" ? (
        <path d="M2.5 8 13.5 3.5 9 13.5 7.2 9.2 2.5 8Z" />
      ) : name === "user" ? (
        <>
          <circle cx="8" cy="5.5" r="2.2" />
          <path d="M3.5 13c.8-2.2 2.4-3.3 4.5-3.3s3.7 1.1 4.5 3.3" />
        </>
      ) : name === "check" ? (
        <path d="M3.5 8.2 6.5 11l6-6.5" />
      ) : (
        <circle cx="8" cy="8" r="2" fill="currentColor" stroke="none" />
      )}
    </svg>
  );
}

function buildFlowModel(
  trajectory: TrajectoryDetail,
  graph: TrajectoryGraph | null,
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const events = [...(trajectory.events ?? [])].sort(
    (a, b) =>
      (a.sequence_number ?? 0) - (b.sequence_number ?? 0) ||
      String(a.occurred_at ?? "").localeCompare(String(b.occurred_at ?? "")),
  );

  const startId = "flow-start";
  const nodes: FlowNode[] = [
    {
      id: startId,
      title: "Start Trajectory",
      subtitle: trajectory.client_type
        ? `${trajectory.client_type} · event trigger`
        : "Runtime event trigger",
      kind: "trigger",
      hash: trajectory.id.slice(0, 10),
    },
  ];

  for (const event of events) {
    const decision = decisionFromEvent(event);
    nodes.push({
      id: event.id,
      title: eventTypeLabel(event.event_type),
      subtitle: subtitleFor(event),
      kind: kindFor(event.event_type),
      decision,
      eventId: event.id,
      hash: event.id.slice(0, 10),
    });
  }

  const edges: FlowEdge[] = [];
  const eventIds = new Set(events.map((event) => event.id));

  const graphEventEdges =
    graph?.edges.filter(
      (edge) =>
        edge.source_entity_type === "EVENT" &&
        edge.target_entity_type === "EVENT" &&
        eventIds.has(edge.source_entity_id) &&
        eventIds.has(edge.target_entity_id),
    ) ?? [];

  if (graphEventEdges.length > 0) {
    if (events[0]) {
      edges.push({
        id: `${startId}->${events[0].id}`,
        from: startId,
        to: events[0].id,
      });
    }
    for (const edge of graphEventEdges) {
      edges.push({
        id: edge.id,
        from: edge.source_entity_id,
        to: edge.target_entity_id,
        label: edge.relation_type.replace(/_/g, " ").toLowerCase(),
      });
    }
  } else {
    let previous = startId;
    for (const event of events) {
      const decision = decisionFromEvent(event);
      const label =
        decision && /approval|deny|allow|require/i.test(decision)
          ? decision.replace(/_/g, " ").toLowerCase()
          : undefined;
      edges.push({
        id: `${previous}->${event.id}`,
        from: previous,
        to: event.id,
        label,
      });
      previous = event.id;
    }
  }

  // Detect decision forks: condition/human nodes with APPROVAL_REQUIRED get yes/no labels
  // on the next sequential edges when multiple children exist.
  const children = new Map<string, FlowEdge[]>();
  for (const edge of edges) {
    const list = children.get(edge.from) ?? [];
    list.push(edge);
    children.set(edge.from, list);
  }
  for (const node of nodes) {
    const outs = children.get(node.id) ?? [];
    if (outs.length < 2) continue;
    if (node.kind !== "condition" && node.kind !== "human" && !node.decision) continue;
    outs.forEach((edge, index) => {
      if (edge.label) return;
      edge.label = index === 0 ? "yes" : index === 1 ? "no" : `path ${index + 1}`;
    });
  }

  return { nodes, edges };
}

type LayoutNode = FlowNode & { x: number; y: number; column: number; depth: number };

function layoutFlow(
  nodes: FlowNode[],
  edges: FlowEdge[],
): {
  placed: LayoutNode[];
  width: number;
  height: number;
} {
  const NODE_W = 260;
  const NODE_H = 72;
  const GAP_Y = 56;
  const GAP_X = 48;
  const PAD = 48;

  const children = new Map<string, string[]>();
  const indegree = new Map<string, number>();
  for (const node of nodes) indegree.set(node.id, 0);
  for (const edge of edges) {
    const list = children.get(edge.from) ?? [];
    list.push(edge.to);
    children.set(edge.from, list);
    indegree.set(edge.to, (indegree.get(edge.to) ?? 0) + 1);
  }

  const roots = nodes.filter((node) => (indegree.get(node.id) ?? 0) === 0);
  const depth = new Map<string, number>();
  const column = new Map<string, number>();
  const queue = [...roots.map((node) => node.id)];
  for (const root of roots) {
    depth.set(root.id, 0);
    column.set(root.id, 0);
  }

  let nextCol = roots.length;
  while (queue.length) {
    const id = queue.shift()!;
    const kids = children.get(id) ?? [];
    kids.forEach((child, index) => {
      const nextDepth = (depth.get(id) ?? 0) + 1;
      depth.set(child, Math.max(depth.get(child) ?? 0, nextDepth));
      if (!column.has(child)) {
        column.set(child, kids.length === 1 ? (column.get(id) ?? 0) : nextCol++);
      } else if (kids.length > 1 && index > 0) {
        column.set(child, nextCol++);
      }
      queue.push(child);
    });
  }

  // Compact columns to 0..n-1
  const usedCols = Array.from(new Set([...column.values()])).sort((a, b) => a - b);
  const colIndex = new Map(usedCols.map((value, index) => [value, index]));
  const colCount = Math.max(1, usedCols.length);

  const placed: LayoutNode[] = nodes.map((node) => {
    const d = depth.get(node.id) ?? 0;
    const c = colIndex.get(column.get(node.id) ?? 0) ?? 0;
    return {
      ...node,
      depth: d,
      column: c,
      x: PAD + c * (NODE_W + GAP_X),
      y: PAD + d * (NODE_H + GAP_Y),
    };
  });

  // Center single-column layouts
  if (colCount === 1) {
    const canvasW = Math.max(720, NODE_W + PAD * 2);
    const x = (canvasW - NODE_W) / 2;
    for (const node of placed) node.x = x;
    return {
      placed,
      width: canvasW,
      height: PAD * 2 + (Math.max(...placed.map((n) => n.depth), 0) + 1) * (NODE_H + GAP_Y) - GAP_Y,
    };
  }

  return {
    placed,
    width: PAD * 2 + colCount * NODE_W + (colCount - 1) * GAP_X,
    height: PAD * 2 + (Math.max(...placed.map((n) => n.depth), 0) + 1) * (NODE_H + GAP_Y) - GAP_Y,
  };
}

function FlowCard({
  node,
  selected,
  onSelect,
}: {
  node: LayoutNode;
  selected: boolean;
  onSelect: () => void;
}) {
  const style = KIND_STYLE[node.kind];
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "absolute flex w-[260px] items-center gap-3 rounded-xl border bg-[#12161f]/95 px-3 py-2.5 text-left transition-shadow",
        style.border,
        selected ? style.glow : "shadow-none hover:shadow-[0_0_16px_rgba(148,163,184,0.15)]",
        selected && "ring-1 ring-violet-400/50",
      )}
      style={{ left: node.x, top: node.y }}
      aria-pressed={selected}
    >
      <span
        className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg", style.iconBg)}
      >
        <NodeIcon name={style.icon} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold text-white">{node.title}</span>
        <span className="mt-0.5 block truncate text-xs text-slate-400">{node.subtitle}</span>
        {node.hash ? (
          <span className="mt-1 block font-mono text-[10px] text-slate-500">#{node.hash}</span>
        ) : null}
      </span>
      {node.decision ? (
        <span className="shrink-0">
          <StatusBadge status={node.decision} />
        </span>
      ) : null}
    </button>
  );
}

export function FlowHierarchyView({
  trajectory,
  graph,
  selectedId,
  onSelect,
}: {
  trajectory: TrajectoryDetail;
  graph: TrajectoryGraph | null;
  selectedId?: string;
  onSelect?: (eventId: string) => void;
}) {
  const { nodes, edges } = useMemo(() => buildFlowModel(trajectory, graph), [trajectory, graph]);
  const { placed, width, height } = useMemo(() => layoutFlow(nodes, edges), [nodes, edges]);
  const [localSelected, setLocalSelected] = useState(selectedId ?? nodes[1]?.id ?? nodes[0]?.id);
  const selected = selectedId ?? localSelected;

  const byId = useMemo(() => new Map(placed.map((node) => [node.id, node])), [placed]);

  if (nodes.length <= 1) {
    return (
      <div
        className="flex min-h-[420px] items-center justify-center rounded-xl border border-base-200 bg-base-50 text-sm text-ink-500"
        data-testid="trajectory-flow"
      >
        No runtime events available to build a flow hierarchy.
      </div>
    );
  }

  return (
    <div
      className="overflow-hidden rounded-xl border border-base-200 bg-[#0b0f19]"
      data-testid="trajectory-flow"
    >
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2">
        <div>
          <div className="text-sm font-semibold text-white">Flow hierarchy</div>
          <div className="text-[11px] text-slate-400">
            Governed execution path derived from trajectory evidence
          </div>
        </div>
        <TechnicalValue className="text-slate-400">{nodes.length - 1} events</TechnicalValue>
      </div>

      <div
        className="relative overflow-auto"
        style={{
          backgroundImage:
            "radial-gradient(circle at 1px 1px, rgba(148,163,184,0.18) 1px, transparent 0)",
          backgroundSize: "18px 18px",
        }}
      >
        <div className="relative min-h-[520px]" style={{ width, height: Math.max(height, 520) }}>
          <svg
            className="pointer-events-none absolute inset-0"
            width={width}
            height={Math.max(height, 520)}
            aria-hidden
          >
            <defs>
              <marker
                id="flow-arrow"
                markerWidth="8"
                markerHeight="8"
                refX="6"
                refY="3"
                orient="auto"
              >
                <path d="M0,0 L6,3 L0,6 Z" fill="rgba(167,139,250,0.85)" />
              </marker>
            </defs>
            {edges.map((edge) => {
              const from = byId.get(edge.from);
              const to = byId.get(edge.to);
              if (!from || !to) return null;
              const x1 = from.x + 130;
              const y1 = from.y + 72;
              const x2 = to.x + 130;
              const y2 = to.y;
              const midY = (y1 + y2) / 2;
              const path =
                Math.abs(x1 - x2) < 4
                  ? `M ${x1} ${y1} L ${x2} ${y2}`
                  : `M ${x1} ${y1} L ${x1} ${midY} L ${x2} ${midY} L ${x2} ${y2}`;
              const labelX = (x1 + x2) / 2;
              const labelY = midY - 8;
              return (
                <g key={edge.id}>
                  <path
                    d={path}
                    fill="none"
                    stroke="rgba(167,139,250,0.75)"
                    strokeWidth="1.5"
                    markerEnd="url(#flow-arrow)"
                  />
                  {edge.label ? (
                    <g transform={`translate(${labelX}, ${labelY})`}>
                      <rect
                        x={-28}
                        y={-10}
                        width={56}
                        height={18}
                        rx={9}
                        fill="#151a24"
                        stroke="rgba(167,139,250,0.35)"
                      />
                      <text
                        textAnchor="middle"
                        y={3}
                        className="fill-violet-300"
                        style={{ fontSize: 10, fontFamily: "ui-sans-serif, system-ui" }}
                      >
                        {edge.label}
                      </text>
                    </g>
                  ) : null}
                </g>
              );
            })}
          </svg>

          {placed.map((node) => (
            <FlowCard
              key={node.id}
              node={node}
              selected={selected === node.id || selected === node.eventId}
              onSelect={() => {
                setLocalSelected(node.id);
                if (node.eventId && onSelect) onSelect(node.eventId);
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
