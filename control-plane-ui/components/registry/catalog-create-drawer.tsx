"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { SideDrawer } from "@/components/ui/side-drawer";
import { FormField } from "@/components/registry/form-field";
import { createDataSource, createExternalService, createMCPServer, createModel } from "@/lib/api";
import { slugifyKey } from "@/lib/slugify";

type CreateType = "MODEL" | "MCP" | "DATA_SOURCE" | "SERVICE";

const EMPTY_MCP = {
  server_key: "",
  name: "",
  description: "",
  environment: "",
  endpoint_reference: "",
};

const EMPTY_DATA = {
  data_source_key: "",
  name: "",
  classification: "",
  contains_personal_data: false,
  contains_sensitive_data: false,
};

const EMPTY_MODEL = {
  provider: "",
  model_name: "",
  deployment_reference: "",
};

const EMPTY_SERVICE = {
  service_key: "",
  name: "",
  description: "",
  endpoint_reference: "",
};

export function CatalogCreateDrawer({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => Promise<void> | void;
}) {
  const [createType, setCreateType] = useState<CreateType>("MCP");
  const [mcpForm, setMcpForm] = useState(EMPTY_MCP);
  const [dataForm, setDataForm] = useState(EMPTY_DATA);
  const [modelForm, setModelForm] = useState(EMPTY_MODEL);
  const [serviceForm, setServiceForm] = useState(EMPTY_SERVICE);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSave = (() => {
    if (createType === "MCP") return Boolean(mcpForm.server_key.trim() && mcpForm.name.trim());
    if (createType === "MODEL")
      return Boolean(modelForm.provider.trim() && modelForm.model_name.trim());
    if (createType === "DATA_SOURCE") {
      return Boolean(dataForm.data_source_key.trim() && dataForm.name.trim());
    }
    return Boolean(serviceForm.service_key.trim() && serviceForm.name.trim());
  })();

  const handleMcpNameChange = (name: string) => {
    setMcpForm((prev) => {
      const autoKey = !prev.server_key || prev.server_key === slugifyKey(prev.name);
      return {
        ...prev,
        name,
        server_key: autoKey ? slugifyKey(name) : prev.server_key,
      };
    });
  };

  const handleCreate = async () => {
    if (!canSave || saving) return;
    setSaving(true);
    setError(null);
    try {
      if (createType === "MCP") {
        await createMCPServer({
          server_key: mcpForm.server_key.trim(),
          name: mcpForm.name.trim(),
          description: mcpForm.description.trim() || undefined,
          environment: mcpForm.environment.trim() || undefined,
          endpoint_reference: mcpForm.endpoint_reference.trim() || undefined,
        });
        setMcpForm(EMPTY_MCP);
      } else if (createType === "DATA_SOURCE") {
        await createDataSource({
          ...dataForm,
          data_source_key: dataForm.data_source_key.trim(),
          name: dataForm.name.trim(),
          classification: dataForm.classification.trim() || undefined,
        });
        setDataForm(EMPTY_DATA);
      } else if (createType === "MODEL") {
        await createModel({
          provider: modelForm.provider.trim(),
          model_name: modelForm.model_name.trim(),
          deployment_reference: modelForm.deployment_reference.trim() || undefined,
        });
        setModelForm(EMPTY_MODEL);
      } else {
        await createExternalService({
          service_key: serviceForm.service_key.trim(),
          name: serviceForm.name.trim(),
          description: serviceForm.description.trim() || undefined,
          endpoint_reference: serviceForm.endpoint_reference.trim() || undefined,
        });
        setServiceForm(EMPTY_SERVICE);
      }
      onClose();
      await onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create resource");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SideDrawer
      open={open}
      onClose={onClose}
      title="Add resource"
      description="Create a model, MCP server, data source, or external service in the catalog."
      width="xl"
      data-testid="resource-create-drawer"
      footer={
        <>
          <Button variant="secondary" disabled={saving} onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={saving || !canSave}
            onClick={() => void handleCreate()}
          >
            {saving ? "Creating…" : "Create"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error ? <p className="text-sm text-danger-600">{error}</p> : null}
        <FormField label="Resource type" required>
          <Select
            value={createType}
            disabled={saving}
            onChange={(e) => setCreateType(e.target.value as CreateType)}
          >
            <option value="MODEL">Model</option>
            <option value="MCP">MCP Server</option>
            <option value="DATA_SOURCE">Data Source</option>
            <option value="SERVICE">External Service</option>
          </Select>
        </FormField>

        {createType === "MCP" && (
          <div className="grid gap-3">
            <FormField label="Name" required>
              <Input
                value={mcpForm.name}
                disabled={saving}
                onChange={(e) => handleMcpNameChange(e.target.value)}
              />
            </FormField>
            <FormField label="Server key" required hint="Filled from the name. Edit to override.">
              <Input
                value={mcpForm.server_key}
                disabled={saving}
                onChange={(e) => setMcpForm({ ...mcpForm, server_key: e.target.value })}
              />
            </FormField>
            <FormField label="Environment">
              <Input
                value={mcpForm.environment}
                disabled={saving}
                onChange={(e) => setMcpForm({ ...mcpForm, environment: e.target.value })}
              />
            </FormField>
            <FormField label="Endpoint">
              <Input
                value={mcpForm.endpoint_reference}
                disabled={saving}
                onChange={(e) => setMcpForm({ ...mcpForm, endpoint_reference: e.target.value })}
              />
            </FormField>
            <FormField label="Description">
              <Textarea
                value={mcpForm.description}
                disabled={saving}
                onChange={(e) => setMcpForm({ ...mcpForm, description: e.target.value })}
              />
            </FormField>
          </div>
        )}

        {createType === "MODEL" && (
          <div className="grid gap-3">
            <FormField label="Provider" required>
              <Input
                value={modelForm.provider}
                disabled={saving}
                onChange={(e) => setModelForm({ ...modelForm, provider: e.target.value })}
              />
            </FormField>
            <FormField label="Model name" required>
              <Input
                value={modelForm.model_name}
                disabled={saving}
                onChange={(e) => setModelForm({ ...modelForm, model_name: e.target.value })}
              />
            </FormField>
            <FormField label="Deployment reference">
              <Input
                value={modelForm.deployment_reference}
                disabled={saving}
                onChange={(e) =>
                  setModelForm({ ...modelForm, deployment_reference: e.target.value })
                }
              />
            </FormField>
          </div>
        )}

        {createType === "DATA_SOURCE" && (
          <div className="grid gap-3">
            <FormField label="Key" required>
              <Input
                value={dataForm.data_source_key}
                disabled={saving}
                onChange={(e) => setDataForm({ ...dataForm, data_source_key: e.target.value })}
              />
            </FormField>
            <FormField label="Name" required>
              <Input
                value={dataForm.name}
                disabled={saving}
                onChange={(e) => setDataForm({ ...dataForm, name: e.target.value })}
              />
            </FormField>
            <FormField label="Classification">
              <Input
                value={dataForm.classification}
                disabled={saving}
                onChange={(e) => setDataForm({ ...dataForm, classification: e.target.value })}
              />
            </FormField>
          </div>
        )}

        {createType === "SERVICE" && (
          <div className="grid gap-3">
            <FormField label="Service key" required>
              <Input
                value={serviceForm.service_key}
                disabled={saving}
                onChange={(e) => setServiceForm({ ...serviceForm, service_key: e.target.value })}
              />
            </FormField>
            <FormField label="Name" required>
              <Input
                value={serviceForm.name}
                disabled={saving}
                onChange={(e) => setServiceForm({ ...serviceForm, name: e.target.value })}
              />
            </FormField>
            <FormField label="Endpoint">
              <Input
                value={serviceForm.endpoint_reference}
                disabled={saving}
                onChange={(e) =>
                  setServiceForm({ ...serviceForm, endpoint_reference: e.target.value })
                }
              />
            </FormField>
            <FormField label="Description">
              <Textarea
                value={serviceForm.description}
                disabled={saving}
                onChange={(e) => setServiceForm({ ...serviceForm, description: e.target.value })}
              />
            </FormField>
          </div>
        )}
      </div>
    </SideDrawer>
  );
}
