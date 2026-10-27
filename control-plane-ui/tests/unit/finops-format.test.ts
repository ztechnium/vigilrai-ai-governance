import { describe, expect, it } from "vitest";
import { formatCost } from "@/lib/finops-format";

describe("FinOps cost display", () => {
  it("shows actual cost without an estimate mark", () => {
    expect(formatCost(0.0084, "ACTUAL")).toContain("0.0084");
  });

  it("marks catalog cost as estimated", () => {
    expect(formatCost(0.008, "ESTIMATED").startsWith("≈")).toBe(true);
  });

  it("does not render unavailable cost as zero", () => {
    expect(formatCost(0, "UNAVAILABLE")).toBe("Unavailable");
    expect(formatCost(null, "ACTUAL")).toBe("Unavailable");
  });
});
