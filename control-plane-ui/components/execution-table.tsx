import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Table } from "@/components/ui/table";
import type { ExecutionAuditSummary } from "@/lib/types";
import { decisionTone, formatDecision } from "@/lib/format";

export function ExecutionTable({
  executions,
  showFilters = false,
}: {
  executions: ExecutionAuditSummary[];
  showFilters?: boolean;
}) {
  if (executions.length === 0) {
    return (
      <div className="rounded-xl border border-base-200 bg-base-100 p-6 text-sm text-ink-500">
        No execution records found for the current filters.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {showFilters && (
        <div className="flex flex-wrap gap-3">
          <input
            className="rounded-lg border border-base-200 px-3 py-2 text-sm"
            placeholder="Search trace or prompt"
          />
          <select className="rounded-lg border border-base-200 px-3 py-2 text-sm">
            <option>Decision: all</option>
            <option>Allowed</option>
            <option>Blocked</option>
            <option>Flagged</option>
          </select>
        </div>
      )}
      <Table
        columns={["Trace ID", "Prompt", "Version", "System", "Decision", "Reason", ""]}
        rows={executions.map((exec) => [
          exec.trace_id,
          exec.prompt_id,
          String(exec.prompt_version),
          exec.system_id,
          <Badge key={exec.execution_id} variant={decisionTone(exec.decision)}>
            {formatDecision(exec.decision)}
          </Badge>,
          exec.reason_codes.length > 0 ? exec.reason_codes.join(", ") : "-",
          <Link
            key={`${exec.execution_id}-link`}
            className="text-sm font-semibold text-accent-600"
            href={`/runtime/executions/${exec.execution_id}/explainability`}
          >
            Explain
          </Link>,
        ])}
      />
    </div>
  );
}
