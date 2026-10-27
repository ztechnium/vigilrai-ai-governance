"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { Plus } from "lucide-react";
import { FormField } from "@/components/registry/form-field";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { SideDrawer } from "@/components/ui/side-drawer";
import { Table } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { createPolicySource, getPolicyLibrary } from "@/lib/api";
import type { PolicySourceSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 50;
const SOURCE_TYPES = [
  { value: "", label: "All sources" },
  { value: "FILE", label: "File" },
  { value: "URL", label: "Website" },
  { value: "MANUAL_TEXT", label: "Manual text" },
];

type CreateMode = "FILE" | "URL" | "MANUAL_TEXT";

const CREATE_MODES: { value: CreateMode; label: string; hint: string }[] = [
  { value: "FILE", label: "Upload file", hint: "Reference a stored policy document" },
  { value: "URL", label: "Website", hint: "Link an external policy page" },
  { value: "MANUAL_TEXT", label: "Manual text", hint: "Paste policy requirements directly" },
];

const EMPTY_FORM = {
  title: "",
  authority: "",
  jurisdiction: "",
  policy_type: "",
  version: "",
  effective_date: "",
  source_uri: "",
  content_text: "",
  content_ref: "",
};

export default function PolicyLibraryPage() {
  const [items, setItems] = useState<PolicySourceSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [status, setStatus] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [createMode, setCreateMode] = useState<CreateMode>("MANUAL_TEXT");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);

  const load = useCallback(
    async (pageOffset = 0, append = false) => {
      setLoading(true);
      setError(null);
      try {
        const res = await getPolicyLibrary({
          search: search.trim() || undefined,
          source_type: sourceType || undefined,
          jurisdiction: jurisdiction.trim() || undefined,
          status: status || undefined,
          limit: PAGE_SIZE,
          offset: pageOffset,
        });
        const rows = res.data.items ?? [];
        setItems((prev) => (append ? [...prev, ...rows] : rows));
        setTotal(res.data.total ?? 0);
        setOffset(pageOffset);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load policy library");
      } finally {
        setLoading(false);
      }
    },
    [search, sourceType, jurisdiction, status],
  );

  useEffect(() => {
    void load(0, false);
  }, [load]);

  const openCreate = (mode: CreateMode = "MANUAL_TEXT") => {
    setCreateMode(mode);
    setSaveError(null);
    setForm(EMPTY_FORM);
    setCreateOpen(true);
  };

  const closeCreate = () => {
    if (saving) return;
    setCreateOpen(false);
    setSaveError(null);
    setForm(EMPTY_FORM);
  };

  const handleCreate = async () => {
    if (!form.title.trim()) return;
    if (createMode === "URL" && !form.source_uri.trim()) return;
    if (createMode === "FILE" && !form.content_ref.trim()) return;
    if (createMode === "MANUAL_TEXT" && !form.content_text.trim()) return;

    setSaving(true);
    setSaveError(null);
    try {
      await createPolicySource({
        title: form.title,
        source_type: createMode,
        authority: form.authority || undefined,
        jurisdiction: form.jurisdiction || undefined,
        policy_type: form.policy_type || undefined,
        version: form.version || undefined,
        effective_date: form.effective_date || undefined,
        source_uri: createMode === "URL" ? form.source_uri : undefined,
        content_text: createMode === "MANUAL_TEXT" ? form.content_text : undefined,
        content_ref: createMode === "FILE" ? form.content_ref || form.title : undefined,
      });
      setCreateOpen(false);
      setForm(EMPTY_FORM);
      setSaveError(null);
      await load(0, false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to create policy source");
    } finally {
      setSaving(false);
    }
  };

  const hasMore = offset + items.length < total;
  const canSave =
    !!form.title.trim() &&
    (createMode !== "URL" || !!form.source_uri.trim()) &&
    (createMode !== "FILE" || !!form.content_ref.trim()) &&
    (createMode !== "MANUAL_TEXT" || !!form.content_text.trim());

  return (
    <div className="space-y-6" data-testid="policy-library-page">
      <SectionHeader
        title="Policy Library"
        subtitle="Source policies, regulations, and internal requirements — not runtime executable rules."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => void load(0, false)}>
              Refresh
            </Button>
            <Button onClick={() => openCreate("MANUAL_TEXT")}>
              <Plus className="size-4" aria-hidden />
              Create Policy
            </Button>
          </div>
        }
      />

      <Panel>
        <div className="flex flex-wrap gap-3">
          <Input
            placeholder="Search policies…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-xs"
          />
          <Select
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value)}
            className="w-40"
          >
            {SOURCE_TYPES.map((opt) => (
              <option key={opt.value || "all"} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
          <Input
            placeholder="Jurisdiction"
            value={jurisdiction}
            onChange={(e) => setJurisdiction(e.target.value)}
            className="w-36"
          />
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-36">
            <option value="">All statuses</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="ARCHIVED">ARCHIVED</option>
          </Select>
          <Button onClick={() => void load(0, false)}>Apply</Button>
        </div>
      </Panel>

      <SideDrawer
        open={createOpen}
        onClose={closeCreate}
        title="Create Policy"
        description="Add a source policy without activating runtime rules. Derived rules start as drafts."
        width="lg"
        data-testid="create-policy-drawer"
        footer={
          <>
            <Button variant="secondary" disabled={saving} onClick={closeCreate}>
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={saving || !canSave}
              onClick={() => void handleCreate()}
            >
              {saving ? "Saving…" : "Create Policy"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase text-ink-400">Source type</p>
            <div className="grid gap-2 sm:grid-cols-3">
              {CREATE_MODES.map((mode) => (
                <button
                  key={mode.value}
                  type="button"
                  disabled={saving}
                  onClick={() => setCreateMode(mode.value)}
                  className={cn(
                    "rounded-md border px-3 py-2.5 text-left transition-colors",
                    createMode === mode.value
                      ? "border-accent-600 bg-accent-50 text-ink-900"
                      : "border-base-200 bg-base-50 text-ink-500 hover:border-base-300 hover:text-ink-900",
                  )}
                >
                  <span className="block text-sm font-semibold">{mode.label}</span>
                  <span className="mt-0.5 block text-[11px] opacity-80">{mode.hint}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Title" required>
              <Input
                autoFocus
                value={form.title}
                disabled={saving}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </FormField>
            <FormField label="Authority / Owner">
              <Input
                value={form.authority}
                disabled={saving}
                onChange={(e) => setForm({ ...form, authority: e.target.value })}
              />
            </FormField>
            <FormField label="Jurisdiction">
              <Input
                value={form.jurisdiction}
                disabled={saving}
                onChange={(e) => setForm({ ...form, jurisdiction: e.target.value })}
              />
            </FormField>
            <FormField label="Policy type">
              <Input
                value={form.policy_type}
                disabled={saving}
                onChange={(e) => setForm({ ...form, policy_type: e.target.value })}
              />
            </FormField>
            <FormField label="Version">
              <Input
                value={form.version}
                disabled={saving}
                onChange={(e) => setForm({ ...form, version: e.target.value })}
              />
            </FormField>
            <FormField label="Effective date">
              <Input
                type="date"
                value={form.effective_date}
                disabled={saving}
                onChange={(e) => setForm({ ...form, effective_date: e.target.value })}
              />
            </FormField>
          </div>

          {createMode === "URL" && (
            <FormField label="Website URL" required>
              <Input
                value={form.source_uri}
                disabled={saving}
                onChange={(e) => setForm({ ...form, source_uri: e.target.value })}
                placeholder="https://company.example/policies/privacy"
                className="font-mono text-xs"
              />
            </FormField>
          )}
          {createMode === "FILE" && (
            <FormField label="Content reference / path" required>
              <Input
                value={form.content_ref}
                disabled={saving}
                onChange={(e) => setForm({ ...form, content_ref: e.target.value })}
                placeholder="s3://bucket/policies/info-sec-v3.pdf"
                className="font-mono text-xs"
              />
            </FormField>
          )}
          {createMode === "MANUAL_TEXT" && (
            <FormField label="Policy requirement" required>
              <Textarea
                rows={8}
                value={form.content_text}
                disabled={saving}
                onChange={(e) => setForm({ ...form, content_text: e.target.value })}
              />
            </FormField>
          )}

          <p className="text-[11px] text-ink-400">
            Uploading a source never auto-activates RAI Rules. Derived rules must start as drafts
            and require human review.
          </p>
          {saveError ? <p className="text-sm text-danger-600">{saveError}</p> : null}
        </div>
      </SideDrawer>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading && items.length === 0 ? (
        <p className="text-sm text-muted-foreground">Loading policy library…</p>
      ) : items.length === 0 ? (
        <Panel>
          <p className="text-sm text-muted-foreground">
            No policy sources yet. Create a file, website, or manual text source to get started.
          </p>
        </Panel>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            Showing {items.length} of {total} sources
          </p>
          <Table
            columns={[
              "Title",
              "Source Type",
              "Authority",
              "Jurisdiction",
              "Version",
              "Effective Date",
              "Obligations",
              "Derived Rules",
              "Status",
              "Updated",
            ]}
            rows={items.map((item) => {
              const cells: ReactNode[] = [
                <span key={item.id} className="inline-flex items-center gap-2">
                  <Link
                    href={`/governance/policies/${item.id}`}
                    className="font-medium text-accent-600 hover:text-accent-700"
                  >
                    {item.title}
                  </Link>
                  {item.scope === "PLATFORM" ? <StatusBadge status="STANDARD" /> : null}
                </span>,
                item.source_type,
                item.authority ?? "—",
                item.jurisdiction ?? "—",
                item.version ?? "—",
                item.effective_date ? new Date(item.effective_date).toLocaleDateString() : "—",
                item.obligation_count ?? 0,
                item.derived_rule_count ?? 0,
                <StatusBadge key={`${item.id}-status`} status={item.status} />,
                item.updated_at ? new Date(item.updated_at).toLocaleString() : "—",
              ];
              return cells;
            })}
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
    </div>
  );
}
