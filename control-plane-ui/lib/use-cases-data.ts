export interface UseCase {
  slug: string;
  title: string;
  summary: string;
  architecture: string[];
  risks: string[];
  controls: string[];
  integration: string;
}

export const USE_CASES: UseCase[] = [
  {
    slug: "ai-sales-agent",
    title: "AI Sales Agent",
    summary:
      "Outbound and inbound sales agents that draft emails, update CRM records, and schedule meetings on behalf of reps.",
    architecture: [
      "Customer CRM and email systems connect through RAI SDK or REST proxy",
      "Runtime identity scoped to sales agent version and delegated user authority",
      "Tool calls (send_email, update_crm, book_meeting) pass through policy and approval gates",
      "Evidence captured for every action with trajectory linkage to deal context",
    ],
    risks: [
      "Unauthorized outreach to prospects outside approved segments",
      "Pricing or discount commitments beyond delegation scope",
      "PII leakage in generated email content",
      "Bulk actions exceeding rate or budget limits",
    ],
    controls: [
      "Content rules for tone, claims, and prohibited language",
      "Tool rules requiring approval for send_email above threshold",
      "Delegation scopes limiting CRM fields and recipient lists",
      "Runtime budgets on outbound volume per identity",
    ],
    integration: "Python SDK or TypeScript SDK with REST fallback for CRM webhooks",
  },
  {
    slug: "customer-support-ai",
    title: "Customer Support AI",
    summary:
      "Support agents that retrieve knowledge, draft responses, issue refunds, and escalate tickets.",
    architecture: [
      "Support platform integrates via RAI proxy or hooks into ticket workflow",
      "RAG domains govern which knowledge sources the agent may retrieve",
      "High-impact tools (refund, account_change) require human-in-the-loop approval",
      "Full trajectory from ticket open to resolution stored as audit evidence",
    ],
    risks: [
      "Incorrect refund or credit amounts",
      "Access to customer data outside ticket scope",
      "Hallucinated policy answers creating liability",
      "Failure to escalate sensitive or regulated requests",
    ],
    controls: [
      "RAG domain approval and leakage risk classification",
      "Tool rules with amount thresholds and mandatory approver roles",
      "Content evaluator for policy-sensitive responses",
      "Incident triggers on repeated violation patterns",
    ],
    integration:
      "REST API with proxy preview for gradual rollout; MCP hooks for IDE-adjacent tools",
  },
  {
    slug: "coding-agent",
    title: "Coding Agent",
    summary: "Autonomous coding assistants that edit repositories, run tests, and deploy changes.",
    architecture: [
      "IDE or CI pipeline connects through MCP or SDK integration",
      "Runtime identity bound to repository and branch scope",
      "Deploy and merge actions gated by deployment assurance and evaluation suites",
      "Trajectory graph links code changes to test runs and deployment receipts",
    ],
    risks: [
      "Unauthorized production deployments",
      "Secrets exfiltration via generated code or tool calls",
      "Dependency or license violations in suggested changes",
      "Destructive git operations without review",
    ],
    controls: [
      "Tool rules blocking deploy without passing evaluation gates",
      "Delegation scopes limiting repos, branches, and environments",
      "Content rules for secret patterns and prohibited imports",
      "Emergency suspend on anomaly detection",
    ],
    integration: "MCP server integration and TypeScript SDK for CI/CD pipelines",
  },
  {
    slug: "internal-knowledge-assistant",
    title: "Internal Knowledge Assistant",
    summary: "Enterprise search and Q&A over internal documents, wikis, and structured data.",
    architecture: [
      "Knowledge connectors registered in RAI registry with classification metadata",
      "RAG domains enforce source allowlists and sensitivity boundaries",
      "Query and retrieval events logged; generated answers evaluated for leakage",
      "Human identity delegation determines document access scope",
    ],
    risks: [
      "Cross-department data leakage via over-broad retrieval",
      "Exposure of confidential M&A or HR documents",
      "Stale or unapproved content presented as authoritative",
      "Prompt injection via untrusted document content",
    ],
    controls: [
      "RAG domain source approval workflow",
      "Data classification tags on registered sources",
      "Content evaluator with fail-closed on high-confidence leakage",
      "Audit logs for every retrieval and generation event",
    ],
    integration: "Python SDK for backend services; REST for lightweight chat frontends",
  },
  {
    slug: "government-citizen-assistant",
    title: "Government / Citizen Assistant",
    summary:
      "Public-facing assistants that help citizens navigate services, forms, and eligibility.",
    architecture: [
      "Citizen portal connects through hardened REST proxy with tenant isolation",
      "Policy obligations mapped from regulatory documents to content and tool rules",
      "Runtime identities scoped per service channel with strict delegation",
      "Evidence packages generated for periodic governance reviews",
    ],
    risks: [
      "Incorrect eligibility or benefit guidance",
      "Bias in citizen-facing language or outcomes",
      "Unauthorized access to citizen records",
      "Non-compliance with accessibility or records retention requirements",
    ],
    controls: [
      "Regulatory policy document linkage and obligation tracking",
      "Mandatory human review for consequential determinations",
      "Tenant isolation and jurisdiction-scoped data boundaries",
      "Governance reviews and attestation workflows",
    ],
    integration: "REST API with mTLS-ready proxy; OIDC for citizen and operator identity",
  },
  {
    slug: "high-risk-enterprise-agent",
    title: "High-Risk Enterprise Agent",
    summary:
      "Agents performing financial transactions, legal document generation, or safety-critical operations.",
    architecture: [
      "Multi-layer approval chain: policy → risk → human → execution",
      "Deployment gates require evaluation suite passage before production activation",
      "Continuous risk monitoring with intervention and emergency suspend capabilities",
      "Portfolio oversight dashboards for executive governance decisions",
    ],
    risks: [
      "Financial loss from unauthorized transactions",
      "Legal exposure from non-compliant document generation",
      "Safety incidents from autonomous physical-world actions",
      "Regulatory penalties from inadequate audit trails",
    ],
    controls: [
      "Fail-closed enforcement on any policy or credential ambiguity",
      "Deployment assurance with evaluation waivers requiring executive approval",
      "Runtime budgets, anomaly detection, and emergency containment",
      "Evidence packages and compliance report generation",
    ],
    integration:
      "Full SDK integration with REST for legacy systems; proxy preview for phased enforcement",
  },
];

export function getUseCase(slug: string): UseCase | undefined {
  return USE_CASES.find((uc) => uc.slug === slug);
}
