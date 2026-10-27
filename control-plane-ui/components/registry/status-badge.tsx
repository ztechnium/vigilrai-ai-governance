import { Badge } from "@/components/ui/badge";

function StatusIcon({ tone }: { tone: "neutral" | "accent" | "warn" | "danger" }) {
  if (tone === "accent") {
    return (
      <svg aria-hidden viewBox="0 0 16 16" className="size-3">
        <circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M5 8.2 7 10l4-4.2" fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    );
  }
  if (tone === "danger") {
    return (
      <svg aria-hidden viewBox="0 0 16 16" className="size-3">
        <circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M5.5 5.5 10.5 10.5M10.5 5.5 5.5 10.5" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    );
  }
  if (tone === "warn") {
    return (
      <svg aria-hidden viewBox="0 0 16 16" className="size-3">
        <path d="M8 2.2 14.2 13H1.8L8 2.2Z" fill="none" stroke="currentColor" strokeWidth="1.4" />
        <path d="M8 6.2v3.2" stroke="currentColor" strokeWidth="1.4" />
        <circle cx="8" cy="11.2" r="0.7" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg aria-hidden viewBox="0 0 16 16" className="size-3">
      <circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 5.2v3.2" stroke="currentColor" strokeWidth="1.4" />
      <circle cx="8" cy="10.8" r="0.7" fill="currentColor" />
    </svg>
  );
}

function toneFor(status: string): "neutral" | "accent" | "warn" | "danger" {
  const upper = status.toUpperCase();
  if (
    upper === "APPROVED" ||
    upper === "ACTIVE" ||
    upper === "ALLOW" ||
    upper === "ALLOWED" ||
    upper === "SUCCESS" ||
    upper === "COMPLETED" ||
    upper === "OPERATIONAL" ||
    upper === "CONNECTED" ||
    upper === "RESOLVED" ||
    upper === "LOW" ||
    upper === "OBSERVED" ||
    upper === "ALLOW"
  ) {
    return "accent";
  }
  if (
    upper === "SUSPENDED" ||
    upper === "RETIRED" ||
    upper === "CRITICAL" ||
    upper === "HIGH" ||
    upper === "MATERIAL" ||
    upper === "DENIED" ||
    upper === "DENY" ||
    upper === "BLOCK" ||
    upper === "REVOKED" ||
    upper === "FAILED" ||
    upper === "EXCEEDED" ||
    upper === "BLOCKED"
  ) {
    return "danger";
  }
  if (
    upper === "UNDER_REVIEW" ||
    upper === "REASSESSMENT_REQUIRED" ||
    upper === "MEDIUM" ||
    upper === "DRAFT" ||
    upper === "WARNING" ||
    upper === "APPROVAL_REQUIRED" ||
    upper === "APPROVAL REQUIRED" ||
    upper === "REQUIRE_APPROVAL" ||
    upper === "REQUIRE APPROVAL" ||
    upper === "INCOMPLETE"
  ) {
    return "warn";
  }
  return "neutral";
}

export function StatusBadge({ status }: { status?: string | null }) {
  const label = (status ?? "UNKNOWN").replace(/_/g, " ");
  const tone = toneFor(label);
  return (
    <Badge variant={tone}>
      <StatusIcon tone={tone} />
      <span className="font-mono uppercase">{label}</span>
    </Badge>
  );
}
