"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { AgentAvatar } from "@/components/agent-avatar";
import { Breadcrumbs } from "@/components/registry/breadcrumbs";
import { Panel } from "@/components/registry/panel";
import { FormField } from "@/components/registry/form-field";
import { StatusBadge } from "@/components/registry/status-badge";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table } from "@/components/ui/table";
import { Tabs } from "@/components/ui/tabs";
import { getRiskBudget, getRiskBudgetChecks, updateRiskBudget } from "@/lib/api";
import { formatCost, formatTokens, sourceLabel } from "@/lib/finops-format";
import type { RuntimeBudget, RuntimeBudgetCheck } from "@/lib/types";

const TABS = ["Policy", "Logs"] as const;
type Tab = (typeof TABS)[number];

const WINDOW_PRESETS = ["5m", "15m", "1h", "24h"] as const;
const WINDOW_SECONDS: Record<string, number> = {
  "5m": 300,
  "15m": 900,
  "1h": 3600,
  "24h": 86400,
};

function windowFromSeconds(seconds?: number): string {
  if (!seconds) return "1h";
  const match = Object.entries(WINDOW_SECONDS).find(([, value]) => value === seconds);
  return match?.[0] ?? "1h";
}

function shortId(value?: string | null) {
  if (!value) return "—";
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

function IdentityCell({
  name,
  image,
  href,
  fallback = "—",
}: {
  name?: string | null;
  image?: string | null;
  href?: string;
  fallback?: string;
}) {
  const label = name?.trim() || fallback;
  const body = (
    <span className="inline-flex items-center gap-2">
      <AgentAvatar name={label === "—" ? null : label} avatar={image} size={22} placeholder />
      <span>{label}</span>
    </span>
  );
  if (!href) return body;
  return (
    <Link href={href} className="text-accent-600 underline">
      {body}
    </Link>
  );
}

export default function RiskBudgetDetailPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const budgetId = params.budgetId as string;

  const tabParam = searchParams.get("tab");
  const tab: Tab = TABS.includes(tabParam as Tab) ? (tabParam as Tab) : "Policy";

  const [budget, setBudget] = useState<RuntimeBudget | null>(null);
  const [checks, setChecks] = useState<RuntimeBudgetCheck[]>([]);
  const [checksTotal, setChecksTotal] = useState(0);
  const [checksOffset, setChecksOffset] = useState(0);
  const [triggersOnly, setTriggersOnly] = useState(true);
  const [loading, setLoading] = useState(true);
  const [logsLoading, setLogsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    name: "",
    tool_name: "",
    limit_value: "100",
    window: "1h",
    effect_on_exceed: "DENY",
    warning_threshold: "0.8",
    amount_parameter_path: "amount",
    enabled: true,
  });

  const setTab = (next: Tab) => {
    const q = new URLSearchParams(searchParams.toString());
    q.set("tab", next);
    router.replace(`/risk/budgets/${budgetId}?${q.toString()}`);
  };

  const loadBudget = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getRiskBudget(budgetId);
      const b = res.data;
      setBudget(b);
      setForm({
        name: b.name,
        tool_name: b.tool_name ?? "",
        limit_value: String(b.limit_value),
        window: windowFromSeconds(b.window_seconds),
        effect_on_exceed: b.effect_on_exceed,
        warning_threshold: String(b.warning_threshold),
        amount_parameter_path: b.amount_parameter_path ?? "amount",
        enabled: b.enabled,
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load budget");
      setBudget(null);
    } finally {
      setLoading(false);
    }
  }, [budgetId]);

  const loadLogs = useCallback(
    async (offset = 0, append = false) => {
      setLogsLoading(true);
      try {
        const res = await getRiskBudgetChecks(budgetId, {
          triggers_only: triggersOnly,
          limit: 50,
          offset,
        });
        setChecks((prev) => (append ? [...prev, ...res.data.items] : res.data.items));
        setChecksTotal(res.data.total);
        setChecksOffset(offset);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load budget logs");
      } finally {
        setLogsLoading(false);
      }
    },
    [budgetId, triggersOnly],
  );

  useEffect(() => {
    void loadBudget();
  }, [loadBudget]);

  useEffect(() => {
    if (tab === "Logs") {
      void loadLogs(0, false);
    }
  }, [tab, loadLogs]);

  async function onSave() {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      await updateRiskBudget(budgetId, {
        name: form.name.trim(),
        tool_name: form.tool_name.trim(),
        limit_value: Number(form.limit_value),
        window: form.window,
        effect_on_exceed: form.effect_on_exceed,
        warning_threshold: Number(form.warning_threshold),
        amount_parameter_path:
          budget?.metric === "AMOUNT" ? form.amount_parameter_path.trim() || null : null,
        enabled: form.enabled,
      });
      await loadBudget();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update budget");
    } finally {
      setSaving(false);
    }
  }

  async function onToggleEnabled() {
    if (!budget) return;
    setSaving(true);
    try {
      await updateRiskBudget(budgetId, { enabled: !budget.enabled });
      await loadBudget();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update budget status");
    } finally {
      setSaving(false);
    }
  }

  const logRows = checks.map((c) => [
    c.created_at ? new Date(c.created_at).toLocaleString() : "—",
    <IdentityCell
      key={`${c.id}-sys`}
      name={c.ai_system_name}
      fallback={shortId(c.ai_system_id)}
      href={c.ai_system_id ? `/governance/registry/${c.ai_system_id}` : undefined}
    />,
    <IdentityCell
      key={`${c.id}-agent`}
      name={c.agent_name}
      image={c.agent_avatar}
      fallback={shortId(c.agent_id)}
      href={c.agent_id ? `/governance/registry/agents/${c.agent_id}` : undefined}
    />,
    <StatusBadge key={`${c.id}-st`} status={c.status} />,
    c.decision,
    c.effect || "—",
    `${c.usage_before} → ${c.projected_usage} / ${c.limit_value}`,
    formatTokens(c.economics?.total_tokens),
    <span key={`${c.id}-cost`} title={sourceLabel(c.economics?.metering_source)}>
      {formatCost(c.economics?.total_cost, c.economics?.cost_state, c.economics?.currency)}
    </span>,
    c.trajectory_id ? (
      <Link
        key={`${c.id}-traj`}
        href={`/runtime/trajectories/${c.trajectory_id}`}
        className="text-accent-600 underline"
      >
        {shortId(c.trajectory_id)}
      </Link>
    ) : (
      "—"
    ),
    c.runtime_conversation_id || c.conversation_id ? (
      <span key={`${c.id}-ext`} title={c.conversation_id || c.runtime_conversation_id || undefined}>
        {shortId(c.conversation_id || c.runtime_conversation_id)}
      </span>
    ) : (
      "—"
    ),
  ]);

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (!budget) {
    return (
      <div className="space-y-4">
        <Breadcrumbs
          items={[
            { label: "Risk", href: "/risk" },
            { label: "Budgets", href: "/risk/budgets" },
            { label: "Detail" },
          ]}
        />
        <p className="text-sm text-red-600">{error || "Budget not found"}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[
          { label: "Risk", href: "/risk" },
          { label: "Budgets", href: "/risk/budgets" },
          { label: budget.name },
        ]}
      />
      <SectionHeader
        title={budget.name}
        subtitle={`${budget.metric} · ${budget.scope_type}${budget.tool_name ? ` · ${budget.tool_name}` : ""}`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant={budget.enabled ? "secondary" : "primary"}
              disabled={saving}
              onClick={() => void onToggleEnabled()}
            >
              {budget.enabled ? "Deactivate" : "Activate"}
            </Button>
            <Button size="sm" variant="outline" onClick={() => router.push("/risk/budgets")}>
              Back to list
            </Button>
          </div>
        }
      />

      <div className="grid gap-3 sm:grid-cols-4">
        <Panel title="Active">
          <StatusBadge status={budget.enabled ? "ACTIVE" : "INACTIVE"} />
        </Panel>
        <Panel title="Triggers">
          <p className="text-2xl font-semibold text-ink-900">{budget.trigger_count ?? 0}</p>
          <p className="text-xs text-muted-foreground">
            {budget.warning_count ?? 0} warning · {budget.exceeded_count ?? 0} exceeded
          </p>
        </Panel>
        <Panel title="All checks">
          <p className="text-2xl font-semibold text-ink-900">{budget.check_count ?? 0}</p>
          <p className="text-xs text-muted-foreground">Every evaluation against this budget</p>
        </Panel>
        <Panel title="Current window">
          <p className="text-2xl font-semibold text-ink-900">
            {budget.current_usage ?? 0} / {budget.limit_value}
          </p>
          <p className="text-xs text-muted-foreground">
            {budget.utilization_pct ?? 0}% · <StatusBadge status={budget.status || "OK"} />
          </p>
        </Panel>
      </div>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <Tabs tabs={[...TABS]} active={tab} onChange={(t) => setTab(t as Tab)} />

      {tab === "Policy" && (
        <Panel title="Update policy">
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="Name">
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </FormField>
            <FormField label="Metric">
              <Input value={budget.metric} disabled />
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
            <FormField label="Warning threshold">
              <Input
                value={form.warning_threshold}
                onChange={(e) => setForm({ ...form, warning_threshold: e.target.value })}
              />
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
            {budget.metric === "AMOUNT" && (
              <FormField label="Amount parameter path">
                <Input
                  value={form.amount_parameter_path}
                  onChange={(e) => setForm({ ...form, amount_parameter_path: e.target.value })}
                />
              </FormField>
            )}
          </div>
          <div className="mt-4">
            <Button disabled={saving} onClick={() => void onSave()}>
              {saving ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </Panel>
      )}

      {tab === "Logs" && (
        <Panel
          title="Execution log"
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <Select
                value={triggersOnly ? "triggers" : "all"}
                onChange={(e) => setTriggersOnly(e.target.value === "triggers")}
              >
                <option value="triggers">Warnings + exceeded</option>
                <option value="all">All checks</option>
              </Select>
              <Button
                size="sm"
                variant="outline"
                disabled={logsLoading}
                onClick={() => void loadLogs(0, false)}
              >
                Refresh
              </Button>
            </div>
          }
        >
          <p className="mb-3 text-xs text-muted-foreground">
            Showing {checks.length} of {checksTotal} {triggersOnly ? "triggers" : "checks"} for this
            budget.
          </p>
          {logsLoading && checks.length === 0 ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : checks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No evaluations recorded yet.</p>
          ) : (
            <>
              <Table
                columns={[
                  "When",
                  "AI System",
                  "Agent",
                  "Status",
                  "Decision",
                  "Effect",
                  "Usage",
                  "Tokens",
                  "Cost",
                  "Trajectory",
                  "Conversation",
                ]}
                rows={logRows}
              />
              {checks.length < checksTotal ? (
                <div className="mt-3">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={logsLoading}
                    onClick={() => void loadLogs(checksOffset + 50, true)}
                  >
                    {logsLoading ? "Loading…" : "Load more"}
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </Panel>
      )}
    </div>
  );
}
