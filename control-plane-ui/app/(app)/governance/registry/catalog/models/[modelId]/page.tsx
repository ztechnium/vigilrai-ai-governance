"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { SectionHeader } from "@/components/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Breadcrumbs } from "@/components/registry/breadcrumbs";
import { FormField } from "@/components/registry/form-field";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { getModel, updateModel } from "@/lib/api";
import type { ModelResourceSummary } from "@/lib/types";

export default function ModelDetailPage() {
  const params = useParams();
  const modelId = params.modelId as string;
  const [model, setModel] = useState<ModelResourceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [form, setForm] = useState({
    provider: "",
    model_name: "",
    model_version: "",
    deployment_reference: "",
    hosting_type: "",
  });

  const load = useCallback(() => {
    setLoading(true);
    getModel(modelId)
      .then((res) => {
        setModel(res.data);
        setForm({
          provider: res.data.provider,
          model_name: res.data.model_name,
          model_version: res.data.model_version ?? "",
          deployment_reference: res.data.deployment_reference ?? "",
          hosting_type: res.data.hosting_type ?? "",
        });
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [modelId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async () => {
    if (!form.provider.trim() || !form.model_name.trim()) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      await updateModel(modelId, {
        provider: form.provider.trim(),
        model_name: form.model_name.trim(),
        model_version: form.model_version.trim() || undefined,
        deployment_reference: form.deployment_reference.trim() || undefined,
        hosting_type: form.hosting_type.trim() || undefined,
      });
      setSaveMessage("Model updated successfully.");
      load();
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Failed to update model");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="p-8 text-center text-sm text-ink-500">Loading model...</div>;
  }

  if (error || !model) {
    return (
      <div className="rounded-xl bg-danger-50 p-6 text-sm text-danger-600">
        {error ?? "Not found"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[
          { label: "Resource Catalog", href: "/governance/registry/catalog" },
          { label: `${model.provider}/${model.model_name}` },
        ]}
      />

      <SectionHeader
        title={`${model.provider} / ${model.model_name}`}
        subtitle="Update model metadata used when associating this resource with agent versions."
        actions={<StatusBadge status={model.status} />}
      />

      <Panel title="Model Details">
        <div className="grid gap-4 md:grid-cols-2">
          <FormField label="Provider" required>
            <Input
              value={form.provider}
              onChange={(e) => setForm({ ...form, provider: e.target.value })}
            />
          </FormField>
          <FormField label="Model Name" required>
            <Input
              value={form.model_name}
              onChange={(e) => setForm({ ...form, model_name: e.target.value })}
            />
          </FormField>
          <FormField label="Model Version">
            <Input
              value={form.model_version}
              onChange={(e) => setForm({ ...form, model_version: e.target.value })}
              placeholder="2024-08-06"
            />
          </FormField>
          <FormField label="Hosting Type">
            <Input
              value={form.hosting_type}
              onChange={(e) => setForm({ ...form, hosting_type: e.target.value })}
              placeholder="managed"
            />
          </FormField>
          <div className="md:col-span-2">
            <FormField label="Deployment Reference">
              <Input
                value={form.deployment_reference}
                onChange={(e) => setForm({ ...form, deployment_reference: e.target.value })}
                placeholder="azure-openai://eastus/gpt-4o"
              />
            </FormField>
          </div>
        </div>

        <div className="mt-6 flex items-center justify-between gap-4">
          {saveMessage && (
            <p
              className={`text-sm ${saveMessage.includes("success") ? "text-accent-600" : "text-danger-600"}`}
            >
              {saveMessage}
            </p>
          )}
          <div className="ml-auto">
            <Button variant="primary" onClick={handleSave} disabled={saving}>
              {saving ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </div>
      </Panel>
    </div>
  );
}
