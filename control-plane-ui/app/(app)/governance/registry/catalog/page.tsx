"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { SideDrawer } from "@/components/ui/side-drawer";
import { Table } from "@/components/ui/table";
import { CatalogUpload } from "@/components/onboarding/catalog-upload";
import { CatalogCreateDrawer } from "@/components/registry/catalog-create-drawer";
import { CatalogUpdateDrawer } from "@/components/registry/catalog-update-drawer";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { getAISystems, getResourceCatalog, seedMCPCatalog } from "@/lib/api";
import type { AISystemSummary, ResourceCatalogItem } from "@/lib/types";

const TYPE_OPTIONS = [
  { value: "", label: "All types" },
  { value: "MODEL", label: "Model" },
  { value: "MCP", label: "MCP Server" },
  { value: "DATA_SOURCE", label: "Data Source" },
  { value: "SERVICE", label: "External Service" },
];

const STATUS_OPTIONS = ["", "ACTIVE", "INACTIVE", "DEPRECATED"];
const PAGE_SIZE = 50;

function typeLabel(t: string) {
  switch (t) {
    case "MODEL":
      return "Model";
    case "MCP":
      return "MCP Server";
    case "DATA_SOURCE":
      return "Data Source";
    case "SERVICE":
      return "Service";
    default:
      return t;
  }
}

function canUpdate(item: ResourceCatalogItem): boolean {
  return item.resource_type === "MCP" || item.resource_type === "MODEL";
}

function UsedByCell({ systems }: { systems: ResourceCatalogItem["used_by_ai_systems"] }) {
  if (!systems.length) return <span className="text-muted-foreground">—</span>;
  const shown = systems.slice(0, 2);
  const rest = systems.length - shown.length;
  return (
    <div className="flex flex-wrap gap-1">
      {shown.map((s) => (
        <Link
          key={s.id}
          href={`/governance/registry/${s.id}`}
          className="text-sm text-accent-600 hover:text-accent-700"
          onClick={(e) => e.stopPropagation()}
        >
          {s.name}
        </Link>
      ))}
      {rest > 0 && (
        <span
          className="text-xs text-muted-foreground"
          title={systems.map((s) => s.name).join(", ")}
        >
          +{rest}
        </span>
      )}
    </div>
  );
}

export default function CatalogPage() {
  const [items, setItems] = useState<ResourceCatalogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [systems, setSystems] = useState<AISystemSummary[]>([]);

  const [search, setSearch] = useState("");
  const [aiSystemId, setAiSystemId] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [status, setStatus] = useState("");
  const [environment, setEnvironment] = useState("");
  const [provider, setProvider] = useState("");

  const [createOpen, setCreateOpen] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [seedMessage, setSeedMessage] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<ResourceCatalogItem | null>(null);
  const [editing, setEditing] = useState<ResourceCatalogItem | null>(null);

  const load = useCallback(
    async (pageOffset = 0, append = false) => {
      setLoading(true);
      setError(null);
      try {
        const res = await getResourceCatalog({
          search: search.trim() || undefined,
          ai_system_id: aiSystemId || undefined,
          resource_type: resourceType || undefined,
          status: status || undefined,
          environment: environment.trim() || undefined,
          provider: provider.trim() || undefined,
          limit: PAGE_SIZE,
          offset: pageOffset,
          sort: "name",
        });
        const rows = res.data.items ?? [];
        setItems((prev) => (append ? [...prev, ...rows] : rows));
        setTotal(res.data.total ?? 0);
        setOffset(pageOffset);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load catalog");
      } finally {
        setLoading(false);
      }
    },
    [search, aiSystemId, resourceType, status, environment, provider],
  );

  useEffect(() => {
    void getAISystems()
      .then((res) => setSystems(res.data ?? []))
      .catch(() => setSystems([]));
  }, []);

  useEffect(() => {
    void load(0, false);
  }, [load]);

  const openUpdate = (item: ResourceCatalogItem) => {
    setDrawer(null);
    setCreateOpen(false);
    setEditing(item);
  };

  const handleSeed = async () => {
    setSeeding(true);
    setSeedMessage(null);
    try {
      const res = await seedMCPCatalog();
      setSeedMessage(
        `Seeded catalog (${res.data.mcps_created ?? 0} MCP servers created, ${res.data.models_created ?? 0} models created)`,
      );
      await load(0, false);
    } catch (err) {
      setSeedMessage(err instanceof Error ? err.message : "Seed failed");
    } finally {
      setSeeding(false);
    }
  };

  const hasMore = offset + items.length < total;

  return (
    <div className="space-y-6" data-testid="resource-catalog-page">
      <SectionHeader
        title="Resource Catalog"
        subtitle="Models, MCPs, data sources, and services available to AI Systems"
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => void load(0, false)}>
              Refresh
            </Button>
            <Button variant="secondary" disabled={seeding} onClick={() => void handleSeed()}>
              {seeding ? "Seeding…" : "Seed MCP catalog"}
            </Button>
            <Button
              onClick={() => {
                setDrawer(null);
                setEditing(null);
                setCreateOpen(true);
              }}
            >
              + Add Resource
            </Button>
          </div>
        }
      />

      {seedMessage && <p className="text-sm text-muted-foreground">{seedMessage}</p>}

      <CatalogUpload downloadLabel="Download example" onImported={() => void load(0, false)} />

      <Panel>
        <div className="flex flex-wrap gap-3">
          <Input
            placeholder="Search resources…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-xs"
          />
          <Select
            value={aiSystemId}
            onChange={(e) => setAiSystemId(e.target.value)}
            className="w-48"
          >
            <option value="">All AI Systems</option>
            {systems.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
          <Select
            value={resourceType}
            onChange={(e) => setResourceType(e.target.value)}
            className="w-44"
          >
            {TYPE_OPTIONS.map((opt) => (
              <option key={opt.value || "all"} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-36">
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt || "all-status"} value={opt}>
                {opt || "All statuses"}
              </option>
            ))}
          </Select>
          <Input
            placeholder="Environment"
            value={environment}
            onChange={(e) => setEnvironment(e.target.value)}
            className="w-36"
          />
          <Input
            placeholder="Provider"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="w-36"
          />
          <Button onClick={() => void load(0, false)}>Apply</Button>
        </div>
      </Panel>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading && items.length === 0 ? (
        <p className="text-sm text-muted-foreground">Loading catalog…</p>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            Showing {items.length} of {total} resources
          </p>
          <Table
            columns={[
              "Name",
              "Key",
              "Type",
              "Used by AI Systems",
              "Details",
              "Environment",
              "Status",
              "Actions",
            ]}
            rows={items.map((item) => {
              const cells: ReactNode[] = [
                item.name,
                item.key,
                typeLabel(item.resource_type),
                <UsedByCell key={`${item.id}-used`} systems={item.used_by_ai_systems} />,
                item.details ?? "—",
                item.environment ?? "—",
                <StatusBadge key={`${item.id}-status`} status={item.status} />,
                canUpdate(item) ? (
                  <button
                    key={`${item.id}-update`}
                    type="button"
                    className="text-sm font-medium text-accent-600 hover:text-accent-700"
                    onClick={() => openUpdate(item)}
                  >
                    Update
                  </button>
                ) : (
                  <button
                    key={`${item.id}-view`}
                    type="button"
                    className="text-sm font-medium text-accent-600 hover:text-accent-700"
                    onClick={() => setDrawer(item)}
                  >
                    View
                  </button>
                ),
              ];
              return cells;
            })}
            onRowClick={(idx) => setDrawer(items[idx] ?? null)}
          />
          {hasMore && (
            <div className="flex justify-center">
              <Button
                variant="secondary"
                disabled={loading}
                onClick={() => void load(offset + PAGE_SIZE, true)}
              >
                {loading ? "Loading…" : "Load more"}
              </Button>
            </div>
          )}
        </>
      )}

      <SideDrawer
        open={drawer != null}
        onClose={() => setDrawer(null)}
        title="Resource details"
        description={drawer ? typeLabel(drawer.resource_type) : undefined}
        width="md"
        data-testid="resource-detail-drawer"
        footer={
          drawer && canUpdate(drawer) ? (
            <Button onClick={() => openUpdate(drawer)}>Update</Button>
          ) : null
        }
      >
        {drawer ? (
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                Name
              </dt>
              <dd className="mt-1 font-medium text-ink-900">{drawer.name}</dd>
            </div>
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                Key
              </dt>
              <dd className="mt-1 text-ink-800">{drawer.key}</dd>
            </div>
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                Provider
              </dt>
              <dd className="mt-1 text-ink-800">{drawer.provider ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                Environment
              </dt>
              <dd className="mt-1 text-ink-800">{drawer.environment ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                Status
              </dt>
              <dd className="mt-1">
                <StatusBadge status={drawer.status} />
              </dd>
            </div>
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                Scope
              </dt>
              <dd className="mt-1 text-ink-800">{drawer.scope}</dd>
            </div>
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                Used by
              </dt>
              <dd className="mt-1 text-ink-800">
                {drawer.used_by_ai_systems.length === 0 ? (
                  "—"
                ) : (
                  <ul className="space-y-1">
                    {drawer.used_by_ai_systems.map((s) => (
                      <li key={s.id}>
                        <Link
                          href={`/governance/registry/${s.id}`}
                          className="text-accent-600 hover:text-accent-700"
                        >
                          {s.name}
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </dd>
            </div>
            {drawer.tool_count != null && (
              <div>
                <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                  Tools
                </dt>
                <dd className="mt-1 text-ink-800">{drawer.tool_count}</dd>
              </div>
            )}
          </dl>
        ) : null}
      </SideDrawer>

      <CatalogCreateDrawer
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => load(0, false)}
      />
      <CatalogUpdateDrawer
        item={editing}
        onClose={() => setEditing(null)}
        onSaved={() => load(0, false)}
      />
    </div>
  );
}
