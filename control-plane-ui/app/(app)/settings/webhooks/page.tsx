"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { SectionHeader } from "@/components/section-header";
import { FormField } from "@/components/registry/form-field";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  createWebhookEndpoint,
  listWebhookDeliveries,
  listWebhookEndpoints,
  rotateWebhookEndpoint,
} from "@/lib/api";
import type { WebhookDeliverySummary, WebhookEndpointSummary } from "@/lib/types";

const DEFAULT_EVENTS = [
  "approval.requested",
  "approval.approved",
  "approval.rejected",
  "approval.cancelled",
  "approval.expired",
  "approval.consumed",
];

export default function WebhookSettingsPage() {
  const [endpoints, setEndpoints] = useState<WebhookEndpointSummary[]>([]);
  const [deliveries, setDeliveries] = useState<WebhookDeliverySummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [secretOnce, setSecretOnce] = useState<string | null>(null);
  const [name, setName] = useState("Approval notifications");
  const [url, setUrl] = useState("https://");
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    setError(null);
    Promise.all([listWebhookEndpoints(), listWebhookDeliveries(40)])
      .then(([ep, del]) => {
        setEndpoints(ep.data.items ?? []);
        setDeliveries(del.data.items ?? []);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async () => {
    setSaving(true);
    setError(null);
    setSecretOnce(null);
    try {
      const res = await createWebhookEndpoint({
        name,
        url,
        event_types: DEFAULT_EVENTS,
      });
      setSecretOnce(res.data.secret);
      setUrl("https://");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create webhook");
    } finally {
      setSaving(false);
    }
  };

  const handleRotate = async (id: string) => {
    setSaving(true);
    setError(null);
    try {
      const res = await rotateWebhookEndpoint(id);
      setSecretOnce(res.data.secret);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to rotate secret");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Webhook endpoints"
        subtitle="Receive signed approval lifecycle notifications. Webhooks are notifications only — agents must retry through VigilRAI to resume."
        actions={
          <Link href="/settings" className="text-sm text-primary hover:underline">
            Back to settings
          </Link>
        }
      />

      {error ? (
        <Panel title="Error">
          <p className="text-sm text-destructive">{error}</p>
        </Panel>
      ) : null}

      {secretOnce ? (
        <Panel title="Signing secret (shown once)">
          <p className="mb-2 text-sm text-muted-foreground">
            Store this secret now. It is used to verify <code>X-RAI-Signature</code> headers.
          </p>
          <code className="block break-all rounded bg-base-100 p-3 text-xs">{secretOnce}</code>
        </Panel>
      ) : null}

      <Panel title="Create endpoint">
        <div className="grid gap-4 md:grid-cols-2">
          <FormField label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField label="HTTPS URL">
            <Input value={url} onChange={(e) => setUrl(e.target.value)} />
          </FormField>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Subscribes to: {DEFAULT_EVENTS.join(", ")}
        </p>
        <div className="mt-4">
          <Button onClick={() => void handleCreate()} disabled={saving}>
            {saving ? "Saving…" : "Create webhook"}
          </Button>
        </div>
      </Panel>

      <Panel title="Endpoints">
        {endpoints.length === 0 ? (
          <p className="text-sm text-muted-foreground">No webhook endpoints yet.</p>
        ) : (
          <ul className="divide-y divide-base-200">
            {endpoints.map((ep) => (
              <li key={ep.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div>
                  <div className="font-medium">{ep.name}</div>
                  <div className="text-xs text-muted-foreground">{ep.url}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    secret {ep.secret_prefix}… · {(ep.event_types || []).join(", ")}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={ep.status} />
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={saving}
                    onClick={() => void handleRotate(ep.id)}
                  >
                    Rotate secret
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="Recent deliveries">
        {deliveries.length === 0 ? (
          <p className="text-sm text-muted-foreground">No deliveries yet.</p>
        ) : (
          <ul className="divide-y divide-base-200 text-sm">
            {deliveries.map((d) => (
              <li key={d.id} className="flex flex-wrap justify-between gap-2 py-2">
                <span>
                  {d.event_type} · {d.event_id.slice(0, 8)}…
                </span>
                <span className="flex items-center gap-2">
                  <StatusBadge status={d.status} />
                  <span className="text-xs text-muted-foreground">
                    attempts {d.attempt_count}
                    {d.last_error ? ` · ${d.last_error}` : ""}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
