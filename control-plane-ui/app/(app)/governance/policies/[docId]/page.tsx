"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Panel } from "@/components/registry/panel";
import { StatusBadge } from "@/components/registry/status-badge";
import { SectionHeader } from "@/components/section-header";
import { getPolicyDetail, getPolicyObligations, getPolicySource } from "@/lib/api";
import type { PolicyDocumentDetail, PolicyObligation, PolicySourceDetail } from "@/lib/types";

type TabType = "overview" | "content" | "obligations" | "derived";

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

export default function PolicyDetailPage() {
  const params = useParams();
  const docId = params.docId as string;

  const [source, setSource] = useState<PolicySourceDetail | null>(null);
  const [legacy, setLegacy] = useState<PolicyDocumentDetail | null>(null);
  const [legacyObligations, setLegacyObligations] = useState<PolicyObligation[]>([]);
  const [activeTab, setActiveTab] = useState<TabType>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchPolicy() {
      try {
        setLoading(true);
        setError(null);
        if (isUuid(docId)) {
          const res = await getPolicySource(docId);
          setSource(res.data);
          setLegacy(null);
        } else {
          const [policyData, obligationsData] = await Promise.all([
            getPolicyDetail(docId),
            getPolicyObligations(docId),
          ]);
          setLegacy(policyData);
          setLegacyObligations(obligationsData);
          setSource(null);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load policy");
      } finally {
        setLoading(false);
      }
    }

    if (docId) {
      void fetchPolicy();
    }
  }, [docId]);

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading policy…</p>;
  }

  if (error || (!source && !legacy)) {
    return (
      <div className="space-y-4">
        <Link href="/governance/policies" className="text-sm text-accent-600 hover:text-accent-700">
          ← Back to Policy Library
        </Link>
        <p className="text-sm text-destructive">{error || "Policy not found"}</p>
      </div>
    );
  }

  const title = source?.title ?? legacy?.doc_id ?? "Policy";
  const tabs: { id: TabType; label: string }[] = source
    ? [
        { id: "overview", label: "Overview" },
        { id: "content", label: "Source Content" },
        { id: "obligations", label: "Obligations" },
        { id: "derived", label: "Derived Rules" },
      ]
    : [
        { id: "overview", label: "Overview" },
        { id: "obligations", label: "Obligations" },
      ];

  return (
    <div className="space-y-6" data-testid="policy-detail-page">
      <div>
        <Link href="/governance/policies" className="text-sm text-accent-600 hover:text-accent-700">
          ← Back to Policy Library
        </Link>
      </div>

      <SectionHeader
        title={title}
        subtitle="Source policy material — not an executable RAI Rule"
        actions={source ? <StatusBadge status={source.status} /> : undefined}
      />

      <div className="flex flex-wrap gap-2 border-b border-border pb-2">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`rounded-md px-3 py-1.5 text-sm ${
              activeTab === tab.id
                ? "bg-base-200 font-medium text-ink-900"
                : "text-ink-500 hover:text-ink-800"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "overview" && (
        <Panel>
          <dl className="grid gap-4 text-sm md:grid-cols-2">
            {source ? (
              <>
                <div>
                  <dt className="text-muted-foreground">Source type</dt>
                  <dd>{source.source_type}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Authority</dt>
                  <dd>{source.authority ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Jurisdiction</dt>
                  <dd>{source.jurisdiction ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Version</dt>
                  <dd>{source.version ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Content digest</dt>
                  <dd className="break-all font-mono text-xs">{source.content_digest ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Ingestion</dt>
                  <dd>{source.ingestion_status}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Source URI</dt>
                  <dd className="break-all">{source.source_uri ?? "—"}</dd>
                </div>
              </>
            ) : (
              <>
                <div>
                  <dt className="text-muted-foreground">Document ID</dt>
                  <dd>{legacy?.doc_id}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Country</dt>
                  <dd>{legacy?.country}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Authority</dt>
                  <dd>{legacy?.authority}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Type</dt>
                  <dd>{legacy?.doc_type}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Version</dt>
                  <dd>{legacy?.version ?? "—"}</dd>
                </div>
              </>
            )}
          </dl>
        </Panel>
      )}

      {activeTab === "content" && source && (
        <Panel>
          <pre className="whitespace-pre-wrap text-sm text-ink-700">
            {source.content_text || "No stored text body for this source."}
          </pre>
        </Panel>
      )}

      {activeTab === "obligations" && (
        <Panel>
          {source ? (
            source.obligations.length === 0 ? (
              <p className="text-sm text-muted-foreground">No obligations extracted yet.</p>
            ) : (
              <ul className="space-y-3">
                {source.obligations.map((o) => (
                  <li key={o.id} className="rounded-md border border-border p-3 text-sm">
                    <div className="font-medium">{o.section_ref || o.topic || o.id}</div>
                    <p className="mt-1 text-muted-foreground">{o.text || "—"}</p>
                    <div className="mt-2 text-xs">Status: {o.status}</div>
                  </li>
                ))}
              </ul>
            )
          ) : legacyObligations.length === 0 ? (
            <p className="text-sm text-muted-foreground">No obligations.</p>
          ) : (
            <ul className="space-y-3">
              {legacyObligations.map((o) => (
                <li key={o.obligation_id} className="rounded-md border border-border p-3 text-sm">
                  <div className="font-medium">{o.section_ref || o.obligation_id}</div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      )}

      {activeTab === "derived" && source && (
        <Panel>
          {source.derived_rules.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No derived RAI Rules linked yet. Creating rules from obligations must leave them
              inactive until human review.
            </p>
          ) : (
            <ul className="space-y-2 text-sm">
              {source.derived_rules.map((r) => (
                <li key={r.id} className="flex gap-3">
                  <span className="font-medium">{r.rule_type}</span>
                  <Link
                    href="/governance/rai-rules"
                    className="text-accent-600 hover:text-accent-700"
                  >
                    {r.rule_id}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      )}
    </div>
  );
}
