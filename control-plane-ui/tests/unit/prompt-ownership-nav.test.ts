import { describe, expect, it } from "vitest";
import { navSections } from "@/lib/nav";

describe("prompt ownership navigation", () => {
  it("removes Prompts from Build & Govern", () => {
    const build = navSections.find((s) => s.label === "Build & Govern");
    expect(build).toBeTruthy();
    const labels = build!.items.map((i) => i.label);
    expect(labels).not.toContain("Prompts");
    expect(labels).toContain("AI Systems");
    expect(labels).toContain("RAI Rules");
  });

  it("keeps trajectories and audit explorer under Runtime", () => {
    const runtime = navSections.find((s) => s.label === "Runtime");
    expect(runtime).toBeTruthy();
    const labels = runtime!.items.map((i) => i.label);
    expect(labels).not.toContain("Conversations");
    expect(labels).toContain("Trajectories");
    expect(labels).toContain("Audit Explorer");
    expect(labels).not.toContain("Integrations");
    expect(labels).not.toContain("Test Console");
  });

  it("drops soon sections and merges team administration", () => {
    const labels = navSections.map((section) => section.label);
    expect(labels).not.toContain("Assurance");
    expect(labels).not.toContain("Governance");
    expect(labels).not.toContain("Audit");
    const items = navSections.flatMap((section) => section.items.map((item) => item.href));
    expect(items).toContain("/organization/team");
    expect(items).not.toContain("/administration/users");
    expect(items).not.toContain("/administration/feature-flags");
    expect(items).not.toContain("/audit/logs");
    expect(items).not.toContain("/pilot");
  });

  it("does not keep a standalone Integrations nav entry", () => {
    const labels = navSections.flatMap((s) => s.items.map((i) => i.label));
    expect(labels).not.toContain("Integrations");
  });
});
