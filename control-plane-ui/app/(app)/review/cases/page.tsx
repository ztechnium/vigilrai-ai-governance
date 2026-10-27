"use client";

import { useEffect, useState } from "react";
import { getCases } from "@/lib/api";
import type { CaseSummary } from "@/lib/types";
import Link from "next/link";

type CaseStatus = "open" | "in-progress" | "resolved";

export default function CasesPage() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<CaseStatus | "all">("all");

  useEffect(() => {
    async function fetchCases() {
      try {
        setLoading(true);
        const status = filterStatus === "all" ? undefined : filterStatus;
        const data = await getCases(status);
        setCases(data);
      } catch (err) {
        console.error("Failed to fetch cases:", err);
        setError(err instanceof Error ? err.message : "Failed to load cases");
      } finally {
        setLoading(false);
      }
    }

    fetchCases();
  }, [filterStatus]);

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
          <h3 className="text-red-800 font-medium">Error loading cases</h3>
          <p className="text-red-600 text-sm mt-1">{error}</p>
        </div>
      </div>
    );
  }

  const getStatusBadge = (status?: string) => {
    const colors: Record<string, string> = {
      open: "bg-red-100 text-red-800",
      "in-progress": "bg-yellow-100 text-yellow-800",
      resolved: "bg-green-100 text-green-800",
    };
    return colors[status || "open"] || "bg-gray-100 text-gray-800";
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Human Review Cases</h1>
        <p className="text-sm text-gray-500 mt-1">
          Cases requiring human review and approval ({cases.length} total)
        </p>
      </div>

      {/* Status Filter */}
      <div className="flex gap-3">
        {["all", "open", "in-progress", "resolved"].map((status) => (
          <button
            key={status}
            onClick={() => setFilterStatus(status as any)}
            className={`px-4 py-2 rounded-lg font-medium transition ${
              filterStatus === status
                ? "bg-blue-600 text-white"
                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
          >
            {status === "all" ? "All Cases" : status.charAt(0).toUpperCase() + status.slice(1)}
          </button>
        ))}
      </div>

      {cases.length === 0 ? (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-12 text-center">
          <div className="text-gray-400 text-5xl mb-4">📋</div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">
            {filterStatus === "all" ? "No cases" : `No ${filterStatus} cases`}
          </h3>
          <p className="text-gray-500">Cases requiring review will appear here</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Case ID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Execution
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Owner
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Reason Codes
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Created
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {cases.map((caseItem) => (
                <tr key={caseItem.case_id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <Link
                      href={`/review/cases/${caseItem.case_id}`}
                      className="text-blue-600 hover:text-blue-800 font-medium text-sm"
                    >
                      {caseItem.case_id.slice(0, 8)}...
                    </Link>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {caseItem.execution_id.slice(0, 8)}...
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`px-2 py-1 text-xs font-medium rounded ${getStatusBadge(caseItem.status)}`}
                    >
                      {caseItem.status || "open"}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {caseItem.owner || "—"}
                  </td>
                  <td className="px-6 py-4 text-sm">
                    {caseItem.reason_codes && caseItem.reason_codes.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {caseItem.reason_codes.slice(0, 2).map((code) => (
                          <span
                            key={code}
                            className="px-2 py-1 text-xs bg-purple-50 text-purple-700 rounded"
                          >
                            {code}
                          </span>
                        ))}
                        {caseItem.reason_codes.length > 2 && (
                          <span className="text-xs text-gray-500">
                            +{caseItem.reason_codes.length - 2} more
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="text-gray-500">—</span>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {caseItem.created_at ? new Date(caseItem.created_at).toLocaleDateString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h3 className="text-blue-900 font-medium text-sm">📰 About Cases</h3>
        <p className="text-blue-700 text-sm mt-1">
          Cases are created when an AI execution requires human review. Reviewers can inspect the
          execution details, reason codes, and actions, then resolve with step-up verification if
          needed.
        </p>
      </div>
    </div>
  );
}
