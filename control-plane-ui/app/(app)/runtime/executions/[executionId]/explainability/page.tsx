"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { SectionHeader } from "@/components/section-header";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { getExecutionExplainability, queryExecutions } from "@/lib/api";
import { decisionTone, formatDecision } from "@/lib/format";
import type { ExecutionExplainability } from "@/lib/types";

export default function ExecutionExplainabilityPage() {
  const { executionId } = useParams<{ executionId: string }>();
  const [record, setRecord] = useState<ExecutionExplainability | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    const resolveSampleExecutionId = async () => {
      const response = await queryExecutions({ limit: 1 });
      const first = response.data[0];
      return first?.execution_id;
    };

    const fetchRecord = async () => {
      const id = executionId === "sample" ? await resolveSampleExecutionId() : executionId;
      if (!id) {
        throw new Error("No executions available.");
      }

      const response = await getExecutionExplainability(id);
      if (!active) return;
      setRecord(response.data);
    };

    fetchRecord()
      .catch((err: Error) => {
        if (!active) return;
        setError(err.message);
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [executionId]);

  const timeline = useMemo(() => {
    if (!record) return [];
    const steps = [
      {
        title: "Allowlist Check",
        detail: "System/module allowlisted for this prompt version.",
        tone: "accent",
      },
      {
        title: "RAI Guard Precheck",
        detail: record.reason_codes.length
          ? `Reason codes: ${record.reason_codes.join(", ")}`
          : "No violations detected in precheck.",
        tone: record.reason_codes.length ? "warn" : "accent",
      },
    ];

    if (record.decision.toLowerCase() === "allow") {
      steps.push({
        title: "Model Invocation",
        detail: record.llm_model ? `Provider model: ${record.llm_model}` : "Model invoked.",
        tone: "accent",
      });
      steps.push({
        title: "RAI Guard Postcheck",
        detail: "Output validated against policies.",
        tone: "accent",
      });
    } else {
      steps.push({
        title: "Decision",
        detail: "Execution blocked before model invocation.",
        tone: "danger",
      });
    }

    return steps;
  }, [record]);

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Execution Explainability"
        subtitle="Deterministic decision path with policy evidence (no raw content)."
        actions={<Badge variant="accent">Explainability</Badge>}
      />

      {loading ? (
        <div className="rounded-xl border border-base-200 bg-base-100 p-6 text-sm text-ink-500">
          Loading execution metadata...
        </div>
      ) : error ? (
        <div className="rounded-xl border border-base-200 bg-danger-100 p-6 text-sm text-danger-600">
          Failed to load execution: {error}
        </div>
      ) : record ? (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <Card
              title="Decision"
              value={formatDecision(record.decision)}
              tone={decisionTone(record.decision)}
            />
            <Card
              title="Reason Codes"
              value={record.reason_codes.length ? record.reason_codes.join(", ") : "-"}
              tone={record.reason_codes.length ? "warn" : "neutral"}
            />
            <Card title="Trace ID" value={record.trace_id} />
          </div>

          <div className="rounded-xl border border-base-200 bg-base-100 p-5">
            <h3 className="mb-3 text-lg font-semibold">Decision Timeline</h3>
            <div className="space-y-4">
              {timeline.map((step) => (
                <div key={step.title} className="flex items-start gap-3">
                  <span
                    className={`mt-1 h-2 w-2 rounded-full ${
                      step.tone === "danger"
                        ? "bg-danger-600"
                        : step.tone === "warn"
                          ? "bg-warn-600"
                          : "bg-accent-500"
                    }`}
                  />
                  <div>
                    <p className="text-sm font-semibold">{step.title}</p>
                    <p className="text-sm text-ink-500">{step.detail}</p>
                    {record.rule_ids &&
                    record.rule_ids.length > 0 &&
                    step.title === "RAI Guard Precheck" ? (
                      <p className="text-xs text-ink-300">Rules: {record.rule_ids.join(", ")}</p>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-base-200 bg-base-100 p-5">
            <h3 className="mb-3 text-lg font-semibold">Evidence (Metadata Only)</h3>
            <div className="grid gap-3 text-sm text-ink-600">
              <div className="flex items-center justify-between">
                <span>Input Hash</span>
                <span className="font-mono text-xs">{record.input_hash ?? "-"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Output Hash</span>
                <span className="font-mono text-xs">{record.output_hash ?? "-"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Policy Version</span>
                <span>{record.policy_version ?? "-"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Guard Version</span>
                <span>{record.guard_version ?? "-"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Latency</span>
                <span>{record.latency_ms ? `${record.latency_ms} ms` : "-"}</span>
              </div>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
