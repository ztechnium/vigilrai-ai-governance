"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { SectionHeader } from "@/components/section-header";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { Table } from "@/components/ui/table";
import { getRiskMonitors } from "@/lib/api";
import type { RiskMonitor } from "@/lib/types";

export default function RiskMonitoringPage() {
  const [items, setItems] = useState<RiskMonitor[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getRiskMonitors({ status: "ACTIVE", limit: 100 });
      setItems(res.data.items ?? []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load monitors");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const rows = useMemo(
    () =>
      items.map((m) => [
        <div key={`${m.id}-scope`}>
          <div className="text-xs text-muted-foreground">{m.scope_type}</div>
          <div className="font-mono text-xs">{m.scope_id.slice(0, 12)}…</div>
        </div>,
        m.reason || "—",
        `${m.current_count} / ${m.current_sum}`,
        m.threshold ?? "—",
        m.started_at ? new Date(m.started_at).toLocaleString() : "—",
        m.expires_at ? new Date(m.expires_at).toLocaleString() : "—",
        <StatusBadge key={`${m.id}-status`} status={m.status} />,
      ]),
    [items],
  );

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Monitoring"
        subtitle="Active MARK_AND_MONITOR and threshold-driven monitoring scopes."
      />
      <Panel title="Active Monitors">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : error ? (
          <p className="text-sm text-red-600">{error}</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No active monitors.</p>
        ) : (
          <Table
            columns={[
              "Scope",
              "Reason",
              "Count / Sum",
              "Threshold",
              "Started",
              "Expires",
              "Status",
            ]}
            rows={rows}
          />
        )}
      </Panel>
    </div>
  );
}
