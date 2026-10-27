"use client";

import { useMemo } from "react";
import { FormField } from "@/components/registry/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type {
  MCPServerSummary,
  PolicySourceSummary,
  ToolResourceSummary,
  ToolRuleConditionSummary,
  ToolRuleSummary,
} from "@/lib/types";

export const RULE_CATEGORIES = [
  "PRIVACY",
  "SECURITY",
  "COMPLIANCE",
  "FINANCIAL",
  "SAFETY",
  "FRAUD",
  "REPUTATIONAL",
  "OPERATIONAL",
  "CUSTOM",
] as const;

export const RULE_SEVERITIES = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;

export const POLICY_EFFECT_OPTIONS = [
  { value: "ALLOW", label: "Allow" },
  { value: "MONITOR", label: "Allow + Monitor" },
  { value: "REQUIRE_APPROVAL", label: "Require Human Approval" },
  { value: "DENY", label: "Block" },
] as const;

export const OPERATORS_BY_VALUE_TYPE: Record<string, Array<{ value: string; label: string }>> = {
  string: [
    { value: "eq", label: "equals" },
    { value: "neq", label: "not equals" },
    { value: "contains", label: "contains" },
    { value: "not_contains", label: "not contains" },
    { value: "regex", label: "matches regex" },
    { value: "in", label: "in" },
    { value: "not_in", label: "not in" },
    { value: "exists", label: "exists" },
    { value: "not_exists", label: "not exists" },
  ],
  number: [
    { value: "eq", label: "=" },
    { value: "neq", label: "≠" },
    { value: "gt", label: ">" },
    { value: "gte", label: ">=" },
    { value: "lt", label: "<" },
    { value: "lte", label: "<=" },
    { value: "exists", label: "exists" },
    { value: "not_exists", label: "not exists" },
  ],
  boolean: [
    { value: "eq", label: "equals" },
    { value: "neq", label: "not equals" },
    { value: "exists", label: "exists" },
    { value: "not_exists", label: "not exists" },
  ],
  array: [
    { value: "contains", label: "contains" },
    { value: "not_contains", label: "not contains" },
    { value: "in", label: "in" },
    { value: "not_in", label: "not in" },
    { value: "exists", label: "exists" },
    { value: "not_exists", label: "not exists" },
  ],
  null: [
    { value: "exists", label: "exists" },
    { value: "not_exists", label: "not exists" },
  ],
};

export const APPROVER_ROLES = [
  { value: "business_approver", label: "Business Approver" },
  { value: "rai_officer", label: "RAI Officer" },
  { value: "admin", label: "Admin" },
];

export interface ToolRuleFormState {
  title: string;
  description: string;
  mcp_server_id: string;
  tool_id: string;
  match_mode: "ALL" | "ANY";
  effect: string;
  enabled: boolean;
  required_approver_role: string;
  severity: string;
  category: string;
  source_policy_id: string;
  conditions: ToolRuleConditionSummary[];
}

export const EMPTY_TOOL_RULE_FORM: ToolRuleFormState = {
  title: "",
  description: "",
  mcp_server_id: "",
  tool_id: "",
  match_mode: "ALL",
  effect: "REQUIRE_APPROVAL",
  enabled: true,
  required_approver_role: "business_approver",
  severity: "MEDIUM",
  category: "OPERATIONAL",
  source_policy_id: "",
  conditions: [],
};

export function toolRuleFormFromSummary(rule: ToolRuleSummary): ToolRuleFormState {
  return {
    title: rule.title,
    description: rule.description ?? "",
    mcp_server_id: rule.mcp_server_id ?? "",
    tool_id: rule.tool_id,
    match_mode: rule.match_mode,
    effect: rule.effect,
    enabled: rule.enabled,
    required_approver_role: rule.required_approver_role ?? "business_approver",
    severity: rule.severity ?? "MEDIUM",
    category: rule.category ?? "",
    source_policy_id: "",
    conditions: rule.conditions.map((c) => ({
      parameter_path: c.parameter_path,
      operator: c.operator,
      value_type: c.value_type,
      value: c.value,
    })),
  };
}

export function toolsForMcp(
  mcpServerId: string,
  mcps: MCPServerSummary[],
  tools: ToolResourceSummary[],
): ToolResourceSummary[] {
  if (!mcpServerId) {
    return tools.filter((t) => !t.mcp_server_id);
  }
  const mcp = mcps.find((m) => m.id === mcpServerId);
  if (mcp?.tools?.length) {
    return mcp.tools.map((t) => ({
      id: t.id,
      tool_key: t.tool_key,
      name: t.name,
      consequential_action: t.consequential_action ?? false,
      status: t.status ?? "ACTIVE",
      mcp_server_id: mcpServerId,
      mcp_server_key: mcp.server_key,
    }));
  }
  return tools.filter((t) => t.mcp_server_id === mcpServerId);
}

interface ToolRuleFormProps {
  value: ToolRuleFormState;
  onChange: (value: ToolRuleFormState) => void;
  mcps: MCPServerSummary[];
  tools: ToolResourceSummary[];
  policySources?: PolicySourceSummary[];
}

function parseConditionValue(valueType: string, raw: string): unknown {
  if (valueType === "number") {
    const num = Number(raw);
    return Number.isNaN(num) ? raw : num;
  }
  if (valueType === "boolean") {
    return raw === "true";
  }
  if (valueType === "array") {
    try {
      return JSON.parse(raw);
    } catch {
      return raw
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    }
  }
  if (valueType === "null") {
    return null;
  }
  return raw;
}

export function ToolRuleForm({
  value,
  onChange,
  mcps,
  tools,
  policySources = [],
}: ToolRuleFormProps) {
  const availableTools = useMemo(
    () => toolsForMcp(value.mcp_server_id, mcps, tools),
    [value.mcp_server_id, mcps, tools],
  );

  const updateCondition = (index: number, patch: Partial<ToolRuleConditionSummary>) => {
    const next = value.conditions.map((c, i) => (i === index ? { ...c, ...patch } : c));
    onChange({ ...value, conditions: next });
  };

  const addCondition = () => {
    onChange({
      ...value,
      conditions: [
        ...value.conditions,
        { parameter_path: "", operator: "eq", value_type: "string", value: "" },
      ],
    });
  };

  const removeCondition = (index: number) => {
    onChange({
      ...value,
      conditions: value.conditions.filter((_, i) => i !== index),
    });
  };

  return (
    <div className="grid gap-4">
      <FormField label="Title" required>
        <Input
          value={value.title}
          onChange={(e) => onChange({ ...value, title: e.target.value })}
          placeholder="High Value Purchase Order"
        />
      </FormField>

      <FormField label="Description">
        <Textarea
          rows={2}
          value={value.description}
          onChange={(e) => onChange({ ...value, description: e.target.value })}
        />
      </FormField>

      <div className="grid gap-4 md:grid-cols-2">
        <FormField label="MCP">
          <Select
            value={value.mcp_server_id}
            onChange={(e) => onChange({ ...value, mcp_server_id: e.target.value, tool_id: "" })}
          >
            <option value="">Standalone tool (no MCP)</option>
            {mcps.map((mcp) => (
              <option key={mcp.id} value={mcp.id}>
                {mcp.name}
              </option>
            ))}
          </Select>
        </FormField>

        <FormField label="Tool" required>
          <Select
            value={value.tool_id}
            onChange={(e) => onChange({ ...value, tool_id: e.target.value })}
          >
            <option value="">Select tool...</option>
            {availableTools.map((tool) => (
              <option key={tool.id} value={tool.id}>
                {tool.name} ({tool.tool_key})
              </option>
            ))}
          </Select>
        </FormField>
      </div>

      <FormField label="Match mode">
        <Select
          value={value.match_mode}
          onChange={(e) => onChange({ ...value, match_mode: e.target.value as "ALL" | "ANY" })}
        >
          <option value="ALL">ALL conditions must match</option>
          <option value="ANY">ANY condition may match</option>
        </Select>
      </FormField>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-ink-700">Conditions</span>
          <Button type="button" variant="secondary" size="sm" onClick={addCondition}>
            + Add condition
          </Button>
        </div>

        {value.conditions.length === 0 ? (
          <p className="text-xs text-ink-500">
            No conditions — rule applies to all invocations of the selected tool.
          </p>
        ) : (
          <div className="space-y-2">
            {value.conditions.map((cond, index) => {
              const operators =
                OPERATORS_BY_VALUE_TYPE[cond.value_type] ?? OPERATORS_BY_VALUE_TYPE.string;
              const isPresence = cond.operator === "exists" || cond.operator === "not_exists";
              return (
                <div
                  key={index}
                  className="grid gap-2 rounded-lg border border-base-200 p-3 md:grid-cols-12"
                >
                  <div className="md:col-span-3">
                    <Input
                      placeholder="parameter path"
                      value={cond.parameter_path}
                      onChange={(e) => updateCondition(index, { parameter_path: e.target.value })}
                    />
                  </div>
                  <div className="md:col-span-2">
                    <Select
                      value={cond.value_type}
                      onChange={(e) =>
                        updateCondition(index, {
                          value_type: e.target.value,
                          operator: OPERATORS_BY_VALUE_TYPE[e.target.value]?.[0]?.value ?? "eq",
                        })
                      }
                    >
                      <option value="string">string</option>
                      <option value="number">number</option>
                      <option value="boolean">boolean</option>
                      <option value="array">array</option>
                      <option value="null">null</option>
                    </Select>
                  </div>
                  <div className="md:col-span-2">
                    <Select
                      value={cond.operator}
                      onChange={(e) => updateCondition(index, { operator: e.target.value })}
                    >
                      {operators.map((op) => (
                        <option key={op.value} value={op.value}>
                          {op.label}
                        </option>
                      ))}
                    </Select>
                  </div>
                  <div className="md:col-span-4">
                    {!isPresence && (
                      <Input
                        placeholder="value"
                        value={
                          cond.value === undefined || cond.value === null
                            ? ""
                            : typeof cond.value === "object"
                              ? JSON.stringify(cond.value)
                              : String(cond.value)
                        }
                        onChange={(e) =>
                          updateCondition(index, {
                            value: parseConditionValue(cond.value_type, e.target.value),
                          })
                        }
                      />
                    )}
                  </div>
                  <div className="md:col-span-1 flex items-center justify-end">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => removeCondition(index)}
                    >
                      ✕
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <FormField label="Effect" required>
          <Select
            value={value.effect}
            onChange={(e) => onChange({ ...value, effect: e.target.value })}
          >
            {POLICY_EFFECT_OPTIONS.map((opt) => (
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

      <div className="grid gap-4 md:grid-cols-2">
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
        Enabled
      </label>
    </div>
  );
}
