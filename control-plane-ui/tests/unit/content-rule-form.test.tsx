import { describe, expect, it } from "vitest";
import {
  CONTENT_APPLIES_TO,
  EMPTY_CONTENT_RULE_FORM,
  RULE_CATEGORIES,
  RULE_SEVERITIES,
  contentRuleFormFromSummary,
} from "@/components/registry/content-rule-form";
import type { ContentRuleSummary } from "@/lib/types";

describe("content rule form", () => {
  it("includes applies_to, category, and severity defaults", () => {
    expect(EMPTY_CONTENT_RULE_FORM.applies_to).toBe("BOTH");
    expect(EMPTY_CONTENT_RULE_FORM.category).toBe("COMPLIANCE");
    expect(EMPTY_CONTENT_RULE_FORM.severity).toBe("MEDIUM");
    expect(CONTENT_APPLIES_TO.map((o) => o.value)).toEqual(["INPUT", "OUTPUT", "BOTH"]);
    expect(RULE_CATEGORIES).toContain("PRIVACY");
    expect(RULE_SEVERITIES).toContain("CRITICAL");
  });

  it("hydrates from summary", () => {
    const rule: ContentRuleSummary = {
      id: "r1",
      policy_collection_id: "c1",
      title: "Banking",
      content: "No bank data",
      effect: "DENY",
      enabled: true,
      applies_to: "OUTPUT",
      category: "PRIVACY",
      severity: "CRITICAL",
    };
    const form = contentRuleFormFromSummary(rule);
    expect(form.applies_to).toBe("OUTPUT");
    expect(form.category).toBe("PRIVACY");
    expect(form.severity).toBe("CRITICAL");
  });
});
