"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import {
  disconnectClientIntegration,
  getClientIntegrations,
  setupClientIntegration,
  testClientIntegration,
} from "@/lib/api";
import type { ClientIntegrationSetup, ClientIntegrationSummary } from "@/lib/types";

const CLIENT_LABELS: Record<string, string> = {
  cursor: "Cursor",
  claude_code: "Claude Code",
  gemini_cli: "Gemini CLI",
};

function formatCoverageLabel(key: string) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function CoverageGrid({ coverage }: { coverage?: Record<string, string> }) {
  if (!coverage) return <p className="text-sm text-muted-foreground">No coverage declared</p>;
  // Prefer capability-level keys; hide duplicate legacy keys when new ones exist.
  const legacy = new Set([
    "mcp_tools",
    "shell",
    "output",
    "tools",
    "post_execution",
    "cloud_agents",
  ]);
  const hasCapabilityKeys = Object.keys(coverage).some((k) => !legacy.has(k));
  const entries = Object.entries(coverage).filter(([k]) =>
    hasCapabilityKeys ? !legacy.has(k) : true,
  );
  return (
    <dl className="mt-2 grid gap-1 text-xs sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div
          key={key}
          className="flex justify-between gap-2 rounded border border-border px-2 py-1"
        >
          <dt className="text-muted-foreground">{formatCoverageLabel(key)}</dt>
          <dd className="font-medium">{value.replace(/_/g, " ")}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ClientIntegrationsPanel({
  identityId,
  onCredentialNeeded,
}: {
  identityId: string;
  onCredentialNeeded?: () => void;
}) {
  const [integrations, setIntegrations] = useState<ClientIntegrationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [setupConfig, setSetupConfig] = useState<ClientIntegrationSetup | null>(null);
  const [testCredential, setTestCredential] = useState("");
  const [testResult, setTestResult] = useState<string | null>(null);
  const [busyClient, setBusyClient] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getClientIntegrations(identityId);
      setIntegrations(res.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load integrations");
    } finally {
      setLoading(false);
    }
  }, [identityId]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSetup = async (clientType: string) => {
    setBusyClient(clientType);
    try {
      const res = await setupClientIntegration(identityId, clientType);
      setSetupConfig(res.data);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Setup failed");
    } finally {
      setBusyClient(null);
    }
  };

  const handleTest = async (clientType: string) => {
    if (!testCredential.trim()) {
      onCredentialNeeded?.();
      setTestResult("Issue a runtime credential and paste it here to test.");
      return;
    }
    setBusyClient(clientType);
    setTestResult(null);
    try {
      const res = await testClientIntegration(identityId, clientType, testCredential.trim());
      setTestResult(res.data.ok ? "Connection test passed" : (res.data.message ?? "Test failed"));
    } catch (err) {
      setTestResult(err instanceof Error ? err.message : "Test failed");
    } finally {
      setBusyClient(null);
    }
  };

  const handleDisconnect = async (clientType: string) => {
    setBusyClient(clientType);
    try {
      await disconnectClientIntegration(identityId, clientType);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Disconnect failed");
    } finally {
      setBusyClient(null);
    }
  };

  return (
    <Panel title="IDE Client Integrations (Cursor / Claude / Gemini)">
      <p className="mb-4 text-sm text-muted-foreground">
        Connect Cursor, Claude Code, or Gemini CLI hooks to this runtime identity. This is separate
        from SDK integrations used by Node/Python apps. Hooks call WP4 authorize before native tool
        execution. Connected status does not imply complete enforcement — coverage is
        per-capability, and local hooks may be modified by users with sufficient local access.
      </p>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading integrations...</p>
      ) : error ? (
        <p className="text-sm text-destructive">{error}</p>
      ) : (
        <div className="space-y-4">
          {integrations.map((integration) => (
            <div key={integration.client_type} className="rounded-lg border border-border p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-medium">
                    {CLIENT_LABELS[integration.client_type] ?? integration.client_type}
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                    <StatusBadge status={integration.status} />
                    <span>{integration.enforcement_mode}</span>
                    {integration.deployment_control && (
                      <span>{integration.deployment_control}</span>
                    )}
                    {integration.verification_status && (
                      <span>Verify: {integration.verification_status}</span>
                    )}
                  </div>
                  <CoverageGrid coverage={integration.coverage} />
                  {integration.coverage_disclaimer && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      {integration.coverage_disclaimer}
                    </p>
                  )}
                  {integration.last_seen_at && (
                    <p className="text-xs text-muted-foreground">
                      Last seen: {new Date(integration.last_seen_at).toLocaleString()}
                    </p>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busyClient === integration.client_type}
                    onClick={() => void handleSetup(integration.client_type)}
                  >
                    Setup
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busyClient === integration.client_type}
                    onClick={() => void handleTest(integration.client_type)}
                  >
                    Test
                  </Button>
                  {integration.status !== "NOT_CONFIGURED" && (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busyClient === integration.client_type}
                      onClick={() => void handleDisconnect(integration.client_type)}
                    >
                      Disconnect
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ))}

          <FormFieldCredential value={testCredential} onChange={setTestCredential} />
          {testResult && <p className="text-sm">{testResult}</p>}

          {setupConfig && (
            <details className="rounded-md border border-border p-3">
              <summary className="cursor-pointer text-sm font-medium">
                Advanced: Generated hook config
              </summary>
              <pre className="mt-2 overflow-auto text-xs">
                {JSON.stringify(setupConfig, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}
    </Panel>
  );
}

function FormFieldCredential({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Runtime credential for Test Connection
      </span>
      <Input
        type="password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Paste X-RAI-Agent-Key for hook testing"
      />
    </label>
  );
}
