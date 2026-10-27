"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { FilterToolbar, MetricStrip, PaginationBar } from "@/components/console/page-parts";
import { KpiCard } from "@/components/kpi-card";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Table } from "@/components/ui/table";
import { FormField } from "@/components/registry/form-field";
import { StatusBadge } from "@/components/registry/status-badge";
import { SideDrawer } from "@/components/ui/side-drawer";
import { createAISystem, getAISystems } from "@/lib/api";
import { BUSINESS_UNITS, RISK_TIERS } from "@/lib/registry-constants";
import { slugifyKey } from "@/lib/slugify";
import type { AISystemSummary } from "@/lib/types";

const EMPTY_FORM = {
  system_key: "",
  name: "",
  description: "",
  business_purpose: "",
  business_unit: "",
  owner_id: "",
  risk_tier: "MEDIUM",
};

export default function RegistryPage() {
  const [systems, setSystems] = useState<AISystemSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [lifecycle, setLifecycle] = useState("");
  const [risk, setRisk] = useState("");
  const [unit, setUnit] = useState("");
  const [owner, setOwner] = useState("");
  const [page, setPage] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  const closeCreate = () => {
    setShowCreate(false);
    setForm(EMPTY_FORM);
  };

  const load = (query?: string) => {
    setLoading(true);
    setError(null);
    getAISystems(query)
      .then((response) => setSystems(response.data))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const stats = useMemo(() => {
    return {
      total: systems.length,
      approved: systems.filter((s) => s.status === "APPROVED").length,
      highRisk: systems.filter((s) => s.risk_tier === "HIGH" || s.risk_tier === "CRITICAL").length,
    };
  }, [systems]);

  const optionsFor = (values: Array<string | null | undefined>) =>
    [...new Set(values.filter((value): value is string => Boolean(value)))].sort().map((value) => ({
      value,
      label: value,
    }));

  const filtered = useMemo(
    () =>
      systems.filter(
        (system) =>
          (!lifecycle || system.status === lifecycle) &&
          (!risk || system.risk_tier === risk) &&
          (!unit || system.business_unit === unit) &&
          (!owner || system.owner_id === owner),
      ),
    [systems, lifecycle, risk, unit, owner],
  );

  const pageSize = 10;
  const pageRows = filtered.slice(page * pageSize, page * pageSize + pageSize);

  const handleDisplayNameChange = (name: string) => {
    setForm((prev) => {
      const autoKey = !prev.system_key || prev.system_key === slugifyKey(prev.name);
      return {
        ...prev,
        name,
        system_key: autoKey ? slugifyKey(name) : prev.system_key,
      };
    });
  };

  const handleCreate = async () => {
    if (!form.system_key.trim() || !form.name.trim()) return;
    setSaving(true);
    try {
      await createAISystem({
        system_key: form.system_key.trim(),
        name: form.name.trim(),
        business_purpose: form.business_purpose || undefined,
        business_unit: form.business_unit || undefined,
        owner_id: form.owner_id || undefined,
        risk_tier: form.risk_tier || undefined,
      });
      closeCreate();
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create system");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Build & Govern"
        title="AI Systems"
        subtitle="Register governed AI systems with ownership, business context, and risk classification."
        actions={
          <Button variant="primary" onClick={() => setShowCreate(true)}>
            + New AI System
          </Button>
        }
      />

      <MetricStrip>
        <KpiCard title="Registered Systems" value={String(stats.total)} />
        <KpiCard title="Approved" value={String(stats.approved)} />
        <KpiCard title="High / Critical Risk" value={String(stats.highRisk)} tone="danger" />
      </MetricStrip>

      <SideDrawer
        open={showCreate}
        onClose={closeCreate}
        title="Create AI System"
        description="Business unit and ownership are set at registration time."
        width="lg"
        data-testid="create-ai-system-drawer"
        footer={
          <>
            <Button variant="secondary" disabled={saving} onClick={closeCreate}>
              Cancel
            </Button>
            <Button variant="primary" disabled={saving} onClick={handleCreate}>
              {saving ? "Creating..." : "Create System"}
            </Button>
          </>
        }
      >
        <div className="grid gap-4">
          <FormField label="Display Name" required>
            <Input
              value={form.name}
              onChange={(e) => handleDisplayNameChange(e.target.value)}
              placeholder="Procurement AI"
            />
          </FormField>
          <FormField
            label="System Key"
            required
            hint="Filled from the display name. Edit to override."
          >
            <Input
              value={form.system_key}
              onChange={(e) => setForm({ ...form, system_key: e.target.value })}
              placeholder="procurement-ai"
              className="font-mono"
            />
          </FormField>
          <FormField label="Business Unit">
            <Input
              list="business-units"
              value={form.business_unit}
              onChange={(e) => setForm({ ...form, business_unit: e.target.value })}
              placeholder="Procurement"
            />
            <datalist id="business-units">
              {BUSINESS_UNITS.map((unitOption) => (
                <option key={unitOption} value={unitOption} />
              ))}
            </datalist>
          </FormField>
          <FormField label="Owner ID">
            <Input
              value={form.owner_id}
              onChange={(e) => setForm({ ...form, owner_id: e.target.value })}
              placeholder="team-procurement"
              className="font-mono"
            />
          </FormField>
          <FormField label="Risk Tier">
            <Select
              value={form.risk_tier}
              onChange={(e) => setForm({ ...form, risk_tier: e.target.value })}
            >
              {RISK_TIERS.map((tier) => (
                <option key={tier} value={tier}>
                  {tier}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Business Purpose">
            <Textarea
              rows={4}
              value={form.business_purpose}
              onChange={(e) => setForm({ ...form, business_purpose: e.target.value })}
              placeholder="What business capability does this AI system support?"
            />
          </FormField>
        </div>
      </SideDrawer>

      <div className="overflow-hidden rounded-lg border border-base-200">
        <FilterToolbar
          value={search}
          onChange={setSearch}
          placeholder="Search by name, key, or business unit..."
          filters={[
            {
              label: "Lifecycle",
              value: lifecycle,
              onChange: (value) => {
                setLifecycle(value);
                setPage(0);
              },
              options: optionsFor(systems.map((system) => system.status)),
            },
            {
              label: "Risk",
              value: risk,
              onChange: (value) => {
                setRisk(value);
                setPage(0);
              },
              options: optionsFor([...RISK_TIERS, ...systems.map((system) => system.risk_tier)]),
            },
            {
              label: "Business Unit",
              value: unit,
              onChange: (value) => {
                setUnit(value);
                setPage(0);
              },
              options: optionsFor([
                ...BUSINESS_UNITS,
                ...systems.map((system) => system.business_unit),
              ]),
            },
            {
              label: "Owner",
              value: owner,
              onChange: (value) => {
                setOwner(value);
                setPage(0);
              },
              options: optionsFor(systems.map((system) => system.owner_id)),
            },
          ]}
          action={
            <Button variant="secondary" onClick={() => load(search || undefined)}>
              Search
            </Button>
          }
        />

        {loading ? (
          <div className="rounded-xl border border-base-200 bg-base-50 p-8 text-center text-sm text-ink-500">
            Loading AI systems...
          </div>
        ) : error ? (
          <div className="rounded-xl border border-danger-200 bg-danger-50 p-6 text-sm text-danger-600">
            {error}
          </div>
        ) : (
          <>
            <Table
              columns={["System", "Business Unit", "Owner", "Status", "Risk", "Agents", ""]}
              rows={
                pageRows.length > 0
                  ? pageRows.map((system) => [
                      <div key={`${system.id}-name`}>
                        <p className="font-semibold text-ink-900">{system.name}</p>
                        <p className="text-xs text-ink-400">{system.system_key}</p>
                      </div>,
                      system.business_unit ?? "—",
                      system.owner_id ?? "—",
                      <StatusBadge key={`${system.id}-status`} status={system.status} />,
                      system.risk_tier ? (
                        <StatusBadge key={`${system.id}-risk`} status={system.risk_tier} />
                      ) : (
                        "—"
                      ),
                      String(system.agent_count),
                      <Link
                        key={system.id}
                        className="text-sm font-semibold text-accent-600 hover:text-accent-500"
                        href={`/governance/registry/${system.id}`}
                      >
                        Manage →
                      </Link>,
                    ])
                  : [["No systems yet", "—", "—", "—", "—", "—", "—"]]
              }
            />
            <PaginationBar
              total={filtered.length}
              page={page}
              pageSize={pageSize}
              onPage={setPage}
            />
          </>
        )}
      </div>
    </div>
  );
}
