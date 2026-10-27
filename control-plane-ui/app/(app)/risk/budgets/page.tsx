"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye } from "lucide-react";
import { SectionHeader } from "@/components/section-header";
import { Panel } from "@/components/registry/panel";
import { Table } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { FormField } from "@/components/registry/form-field";
import { createRiskBudget, getAISystems, getRiskBudgets, updateRiskBudget } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AISystemSummary, RuntimeBudget } from "@/lib/types";

const WINDOW_PRESETS = ["5m", "15m", "1h", "24h"] as const;

type BudgetFormState = {
  ai_system_id: string;
  scope_type: string;
  name: string;
  metric: string;
  tool_name: string;
  limit_value: string;
  window: string;
  effect_on_exceed: string;
  warning_threshold: string;
  amount_parameter_path: string;
  enabled: boolean;
};

const EMPTY_FORM: BudgetFormState = {
  ai_system_id: "",
  scope_type: "AI_SYSTEM",
  name: "",
  metric: "ACTION_COUNT",
  tool_name: "",
  limit_value: "100",
  window: "1h",
  effect_on_exceed: "DENY",
  warning_threshold: "0.8",
  amount_parameter_path: "amount",
  enabled: true,
};

export default function RiskBudgetsPage() {
  const router = useRouter();
  const [items, setItems] = useState<RuntimeBudget[]>([]);
  const [systems, setSystems] = useState<AISystemSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<BudgetFormState>(EMPTY_FORM);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [budgets, sys] = await Promise.all([getRiskBudgets({ limit: 100 }), getAISystems()]);
      setItems(budgets.data.items ?? []);
      setSystems(Array.isArray(sys.data) ? sys.data : []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load budgets");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function openCreate() {
    setForm(EMPTY_FORM);
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setForm(EMPTY_FORM);
  }

  async function onCreate() {
    if (!form.name.trim()) return;
    if (form.scope_type !== "ORGANIZATION" && !form.ai_system_id) return;
    setSaving(true);
    try {
      const created = await createRiskBudget({
        ai_system_id: form.ai_system_id || undefined,
        scope_type: form.scope_type,
        name: form.name.trim(),
        metric: form.metric,
        tool_name: form.tool_name.trim() || undefined,
        limit_value: Number(form.limit_value),
        window: form.window,
        effect_on_exceed: form.effect_on_exceed,
        warning_threshold: Number(form.warning_threshold),
        amount_parameter_path:
          form.metric === "AMOUNT" ? form.amount_parameter_path.trim() || undefined : undefined,
        enabled: form.enabled,
      });
      closeForm();
      router.push(`/risk/budgets/${created.data.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create budget");
    } finally {
      setSaving(false);
    }
  }

  async function onToggleEnabled(budget: RuntimeBudget) {
    setBusyId(budget.id);
    try {
      await updateRiskBudget(budget.id, { enabled: !budget.enabled });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update budget status");
    } finally {
      setBusyId(null);
    }
  }

  const rows = items.map((b) => [
    <Link
      key={`${b.id}-name`}
      href={`/risk/budgets/${b.id}`}
      className="font-medium text-accent-600 underline"
    >
      {b.name}
    </Link>,
    b.scope_type,
    b.metric,
    b.tool_name || "—",
    b.limit_value,
    `${b.window_seconds}s`,
    <div key={`${b.id}-triggers`} className="text-xs">
      <div className="font-semibold text-ink-900">{b.trigger_count ?? 0}</div>
      <div className="text-muted-foreground">
        {b.warning_count ?? 0} warn · {b.exceeded_count ?? 0} exceed
      </div>
    </div>,
    <button
      key={`${b.id}-enabled`}
      type="button"
      role="switch"
      aria-checked={b.enabled}
      aria-label={b.enabled ? `Deactivate ${b.name}` : `Activate ${b.name}`}
      disabled={busyId === b.id}
      onClick={() => void onToggleEnabled(b)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition disabled:opacity-60",
        b.enabled ? "border-accent-500 bg-accent-600" : "border-base-200 bg-base-200",
      )}
    >
      <span
        className={cn(
          "inline-block size-3.5 rounded-full bg-white transition",
          b.enabled ? "translate-x-4" : "translate-x-0.5",
        )}
      />
    </button>,
    b.effect_on_exceed,
    <Link
      key={`${b.id}-details`}
      href={`/risk/budgets/${b.id}`}
      aria-label={`View details for ${b.name}`}
      className="inline-flex size-7 items-center justify-center rounded-md border border-base-200 text-ink-600 hover:bg-base-700"
    >
      <Eye className="size-4" aria-hidden />
    </Link>,
  ]);

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Spend controls"
        subtitle="Hierarchical limits on action count, tool usage, amounts, tokens, and cost. Parent and child budgets all apply — a child never replaces a parent."
        actions={
          <Button onClick={() => (showForm ? closeForm() : openCreate())}>
            {showForm ? "Cancel" : "Create spend control"}
          </Button>
        }
      />
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {showForm && (
        <Panel title="New spend control">
          <p className="mb-3 text-sm text-ink-600">
            Step through what to control, where it applies (organization → AI system → agent →
            tenant), the limit, and what happens at the limit. Overlapping parent controls still
            apply.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="AI System (optional for org-wide)">
              <Select
                value={form.ai_system_id}
                onChange={(e) => setForm({ ...form, ai_system_id: e.target.value })}
              >
                <option value="">Organization-wide…</option>
                {systems.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField label="Applies to (scope)">
              <Select
                value={form.scope_type || "AI_SYSTEM"}
                onChange={(e) => setForm({ ...form, scope_type: e.target.value })}
              >
                <option value="ORGANIZATION">Organization</option>
                <option value="AI_SYSTEM">AI System</option>
                <option value="AGENT">Agent</option>
                <option value="AGENT_VERSION">Agent version</option>
                <option value="RUNTIME_IDENTITY">Runtime identity</option>
                <option value="DELEGATION">Tenant / Delegation</option>
                <option value="MODEL">Model</option>
                <option value="TOOL">Tool</option>
              </Select>
            </FormField>
            <FormField label="Name">
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </FormField>
            <FormField label="Metric">
              <Select
                value={form.metric}
                onChange={(e) => setForm({ ...form, metric: e.target.value })}
              >
                {["ACTION_COUNT", "TOOL_COUNT", "AMOUNT", "TOKEN_USAGE", "COST"].map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField label="Tool name (optional)">
              <Input
                value={form.tool_name}
                onChange={(e) => setForm({ ...form, tool_name: e.target.value })}
                placeholder="create_order"
              />
            </FormField>
            <FormField label="Limit">
              <Input
                value={form.limit_value}
                onChange={(e) => setForm({ ...form, limit_value: e.target.value })}
              />
            </FormField>
            <FormField label="Window">
              <Select
                value={form.window}
                onChange={(e) => setForm({ ...form, window: e.target.value })}
              >
                {WINDOW_PRESETS.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField label="Effect on exceed">
              <Select
                value={form.effect_on_exceed}
                onChange={(e) => setForm({ ...form, effect_on_exceed: e.target.value })}
              >
                {["MONITOR", "REQUIRE_APPROVAL", "DENY", "SUSPEND_RUNTIME_IDENTITY"].map((e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField label="Active">
              <Select
                value={form.enabled ? "true" : "false"}
                onChange={(e) => setForm({ ...form, enabled: e.target.value === "true" })}
              >
                <option value="true">Active</option>
                <option value="false">Inactive</option>
              </Select>
            </FormField>
            {form.metric === "AMOUNT" && (
              <FormField label="Amount parameter path">
                <Input
                  value={form.amount_parameter_path}
                  onChange={(e) => setForm({ ...form, amount_parameter_path: e.target.value })}
                />
              </FormField>
            )}
          </div>
          <div className="mt-4">
            <Button disabled={saving} onClick={() => void onCreate()}>
              {saving ? "Saving…" : "Save budget"}
            </Button>
          </div>
        </Panel>
      )}
      <Panel title="Active spend controls">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No spend controls yet. Create an organization or AI-system limit to govern cost, tokens,
            or action volume.
          </p>
        ) : (
          <Table
            columns={[
              "Name",
              "Scope",
              "Metric",
              "Resource",
              "Limit",
              "Window",
              "Triggers",
              "Active",
              "Effect",
              "",
            ]}
            rows={rows}
          />
        )}
      </Panel>
    </div>
  );
}
