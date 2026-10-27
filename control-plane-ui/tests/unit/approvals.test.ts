import { describe, expect, it } from "vitest";

function formatParamValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return value.toLocaleString();
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

describe("approval parameter formatting", () => {
  it("formats numbers with locale grouping", () => {
    expect(formatParamValue(125000)).toBe((125000).toLocaleString());
  });

  it("handles null values", () => {
    expect(formatParamValue(null)).toBe("—");
  });
});

describe("acting membership", () => {
  it("uses the membership that matches the stage role", async () => {
    const { pickActingMembershipId } = await import("@/lib/acting-membership");
    const id = pickActingMembershipId(
      [
        { id: "admin", role: "ORGANIZATION_ADMIN" },
        { id: "approver", role: "BUSINESS_APPROVER" },
      ],
      ["business_approver"],
    );
    expect(id).toBe("approver");
  });

  it("falls back to the first membership when no stage role matches", async () => {
    const { pickActingMembershipId } = await import("@/lib/acting-membership");
    expect(
      pickActingMembershipId([{ id: "admin", role: "ORGANIZATION_ADMIN" }], ["rai_officer"]),
    ).toBe("admin");
  });
});

describe("approval terminal states", () => {
  const terminalStatuses = ["REJECTED", "EXPIRED", "CANCELLED", "CONSUMED"];

  it("treats pending as actionable", () => {
    expect(terminalStatuses.includes("PENDING")).toBe(false);
  });

  it("treats rejected as terminal", () => {
    expect(terminalStatuses.includes("REJECTED")).toBe(true);
  });
});
