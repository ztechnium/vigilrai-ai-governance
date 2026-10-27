"use client";

import { FormField } from "@/components/registry/form-field";
import {
  APPROVER_ROLES,
  POLICY_EFFECT_OPTIONS,
  RULE_CATEGORIES,
  RULE_SEVERITIES,
} from "@/components/registry/tool-rule-form";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { ContentRuleSummary, PolicySourceSummary } from "@/lib/types";

export const CONTENT_APPLIES_TO = [
  { value: "INPUT", label: "Input" },
  { value: "OUTPUT", label: "Output" },
  { value: "BOTH", label: "Both" },
] as const;

export { RULE_CATEGORIES, RULE_SEVERITIES };

export interface ContentRuleFormState {
  title: string;
  content: string;
  effect: string;
  enabled: boolean;
  required_approver_role: string;
  applies_to: string;
  category: string;
  severity: string;
  source_policy_id: string;
}

export const EMPTY_CONTENT_RULE_FORM: ContentRuleFormState = {
  title: "",
  content: "",
  effect: "MONITOR",
  enabled: true,
  required_approver_role: "business_approver",
  applies_to: "BOTH",
  category: "COMPLIANCE",
  severity: "MEDIUM",
  source_policy_id: "",
};

export function contentRuleFormFromSummary(rule: ContentRuleSummary): ContentRuleFormState {
  return {
    title: rule.title,
    content: rule.content,
    effect: rule.effect,
    enabled: rule.enabled,
    required_approver_role: rule.required_approver_role ?? "business_approver",
    applies_to: rule.applies_to ?? "BOTH",
    category: rule.category ?? "",
    severity: rule.severity ?? "MEDIUM",
    source_policy_id: "",
  };
}

interface ContentRuleFormProps {
  value: ContentRuleFormState;
  onChange: (value: ContentRuleFormState) => void;
  policySources?: PolicySourceSummary[];
}

export function ContentRuleForm({ value, onChange, policySources = [] }: ContentRuleFormProps) {
  return (
    <div className="grid gap-4">
      <FormField label="Title" required>
        <Input
          value={value.title}
          onChange={(e) => onChange({ ...value, title: e.target.value })}
          placeholder="Do not expose confidential supplier data"
        />
      </FormField>

      <FormField label="Rule / Instruction" required>
        <Textarea
          rows={4}
          value={value.content}
          onChange={(e) => onChange({ ...value, content: e.target.value })}
          placeholder="The agent must not disclose supplier banking information..."
        />
      </FormField>

      <div className="grid gap-4 md:grid-cols-3">
        <FormField label="Applies to" required>
          <Select
            value={value.applies_to}
            onChange={(e) => onChange({ ...value, applies_to: e.target.value })}
          >
            {CONTENT_APPLIES_TO.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
        </FormField>

        <FormField label="Category">
          <Select
            value={value.category}
            onChange={(e) => onChange({ ...value, category: e.target.value })}
          >
            <option value="">Select category</option>
            {RULE_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
        </FormField>

        <FormField label="Severity">
          <Select
            value={value.severity}
            onChange={(e) => onChange({ ...value, severity: e.target.value })}
          >
            {RULE_SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </FormField>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <FormField label="Effect" required>
          <Select
            value={value.effect}
            onChange={(e) => onChange({ ...value, effect: e.target.value })}
          >
            {POLICY_EFFECT_OPTIONS.filter((o) => o.value !== "ALLOW").map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
        </FormField>

        {value.effect === "REQUIRE_APPROVAL" && (
          <FormField label="Approver role" required>
            <Select
              value={value.required_approver_role}
              onChange={(e) => onChange({ ...value, required_approver_role: e.target.value })}
            >
              {APPROVER_ROLES.map((role) => (
                <option key={role.value} value={role.value}>
                  {role.label}
                </option>
              ))}
            </Select>
          </FormField>
        )}
      </div>

      {policySources.length > 0 && (
        <FormField label="Source policy (optional)">
          <Select
            value={value.source_policy_id}
            onChange={(e) => onChange({ ...value, source_policy_id: e.target.value })}
          >
            <option value="">None</option>
            {policySources.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </Select>
        </FormField>
      )}

      <label className="flex items-center gap-2 text-sm text-ink-700">
        <input
          type="checkbox"
          checked={value.enabled}
          onChange={(e) => onChange({ ...value, enabled: e.target.checked })}
        />
        Enabled (Active)
      </label>

      <p className="text-xs text-ink-500">
        Content rules define semantic governance. The Content Evaluator detects violations; RAI maps
        them to the configured effect — the evaluator never chooses enforcement.
      </p>
    </div>
  );
}
