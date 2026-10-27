"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { SectionHeader } from "@/components/section-header";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { Table } from "@/components/ui/table";
import {
  OrgPortfolioFilter,
  countMapRows,
  formatShortDate,
} from "@/components/portfolio/org-portfolio-filter";
import { getPortfolioDashboard, listOrganizations } from "@/lib/api";
import type { Organization, PortfolioDashboard } from "@/lib/types";

function PortfolioDashboardContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const orgFromQuery = searchParams.get("organization_id") ?? "";

  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [organizationId, setOrganizationId] = useState(orgFromQuery);
  const [data, setData] = useState<PortfolioDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void listOrganizations()
      .then((res) => {
        setOrgs(res.data.items);
        setOrganizationId((current) => current || res.data.items[0]?.id || "");
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load organizations"),
      );
  }, []);

  const setOrg = (id: string) => {
    setOrganizationId(id);
    router.replace(id ? `/portfolio?organization_id=${id}` : "/portfolio");
  };

  const load = useCallback(async () => {
    if (!organizationId) {
      setData(null);
      return;
    }
    setLoading(true);
    try {
      const res = await getPortfolioDashboard(organizationId);
      setData(res.data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load portfolio dashboard");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Portfolio Dashboard"
        subtitle="Organization-wide AI posture, attention queue, and executive drill-down."
      />
      {error && <p className="text-sm text-red-600">{error}</p>}

      <Panel>
        <OrgPortfolioFilter
          orgs={orgs}
          organizationId={organizationId}
          onOrganizationChange={setOrg}
          onRefresh={() => void load()}
          loading={loading}
        />
      </Panel>

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {data && (
        <>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <StatusBadge status={data.freshness} />
            <span className="text-muted-foreground">
              Refreshed {formatShortDate(data.last_refreshed_at)} · {data.period_days}d window
            </span>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {(
              [
                ["AI Systems", data.kpis.ai_systems],
                ["Critical / High Risk", data.kpis.critical_risk],
                ["Invalid Assurance", data.kpis.invalid_assurance],
                ["Critical Incidents", data.kpis.critical_incidents],
                ["Attention", data.kpis.attention],
              ] as const
            ).map(([label, value]) => (
              <Panel key={label}>
                <div className="space-y-1">
                  <p className="text-xs uppercase text-ink-500">{label}</p>
                  <p className="text-2xl font-semibold">{value}</p>
                </div>
              </Panel>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Panel title="Risk by severity">
              <Table
                columns={["Severity", "Count"]}
                rows={countMapRows(data.risk_posture.by_severity)}
              />
            </Panel>
            <Panel title="Assurance by status">
              <Table
                columns={["Status", "Count"]}
                rows={countMapRows(data.assurance_posture.by_status)}
              />
            </Panel>
            <Panel title="Control coverage">
              <Table
                columns={["Status", "Count"]}
                rows={countMapRows(data.control_coverage.by_status)}
              />
            </Panel>
          </div>

          <Panel title="Executive attention queue">
            <Table
              columns={["Severity", "Type", "Title", "Action"]}
              rows={(data.attention.items ?? [])
                .slice(0, 15)
                .map((item, idx) => [
                  <StatusBadge key={`att-sev-${idx}`} status={item.severity} />,
                  item.type,
                  item.title,
                  item.recommended_action,
                ])}
            />
          </Panel>

          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Recent changes">
              <Table
                columns={["When", "Type", "Title"]}
                rows={(data.recent_changes ?? [])
                  .slice(0, 12)
                  .map((c) => [
                    formatShortDate(typeof c.occurred_at === "string" ? c.occurred_at : null),
                    String(c.type ?? "—"),
                    String(c.title ?? "—"),
                  ])}
              />
            </Panel>
            <Panel title="Upcoming expiries">
              <Table
                columns={["Severity", "Type", "Title", "Due"]}
                rows={(data.upcoming_expiries ?? []).map((item, idx) => [
                  <StatusBadge key={`exp-sev-${idx}`} status={item.severity} />,
                  item.type,
                  item.title,
                  formatShortDate(item.due_at),
                ])}
              />
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}

export default function PortfolioPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Loading…</p>}>
      <PortfolioDashboardContent />
    </Suspense>
  );
}
