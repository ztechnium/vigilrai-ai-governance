"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";

/** Must stay aligned with backend AI_SYSTEM_TRANSITIONS. */
const SYSTEM_TRANSITIONS: Record<string, string[]> = {
  DRAFT: ["UNDER_REVIEW", "RETIRED"],
  UNDER_REVIEW: ["APPROVED", "DRAFT", "RETIRED"],
  APPROVED: ["SUSPENDED", "UNDER_REVIEW", "RETIRED"],
  SUSPENDED: ["APPROVED", "RETIRED"],
  RETIRED: ["DRAFT"],
};

/** Must stay aligned with backend AGENT_TRANSITIONS. */
const AGENT_TRANSITIONS: Record<string, string[]> = {
  DRAFT: ["UNDER_REVIEW", "RETIRED"],
  UNDER_REVIEW: ["APPROVED", "DRAFT", "RETIRED"],
  APPROVED: ["SUSPENDED", "UNDER_REVIEW", "RETIRED"],
  SUSPENDED: ["APPROVED", "RETIRED"],
  RETIRED: ["DRAFT"],
};

/** Must stay aligned with backend AGENT_VERSION_TRANSITIONS. */
const VERSION_TRANSITIONS: Record<string, string[]> = {
  DRAFT: ["UNDER_REVIEW", "RETIRED"],
  UNDER_REVIEW: ["APPROVED", "DRAFT", "REASSESSMENT_REQUIRED", "RETIRED"],
  REASSESSMENT_REQUIRED: ["UNDER_REVIEW", "DRAFT", "RETIRED"],
  // Reopen approved versions for dependency / catalog changes, then re-review.
  APPROVED: ["REASSESSMENT_REQUIRED", "RETIRED"],
  RETIRED: ["DRAFT"],
};

const TRANSITIONS_BY_KIND = {
  system: SYSTEM_TRANSITIONS,
  agent: AGENT_TRANSITIONS,
  version: VERSION_TRANSITIONS,
} as const;

export type LifecycleEntityKind = keyof typeof TRANSITIONS_BY_KIND;

const STATUS_LABELS: Record<string, string> = {
  UNDER_REVIEW: "Submit for review",
  APPROVED: "Approve",
  DRAFT: "Return to draft",
  SUSPENDED: "Suspend",
  RETIRED: "Retire",
  REASSESSMENT_REQUIRED: "Require reassessment",
};

const WORKFLOW_HINTS: Record<LifecycleEntityKind, Record<string, string>> = {
  system: {
    DRAFT:
      "Governance path: Submit for review → Approve. Only APPROVED systems are eligible for runtime identities and approvals.",
    UNDER_REVIEW:
      "Review complete? Choose Approve to make this governance-eligible for runtime use.",
    APPROVED: "Governance-eligible. Agents and agent versions must also be approved separately.",
    SUSPENDED: "Not governance-eligible while suspended. Re-approve or retire.",
    RETIRED:
      "Retired systems block runtime approvals. Reactivate to draft to run the approval workflow again.",
  },
  agent: {
    DRAFT: "Submit for review, then approve before binding runtime identities.",
    UNDER_REVIEW: "Approve to make this agent governance-eligible.",
    APPROVED: "Agent is approved. Exact agent versions still need their own approval.",
    SUSPENDED: "Not governance-eligible while suspended.",
    RETIRED: "Retired agents cannot host new runtime authority until reactivated.",
  },
  version: {
    DRAFT:
      "Add MCP/tool dependencies here, then Submit for review → Approve. Only APPROVED versions can bind runtime identities.",
    UNDER_REVIEW:
      "Approve for runtime use, return to draft, or mark reassessment required if catalog/deps need changes.",
    REASSESSMENT_REQUIRED:
      "Dependencies are mutable again. Update MCP/tools, then submit for review.",
    APPROVED:
      "Immutable while approved. Choose Require reassessment to edit dependencies, or Retire.",
    RETIRED: "Reactivate to draft to start a new governance cycle.",
  },
};

const RECOMMENDED: Record<LifecycleEntityKind, Record<string, string>> = {
  system: {
    DRAFT: "UNDER_REVIEW",
    UNDER_REVIEW: "APPROVED",
    SUSPENDED: "APPROVED",
    RETIRED: "DRAFT",
  },
  agent: {
    DRAFT: "UNDER_REVIEW",
    UNDER_REVIEW: "APPROVED",
    SUSPENDED: "APPROVED",
    RETIRED: "DRAFT",
  },
  version: {
    DRAFT: "UNDER_REVIEW",
    UNDER_REVIEW: "APPROVED",
    REASSESSMENT_REQUIRED: "UNDER_REVIEW",
    APPROVED: "REASSESSMENT_REQUIRED",
    RETIRED: "DRAFT",
  },
};

export function LifecycleActions({
  currentStatus,
  onTransition,
  entityKind = "system",
}: {
  currentStatus: string;
  onTransition: (status: string) => Promise<void>;
  /** Defaults to system for backward compatibility. */
  entityKind?: LifecycleEntityKind;
}) {
  const transitions = TRANSITIONS_BY_KIND[entityKind];
  const options = useMemo(() => transitions[currentStatus] ?? [], [transitions, currentStatus]);
  const recommended = RECOMMENDED[entityKind][currentStatus];
  const [target, setTarget] = useState(recommended ?? options[0] ?? "");
  const [loading, setLoading] = useState(false);
  const [confirmRetire, setConfirmRetire] = useState(false);

  useEffect(() => {
    setTarget(recommended ?? options[0] ?? "");
    setConfirmRetire(false);
  }, [currentStatus, recommended, options]);

  if (options.length === 0) {
    return <p className="text-sm text-ink-400">No lifecycle transitions available.</p>;
  }

  const hint = WORKFLOW_HINTS[entityKind][currentStatus];
  const isRetire = target === "RETIRED";
  const isReactivate = currentStatus === "RETIRED" && target === "DRAFT";
  const isReassess = target === "REASSESSMENT_REQUIRED";

  return (
    <div className="space-y-3">
      {hint && (
        <p className="rounded-lg border border-base-200 bg-base-50 px-3 py-2 text-sm text-ink-600">
          {hint}
        </p>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[220px] flex-1">
          <Select value={target} onChange={(e) => setTarget(e.target.value)}>
            {options.map((opt) => (
              <option key={opt} value={opt}>
                {STATUS_LABELS[opt] ?? opt}
                {opt === recommended ? " (recommended)" : ""}
              </option>
            ))}
          </Select>
        </div>
        <Button
          variant={isRetire ? "secondary" : "primary"}
          disabled={loading || !target || (isRetire && !confirmRetire)}
          onClick={async () => {
            if (isRetire && !confirmRetire) {
              setConfirmRetire(true);
              return;
            }
            setLoading(true);
            try {
              await onTransition(target);
              setConfirmRetire(false);
            } finally {
              setLoading(false);
            }
          }}
        >
          {loading
            ? "Applying..."
            : isRetire && !confirmRetire
              ? "Confirm retire"
              : isReactivate
                ? "Reactivate to draft"
                : isReassess
                  ? "Require reassessment"
                  : "Apply transition"}
        </Button>
      </div>

      {isRetire && confirmRetire && (
        <p className="text-sm text-amber-700">
          Retiring blocks runtime approvals for this record. Click again to confirm, or choose
          another transition.
        </p>
      )}

      {currentStatus === "DRAFT" && (
        <p className="text-xs text-ink-500">
          <strong className="text-ink-700">Note:</strong> &quot;Approve&quot; appears only after
          status is Under Review.
        </p>
      )}
    </div>
  );
}
