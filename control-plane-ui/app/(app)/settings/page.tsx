"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { SectionHeader } from "@/components/section-header";
import { FormField } from "@/components/registry/form-field";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  getAISystems,
  getContentEvaluatorConfig,
  testContentEvaluator,
  upsertContentEvaluatorConfig,
} from "@/lib/api";
import { useOrganization } from "@/lib/hooks/use-auth";
import type { AISystemSummary, ContentEvaluatorConfig } from "@/lib/types";

type ProviderId = "mock" | "openai" | "deepseek" | "gemini";

const PROVIDERS: Array<{
  id: ProviderId;
  label: string;
  description: string;
  defaultModel: string;
  modelHint: string;
  needsApiKey: boolean;
}> = [
  {
    id: "mock",
    label: "Mock",
    description: "Local demo / CI. No external API key.",
    defaultModel: "mock-evaluator",
    modelHint: "Fixed mock model for deterministic tests.",
    needsApiKey: false,
  },
  {
    id: "openai",
    label: "OpenAI",
    description: "OpenAI Chat Completions API.",
    defaultModel: "gpt-4o-mini",
    modelHint: "Examples: gpt-4o-mini, gpt-4o, gpt-4.1-mini",
    needsApiKey: true,
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    description: "DeepSeek OpenAI-compatible API.",
    defaultModel: "deepseek-chat",
    modelHint: "Examples: deepseek-chat, deepseek-reasoner",
    needsApiKey: true,
  },
  {
    id: "gemini",
    label: "Gemini",
    description: "Google Gemini generateContent API.",
    defaultModel: "gemini-1.5-flash",
    modelHint: "Examples: gemini-1.5-flash, gemini-1.5-pro, gemini-2.0-flash",
    needsApiKey: true,
  },
];

function providerMeta(id: string) {
  return PROVIDERS.find((item) => item.id === id) ?? PROVIDERS[0];
}

export default function SettingsPage() {
  const { activeOrganization } = useOrganization();
  const [systems, setSystems] = useState<AISystemSummary[]>([]);
  const [config, setConfig] = useState<ContentEvaluatorConfig | null>(null);
  const [aiSystemId, setAiSystemId] = useState("");
  const [provider, setProvider] = useState<ProviderId>("openai");
  const [model, setModel] = useState(providerMeta("openai").defaultModel);
  const [apiKey, setApiKey] = useState("");
  const [failClosed, setFailClosed] = useState(false);
  const [testContent, setTestContent] = useState("Customer bank account is EG12 3456 7890");
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const selected = useMemo(() => providerMeta(provider), [provider]);

  const loadSystems = useCallback(async () => {
    try {
      const systemsRes = await getAISystems().catch(() => ({
        data: [] as AISystemSummary[],
      }));
      const list = systemsRes.data ?? [];
      setSystems(list);
      setAiSystemId((current) => current || list[0]?.id || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load AI systems");
    }
  }, []);

  const loadConfig = useCallback(async (systemId: string) => {
    if (!systemId) {
      setConfig(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const cfgRes = await getContentEvaluatorConfig(systemId);
      setConfig(cfgRes.data);
      const nextProvider = (cfgRes.data.provider as ProviderId) || "openai";
      const meta = providerMeta(nextProvider);
      setProvider(meta.id);
      setModel(cfgRes.data.model || meta.defaultModel);
      setFailClosed(Boolean(cfgRes.data.fail_closed));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSystems();
  }, [loadSystems]);

  useEffect(() => {
    void loadConfig(aiSystemId);
  }, [aiSystemId, loadConfig]);

  function onProviderChange(next: string) {
    const meta = providerMeta(next);
    setProvider(meta.id);
    setModel(meta.defaultModel);
    setApiKey("");
    setMessage(null);
  }

  async function onSave() {
    if (!aiSystemId) {
      setError("Select an AI System owned by your organization.");
      return;
    }
    if (selected.needsApiKey && !apiKey && !config?.has_api_key) {
      setError(`API key is required for ${selected.label}.`);
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const res = await upsertContentEvaluatorConfig({
        ai_system_id: aiSystemId,
        provider,
        model: model.trim() || selected.defaultModel,
        enabled: true,
        api_key: apiKey || null,
        fail_closed: failClosed,
      });
      setConfig(res.data);
      setApiKey("");
      setMessage("Provider settings saved for this organization AI System.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function onTest() {
    if (!aiSystemId) {
      setError("Select an AI System that has Content Rules before testing.");
      return;
    }
    setTesting(true);
    setError(null);
    setMessage(null);
    setTestResult(null);
    try {
      const res = await testContentEvaluator({
        ai_system_id: aiSystemId,
        content: testContent,
        content_type: "OUTPUT",
      });
      setTestResult(res.data);
      setMessage("Test evaluation completed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Settings"
        subtitle="Tenant-scoped LLM provider for content rule evaluation. Keys stay in your organization."
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <Link href="/settings/webhooks" className="text-sm text-primary hover:underline">
              Webhooks
            </Link>
            {activeOrganization ? (
              <span className="rounded-md border border-base-200 bg-base-50 px-2.5 py-1 text-xs text-ink-600">
                Org: {activeOrganization.name}
              </span>
            ) : null}
          </div>
        }
      />

      <div className="rounded-lg border border-base-200 bg-base-50 px-4 py-3 text-sm text-ink-600">
        Content evaluator settings for this instance. Config is stored per AI System. For content
        rules, also see{" "}
        <Link href="/risk/content-evaluator" className="font-medium text-accent-600">
          Content Evaluator
        </Link>
        .
      </div>

      {loading ? (
        <div className="rounded-xl border border-base-200 bg-base-50 p-6 text-sm text-ink-500">
          Loading organization settings…
        </div>
      ) : (
        <>
          {error ? (
            <div className="rounded-xl border border-danger-100 bg-danger-50 p-4 text-sm text-danger-600">
              {error}
            </div>
          ) : null}
          {message ? (
            <div className="rounded-xl border border-base-200 bg-base-50 p-4 text-sm text-ink-700">
              {message}
            </div>
          ) : null}

          <Panel
            title="Content evaluator provider"
            description="Choose a provider, then fill only the fields that provider needs."
          >
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-3">
                <StatusBadge status={config?.status || "NOT_ACTIVE"} />
                {config?.health_status ? (
                  <span className="text-xs text-ink-500">Health: {config.health_status}</span>
                ) : null}
                {config?.has_api_key ? (
                  <span className="text-xs text-ink-500">API key on file</span>
                ) : null}
              </div>

              <FormField
                label="AI System"
                required
                hint="Must belong to your organization. Settings apply only to this system."
              >
                <Select
                  value={aiSystemId}
                  onChange={(e) => {
                    setAiSystemId(e.target.value);
                    setTestResult(null);
                  }}
                >
                  <option value="">Select AI System…</option>
                  {systems.map((system) => (
                    <option key={system.id} value={system.id}>
                      {system.name} ({system.system_key ?? system.id.slice(0, 8)})
                    </option>
                  ))}
                </Select>
              </FormField>

              <FormField label="Provider" required hint={selected.description}>
                <Select value={provider} onChange={(e) => onProviderChange(e.target.value)}>
                  {PROVIDERS.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </Select>
              </FormField>

              <div className="rounded-lg border border-base-200 bg-base-50 p-4">
                <p className="mb-3 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                  {selected.label} settings
                </p>
                <div className="grid gap-4">
                  <FormField label="Model" required hint={selected.modelHint}>
                    <Input
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      placeholder={selected.defaultModel}
                    />
                  </FormField>

                  {selected.needsApiKey ? (
                    <FormField
                      label={`${selected.label} API key`}
                      required={!config?.has_api_key}
                      hint={
                        config?.has_api_key
                          ? "Leave blank to keep the current key."
                          : "Stored server-side for this organization only."
                      }
                    >
                      <Input
                        type="password"
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        placeholder={
                          config?.has_api_key ? "•••••••• (unchanged if blank)" : "Paste API key"
                        }
                        autoComplete="off"
                      />
                    </FormField>
                  ) : (
                    <p className="text-sm text-ink-500">
                      Mock does not call an external provider. No API key is required.
                    </p>
                  )}

                  <FormField
                    label="Fail closed"
                    hint="When on, evaluator failures block instead of soft-failing."
                  >
                    <Select
                      value={failClosed ? "yes" : "no"}
                      onChange={(e) => setFailClosed(e.target.value === "yes")}
                    >
                      <option value="no">No — soft fail</option>
                      <option value="yes">Yes — fail closed</option>
                    </Select>
                  </FormField>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  disabled={saving || !aiSystemId}
                  onClick={() => void onSave()}
                >
                  {saving ? "Saving…" : "Save & activate"}
                </Button>
                <Button
                  variant="secondary"
                  disabled={loading}
                  onClick={() => void loadConfig(aiSystemId)}
                >
                  Refresh
                </Button>
              </div>
            </div>
          </Panel>

          <Panel
            title="Test evaluation"
            description="Runs against Content Rules for the selected AI System. Does not create production findings."
          >
            <div className="space-y-4">
              <FormField label="Sample content">
                <Textarea
                  rows={4}
                  value={testContent}
                  onChange={(e) => setTestContent(e.target.value)}
                />
              </FormField>
              <Button
                variant="secondary"
                disabled={testing || !aiSystemId}
                onClick={() => void onTest()}
              >
                {testing ? "Evaluating…" : "Run test"}
              </Button>
              {testResult ? (
                <pre className="max-h-[420px] overflow-auto rounded-lg border border-base-200 bg-base-100 p-3 text-xs text-ink-700">
                  {JSON.stringify(testResult, null, 2)}
                </pre>
              ) : null}
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
