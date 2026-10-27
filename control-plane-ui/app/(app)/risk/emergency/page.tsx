"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { SectionHeader } from "@/components/section-header";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { Table } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/registry/form-field";
import {
  emergencyReactivateRuntimeIdentity,
  emergencySuspendRuntimeIdentity,
  getRuntimeIdentities,
} from "@/lib/api";
import type { RuntimeIdentitySummary } from "@/lib/types";

export default function EmergencyControlsPage() {
  const [identities, setIdentities] = useState<RuntimeIdentitySummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<"suspend" | "reactivate" | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getRuntimeIdentities();
      setIdentities(Array.isArray(res.data) ? res.data : []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load identities");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const suspended = useMemo(() => identities.filter((i) => i.status === "SUSPENDED"), [identities]);

  async function runAction() {
    if (!confirmId || !confirmAction || !reason.trim()) {
      setError("Reason is required and you must confirm the action.");
      return;
    }
    setBusyId(confirmId);
    setError(null);
    try {
      if (confirmAction === "suspend") {
        await emergencySuspendRuntimeIdentity(confirmId, reason.trim(), true);
      } else {
        await emergencyReactivateRuntimeIdentity(confirmId, reason.trim(), true);
      }
      setConfirmId(null);
      setConfirmAction(null);
      setReason("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Emergency action failed");
    } finally {
      setBusyId(null);
    }
  }

  const rows = useMemo(
    () =>
      identities.map((i) => [
        <Link
          key={`${i.id}-name`}
          className="underline"
          href={`/governance/runtime-identities/${i.id}`}
        >
          {i.name || i.id.slice(0, 8)}
        </Link>,
        <StatusBadge key={`${i.id}-st`} status={i.status} />,
        i.environment || "—",
        <div key={`${i.id}-actions`} className="flex gap-2">
          {i.status === "ACTIVE" && (
            <Button
              variant="outline"
              disabled={busyId === i.id}
              onClick={() => {
                setConfirmId(i.id);
                setConfirmAction("suspend");
              }}
            >
              Suspend
            </Button>
          )}
          {i.status === "SUSPENDED" && (
            <Button
              variant="outline"
              disabled={busyId === i.id}
              onClick={() => {
                setConfirmId(i.id);
                setConfirmAction("reactivate");
              }}
            >
              Reactivate
            </Button>
          )}
        </div>,
      ]),
    [identities, busyId],
  );

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Emergency Controls"
        subtitle="Runtime Identity kill switch — requires confirmation, reason, and risk:emergency authorization. Suspended identities fail closed in WP2/WP4."
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <Panel>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            Suspended identities
          </p>
          <p className="mt-2 text-3xl font-semibold">{suspended.length}</p>
        </Panel>
        <Panel>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Total identities</p>
          <p className="mt-2 text-3xl font-semibold">{identities.length}</p>
        </Panel>
      </div>
      {confirmId && confirmAction && (
        <Panel title={`Confirm ${confirmAction}`}>
          <p className="mb-3 text-sm text-muted-foreground">
            This action is audited and enforced server-side. Downstream invocations will be blocked
            while suspended.
          </p>
          <FormField label="Reason (required)">
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Explain why this emergency action is required"
            />
          </FormField>
          <div className="mt-4 flex gap-2">
            <Button disabled={!!busyId || !reason.trim()} onClick={() => void runAction()}>
              Confirm {confirmAction}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setConfirmId(null);
                setConfirmAction(null);
                setReason("");
              }}
            >
              Cancel
            </Button>
          </div>
        </Panel>
      )}
      <Panel title="Runtime identities">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : error ? (
          <p className="text-sm text-red-600">{error}</p>
        ) : identities.length === 0 ? (
          <p className="text-sm text-muted-foreground">No runtime identities.</p>
        ) : (
          <Table columns={["Identity", "Status", "Environment", "Actions"]} rows={rows} />
        )}
      </Panel>
    </div>
  );
}
