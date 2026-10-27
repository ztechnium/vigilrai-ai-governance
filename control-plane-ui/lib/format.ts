export function formatDecision(decision: string) {
  const normalized = decision.toLowerCase();
  if (normalized === "block" || normalized === "blocked") return "Blocked";
  if (normalized === "flag" || normalized === "flagged") return "Flagged";
  return "Allowed";
}

export function decisionTone(decision: string): "neutral" | "warn" | "danger" {
  const normalized = decision.toLowerCase();
  if (normalized === "block" || normalized === "blocked") return "danger";
  if (normalized === "flag" || normalized === "flagged") return "warn";
  return "neutral";
}

export function formatEnforcementDecision(decision: string) {
  switch (decision) {
    case "ALLOW":
      return "Allowed";
    case "DENY":
      return "Denied";
    case "REQUIRE_APPROVAL":
      return "Approval Required";
    case "MONITOR":
      return "Monitored";
    default:
      return decision;
  }
}

export function enforcementTone(decision: string): "neutral" | "warn" | "danger" | "success" {
  switch (decision) {
    case "ALLOW":
      return "success";
    case "MONITOR":
      return "neutral";
    case "REQUIRE_APPROVAL":
      return "warn";
    case "DENY":
      return "danger";
    default:
      return "neutral";
  }
}

export function formatExecutionStatus(status: string) {
  switch (status) {
    case "NOT_ATTEMPTED":
      return "Not Attempted";
    case "PENDING_CLIENT_REPORT":
      return "Pending Client Report";
    case "STARTED":
    case "IN_PROGRESS":
      return "Started";
    case "SUCCEEDED":
      return "Succeeded";
    case "FAILED":
      return "Failed";
    case "UNKNOWN":
      return "Unknown";
    default:
      return status;
  }
}
