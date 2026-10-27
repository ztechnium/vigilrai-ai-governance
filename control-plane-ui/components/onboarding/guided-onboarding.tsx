"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SectionHeader } from "@/components/section-header";
import { CatalogUpload } from "@/components/onboarding/catalog-upload";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { FormField } from "@/components/registry/form-field";
import { TechnicalValue } from "@/components/console/page-parts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  createAgent,
  createAgentVersion,
  createAISystem,
  createRuntimeIdentity,
  getAISystems,
  getAgentVersions,
  getAgents,
  getRuntimeCredentials,
  getRuntimeIdentities,
  getTrajectories,
  issueRuntimeCredential,
  transitionAgentVersion,
  transitionAISystem,
} from "@/lib/api";
import { BUSINESS_UNITS, RISK_TIERS } from "@/lib/registry-constants";
import { fetchOnboarding, patchOnboarding, type OnboardingResponse } from "@/lib/public-api";
import { cn } from "@/lib/utils";
import type { AISystemSummary, TrajectorySummary } from "@/lib/types";

const STEPS = ["System", "Agent", "Version", "Runtime", "Credential", "Connect", "Verify"] as const;

const CHECKLIST_WIZARD: Record<string, number> = {
  first_ai_system: 0,
  agent_version: 1,
  runtime_identity: 3,
  choose_integration: 4,
  connect_application: 5,
  test_connection: 5,
  first_governed_action: 5,
  inspect_trajectory: 6,
};

const CHECKLIST_GUIDE: Record<string, { detail: string; href?: string; hrefLabel?: string }> = {
  organization_profile: {
    detail: "Organization name, industry, and logo are saved from the welcome wizard.",
  },
  team_roles: {
    detail: "Confirm an organization admin and a RAI officer are active.",
    href: "/organization/team",
    hrefLabel: "Open team",
  },
  first_ai_system: {
    detail: "Register the AI system this runtime will govern.",
  },
  agent_version: {
    detail: "Add the agent and approve its first version.",
  },
  resources: {
    detail:
      "Add models, MCP servers, tools, and services. A spreadsheet can load all of them at once.",
  },
  first_policies: {
    detail: "Attach the first policies that should govern this system.",
    href: "/governance/policies",
    hrefLabel: "Open policies",
  },
  choose_integration: {
    detail: "Create the SDK integration the application will call.",
  },
  runtime_identity: {
    detail: "Create the runtime identity that holds the agent credential.",
  },
  connect_application: {
    detail: "Send a heartbeat from the SDK so the integration shows as connected.",
  },
  test_connection: {
    detail: "Run a test call and confirm the credential is accepted.",
  },
  first_governed_action: {
    detail: "Authorize an action and execute it only when the decision is allow.",
  },
  inspect_trajectory: {
    detail: "Open the first trajectory and confirm the decision was recorded.",
  },
  production_readiness: {
    detail: "Mark the organization ready when the connect path has been exercised.",
  },
};

type WizardProgress = {
  systemId?: string;
  systemName?: string;
  systemKey?: string;
  agentId?: string;
  agentName?: string;
  agentKey?: string;
  versionId?: string;
  versionNumber?: number;
  versionLifecycle?: string;
  runtimeId?: string;
  runtimeName?: string;
  credentialId?: string;
  credentialPrefix?: string;
  trajectoryId?: string;
  connectSkipped?: boolean;
};

function storageKey(orgId: string) {
  return `rai_onboarding_wizard_${orgId}`;
}

function slugify(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}

function loadProgress(orgId: string): WizardProgress {
  try {
    const raw = window.sessionStorage.getItem(storageKey(orgId));
    return raw ? (JSON.parse(raw) as WizardProgress) : {};
  } catch {
    return {};
  }
}

function saveProgress(orgId: string, progress: WizardProgress) {
  window.sessionStorage.setItem(storageKey(orgId), JSON.stringify(progress));
}

function derivedStep(progress: WizardProgress): number {
  if (!progress.systemId) return 0;
  if (!progress.agentId) return 1;
  if (!progress.versionId || progress.versionLifecycle !== "APPROVED") return 2;
  if (!progress.runtimeId) return 3;
  if (!progress.credentialId && !progress.credentialPrefix) return 4;
  if (!progress.trajectoryId && !progress.connectSkipped) return 5;
  return 6;
}

function checklistDone(onboarding: OnboardingResponse | null, stepId: string): boolean {
  return Boolean(onboarding?.steps.find((step) => step.id === stepId)?.done);
}

/** Prefer live registry + org checklist over stale session progress. */
async function hydrateProgressFromOrg(
  organizationId: string,
  onboarding: OnboardingResponse,
  systems: AISystemSummary[],
  stored: WizardProgress,
): Promise<WizardProgress> {
  const next: WizardProgress = { ...stored };

  const preferredSystemId =
    onboarding.onboarding.first_ai_system_id ??
    next.systemId ??
    (checklistDone(onboarding, "first_ai_system") || systems.length > 0
      ? systems[0]?.id
      : undefined);

  if (preferredSystemId) {
    const system = systems.find((item) => item.id === preferredSystemId) ?? systems[0];
    if (system) {
      next.systemId = system.id;
      next.systemName = system.name;
      next.systemKey = system.system_key;
    }
  }

  if (onboarding.onboarding.first_trajectory_id) {
    next.trajectoryId = onboarding.onboarding.first_trajectory_id;
  }

  if (!next.systemId) return next;

  const agents = await getAgents(next.systemId);
  const preferredAgent = agents.data.find((item) => item.id === next.agentId) ?? agents.data[0];
  if (
    preferredAgent &&
    (next.agentId || checklistDone(onboarding, "agent_version") || agents.data.length > 0)
  ) {
    next.agentId = preferredAgent.id;
    next.agentName = preferredAgent.name;
    next.agentKey = preferredAgent.agent_key;
  }

  if (!next.agentId) return next;

  const versions = await getAgentVersions(next.agentId);
  const preferredVersion =
    versions.data.find((item) => item.id === next.versionId) ??
    versions.data.find((item) => item.lifecycle_status === "APPROVED") ??
    versions.data[0];
  if (preferredVersion) {
    next.versionId = preferredVersion.id;
    next.versionNumber = preferredVersion.version_number;
    next.versionLifecycle = preferredVersion.lifecycle_status;
  }

  if (!next.agentId) return next;

  const runtimes = await getRuntimeIdentities({ agent_id: next.agentId });
  const preferredRuntime =
    runtimes.data.find((item) => item.id === next.runtimeId) ?? runtimes.data[0];
  if (
    preferredRuntime &&
    (next.runtimeId || checklistDone(onboarding, "runtime_identity") || runtimes.data.length > 0)
  ) {
    next.runtimeId = preferredRuntime.id;
    next.runtimeName = preferredRuntime.name;
  }

  if (!next.runtimeId) return next;

  const creds = await getRuntimeCredentials(next.runtimeId);
  const preferredCred =
    creds.data.find((item) => item.id === next.credentialId) ??
    creds.data.find((item) => item.status === "ACTIVE") ??
    creds.data[0];
  if (preferredCred) {
    next.credentialId = preferredCred.id;
    next.credentialPrefix = preferredCred.credential_key;
  }

  if (
    !next.trajectoryId &&
    (checklistDone(onboarding, "inspect_trajectory") ||
      checklistDone(onboarding, "connect_application") ||
      checklistDone(onboarding, "test_connection") ||
      checklistDone(onboarding, "first_governed_action"))
  ) {
    try {
      const trajRes = await getTrajectories({
        ai_system_id: next.systemId,
        limit: 5,
      });
      const match =
        trajRes.data.items.find((item) =>
          next.runtimeId ? item.runtime_identity_id === next.runtimeId : true,
        ) ?? trajRes.data.items[0];
      if (match) next.trajectoryId = match.id;
    } catch {
      // ignore
    }
  }

  void organizationId;
  return next;
}

function ContextChain({ items }: { items: [string, string][] }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {items.map(([label, value], index) => (
        <span key={label} className="inline-flex items-center gap-2">
          {index > 0 ? <span className="text-ink-300">→</span> : null}
          <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
            {label}
          </span>
          <TechnicalValue>{value || "—"}</TechnicalValue>
        </span>
      ))}
    </div>
  );
}

function TechnicalCopyField({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-center gap-2 rounded-md border border-base-200 bg-base-100 px-3 py-2 font-mono text-xs text-ink-800">
      <span className="min-w-0 flex-1 break-all">{value}</span>
      <button
        type="button"
        className="shrink-0 text-ink-400 hover:text-ink-800"
        aria-label="Copy value"
        onClick={() => {
          void navigator.clipboard?.writeText(value);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1200);
        }}
      >
        {copied ? "✓" : "Copy"}
      </button>
    </div>
  );
}

function StepShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Panel title={title}>
      <div className="space-y-4">{children}</div>
    </Panel>
  );
}

function DoneBanner({ label, onNext }: { label: string; onNext: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-accent-200 bg-accent-50 p-3 text-xs">
      <span className="font-medium text-accent-700">✓ {label}</span>
      <Button size="sm" onClick={onNext}>
        Continue
      </Button>
    </div>
  );
}

function SecretRevealModal({
  secret,
  prefix,
  onDone,
}: {
  secret: string;
  prefix: string;
  onDone: () => void;
}) {
  const [ack, setAck] = useState(false);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 p-4">
      <div className="w-full max-w-lg rounded-xl border border-base-200 bg-base-50 p-5 shadow-panel">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-accent-600">
          Credential created
        </div>
        <h2 className="mt-2 text-sm font-semibold text-ink-900">
          Copy this secret now. It will not be shown again.
        </h2>
        <p className="mt-1 text-xs text-ink-500">
          Only the prefix <TechnicalValue>{prefix}</TechnicalValue> is retained.
        </p>
        <div className="mt-4">
          <TechnicalCopyField value={secret} />
        </div>
        <label className="mt-4 flex cursor-pointer items-center gap-2 text-xs text-ink-700">
          <input
            type="checkbox"
            checked={ack}
            onChange={(event) => setAck(event.target.checked)}
            className="size-4"
          />
          I have saved this credential in an approved secret store
        </label>
        <div className="mt-4 flex justify-end">
          <Button disabled={!ack} onClick={onDone}>
            I Have Saved It
          </Button>
        </div>
      </div>
    </div>
  );
}

export function GuidedOnboarding({ organizationId }: { organizationId: string }) {
  const [checklist, setChecklist] = useState<OnboardingResponse | null>(null);
  const [progress, setProgress] = useState<WizardProgress>({});
  const [step, setStep] = useState(0);
  const [systems, setSystems] = useState<AISystemSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [secretReveal, setSecretReveal] = useState<{ secret: string; prefix: string } | null>(null);
  const [credentialSecret, setCredentialSecret] = useState("");
  const [trajectory, setTrajectory] = useState<TrajectorySummary | null>(null);
  const [booting, setBooting] = useState(true);
  const [selectedChecklist, setSelectedChecklist] = useState("organization_profile");
  const checklistInitialized = useRef(false);

  const updateProgress = useCallback(
    (patch: WizardProgress) => {
      setProgress((prev) => {
        const next = { ...prev, ...patch };
        saveProgress(organizationId, next);
        return next;
      });
    },
    [organizationId],
  );

  const refreshChecklist = useCallback(async () => {
    const data = await fetchOnboarding(organizationId);
    setChecklist(data);
    return data;
  }, [organizationId]);

  const markStep = useCallback(
    async (completeStep: string, extras?: Parameters<typeof patchOnboarding>[1]) => {
      const data = await patchOnboarding(organizationId, {
        complete_step: completeStep,
        ...extras,
      });
      setChecklist(data);
      return data;
    },
    [organizationId],
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const stored = loadProgress(organizationId);
        const [onboarding, systemsRes] = await Promise.all([
          fetchOnboarding(organizationId),
          getAISystems(),
        ]);
        if (cancelled) return;
        setChecklist(onboarding);
        setSystems(systemsRes.data);

        const next = await hydrateProgressFromOrg(
          organizationId,
          onboarding,
          systemsRes.data,
          stored,
        );
        if (cancelled) return;

        // Persist first AI system on the org record when checklist already implies it.
        if (
          next.systemId &&
          !onboarding.onboarding.first_ai_system_id &&
          checklistDone(onboarding, "first_ai_system")
        ) {
          try {
            const updated = await patchOnboarding(organizationId, {
              first_ai_system_id: next.systemId,
              complete_step: "first_ai_system",
            });
            if (!cancelled) setChecklist(updated);
          } catch {
            // non-blocking
          }
        }

        setProgress(next);
        saveProgress(organizationId, next);
        setStep(derivedStep(next));

        if (next.trajectoryId) {
          try {
            const trajRes = await getTrajectories({
              ai_system_id: next.systemId,
              limit: 10,
            });
            if (!cancelled) {
              const match =
                trajRes.data.items.find((item) => item.id === next.trajectoryId) ??
                trajRes.data.items[0] ??
                null;
              setTrajectory(match);
            }
          } catch {
            // ignore
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to load onboarding");
        }
      } finally {
        if (!cancelled) setBooting(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [organizationId]);

  useEffect(() => {
    if (step < 5 || !progress.systemId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await getTrajectories({ ai_system_id: progress.systemId, limit: 5 });
        if (cancelled) return;
        const match =
          res.data.items.find((item) =>
            progress.runtimeId ? item.runtime_identity_id === progress.runtimeId : true,
          ) ?? res.data.items[0];
        if (match) {
          setTrajectory(match);
          if (!progress.trajectoryId) {
            updateProgress({ trajectoryId: match.id });
            void markStep("inspect_trajectory", { first_trajectory_id: match.id });
            void markStep("test_connection");
            void markStep("first_governed_action");
            void markStep("connect_application");
          }
        }
      } catch {
        // ignore poll errors
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 8000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [
    step,
    progress.systemId,
    progress.runtimeId,
    progress.trajectoryId,
    markStep,
    updateProgress,
  ]);

  const chain = useMemo(
    (): [string, string][] => [
      ["AI System", progress.systemName ?? "—"],
      ["Agent", progress.agentName ?? "—"],
      ["Version", progress.versionNumber != null ? `v${progress.versionNumber}` : "—"],
      ["Runtime Identity", progress.runtimeName ?? "—"],
    ],
    [progress],
  );

  const maxReachable = derivedStep(progress);

  useEffect(() => {
    if (!checklist || checklistInitialized.current) return;
    const next = checklist.steps.find((item) => !item.done);
    if (next) setSelectedChecklist(next.id);
    checklistInitialized.current = true;
  }, [checklist]);

  const selectedStep = checklist?.steps.find((item) => item.id === selectedChecklist) ?? null;

  async function finishChecklist(stepId: string) {
    setBusy(true);
    setError(null);
    try {
      await markStep(stepId, stepId === "production_readiness" ? { status: "READY" } : undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to finish this step");
    } finally {
      setBusy(false);
    }
  }

  if (booting) {
    return (
      <div className="rounded-xl border border-base-200 bg-base-50 p-6 text-sm text-ink-500">
        Loading onboarding…
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="guided-onboarding">
      <SectionHeader
        title="Connect Your First AI System"
        subtitle="Register an AI workload, establish its runtime identity, and begin capturing governed execution evidence."
        actions={
          <Link href="/dashboard">
            <Button variant="ghost">Back to Control Posture</Button>
          </Link>
        }
      />

      {error ? (
        <div className="rounded-lg border border-danger-200 bg-danger-50 p-3 text-sm text-danger-600">
          {error}
        </div>
      ) : null}

      <ol className="grid grid-cols-2 overflow-hidden rounded-lg border border-base-200 bg-base-50 sm:grid-cols-7">
        {STEPS.map((label, index) => {
          const done = index < maxReachable;
          const current = index === step;
          return (
            <li key={label}>
              <button
                type="button"
                onClick={() => setStep(index)}
                className={cn(
                  "flex w-full items-center gap-2 border-b-2 px-3 py-3 text-left text-xs",
                  current ? "border-accent-600 bg-accent-50" : "border-transparent",
                  index > maxReachable && "opacity-80",
                )}
              >
                <span
                  className={cn(
                    "flex size-5 items-center justify-center rounded border font-mono text-[10px]",
                    done
                      ? "border-accent-300 bg-accent-50 text-accent-700"
                      : current
                        ? "border-accent-600 text-accent-600"
                        : "border-base-200 text-ink-400",
                  )}
                >
                  {done ? "✓" : index + 1}
                </span>
                <span className={current ? "font-semibold text-ink-900" : "text-ink-500"}>
                  {label}
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      {progress.systemId ? (
        <div className="rounded-lg border border-base-200 bg-base-50 px-4 py-3">
          <ContextChain items={chain} />
        </div>
      ) : null}

      {checklist ? (
        <div className="rounded-lg border border-base-200 bg-base-50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                Organization onboarding
              </div>
              <div className="mt-1 text-sm font-semibold text-ink-900">
                {checklist.progress.completed}/{checklist.progress.total} checklist steps complete
                {checklist.onboarding.status ? (
                  <span className="ml-2 inline-flex align-middle">
                    <StatusBadge status={checklist.onboarding.status} />
                  </span>
                ) : null}
              </div>
            </div>
            {checklist.next_recommended_action ? (
              <p className="text-xs text-ink-500">Next: {checklist.next_recommended_action}</p>
            ) : (
              <p className="text-xs text-accent-700">All checklist steps complete</p>
            )}
          </div>
          <ul className="mt-3 flex flex-wrap gap-2">
            {checklist.steps.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedChecklist(item.id);
                    const target = CHECKLIST_WIZARD[item.id];
                    if (target !== undefined) setStep(target);
                  }}
                  className={cn(
                    "rounded-md border px-2 py-1 text-left text-[11px]",
                    selectedChecklist === item.id && "ring-1 ring-accent-600",
                    item.done
                      ? "border-accent-200 bg-accent-50 text-accent-700"
                      : item.blocked
                        ? "border-warn-100 bg-warn-50 text-warn-700"
                        : "border-base-200 bg-base-100 text-ink-500",
                  )}
                >
                  {item.done ? "✓ " : item.blocked ? "◌ " : "○ "}
                  {item.label}
                </button>
              </li>
            ))}
          </ul>
          {selectedStep ? (
            <div className="mt-4 space-y-3 border-t border-base-200 pt-4">
              <div className="text-sm font-semibold text-ink-900">{selectedStep.label}</div>
              <p className="text-xs text-ink-500">
                {CHECKLIST_GUIDE[selectedStep.id]?.detail}
                {selectedStep.blocked_reason ? ` ${selectedStep.blocked_reason}` : ""}
              </p>
              {selectedStep.id === "resources" ? <CatalogUpload compact /> : null}
              <div className="flex flex-wrap gap-2">
                {CHECKLIST_GUIDE[selectedStep.id]?.href ? (
                  <Link href={CHECKLIST_GUIDE[selectedStep.id].href!}>
                    <Button variant="secondary" size="sm">
                      {CHECKLIST_GUIDE[selectedStep.id].hrefLabel}
                    </Button>
                  </Link>
                ) : null}
                <Button
                  size="sm"
                  disabled={busy || selectedStep.done}
                  onClick={() => void finishChecklist(selectedStep.id)}
                >
                  {selectedStep.done ? "Finished" : busy ? "Saving…" : "Mark finished"}
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {step > 0 && !progress.systemId ? (
        <p className="text-sm text-ink-500">
          Create an AI system before this connect step. You can still mark the checklist item
          finished.
        </p>
      ) : null}
      {step > 1 && progress.systemId && !progress.agentId ? (
        <p className="text-sm text-ink-500">Add an agent before this connect step.</p>
      ) : null}
      {step > 2 && progress.agentId && !progress.versionId ? (
        <p className="text-sm text-ink-500">Create a version before this connect step.</p>
      ) : null}

      <div className="max-w-3xl">
        {step === 0 ? (
          <SystemStep
            systems={systems}
            existing={progress.systemName}
            busy={busy}
            onSelectExisting={async (system) => {
              setBusy(true);
              setError(null);
              try {
                updateProgress({
                  systemId: system.id,
                  systemName: system.name,
                  systemKey: system.system_key,
                  agentId: undefined,
                  agentName: undefined,
                  agentKey: undefined,
                  versionId: undefined,
                  versionNumber: undefined,
                  versionLifecycle: undefined,
                  runtimeId: undefined,
                  runtimeName: undefined,
                  credentialId: undefined,
                  credentialPrefix: undefined,
                  trajectoryId: undefined,
                });
                await markStep("first_ai_system", { first_ai_system_id: system.id });
                setStep(1);
              } catch (err) {
                setError(err instanceof Error ? err.message : "Unable to select system");
              } finally {
                setBusy(false);
              }
            }}
            onCreate={async (form) => {
              setBusy(true);
              setError(null);
              try {
                const res = await createAISystem({
                  system_key: form.key,
                  name: form.name,
                  business_purpose: form.purpose || undefined,
                  business_unit: form.unit || undefined,
                  owner_id: form.owner || undefined,
                  risk_tier: form.risk,
                });
                if (res.data.status === "DRAFT") {
                  try {
                    await transitionAISystem(res.data.id, "ACTIVE");
                  } catch {
                    // optional
                  }
                }
                updateProgress({
                  systemId: res.data.id,
                  systemName: res.data.name,
                  systemKey: res.data.system_key,
                });
                setSystems((prev) => [res.data, ...prev]);
                await markStep("first_ai_system", { first_ai_system_id: res.data.id });
                setStep(1);
              } catch (err) {
                setError(err instanceof Error ? err.message : "Unable to create AI system");
              } finally {
                setBusy(false);
              }
            }}
            onDone={() => setStep(1)}
          />
        ) : null}

        {step === 1 && progress.systemId ? (
          <AgentStep
            systemName={progress.systemName ?? ""}
            existing={progress.agentName}
            busy={busy}
            onCreate={async (form) => {
              setBusy(true);
              setError(null);
              try {
                const res = await createAgent(progress.systemId!, {
                  agent_key: form.key,
                  name: form.name,
                  business_purpose: form.description || undefined,
                });
                updateProgress({
                  agentId: res.data.id,
                  agentName: res.data.name,
                  agentKey: res.data.agent_key,
                });
                setStep(2);
              } catch (err) {
                setError(err instanceof Error ? err.message : "Unable to create agent");
              } finally {
                setBusy(false);
              }
            }}
            onDone={() => setStep(2)}
          />
        ) : null}

        {step === 2 && progress.systemId && progress.agentId ? (
          <VersionStep
            systemName={progress.systemName ?? ""}
            agentName={progress.agentName ?? ""}
            versionId={progress.versionId}
            versionNumber={progress.versionNumber}
            lifecycle={progress.versionLifecycle}
            busy={busy}
            onCreate={async (form) => {
              setBusy(true);
              setError(null);
              try {
                const res = await createAgentVersion(progress.agentId!, {
                  change_summary: "Initial onboarding version",
                  configuration_snapshot: {
                    model: form.model,
                    tools: form.tools
                      .split(",")
                      .map((item) => item.trim())
                      .filter(Boolean),
                  },
                });
                updateProgress({
                  versionId: res.data.id,
                  versionNumber: res.data.version_number,
                  versionLifecycle: res.data.lifecycle_status,
                });
              } catch (err) {
                setError(err instanceof Error ? err.message : "Unable to create version");
              } finally {
                setBusy(false);
              }
            }}
            onTransition={async (status) => {
              if (!progress.versionId) return;
              setBusy(true);
              setError(null);
              try {
                const res = await transitionAgentVersion(progress.versionId, status);
                updateProgress({ versionLifecycle: res.data.lifecycle_status });
                if (res.data.lifecycle_status === "APPROVED") {
                  await markStep("agent_version");
                }
              } catch (err) {
                setError(err instanceof Error ? err.message : "Lifecycle transition failed");
              } finally {
                setBusy(false);
              }
            }}
            onContinue={() => setStep(3)}
          />
        ) : null}

        {step === 3 && progress.systemId && progress.agentId && progress.versionId ? (
          <RuntimeStep
            chain={chain}
            systemKey={progress.systemKey ?? "runtime"}
            existing={progress.runtimeName}
            busy={busy}
            onCreate={async (form) => {
              setBusy(true);
              setError(null);
              try {
                const res = await createRuntimeIdentity({
                  agent_id: progress.agentId!,
                  agent_version_id: progress.versionId!,
                  name: form.name,
                  environment: form.environment,
                  identity_type: "SERVICE",
                });
                updateProgress({ runtimeId: res.data.id, runtimeName: res.data.name });
                await markStep("runtime_identity");
                setStep(4);
              } catch (err) {
                setError(err instanceof Error ? err.message : "Unable to create runtime identity");
              } finally {
                setBusy(false);
              }
            }}
            onDone={() => setStep(4)}
          />
        ) : null}

        {step === 4 && progress.runtimeId ? (
          <CredentialStep
            existing={progress.credentialPrefix}
            busy={busy}
            onIssue={async () => {
              setBusy(true);
              setError(null);
              try {
                const res = await issueRuntimeCredential(progress.runtimeId!);
                const secret = res.data.plaintext_secret ?? "";
                const prefix = res.data.credential_key;
                updateProgress({ credentialId: res.data.id, credentialPrefix: prefix });
                if (secret) {
                  setCredentialSecret(secret);
                  setSecretReveal({ secret, prefix });
                } else {
                  setStep(5);
                }
              } catch (err) {
                setError(err instanceof Error ? err.message : "Unable to issue credential");
              } finally {
                setBusy(false);
              }
            }}
            onDone={() => setStep(5)}
          />
        ) : null}

        {step === 5 ? (
          <ConnectStep
            systemKey={progress.systemKey ?? "—"}
            agentKey={progress.agentKey ?? "—"}
            versionLabel={progress.versionNumber != null ? `v${progress.versionNumber}` : "—"}
            runtimeName={progress.runtimeName ?? "—"}
            secret={credentialSecret}
            lastEvent={trajectory?.started_at}
            busy={busy}
            onVerify={() => setStep(6)}
            onComplete={async () => {
              setBusy(true);
              setError(null);
              try {
                await markStep("connect_application");
                updateProgress({ connectSkipped: true });
                setStep(6);
              } catch (err) {
                setError(err instanceof Error ? err.message : "Unable to complete this step");
              } finally {
                setBusy(false);
              }
            }}
          />
        ) : null}

        {step === 6 ? (
          <VerifyStep
            trajectory={trajectory}
            busy={busy}
            complete={Boolean(checklist?.complete)}
            onFinish={async () => {
              setBusy(true);
              setError(null);
              try {
                await patchOnboarding(organizationId, {
                  status: "READY",
                  complete_step: "production_readiness",
                  ...(trajectory?.id ? { first_trajectory_id: trajectory.id } : {}),
                });
                await refreshChecklist();
              } catch (err) {
                setError(err instanceof Error ? err.message : "Unable to finish setup");
              } finally {
                setBusy(false);
              }
            }}
          />
        ) : null}
      </div>

      {secretReveal ? (
        <SecretRevealModal
          secret={secretReveal.secret}
          prefix={secretReveal.prefix}
          onDone={() => {
            setSecretReveal(null);
            setStep(5);
          }}
        />
      ) : null}
    </div>
  );
}

function SystemStep({
  systems,
  existing,
  busy,
  onSelectExisting,
  onCreate,
  onDone,
}: {
  systems: AISystemSummary[];
  existing?: string;
  busy: boolean;
  onSelectExisting: (system: AISystemSummary) => Promise<void>;
  onCreate: (form: {
    name: string;
    key: string;
    purpose: string;
    unit: string;
    owner: string;
    risk: string;
  }) => Promise<void>;
  onDone: () => void;
}) {
  const [pick, setPick] = useState("");
  const [touched, setTouched] = useState(false);
  const [form, setForm] = useState({
    name: "",
    key: "",
    purpose: "",
    unit: "",
    owner: "",
    risk: "MEDIUM",
  });

  if (existing) {
    return (
      <StepShell title="Step 1 — AI System">
        <DoneBanner label={`${existing} registered`} onNext={onDone} />
      </StepShell>
    );
  }

  return (
    <StepShell title="Step 1 — AI System">
      {systems.length > 0 ? (
        <FormField label="Use an existing AI system">
          <div className="flex gap-2">
            <Select value={pick} onChange={(event) => setPick(event.target.value)}>
              <option value="">Select…</option>
              {systems.map((system) => (
                <option key={system.id} value={system.id}>
                  {system.name}
                </option>
              ))}
            </Select>
            <Button
              variant="secondary"
              disabled={!pick || busy}
              onClick={() => {
                const system = systems.find((item) => item.id === pick);
                if (system) void onSelectExisting(system);
              }}
            >
              Select
            </Button>
          </div>
        </FormField>
      ) : null}

      <FormField label="Display name" required>
        <Input
          autoFocus
          value={form.name}
          disabled={busy}
          placeholder="Lapeep"
          onChange={(event) => {
            const name = event.target.value;
            setForm((prev) => ({
              ...prev,
              name,
              ...(!touched ? { key: slugify(name) } : {}),
            }));
          }}
        />
      </FormField>
      <FormField label="System key" hint="Auto-generated; editable until created." required>
        <Input
          className="font-mono"
          value={form.key}
          disabled={busy}
          onChange={(event) => {
            setTouched(true);
            setForm((prev) => ({ ...prev, key: slugify(event.target.value) }));
          }}
        />
      </FormField>
      <FormField label="Business purpose">
        <Textarea
          rows={3}
          value={form.purpose}
          disabled={busy}
          onChange={(event) => setForm((prev) => ({ ...prev, purpose: event.target.value }))}
        />
      </FormField>
      <div className="grid gap-4 sm:grid-cols-3">
        <FormField label="Business unit" required>
          <Input
            list="onboarding-bu"
            value={form.unit}
            disabled={busy}
            onChange={(event) => setForm((prev) => ({ ...prev, unit: event.target.value }))}
          />
          <datalist id="onboarding-bu">
            {BUSINESS_UNITS.map((unit) => (
              <option key={unit} value={unit} />
            ))}
          </datalist>
        </FormField>
        <FormField label="Owner" required>
          <Input
            value={form.owner}
            disabled={busy}
            onChange={(event) => setForm((prev) => ({ ...prev, owner: event.target.value }))}
          />
        </FormField>
        <FormField label="Risk tier" required>
          <Select
            value={form.risk}
            disabled={busy}
            onChange={(event) => setForm((prev) => ({ ...prev, risk: event.target.value }))}
          >
            {RISK_TIERS.map((tier) => (
              <option key={tier} value={tier}>
                {tier}
              </option>
            ))}
          </Select>
        </FormField>
      </div>
      <Button
        disabled={busy || !form.name.trim() || !form.key || !form.unit.trim() || !form.owner.trim()}
        onClick={() => void onCreate(form)}
      >
        {busy ? "Creating…" : "Create AI System"}
      </Button>
    </StepShell>
  );
}

function AgentStep({
  systemName,
  existing,
  busy,
  onCreate,
  onDone,
}: {
  systemName: string;
  existing?: string;
  busy: boolean;
  onCreate: (form: { name: string; key: string; description: string }) => Promise<void>;
  onDone: () => void;
}) {
  const [touched, setTouched] = useState(false);
  const [form, setForm] = useState({ name: "", key: "", description: "" });

  if (existing) {
    return (
      <StepShell title="Step 2 — Agent">
        <DoneBanner label={`${existing} created`} onNext={onDone} />
      </StepShell>
    );
  }

  return (
    <StepShell title="Step 2 — Agent">
      <ContextChain items={[["AI System", systemName]]} />
      <FormField label="Agent name" required>
        <Input
          autoFocus
          value={form.name}
          disabled={busy}
          placeholder="Customer Support Agent"
          onChange={(event) => {
            const name = event.target.value;
            setForm((prev) => ({
              ...prev,
              name,
              ...(!touched ? { key: slugify(name) } : {}),
            }));
          }}
        />
      </FormField>
      <FormField label="Agent key" required>
        <Input
          className="font-mono"
          value={form.key}
          disabled={busy}
          onChange={(event) => {
            setTouched(true);
            setForm((prev) => ({ ...prev, key: slugify(event.target.value) }));
          }}
        />
      </FormField>
      <FormField label="Description / purpose (optional)">
        <Textarea
          rows={3}
          value={form.description}
          disabled={busy}
          onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
        />
      </FormField>
      <Button disabled={busy || !form.name.trim() || !form.key} onClick={() => void onCreate(form)}>
        {busy ? "Creating…" : "Create Agent"}
      </Button>
    </StepShell>
  );
}

function VersionStep({
  systemName,
  agentName,
  versionId,
  versionNumber,
  lifecycle,
  busy,
  onCreate,
  onTransition,
  onContinue,
}: {
  systemName: string;
  agentName: string;
  versionId?: string;
  versionNumber?: number;
  lifecycle?: string;
  busy: boolean;
  onCreate: (form: { model: string; tools: string }) => Promise<void>;
  onTransition: (status: string) => Promise<void>;
  onContinue: () => void;
}) {
  const [model, setModel] = useState("gpt-4o-mini");
  const [tools, setTools] = useState("lookup_order");
  const label = versionNumber != null ? `v${versionNumber}` : "v1";

  return (
    <StepShell title="Step 3 — Agent Version">
      <ContextChain
        items={[
          ["System", systemName],
          ["Agent", agentName],
          ["Version", label],
        ]}
      />
      {!versionId ? (
        <>
          <FormField label="Model" hint="Required before review.">
            <Input
              className="font-mono"
              value={model}
              disabled={busy}
              onChange={(event) => setModel(event.target.value)}
            />
          </FormField>
          <FormField label="Tools (optional)">
            <Input
              className="font-mono"
              value={tools}
              disabled={busy}
              onChange={(event) => setTools(event.target.value)}
            />
          </FormField>
          <Button disabled={busy || !model.trim()} onClick={() => void onCreate({ model, tools })}>
            {busy ? "Creating…" : "Create Version"}
          </Button>
        </>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3 rounded-md border border-base-200 bg-base-100 p-3 text-xs">
            <span className="font-mono font-semibold">{label}</span>
            {lifecycle ? <StatusBadge status={lifecycle} /> : null}
            <span className="text-ink-500">
              DRAFT → UNDER REVIEW → APPROVED. Only approved versions can be bound to a runtime
              identity.
            </span>
          </div>
          {lifecycle === "DRAFT" ? (
            <Button disabled={busy} onClick={() => void onTransition("UNDER_REVIEW")}>
              {busy ? "Submitting…" : "Submit for Review"}
            </Button>
          ) : null}
          {lifecycle === "UNDER_REVIEW" ? (
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => void onTransition("DRAFT")}
              >
                Return to Draft
              </Button>
              <Button disabled={busy} onClick={() => void onTransition("APPROVED")}>
                {busy ? "Approving…" : "Approve Version"}
              </Button>
            </div>
          ) : null}
          {lifecycle === "APPROVED" ? (
            <DoneBanner label={`${label} approved`} onNext={onContinue} />
          ) : null}
        </>
      )}
    </StepShell>
  );
}

function RuntimeStep({
  chain,
  systemKey,
  existing,
  busy,
  onCreate,
  onDone,
}: {
  chain: [string, string][];
  systemKey: string;
  existing?: string;
  busy: boolean;
  onCreate: (form: { name: string; environment: string }) => Promise<void>;
  onDone: () => void;
}) {
  const [name, setName] = useState(`${systemKey}-production`.slice(0, 63));
  const [environment, setEnvironment] = useState("production");

  if (existing) {
    return (
      <StepShell title="Step 4 — Runtime Identity">
        <DoneBanner label={`${existing} created`} onNext={onDone} />
      </StepShell>
    );
  }

  return (
    <StepShell title="Step 4 — Runtime Identity">
      <dl className="grid grid-cols-2 gap-3 rounded-md border border-base-200 bg-base-100 p-3 text-xs sm:grid-cols-4">
        {chain.slice(0, 3).map(([label, value]) => (
          <div key={label}>
            <dt className="text-[10px] uppercase text-ink-400">{label}</dt>
            <dd className="font-mono text-ink-800">{value}</dd>
          </div>
        ))}
        <div>
          <dt className="text-[10px] uppercase text-ink-400">Environment</dt>
          <dd>{environment}</dd>
        </div>
      </dl>
      <FormField label="Runtime identity name" required>
        <Input
          className="font-mono"
          value={name}
          disabled={busy}
          onChange={(event) => setName(slugify(event.target.value))}
        />
      </FormField>
      <FormField label="Environment">
        <Select
          value={environment}
          disabled={busy}
          onChange={(event) => setEnvironment(event.target.value)}
        >
          <option value="production">Production</option>
          <option value="staging">Staging</option>
          <option value="development">Development</option>
        </Select>
      </FormField>
      <p className="text-xs text-ink-500">
        After creation, issue a credential and connect your application to begin capturing governed
        runtime evidence.
      </p>
      <Button disabled={busy || !name} onClick={() => void onCreate({ name, environment })}>
        {busy ? "Creating…" : "Create Runtime Identity"}
      </Button>
    </StepShell>
  );
}

function CredentialStep({
  existing,
  busy,
  onIssue,
  onDone,
}: {
  existing?: string;
  busy: boolean;
  onIssue: () => Promise<void>;
  onDone: () => void;
}) {
  return (
    <StepShell title="Step 5 — Runtime Credential">
      {existing ? (
        <DoneBanner label={`Credential ${existing}… active`} onNext={onDone} />
      ) : (
        <>
          <p className="text-xs text-ink-500">
            The credential authenticates your application as this runtime identity. The secret is
            shown once.
          </p>
          <Button disabled={busy} onClick={() => void onIssue()}>
            {busy ? "Issuing…" : "Issue Runtime Credential"}
          </Button>
        </>
      )}
    </StepShell>
  );
}

function ConnectStep({
  systemKey,
  agentKey,
  versionLabel,
  runtimeName,
  secret,
  lastEvent,
  busy,
  onVerify,
  onComplete,
}: {
  systemKey: string;
  agentKey: string;
  versionLabel: string;
  runtimeName: string;
  secret: string;
  lastEvent?: string | null;
  busy: boolean;
  onVerify: () => void;
  onComplete: () => void;
}) {
  const snippet = `// Authenticate with your runtime credential (server-side only)
// Never place secrets in browser JavaScript.

const response = await fetch("https://api.example.com/v1/runtime/...", {
  headers: {
    Authorization: \`Bearer \${process.env.RAI_RUNTIME_CREDENTIAL}\`,
    "X-RAI-Client": "my-app",
  },
});`;

  return (
    <StepShell title="Step 6 — Connect Application">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-base-200 bg-base-100 p-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-[10px] font-semibold uppercase text-ink-400">
            Connection status
          </span>
          <StatusBadge status={lastEvent ? "CONNECTED" : "WAITING"} />
          {!lastEvent ? (
            <span className="text-ink-500">Waiting for first event…</span>
          ) : (
            <span className="text-ink-500">Last event {new Date(lastEvent).toLocaleString()}</span>
          )}
        </div>
        {lastEvent ? (
          <Button size="sm" onClick={onVerify}>
            Verify Trajectory
          </Button>
        ) : null}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {(
          [
            ["AI System", systemKey],
            ["Agent", agentKey],
            ["Version", versionLabel],
            ["Runtime Identity", runtimeName],
          ] as const
        ).map(([label, value]) => (
          <div key={label}>
            <div className="mb-1 text-[10px] font-semibold uppercase text-ink-400">{label}</div>
            <TechnicalCopyField value={value} />
          </div>
        ))}
      </div>

      {secret ? (
        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase text-ink-400">
            Credential (this session)
          </div>
          <TechnicalCopyField value={secret} />
        </div>
      ) : null}

      <div>
        <div className="mb-1 text-[10px] font-semibold uppercase text-ink-400">
          Example integration
        </div>
        <pre className="overflow-x-auto rounded-md border border-base-200 bg-base-100 p-3 font-mono text-[11px] text-ink-700">
          {snippet}
        </pre>
      </div>

      <p className="text-xs text-ink-500">
        Send traffic through your connected application. VigilRAI will authenticate the runtime
        credential, evaluate policy, and record a trajectory automatically.
      </p>
      <div className="flex flex-wrap gap-2">
        <Link href="/docs/quickstart">
          <Button variant="ghost" size="sm">
            Developer quickstart
          </Button>
        </Link>
        <Button size="sm" disabled={busy} onClick={onComplete}>
          {busy ? "Saving…" : "Mark complete"}
        </Button>
      </div>
    </StepShell>
  );
}

function VerifyStep({
  trajectory,
  onFinish,
  busy,
  complete,
}: {
  trajectory: TrajectorySummary | null;
  onFinish: () => Promise<void>;
  busy: boolean;
  complete: boolean;
}) {
  if (!trajectory) {
    return (
      <StepShell title="Step 7 — Verify First Trajectory">
        <p className="text-sm text-ink-500">
          Waiting for the first governed trajectory. Keep this page open while your application
          sends traffic.
        </p>
      </StepShell>
    );
  }

  return (
    <StepShell title="Step 7 — Verify First Trajectory">
      <div className="flex items-center gap-2 text-sm text-accent-700">
        ✓ VigilRAI is receiving runtime evidence.
      </div>
      <div className="mt-2 grid gap-3 rounded-md border border-base-200 bg-base-100 p-3 text-xs sm:grid-cols-4">
        <div>
          <div className="text-[10px] uppercase text-ink-400">Trajectory</div>
          <TechnicalValue>{trajectory.id}</TechnicalValue>
        </div>
        <div>
          <div className="text-[10px] uppercase text-ink-400">Status</div>
          <StatusBadge status={trajectory.status} />
        </div>
        <div>
          <div className="text-[10px] uppercase text-ink-400">Risk</div>
          {trajectory.assurance_summary?.highest ? (
            <StatusBadge status={trajectory.assurance_summary.highest} />
          ) : (
            "—"
          )}
        </div>
        <div>
          <div className="text-[10px] uppercase text-ink-400">Events</div>
          <span className="font-mono">{trajectory.event_count}</span>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Link href={`/runtime/trajectories/${trajectory.id}`}>
          <Button variant="secondary">Inspect Trajectory</Button>
        </Link>
        <Button disabled={busy || complete} onClick={() => void onFinish()}>
          {complete ? "Setup complete" : busy ? "Finishing…" : "Finish Setup"}
        </Button>
        {complete ? (
          <Link href="/dashboard">
            <Button>Go to Control Posture</Button>
          </Link>
        ) : null}
      </div>
    </StepShell>
  );
}
