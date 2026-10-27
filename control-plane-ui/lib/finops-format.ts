export type CostState =
  "ACTUAL" | "ESTIMATED" | "METERED" | "BILLED" | "UNAVAILABLE" | "MIXED" | string;

const SOURCE_LABELS: Record<string, string> = {
  PROVIDER_RESPONSE: "Provider reported",
  GATEWAY_OBSERVED: "Gateway observed",
  SIGNED_SERVICE: "Signed service",
  SDK_REPORTED: "SDK reported",
  AGENT_SUPPLIED: "Agent supplied",
  PRICING_CATALOG_DERIVED: "Pricing catalog",
  PROVIDER_BILLING_API: "Provider billing",
  INVOICE_IMPORT: "Invoice import",
  EXPLICIT_COST: "Explicit cost",
  ESTIMATED: "Estimated",
  UNKNOWN: "Unknown source",
  MIXED: "Mixed sources",
};

export function sourceLabel(source?: string | null) {
  if (!source) return "Unknown source";
  return SOURCE_LABELS[source] ?? source;
}

export function costStateLabel(state?: string | null) {
  switch (state) {
    case "BILLED":
      return "Billed";
    case "METERED":
    case "ACTUAL":
      return "Metered";
    case "ESTIMATED":
      return "Estimated";
    case "MIXED":
      return "Mixed";
    default:
      return "Unavailable";
  }
}

export function formatMoney(amount: number | null | undefined, currency = "USD") {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return null;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: amount >= 1 ? 2 : 4,
  }).format(amount);
}

export function formatCost(
  amount: number | null | undefined,
  state?: string | null,
  currency = "USD",
) {
  if (!state || state === "UNAVAILABLE" || amount === null || amount === undefined) {
    return "Unavailable";
  }
  const money = formatMoney(amount, currency) ?? "Unavailable";
  if (state === "ESTIMATED") return `≈ ${money}`;
  if (state === "METERED" || state === "ACTUAL") return `${money} metered`;
  if (state === "BILLED") return `${money} billed`;
  return money;
}

export function formatLatency(ms?: number | null) {
  if (ms === null || ms === undefined || Number.isNaN(ms) || ms < 0) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.round(ms / 60_000);
  return `${minutes}m`;
}

export function formatTokens(value?: number | null) {
  if (value === null || value === undefined) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}
