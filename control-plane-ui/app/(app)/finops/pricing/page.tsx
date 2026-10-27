"use client";

import { useEffect, useMemo, useState } from "react";
import { SectionHeader } from "@/components/section-header";
import { Panel } from "@/components/registry/panel";
import { Table } from "@/components/ui/table";
import { apiGet } from "@/lib/api";

type PricingRow = {
  id: string;
  provider: string;
  model: string;
  input_token_price: number;
  output_token_price: number;
  cached_input_token_price?: number | null;
  pricing_unit?: number | null;
  currency: string;
  effective_from?: string | null;
  effective_to?: string | null;
  enabled: boolean;
};

type CursorPlan = {
  id: string;
  name: string;
  price: number | null;
  currency?: string;
  per?: string;
  audience?: string;
  custom?: boolean;
};

type CursorModel = {
  id: string;
  display_name: string;
  vendor: string;
  pool: string;
  input_token_price: number;
  output_token_price: number;
  cached_input_token_price?: number | null;
  cache_write_token_price?: number | null;
  cursor_token_rate_exempt: boolean;
};

type CursorCatalog = {
  version: string;
  source_url: string;
  pricing_unit: number;
  cursor_token_rate_per_million: number;
  plans: CursorPlan[];
  models: CursorModel[];
};

function formatRate(value: number | null | undefined): string {
  if (value == null) return "—";
  return `$${value}`;
}

function formatPlan(plan: CursorPlan): string {
  if (plan.price == null) return `${plan.name} · custom`;
  const amount = plan.currency === "INR" ? `₹${plan.price}` : `$${plan.price}`;
  const per = plan.per ? `/${plan.per}` : "";
  const audience = plan.audience ? ` (${plan.audience})` : "";
  return `${plan.name} ${amount}${per}/mo${audience}`;
}

export default function FinOpsPricingPage() {
  const [items, setItems] = useState<PricingRow[]>([]);
  const [cursorCatalog, setCursorCatalog] = useState<CursorCatalog | null>(null);
  const [cursorLoading, setCursorLoading] = useState(true);
  const [modelQuery, setModelQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    apiGet<{ items: PricingRow[] }>("/v1/finops/pricing")
      .then((catalog) => {
        if (!active) return;
        setItems(catalog.data.items ?? []);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Unable to load pricing");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    apiGet<CursorCatalog>("/v1/finops/pricing/cursor")
      .then((cursor) => {
        if (!active) return;
        setCursorCatalog(cursor.data);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Unable to load Cursor pricing");
      })
      .finally(() => {
        if (active) setCursorLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const cursorModels = useMemo(() => {
    const models = cursorCatalog?.models ?? [];
    const query = modelQuery.trim().toLowerCase();
    if (!query) return models;
    return models.filter((model) =>
      `${model.display_name} ${model.id} ${model.vendor}`.toLowerCase().includes(query),
    );
  }, [cursorCatalog, modelQuery]);

  return (
    <div className="space-y-6" data-testid="finops-pricing">
      <SectionHeader
        eyebrow="FinOps"
        title="Pricing catalog"
        subtitle="Versioned provider/model prices. New versions affect future metering only — historical spans keep their pricing snapshot."
      />
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Panel title="Cursor published rates">
        {loading || cursorLoading ? (
          <p className="text-sm text-ink-500">Loading…</p>
        ) : cursorCatalog == null ? (
          <p className="text-sm text-ink-500">Cursor rates are unavailable.</p>
        ) : (
          <div className="space-y-4" data-testid="cursor-pricing">
            <p className="text-sm text-ink-500">
              Token rates are USD per {cursorCatalog.pricing_unit.toLocaleString()} tokens, from the{" "}
              <a
                className="underline"
                href={cursorCatalog.source_url}
                target="_blank"
                rel="noreferrer"
              >
                Cursor pricing docs
              </a>{" "}
              ({cursorCatalog.version}). Teams and Enterprise add $
              {cursorCatalog.cursor_token_rate_per_million}/M tokens on third-party models. Grok and
              Composer are exempt. Input tokens here are uncached; pass cache reads and cache writes
              separately.
            </p>
            <p className="text-sm text-ink-700" data-testid="cursor-plans">
              {cursorCatalog.plans.map(formatPlan).join(" · ")}
            </p>
            <input
              className="w-full max-w-sm rounded-md border border-base-300 bg-base-50 px-3 py-2 text-sm"
              placeholder="Filter Cursor models"
              value={modelQuery}
              onChange={(event) => setModelQuery(event.target.value)}
              aria-label="Filter Cursor models"
            />
            <Table
              columns={[
                "Model",
                "Vendor",
                "Pool",
                "Input",
                "Cache write",
                "Cache read",
                "Output",
                "Token rate",
              ]}
              rows={cursorModels.map((model) => [
                model.display_name,
                model.vendor,
                model.pool === "cursor_models" ? "Cursor models" : "Other models",
                formatRate(model.input_token_price),
                formatRate(model.cache_write_token_price),
                formatRate(model.cached_input_token_price),
                formatRate(model.output_token_price),
                model.cursor_token_rate_exempt ? "Exempt" : "Teams / Enterprise",
              ])}
              rowTestIds={cursorModels.map((model) => `cursor-model-${model.id}`)}
            />
          </div>
        )}
      </Panel>
      <Panel title="Active and historical versions">
        {loading ? (
          <p className="text-sm text-ink-500">Loading…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-ink-500">No pricing entries yet.</p>
        ) : (
          <Table
            columns={[
              "Provider",
              "Model",
              "Effective from",
              "Input",
              "Output",
              "Cache",
              "Unit",
              "Currency",
              "Status",
            ]}
            rows={items.map((row) => [
              row.provider,
              row.model,
              row.effective_from ? new Date(row.effective_from).toLocaleDateString() : "—",
              row.input_token_price,
              row.output_token_price,
              row.cached_input_token_price ?? "—",
              (row.pricing_unit ?? 1000).toLocaleString(),
              row.currency,
              row.enabled && !row.effective_to ? "Active" : "Closed",
            ])}
          />
        )}
      </Panel>
    </div>
  );
}
