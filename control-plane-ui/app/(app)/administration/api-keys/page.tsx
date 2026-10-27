"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { SectionHeader } from "@/components/section-header";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table } from "@/components/ui/table";
import { getApiKeys, getSystems, issueApiKey, revokeApiKey } from "@/lib/api";
import type { ApiKeySummary, IssuedApiKey, SystemSummary } from "@/lib/types";

const SCOPE_OPTIONS = ["execute", "admin", "read"] as const;

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeySummary[]>([]);
  const [systems, setSystems] = useState<SystemSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [systemId, setSystemId] = useState("");
  const [customSystemId, setCustomSystemId] = useState("");
  const [scopes, setScopes] = useState<string[]>(["execute"]);
  const [issued, setIssued] = useState<IssuedApiKey | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [keysRes, systemsRes] = await Promise.all([
        getApiKeys(),
        getSystems().catch(() => ({ data: [] as SystemSummary[] })),
      ]);
      setKeys(keysRes.data ?? []);
      setSystems(systemsRes.data ?? []);
      if (!systemId && (systemsRes.data?.length ?? 0) > 0) {
        setSystemId(systemsRes.data[0].system_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load API keys");
    } finally {
      setLoading(false);
    }
  }, [systemId]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial load only
  }, []);

  const resolvedSystemId = (customSystemId.trim() || systemId).trim();

  function toggleScope(scope: string) {
    setScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    );
  }

  async function handleIssue() {
    if (!resolvedSystemId) {
      setError("System ID is required.");
      return;
    }
    if (scopes.length === 0) {
      setError("Select at least one scope.");
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    setIssued(null);
    setCopied(false);
    try {
      const res = await issueApiKey({
        system_id: resolvedSystemId,
        scopes,
      });
      setIssued(res.data);
      setMessage("API key issued. Copy the plaintext key now — it is shown only once.");
      setCustomSystemId("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to issue API key");
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke(apiKeyId: string) {
    if (!window.confirm(`Revoke API key ${apiKeyId}?`)) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await revokeApiKey(apiKeyId);
      setMessage("API key revoked.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revoke API key");
    } finally {
      setBusy(false);
    }
  }

  async function copyIssuedKey() {
    if (!issued?.api_key) return;
    try {
      await navigator.clipboard.writeText(issued.api_key);
      setCopied(true);
    } catch {
      setError("Could not copy to clipboard — select and copy manually.");
    }
  }

  const rows = useMemo(
    () =>
      keys.map((key) => {
        const status =
          key.revoked_at || key.status === "revoked" ? "revoked" : key.status || "active";
        return [
          <span key={`${key.api_key_id}-id`} className="font-mono text-xs">
            {key.api_key_id}
          </span>,
          key.system_id,
          (key.scopes ?? []).join(", ") || "—",
          <StatusBadge key={`${key.api_key_id}-status`} status={status} />,
          key.created_at ? new Date(key.created_at).toLocaleString() : "—",
          status === "active" ? (
            <Button
              key={`${key.api_key_id}-revoke`}
              size="sm"
              variant="danger"
              disabled={busy}
              onClick={() => void handleRevoke(key.api_key_id)}
            >
              Revoke
            </Button>
          ) : (
            "—"
          ),
        ];
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- revoke uses stable handlers
    [keys, busy],
  );

  return (
    <div className="space-y-6">
      <SectionHeader
        title="API Keys"
        subtitle="Issue, list, and revoke access keys for runtime execution."
        actions={<Badge variant="neutral">Administration</Badge>}
      />

      {error && (
        <div className="rounded-xl border border-danger-100 bg-danger-100/40 p-4 text-sm text-danger-600">
          {error}
        </div>
      )}
      {message && (
        <div className="rounded-xl border border-base-200 bg-white p-4 text-sm text-ink-700">
          {message}
        </div>
      )}

      <Panel
        title="Issue new API key"
        description="Plaintext secret is returned once. Store it securely."
      >
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block text-sm">
            Registered system
            <Select
              className="mt-1"
              value={systemId}
              onChange={(e) => setSystemId(e.target.value)}
              disabled={systems.length === 0}
            >
              {systems.length === 0 ? (
                <option value="">No registered systems</option>
              ) : (
                systems.map((s) => (
                  <option key={s.system_id} value={s.system_id}>
                    {s.name} ({s.system_id})
                  </option>
                ))
              )}
            </Select>
          </label>
          <label className="block text-sm">
            Or custom system ID
            <Input
              className="mt-1"
              value={customSystemId}
              onChange={(e) => setCustomSystemId(e.target.value)}
              placeholder="Overrides dropdown when set"
            />
          </label>
        </div>
        <div className="mt-4">
          <p className="mb-2 text-sm">Scopes</p>
          <div className="flex flex-wrap gap-3">
            {SCOPE_OPTIONS.map((scope) => (
              <label key={scope} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={scopes.includes(scope)}
                  onChange={() => toggleScope(scope)}
                />
                {scope}
              </label>
            ))}
          </div>
        </div>
        <div className="mt-4">
          <Button disabled={busy || !resolvedSystemId} onClick={() => void handleIssue()}>
            {busy ? "Issuing…" : "Issue API key"}
          </Button>
        </div>
      </Panel>

      {issued && (
        <Panel title="New key — copy now">
          <p className="mb-3 text-sm text-ink-500">
            {issued.note || "This plaintext key will not be shown again."}
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <code className="block max-w-full flex-1 overflow-x-auto rounded-lg border border-base-200 bg-base-100 px-3 py-2 font-mono text-sm">
              {issued.api_key}
            </code>
            <Button variant="outline" onClick={() => void copyIssuedKey()}>
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            ID: {issued.api_key_id} · System: {issued.system_id} · Scopes:{" "}
            {issued.scopes.join(", ")}
          </p>
        </Panel>
      )}

      <Panel
        title="All API keys"
        actions={
          <Button
            size="sm"
            variant="outline"
            disabled={loading || busy}
            onClick={() => void load()}
          >
            Refresh
          </Button>
        }
      >
        {loading ? (
          <p className="text-sm text-ink-500">Loading API keys…</p>
        ) : keys.length === 0 ? (
          <p className="text-sm text-ink-500">No API keys yet. Issue one above.</p>
        ) : (
          <Table
            columns={["Key ID", "System", "Scopes", "Status", "Created", "Actions"]}
            rows={rows}
          />
        )}
      </Panel>
    </div>
  );
}
