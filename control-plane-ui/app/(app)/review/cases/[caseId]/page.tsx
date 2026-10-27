"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getCaseDetail, resolveCase } from "@/lib/api";
import type { CaseDetail } from "@/lib/types";

export default function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const router = useRouter();
  const [record, setRecord] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resolution, setResolution] = useState("");
  const [owner, setOwner] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    getCaseDetail(caseId)
      .then((data) => {
        if (!active) return;
        setRecord(data);
      })
      .catch((err: Error) => {
        if (!active) return;
        setError(err.message);
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [caseId]);

  const onResolve = async () => {
    if (!record) return;
    setSubmitting(true);
    setSubmitError(null);

    try {
      await resolveCase(record.case_id, {
        status: "resolved",
        resolution: resolution || undefined,
        owner: owner || undefined,
      });
      const updated = await getCaseDetail(record.case_id);
      setRecord(updated);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to resolve case");
    } finally {
      setSubmitting(false);
    }
  };

  const badgeClass = (status?: string) => {
    const colors: Record<string, string> = {
      open: "bg-red-100 text-red-800",
      "in-progress": "bg-yellow-100 text-yellow-800",
      resolved: "bg-green-100 text-green-800",
    };
    return colors[status || "open"] || "bg-gray-100 text-gray-800";
  };

  if (loading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-200 rounded w-1/4"></div>
          <div className="h-64 bg-gray-200 rounded"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <h3 className="text-red-800 font-medium">Error loading case</h3>
          <p className="text-red-600 text-sm mt-1">{error}</p>
        </div>
      </div>
    );
  }

  if (!record) {
    return null;
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Case {record.case_id}</h1>
          <p className="text-sm text-gray-500 mt-1">Human review case detail and actions</p>
        </div>
        <button
          onClick={() => router.back()}
          className="px-3 py-2 text-sm rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50"
        >
          Back
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="text-xs text-gray-500">Status</p>
          <span
            className={`inline-flex mt-2 px-2 py-1 text-xs font-medium rounded ${badgeClass(record.status)}`}
          >
            {record.status || "open"}
          </span>
        </div>
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="text-xs text-gray-500">Execution</p>
          <div className="mt-2 text-sm text-gray-900">{record.execution_id}</div>
          <Link
            href={`/runtime/executions/${record.execution_id}/explainability`}
            className="text-xs text-blue-600 hover:text-blue-800"
          >
            View explainability
          </Link>
        </div>
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="text-xs text-gray-500">Owner</p>
          <div className="mt-2 text-sm text-gray-900">{record.owner || "Unassigned"}</div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="text-sm font-medium text-gray-900">Reason Codes</p>
          {record.reason_codes && record.reason_codes.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-2">
              {record.reason_codes.map((code) => (
                <span key={code} className="px-2 py-1 text-xs bg-purple-50 text-purple-700 rounded">
                  {code}
                </span>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-sm text-gray-500">No reason codes</p>
          )}
        </div>

        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="text-sm font-medium text-gray-900">Execution Context</p>
          <div className="mt-2 space-y-2 text-sm text-gray-700">
            <div className="flex items-center justify-between">
              <span>System</span>
              <span>{record.execution?.system_id || "-"}</span>
            </div>
            <div className="flex items-center justify-between">
              <span>Module</span>
              <span>{record.execution?.module || "-"}</span>
            </div>
            <div className="flex items-center justify-between">
              <span>Decision</span>
              <span>{record.execution?.decision || "-"}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="text-sm font-medium text-gray-900">Actions</p>
          {record.actions && Object.keys(record.actions).length > 0 ? (
            <pre className="mt-2 text-xs text-gray-700 whitespace-pre-wrap">
              {JSON.stringify(record.actions, null, 2)}
            </pre>
          ) : (
            <p className="mt-2 text-sm text-gray-500">No actions recorded</p>
          )}
        </div>

        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="text-sm font-medium text-gray-900">Resolution</p>
          <div className="mt-2 text-sm text-gray-700">{record.resolution || "Not resolved"}</div>
          <div className="mt-3 text-xs text-gray-500">
            Created: {record.created_at ? new Date(record.created_at).toLocaleString() : "-"}
          </div>
          <div className="text-xs text-gray-500">
            Updated: {record.updated_at ? new Date(record.updated_at).toLocaleString() : "-"}
          </div>
        </div>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
        <div>
          <h3 className="text-sm font-medium text-gray-900">Resolve Case</h3>
          <p className="text-xs text-gray-500 mt-1">
            Resolving a case may require step-up verification in production.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <label className="text-xs text-gray-600">Resolution note</label>
            <input
              value={resolution}
              onChange={(event) => setResolution(event.target.value)}
              className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm"
              placeholder="confirmed_block"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-gray-600">Owner (optional)</label>
            <input
              value={owner}
              onChange={(event) => setOwner(event.target.value)}
              className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm"
              placeholder="admin"
            />
          </div>
        </div>
        {submitError ? <p className="text-xs text-red-600">{submitError}</p> : null}
        <button
          onClick={onResolve}
          disabled={submitting}
          className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium disabled:opacity-60"
        >
          {submitting ? "Resolving..." : "Mark Resolved"}
        </button>
      </div>
    </div>
  );
}
