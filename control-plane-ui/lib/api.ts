import type {
  ExecutionAuditSummary,
  ExecutionExplainability,
  PromptSummary,
  PromptDetail,
  PromptVersionSummary,
  AllowlistEntry,
  PromptRuleSummary,
  RaiRuleSummary,
  PolicyDocumentSummary,
  PolicyDocumentDetail,
  PolicyObligation,
  RagDomainSummary,
  RagDomainDetail,
  RagSourceSummary,
  CaseSummary,
  CaseDetail,
  ApiKeySummary,
  IssuedApiKey,
  SystemSummary,
  ProviderSettings,
  ProviderStatus,
  ProviderTestResult,
  ProviderModelListResponse,
  RbacContext,
  RoleSummary,
  UserSummary,
  AISystemSummary,
  AISystemConfigurationProvenance,
  AgentSummary,
  AgentVersionSummary,
  VersionDependency,
  MaterialChange,
  ToolResourceSummary,
  MCPServerSummary,
  DataSourceSummary,
  ModelResourceSummary,
  ExternalServiceSummary,
  RiskAssessmentSummary,
  AISystemHierarchy,
  RuntimeIdentitySummary,
  RuntimeCredentialSummary,
  DelegationSummary,
  DelegationScope,
  DelegationResourceCatalog,
  DelegationScopeSelection,
  ApprovalRequestSummary,
  ApprovalRequestDetail,
  PolicyCollectionDetail,
  ContentRuleSummary,
  ToolRuleSummary,
  ToolRuleConditionSummary,
  EnforcementReceiptDetail,
  EnforcementReceiptSummary,
  RuntimeActionResult,
  RuntimeTestRequest,
  ClientIntegrationSummary,
  ClientIntegrationSetup,
  TrajectoryDetail,
  TrajectoryGraph,
  TrajectoryListResponse,
  TrajectoryLifecycle,
  TrajectoryRiskFindings,
  TrajectorySummary,
  ConversationListResponse,
  ConversationPolicyTrigger,
  RuntimeConversationSummary,
  AuditSearchResponse,
  ObservedPromptSummary,
  ObservedPromptDetail,
  AllPolicyRulesResponse,
  ResourceCatalogResponse,
  UnifiedRaiRulesResponse,
  PolicyLibraryListResponse,
  PolicySourceDetail,
  PolicySourceSummary,
  EvidenceEvent,
  EvidenceEventDetail,
  EvidenceFinding,
  EvidenceArtifact,
  RiskOverview,
  RuntimeRiskFinding,
  RiskMonitor,
  InterventionDecision,
  PolicyRecommendation,
  ContentEvaluatorConfig,
  TrajectoryRiskBundle,
  EvaluationSuite,
  EvaluationSuiteDetail,
  EvaluationCase,
  EvaluationRequirement,
  EvaluationPlan,
  EvaluationRun,
  EvaluationRunDetail,
  DeploymentGate,
  DeploymentGateEvaluationResult,
  VersionAssurance,
  DeploymentReadiness,
  EvaluationWaiver,
  RuntimeBudget,
  RuntimeBudgetCheck,
  Organization,
  OrganizationGovernanceProfile,
  OrganizationMembership,
  Department,
  AISystemAccountability,
  GovernanceClassification,
  ControlFramework,
  ControlAssessment,
  GovernanceReview,
  GovernanceException,
  AIIncident,
  IncidentCorrectiveAction,
  GovernanceEvidencePackage,
  Pilot,
  PilotReadinessResult,
  PilotDashboard,
  DueWork,
  PortfolioSummary,
  PortfolioDashboard,
  PortfolioInventoryResponse,
  PortfolioRiskPosture,
  PortfolioAssurancePosture,
  PortfolioControlPosture,
  PortfolioIncidentPosture,
  PortfolioRuntimeActivity,
  PortfolioEvidenceResponse,
  PortfolioOwnershipResponse,
  PortfolioAttentionQueue,
  PortfolioTrendsResponse,
  PortfolioChangesResponse,
  PortfolioExportResponse,
  PortfolioReport,
  PortfolioReportListResponse,
  PortfolioReportSchedule,
  PortfolioReportScheduleListResponse,
  ExecutiveGovernanceDecision,
  ExecutiveGovernanceDecisionListResponse,
  ReportSummary,
  RiskReport,
  PolicyReport,
  BudgetReport,
  RuntimeReport,
  AssuranceReport,
  AISystemReport,
  ConversationReport,
  ReportSnapshot,
  ReportFilters,
} from "@/lib/types";
export const ADMIN_AUTH_TOKEN_STORAGE_KEY = "rai.cp.adminAuthToken";
export const ADMIN_REFRESH_TOKEN_STORAGE_KEY = "rai.cp.adminRefreshToken";
export const ACTIVE_ORG_STORAGE_KEY = "rai.cp.activeOrganizationId";
export const PLATFORM_ADMIN_STORAGE_KEY = "rai.cp.isPlatformAdmin";

export interface ApiResponse<T> {
  data: T;
  traceId?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public traceId?: string,
  ) {
    super(message);
  }
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";
const ADMIN_TOKEN = process.env.NEXT_PUBLIC_ADMIN_TOKEN;

/** Persist SaaS access + refresh tokens (refresh keeps sessions alive past access TTL). */
export function persistSessionTokens(accessToken: string, refreshToken?: string | null) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ADMIN_AUTH_TOKEN_STORAGE_KEY, accessToken);
  if (refreshToken) {
    window.localStorage.setItem(ADMIN_REFRESH_TOKEN_STORAGE_KEY, refreshToken);
  }
}

export function clearSessionTokens() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ADMIN_AUTH_TOKEN_STORAGE_KEY);
  window.localStorage.removeItem(ADMIN_REFRESH_TOKEN_STORAGE_KEY);
}

function buildHeaders() {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  const isBrowser = typeof window !== "undefined";
  const authToken = isBrowser ? window.localStorage.getItem(ADMIN_AUTH_TOKEN_STORAGE_KEY) : null;

  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }

  if (ADMIN_TOKEN) {
    headers["X-Admin-Token"] = ADMIN_TOKEN;
  }

  return headers;
}

async function parseResponse<T>(response: Response): Promise<ApiResponse<T>> {
  const traceId = response.headers.get("x-trace-id") ?? undefined;

  if (!response.ok) {
    let message = `API request failed: ${response.status}`;
    try {
      const payload = (await response.json()) as {
        message?: string;
        detail?: string | { message?: string };
      };
      if (payload?.message) {
        message = payload.message;
      } else if (typeof payload?.detail === "string") {
        message = payload.detail;
      } else if (payload?.detail && typeof payload.detail === "object" && payload.detail.message) {
        message = payload.detail.message;
      }
    } catch {
      // ignore JSON parse errors
    }
    throw new ApiError(message, response.status, traceId);
  }

  const data = (await response.json()) as T;
  return { data, traceId };
}

let refreshInFlight: Promise<boolean> | null = null;

/** Attempt to rotate the access JWT using the stored refresh token. */
export async function refreshAccessTokenIfNeeded(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  const refreshToken = window.localStorage.getItem(ADMIN_REFRESH_TOKEN_STORAGE_KEY);
  if (!refreshToken) return false;

  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/v1/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
          cache: "no-store",
        });
        if (!response.ok) {
          clearSessionTokens();
          return false;
        }
        const body = (await response.json()) as {
          access_token?: string;
          refresh_token?: string;
        };
        if (!body.access_token) {
          clearSessionTokens();
          return false;
        }
        persistSessionTokens(body.access_token, body.refresh_token ?? refreshToken);
        return true;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }

  return refreshInFlight;
}

async function request<T>(path: string, init?: RequestInit): Promise<ApiResponse<T>> {
  const doFetch = () =>
    fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        ...buildHeaders(),
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });

  let response = await doFetch();

  // Expired access JWT → rotate via refresh token once, then retry.
  if (
    response.status === 401 &&
    path !== "/v1/auth/login" &&
    path !== "/v1/auth/refresh" &&
    path !== "/v1/auth/forgot-password" &&
    path !== "/v1/auth/reset-password" &&
    path !== "/admin/api/auth/login"
  ) {
    const refreshed = await refreshAccessTokenIfNeeded();
    if (refreshed) {
      response = await doFetch();
    }
  }

  return parseResponse<T>(response);
}

export function apiGet<T>(path: string): Promise<ApiResponse<T>> {
  return request<T>(path);
}

export function apiPost<T>(path: string, body: unknown): Promise<ApiResponse<T>> {
  return request<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function apiPut<T>(path: string, body: unknown): Promise<ApiResponse<T>> {
  return request<T>(path, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function apiPatch<T>(path: string, body: unknown): Promise<ApiResponse<T>> {
  return request<T>(path, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// Helper to unwrap ApiResponse and return just the data
async function unwrapResponse<T>(promise: Promise<ApiResponse<T>>): Promise<T> {
  const response = await promise;
  return response.data;
}

export function apiDelete<T>(path: string): Promise<ApiResponse<T>> {
  return request<T>(path, { method: "DELETE" });
}

export function adminLogin(payload: { email: string; password: string }) {
  return apiPost<{
    access_token: string;
    token_type: "bearer";
    user: { email: string; user_id: string; roles: string[] };
  }>("/admin/api/auth/login", payload);
}

export function saasLogin(payload: { email: string; password: string }) {
  return apiPost<{
    access_token: string;
    refresh_token: string;
    token_type: "bearer";
    user: { id: string; email: string; name: string; email_verified: boolean };
    roles: string[];
    memberships: Array<{ id: string; role: string }>;
    welcome_completed: boolean;
    platform_roles: string[];
  }>("/v1/auth/login", payload);
}

export function refreshSession(refreshToken: string) {
  return apiPost<{
    access_token: string;
    refresh_token: string;
    token_type: "bearer";
  }>("/v1/auth/refresh", { refresh_token: refreshToken });
}

export function getAuthMe() {
  return apiGet<{
    user: { id: string; email: string; name: string; email_verified: boolean };
    roles: string[];
    memberships: Array<{ id: string; role: string }>;
    welcome_completed: boolean;
    platform_roles: string[];
  }>("/v1/auth/me");
}

export function verifyEmailToken(token: string) {
  return apiPost<{ status: string; email_verified: boolean; welcome_email_sent?: boolean }>(
    "/v1/auth/verify-email",
    { token },
  );
}

export function resendVerificationEmail(email: string) {
  return apiPost<{ status?: string; email_sent?: boolean; message?: string }>(
    "/v1/auth/resend-verification",
    { email },
  );
}

export function forgotPassword(email: string) {
  return apiPost<{ status: string; message: string }>("/v1/auth/forgot-password", {
    email,
  });
}

export function resetPassword(payload: { token: string; new_password: string }) {
  return apiPost<{ status: string }>("/v1/auth/reset-password", payload);
}

export function getAdminMe() {
  return apiGet<{ email: string; user_id: string; roles: string[] }>("/admin/api/auth/me");
}

// Runtime visibility
export function queryExecutions(payload: {
  limit?: number;
  system_id?: string;
  prompt_id?: string;
  decision?: string;
}) {
  return apiPost<ExecutionAuditSummary[]>("/admin/api/executions/query", payload);
}

export function getExecutionExplainability(executionId: string) {
  return apiGet<ExecutionExplainability>(`/admin/api/executions/${executionId}`);
}

// Legacy prompt-catalog admin APIs (deprecated product surface).
// RAI does not manage application prompt templates/persona.
// Prefer Runtime → Conversations / Trajectories for observed content.
// Do not build new UI on these endpoints; PromptCatalogService is Phase-C cleanup.
/** @deprecated Prefer runtime conversations/trajectories for observed prompts. */
export function getPrompts() {
  return apiGet<PromptSummary[]>("/admin/api/prompts");
}

/** @deprecated Prefer runtime conversations/trajectories for observed prompts. */
export function getPromptDetail(promptId: string) {
  return apiGet<PromptDetail>(`/admin/api/prompts/${promptId}`);
}

/** @deprecated Prefer runtime conversations/trajectories for observed prompts. */
export function getPromptVersions(promptId: string) {
  return apiGet<PromptVersionSummary[]>(`/admin/api/prompts/${promptId}/versions`);
}

/** @deprecated Prefer runtime conversations/trajectories for observed prompts. */
export function getAllowlist(promptId: string, version: number) {
  return apiGet<AllowlistEntry[]>(`/admin/api/prompts/${promptId}/versions/${version}/allowlist`);
}

/** @deprecated Prefer runtime conversations/trajectories for observed prompts. */
export function getPromptRules(promptId: string, version: number) {
  return apiGet<PromptRuleSummary[]>(`/admin/api/prompts/${promptId}/versions/${version}/rules`);
}

export function getRaiRules() {
  return apiGet<RaiRuleSummary[]>("/admin/api/rai-rules");
}

export function getPolicies(): Promise<PolicyDocumentSummary[]> {
  return unwrapResponse(apiGet<PolicyDocumentSummary[]>("/admin/api/policies"));
}

export function getPolicyDetail(docId: string): Promise<PolicyDocumentDetail> {
  return unwrapResponse(apiGet<PolicyDocumentDetail>(`/admin/api/policies/${docId}`));
}

export function uploadPolicy(data: {
  doc_id: string;
  country: string;
  authority: string;
  doc_type: string;
  version?: string;
  effective_date?: string;
  content_ref?: string;
}): Promise<PolicyDocumentDetail> {
  return unwrapResponse(apiPost<PolicyDocumentDetail>("/admin/api/policies", data));
}

export function getPolicyObligations(docId: string): Promise<PolicyObligation[]> {
  return unwrapResponse(apiGet<PolicyObligation[]>(`/admin/api/policies/${docId}/obligations`));
}

export function getRagDomains(): Promise<RagDomainSummary[]> {
  return unwrapResponse(apiGet<RagDomainSummary[]>("/admin/api/rag-domains"));
}

export function getRagDomainDetail(domainId: string): Promise<RagDomainDetail> {
  return unwrapResponse(apiGet<RagDomainDetail>(`/admin/api/rag-domains/${domainId}`));
}

export function createRagDomain(data: {
  domain_id: string;
  name: string;
  description?: string;
  country?: string;
  owner_email?: string;
  approval_required?: boolean;
}): Promise<RagDomainDetail> {
  return unwrapResponse(apiPost<RagDomainDetail>("/admin/api/rag-domains", data));
}

export function getRagSources(domainId: string): Promise<RagSourceSummary[]> {
  return unwrapResponse(apiGet<RagSourceSummary[]>(`/admin/api/rag-domains/${domainId}/sources`));
}

export function addRagSource(
  domainId: string,
  data: {
    source_id: string;
    source_name: string;
    source_type?: string;
    access_url?: string;
    description?: string;
    leakage_risk_level?: string;
  },
): Promise<RagSourceSummary> {
  return unwrapResponse(
    apiPost<RagSourceSummary>(`/admin/api/rag-domains/${domainId}/sources`, data),
  );
}

export function approveRagDomain(
  domainId: string,
  data: Record<string, unknown> = {},
): Promise<{ domain_id: string; status: string; message: string }> {
  return unwrapResponse(
    apiPost<{ domain_id: string; status: string; message: string }>(
      `/admin/api/rag-domains/${domainId}/approve`,
      data,
    ),
  );
}

export function getCases(status?: string): Promise<CaseSummary[]> {
  const params = status ? `?status=${status}` : "";
  return unwrapResponse(apiGet<CaseSummary[]>(`/admin/api/cases${params}`));
}

export function getCaseDetail(caseId: string): Promise<CaseDetail> {
  return unwrapResponse(apiGet<CaseDetail>(`/admin/api/cases/${caseId}`));
}

export function resolveCase(
  caseId: string,
  data: {
    status: string;
    resolution?: string;
    owner?: string;
  },
): Promise<{ case_id: string; status: string; resolution?: string; message: string }> {
  return unwrapResponse(
    apiPost<{ case_id: string; status: string; resolution?: string; message: string }>(
      `/admin/api/cases/${caseId}/resolve`,
      data,
    ),
  );
}

// Administration
export function getApiKeys() {
  return apiGet<ApiKeySummary[]>("/admin/api/api-keys");
}

export function issueApiKey(payload: { system_id: string; scopes?: string[] }) {
  return apiPost<IssuedApiKey>("/admin/api/api-keys/issue", payload);
}

export function revokeApiKey(apiKeyId: string) {
  return apiPost<{ ok: boolean; api_key_id: string; status: string }>(
    "/admin/api/api-keys/revoke",
    { api_key_id: apiKeyId },
  );
}

export function getSystems() {
  return apiGet<SystemSummary[]>("/admin/api/systems");
}

export function getProviderSettings() {
  return apiGet<ProviderSettings>("/admin/api/provider-settings");
}

export function updateProviderSettings(payload: Partial<ProviderSettings>) {
  return apiPut<{ ok: boolean; settings: ProviderSettings }>(
    "/admin/api/provider-settings",
    payload,
  );
}

export function getProviderStatus(activeOnly = false) {
  const suffix = activeOnly ? "?active_only=true" : "";
  return apiGet<ProviderStatus[]>(`/admin/api/providers/status${suffix}`);
}

export function testProvider(payload: { provider: string; model?: string }) {
  return apiPost<ProviderTestResult>("/admin/api/providers/test", payload);
}

export function getProviderModels(provider: string) {
  const encoded = encodeURIComponent(provider);
  return apiGet<ProviderModelListResponse>(`/admin/api/providers/models?provider=${encoded}`);
}

// Roles and users
export function getRbacContext() {
  return apiGet<RbacContext>("/admin/api/rbac/context");
}

export function getUsers() {
  return apiGet<UserSummary[]>("/admin/api/users");
}

export function createUser(payload: {
  user_id: string;
  email: string;
  name: string;
  status?: string;
  roles?: string[];
}) {
  return apiPost<{ ok: boolean; user_id: string; roles: string[] }>("/admin/api/users", payload);
}

export function updateUser(
  userId: string,
  payload: {
    email?: string;
    name?: string;
    status?: string;
  },
) {
  return apiPut<{ ok: boolean; user_id: string }>(
    `/admin/api/users/${encodeURIComponent(userId)}`,
    payload,
  );
}

export function assignUserRoles(userId: string, roles: string[]) {
  return apiPost<{ ok: boolean; user_id: string; roles: string[] }>(
    `/admin/api/users/${encodeURIComponent(userId)}/roles`,
    { roles },
  );
}

export function deleteUser(userId: string) {
  return apiDelete<{ ok: boolean; user_id: string; deleted: boolean }>(
    `/admin/api/users/${encodeURIComponent(userId)}`,
  );
}

export function getRoles() {
  return apiGet<RoleSummary[]>("/admin/api/roles");
}

export function createRole(payload: {
  role_id: string;
  name: string;
  description?: string;
  permissions?: string[];
}) {
  return apiPost<{ ok: boolean; role_id: string }>("/admin/api/roles", payload);
}

export function updateRolePermissions(roleId: string, permissions: string[]) {
  return apiPost<{ ok: boolean; role_id: string; permissions: string[] }>(
    `/admin/api/roles/${encodeURIComponent(roleId)}/permissions`,
    { permissions },
  );
}

// Registry (WP1)
export function getAISystems(search?: string) {
  const query = search ? `?search=${encodeURIComponent(search)}` : "";
  return apiGet<AISystemSummary[]>(`/v1/ai-systems${query}`);
}

export function getAISystem(systemId: string) {
  return apiGet<AISystemSummary>(`/v1/ai-systems/${systemId}`);
}

export function getAISystemHierarchy(systemId: string) {
  return apiGet<AISystemHierarchy>(`/v1/ai-systems/${systemId}/hierarchy`);
}

/** Last application-reported configuration provenance for an AI system. */
export function getAISystemConfigurationProvenance(systemId: string) {
  return apiGet<AISystemConfigurationProvenance>(
    `/v1/ai-systems/${systemId}/configuration-provenance`,
  );
}

export function createAISystem(payload: {
  system_key: string;
  name: string;
  business_purpose?: string;
  business_unit?: string;
  owner_id?: string;
  risk_tier?: string;
}) {
  return apiPost<AISystemSummary>("/v1/ai-systems", payload);
}

export function getAgents(systemId: string) {
  return apiGet<AgentSummary[]>(`/v1/ai-systems/${systemId}/agents`);
}

export function getAgent(agentId: string) {
  return apiGet<AgentSummary>(`/v1/agents/${agentId}`);
}

export function getAgentVersions(agentId: string) {
  return apiGet<AgentVersionSummary[]>(`/v1/agents/${agentId}/versions`);
}

export function getAgentVersion(versionId: string) {
  return apiGet<AgentVersionSummary>(`/v1/agent-versions/${versionId}`);
}

export function getVersionDependencies(versionId: string) {
  return apiGet<VersionDependency[]>(`/v1/agent-versions/${versionId}/dependencies`);
}

export function getMaterialChanges(versionId: string) {
  return apiGet<MaterialChange[]>(`/v1/agent-versions/${versionId}/material-changes`);
}

export function updateAISystem(
  systemId: string,
  payload: Partial<{
    name: string;
    description: string;
    business_purpose: string;
    business_unit: string;
    owner_id: string;
    technical_owner_id: string;
    risk_tier: string;
    data_classification: string;
  }>,
) {
  return apiPatch<AISystemSummary>(`/v1/ai-systems/${systemId}`, payload);
}

export function transitionAISystem(systemId: string, status: string) {
  return apiPost<AISystemSummary>(`/v1/ai-systems/${systemId}/lifecycle`, { status });
}

export function createAgent(
  systemId: string,
  payload: {
    agent_key: string;
    name: string;
    description?: string;
    business_purpose?: string;
    owner_id?: string;
    avatar?: string;
  },
) {
  return apiPost<AgentSummary>(`/v1/ai-systems/${systemId}/agents`, payload);
}

export function updateAgent(
  agentId: string,
  payload: Partial<{
    name: string;
    description: string;
    business_purpose: string;
    owner_id: string;
    avatar: string;
  }>,
) {
  return apiPatch<AgentSummary>(`/v1/agents/${agentId}`, payload);
}

export function transitionAgent(agentId: string, status: string) {
  return apiPost<AgentSummary>(`/v1/agents/${agentId}/lifecycle`, { status });
}

export function createAgentVersion(
  agentId: string,
  payload: {
    change_summary?: string;
    risk_tier?: string;
    configuration_snapshot?: Record<string, unknown>;
  },
) {
  return apiPost<AgentVersionSummary>(`/v1/agents/${agentId}/versions`, payload);
}

export function updateAgentVersion(
  versionId: string,
  payload: Partial<{
    change_summary: string;
    risk_tier: string;
    configuration_snapshot: Record<string, unknown>;
  }>,
) {
  return apiPatch<AgentVersionSummary>(`/v1/agent-versions/${versionId}`, payload);
}

export function transitionAgentVersion(versionId: string, status: string) {
  return apiPost<AgentVersionSummary>(`/v1/agent-versions/${versionId}/lifecycle`, {
    status,
  });
}

export function addVersionDependency(
  versionId: string,
  payload: {
    resource_type: string;
    resource_id: string;
    usage_purpose?: string;
    access_mode?: string;
    capability_declaration?: string;
    required?: boolean;
  },
) {
  return apiPost<{ id: string }>(`/v1/agent-versions/${versionId}/dependencies`, payload);
}

export function removeVersionDependency(versionId: string, dependencyId: string) {
  return apiDelete<{ ok: boolean }>(`/v1/agent-versions/${versionId}/dependencies/${dependencyId}`);
}

export function getTools() {
  return apiGet<ToolResourceSummary[]>("/v1/registry/tools");
}

export function createTool(payload: {
  tool_key: string;
  name: string;
  description?: string;
  category?: string;
  provider?: string;
  mcp_server_id?: string;
  sensitivity?: string;
  consequential_action?: boolean;
}) {
  return apiPost<ToolResourceSummary>("/v1/registry/tools", payload);
}

export function updateTool(
  toolId: string,
  payload: {
    name?: string;
    description?: string;
    category?: string;
    consequential_action?: boolean;
    status?: string;
    capability_type?: string;
    side_effect?: string;
    default_risk?: string;
    default_requires_approval?: boolean;
  },
) {
  return apiPatch<ToolResourceSummary>(`/v1/registry/tools/${toolId}`, payload);
}

export function getMCPServers() {
  return apiGet<MCPServerSummary[]>("/v1/registry/mcp-servers");
}

export function getMCPServer(mcpServerId: string) {
  return apiGet<MCPServerSummary>(`/v1/registry/mcp-servers/${mcpServerId}`);
}

export function createMCPServer(payload: {
  server_key: string;
  name: string;
  description?: string;
  provider?: string;
  environment?: string;
  endpoint_reference?: string;
  trust_classification?: string;
}) {
  return apiPost<MCPServerSummary>("/v1/registry/mcp-servers", payload);
}

export function updateMCPServer(
  mcpServerId: string,
  payload: {
    name?: string;
    description?: string;
    provider?: string;
    environment?: string;
    endpoint_reference?: string;
    trust_classification?: string;
  },
) {
  return apiPatch<MCPServerSummary>(`/v1/registry/mcp-servers/${mcpServerId}`, payload);
}

export function seedMCPCatalog() {
  return apiPost<{
    mcps_created: number;
    mcps_updated: number;
    tools_created: number;
    tools_updated: number;
    models_created?: number;
    models_updated?: number;
    mcp_ids: Record<string, string>;
  }>("/v1/registry/mcp-servers/seed-catalog", {});
}

export function syncMCPTools(mcpId: string) {
  return apiPost<{
    mcp_server_id: string;
    matched: string[];
    discovered: string[];
    deprecated: string[];
  }>(`/v1/registry/mcp-servers/${mcpId}/sync-tools`, {});
}

export function discoverMCPTools(mcpId: string) {
  return apiPost<
    Array<{
      native_name: string;
      description?: string | null;
      input_schema?: Record<string, unknown> | null;
    }>
  >(`/v1/registry/mcp-servers/${mcpId}/discover-tools`, {});
}

export function getDataSources() {
  return apiGet<DataSourceSummary[]>("/v1/registry/data-sources");
}

export function createDataSource(payload: {
  data_source_key: string;
  name: string;
  description?: string;
  owner?: string;
  classification?: string;
  contains_personal_data?: boolean;
  contains_sensitive_data?: boolean;
  jurisdiction?: string;
}) {
  return apiPost<DataSourceSummary>("/v1/registry/data-sources", payload);
}

export function getModels() {
  return apiGet<ModelResourceSummary[]>("/v1/registry/models");
}

export function getModel(modelId: string) {
  return apiGet<ModelResourceSummary>(`/v1/registry/models/${modelId}`);
}

export function createModel(payload: {
  provider: string;
  model_name: string;
  model_version?: string;
  deployment_reference?: string;
  hosting_type?: string;
}) {
  return apiPost<ModelResourceSummary>("/v1/registry/models", payload);
}

export function updateModel(
  modelId: string,
  payload: {
    provider?: string;
    model_name?: string;
    model_version?: string;
    deployment_reference?: string;
    hosting_type?: string;
  },
) {
  return apiPatch<ModelResourceSummary>(`/v1/registry/models/${modelId}`, payload);
}

export function getExternalServices() {
  return apiGet<ExternalServiceSummary[]>("/v1/registry/external-services");
}

export async function downloadCatalogTemplate(): Promise<void> {
  const headers = buildHeaders();
  delete headers["Content-Type"];
  const response = await fetch(`${API_BASE_URL}/v1/registry/catalog/import-template`, {
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError(
      `Unable to download the catalog template: ${response.status}`,
      response.status,
    );
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "rai-catalog-template.xlsx";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function importCatalogWorkbook(file: File): Promise<{
  created: number;
  updated: number;
  rows: number;
}> {
  const headers = buildHeaders();
  delete headers["Content-Type"];
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API_BASE_URL}/v1/registry/catalog/import`, {
    method: "POST",
    headers,
    body,
    cache: "no-store",
  });
  const parsed = await parseResponse<{ created: number; updated: number; rows: number }>(response);
  return parsed.data;
}

export function createExternalService(payload: {
  service_key: string;
  name: string;
  description?: string;
  provider?: string;
  environment?: string;
  endpoint_reference?: string;
  sensitivity?: string;
  trust_classification?: string;
}) {
  return apiPost<ExternalServiceSummary>("/v1/registry/external-services", payload);
}

export function createRiskAssessment(payload: {
  ai_system_id: string;
  agent_version_id?: string;
  risk_tier?: string;
  overall_score?: number;
  rationale?: string;
}) {
  return apiPost<{ id: string }>("/v1/risk-assessments", payload);
}

export function getVersionRiskAssessments(versionId: string) {
  return apiGet<RiskAssessmentSummary[]>(`/v1/agent-versions/${versionId}/risk-assessments`);
}

export function updateRiskAssessmentStatus(assessmentId: string, status: string) {
  return apiPost<RiskAssessmentSummary>(`/v1/risk-assessments/${assessmentId}/lifecycle`, {
    status,
  });
}

// --- WP2 Runtime Identities ---

export function getRuntimeIdentities(params?: {
  agent_id?: string;
  agent_version_id?: string;
  status?: string;
  environment?: string;
  search?: string;
}) {
  const query = new URLSearchParams();
  if (params?.agent_id) query.set("agent_id", params.agent_id);
  if (params?.agent_version_id) query.set("agent_version_id", params.agent_version_id);
  if (params?.status) query.set("status", params.status);
  if (params?.environment) query.set("environment", params.environment);
  if (params?.search) query.set("search", params.search);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<RuntimeIdentitySummary[]>(`/v1/runtime-identities${suffix}`);
}

export function getRuntimeIdentity(identityId: string) {
  return apiGet<RuntimeIdentitySummary>(`/v1/runtime-identities/${identityId}`);
}

export function createRuntimeIdentity(payload: {
  agent_id: string;
  agent_version_id: string;
  name: string;
  identity_type?: string;
  auth_provider?: string;
  external_subject?: string;
  environment?: string;
  expires_at?: string;
}) {
  return apiPost<RuntimeIdentitySummary>("/v1/runtime-identities", payload);
}

export function updateRuntimeIdentity(
  identityId: string,
  payload: {
    name?: string;
    environment?: string;
    auth_provider?: string;
    external_subject?: string;
    expires_at?: string;
  },
) {
  return apiPatch<RuntimeIdentitySummary>(`/v1/runtime-identities/${identityId}`, payload);
}

export function suspendRuntimeIdentity(identityId: string, reason?: string) {
  return apiPost<RuntimeIdentitySummary>(`/v1/runtime-identities/${identityId}/suspend`, {
    reason,
  });
}

export function activateRuntimeIdentity(identityId: string) {
  return apiPost<RuntimeIdentitySummary>(`/v1/runtime-identities/${identityId}/activate`, {});
}

export function revokeRuntimeIdentity(identityId: string, reason?: string) {
  return apiPost<RuntimeIdentitySummary>(`/v1/runtime-identities/${identityId}/revoke`, { reason });
}

export function getRuntimeCredentials(identityId: string) {
  return apiGet<RuntimeCredentialSummary[]>(`/v1/runtime-identities/${identityId}/credentials`);
}

export function issueRuntimeCredential(identityId: string, payload?: { expires_at?: string }) {
  return apiPost<RuntimeCredentialSummary>(
    `/v1/runtime-identities/${identityId}/credentials`,
    payload ?? {},
  );
}

export function rotateRuntimeCredential(
  identityId: string,
  credentialId: string,
  payload?: { expires_at?: string },
) {
  return apiPost<RuntimeCredentialSummary>(
    `/v1/runtime-identities/${identityId}/credentials/${credentialId}/rotate`,
    payload ?? {},
  );
}

export function revokeRuntimeCredential(identityId: string, credentialId: string) {
  return apiPost<RuntimeCredentialSummary>(
    `/v1/runtime-identities/${identityId}/credentials/${credentialId}/revoke`,
    {},
  );
}

export function getDelegationResources(versionId: string) {
  return apiGet<DelegationResourceCatalog>(`/v1/agent-versions/${versionId}/delegation-resources`);
}

export function getDelegations(params?: {
  delegate_runtime_identity_id?: string;
  delegator_id?: string;
  status?: string;
}) {
  const query = new URLSearchParams();
  if (params?.delegate_runtime_identity_id) {
    query.set("delegate_runtime_identity_id", params.delegate_runtime_identity_id);
  }
  if (params?.delegator_id) query.set("delegator_id", params.delegator_id);
  if (params?.status) query.set("status", params.status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<DelegationSummary[]>(`/v1/delegations${suffix}`);
}

export function getDelegation(delegationId: string) {
  return apiGet<DelegationSummary>(`/v1/delegations/${delegationId}`);
}

export function createDelegation(payload: {
  delegator_type: string;
  delegator_id: string;
  delegate_runtime_identity_id: string;
  parent_delegation_id?: string;
  scope?: DelegationScope;
  expires_at?: string;
}) {
  return apiPost<DelegationSummary>("/v1/delegations", payload);
}

export function updateDelegation(
  delegationId: string,
  payload: {
    delegator_type?: string;
    delegator_id?: string;
    scope?: DelegationScope;
    expires_at?: string | null;
    clear_expires_at?: boolean;
  },
) {
  return apiPatch<DelegationSummary>(`/v1/delegations/${delegationId}`, payload);
}

export function revokeDelegation(delegationId: string, reason?: string) {
  return apiPost<DelegationSummary>(`/v1/delegations/${delegationId}/revoke`, {
    reason,
  });
}

export function getApprovalRequests(params?: {
  status?: string;
  view?: string;
  ai_system_id?: string;
  agent_id?: string;
  agent_version_id?: string;
  runtime_identity_id?: string;
  risk_tier?: string;
  search?: string;
}) {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.view) query.set("view", params.view);
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.agent_id) query.set("agent_id", params.agent_id);
  if (params?.agent_version_id) query.set("agent_version_id", params.agent_version_id);
  if (params?.runtime_identity_id) query.set("runtime_identity_id", params.runtime_identity_id);
  if (params?.risk_tier) query.set("risk_tier", params.risk_tier);
  if (params?.search) query.set("search", params.search);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<ApprovalRequestSummary[]>(`/v1/approval-requests${suffix}`);
}

export function getApprovalRequest(requestId: string) {
  return apiGet<ApprovalRequestDetail>(`/v1/approval-requests/${requestId}`);
}

export function createApprovalRequest(payload: {
  runtime_identity_id: string;
  delegation_id?: string;
  integration_type?: string;
  integration_id?: string;
  tool_id?: string;
  target_type?: string;
  target_identifier?: string;
  parameters?: Record<string, unknown>;
  business_reason?: string;
  force?: boolean;
}) {
  return apiPost<ApprovalRequestDetail>("/v1/approval-requests", payload);
}

export function approveApprovalRequest(
  requestId: string,
  payload: { acting_membership_id: string; decision_reason?: string },
) {
  return apiPost<ApprovalRequestDetail>(`/v1/approval-requests/${requestId}/approve`, payload);
}

export function rejectApprovalRequest(
  requestId: string,
  payload: { acting_membership_id: string; decision_reason?: string },
) {
  return apiPost<ApprovalRequestDetail>(`/v1/approval-requests/${requestId}/reject`, payload);
}

export function cancelApprovalRequest(requestId: string) {
  return apiPost<ApprovalRequestDetail>(`/v1/approval-requests/${requestId}/cancel`, {});
}

// Policy engine (AI System policy collections)
export function getSystemPolicies(systemId: string) {
  return apiGet<PolicyCollectionDetail>(`/v1/ai-systems/${systemId}/policies`);
}

export function getAllPolicyRules() {
  return apiGet<AllPolicyRulesResponse>("/v1/policies/rules");
}

export function getResourceCatalog(params?: {
  search?: string;
  ai_system_id?: string;
  resource_type?: string;
  status?: string;
  environment?: string;
  provider?: string;
  scope?: string;
  limit?: number;
  offset?: number;
  sort?: string;
}) {
  const q = new URLSearchParams();
  if (params?.search) q.set("search", params.search);
  if (params?.ai_system_id) q.set("ai_system_id", params.ai_system_id);
  if (params?.resource_type) q.set("resource_type", params.resource_type);
  if (params?.status) q.set("status", params.status);
  if (params?.environment) q.set("environment", params.environment);
  if (params?.provider) q.set("provider", params.provider);
  if (params?.scope) q.set("scope", params.scope);
  if (params?.limit != null) q.set("limit", String(params.limit));
  if (params?.offset != null) q.set("offset", String(params.offset));
  if (params?.sort) q.set("sort", params.sort);
  const qs = q.toString();
  return apiGet<ResourceCatalogResponse>(`/v1/resource-catalog${qs ? `?${qs}` : ""}`);
}

export function getRaiRulesUnified(params?: {
  search?: string;
  ai_system_id?: string;
  rule_type?: string;
  tool_id?: string;
  mcp_server_id?: string;
  effect?: string;
  severity?: string;
  status?: string;
  category?: string;
  source_policy_id?: string;
  limit?: number;
  offset?: number;
  sort?: string;
}) {
  const q = new URLSearchParams();
  if (params?.search) q.set("search", params.search);
  if (params?.ai_system_id) q.set("ai_system_id", params.ai_system_id);
  if (params?.rule_type) q.set("rule_type", params.rule_type);
  if (params?.tool_id) q.set("tool_id", params.tool_id);
  if (params?.mcp_server_id) q.set("mcp_server_id", params.mcp_server_id);
  if (params?.effect) q.set("effect", params.effect);
  if (params?.severity) q.set("severity", params.severity);
  if (params?.status) q.set("status", params.status);
  if (params?.category) q.set("category", params.category);
  if (params?.source_policy_id) q.set("source_policy_id", params.source_policy_id);
  if (params?.limit != null) q.set("limit", String(params.limit));
  if (params?.offset != null) q.set("offset", String(params.offset));
  if (params?.sort) q.set("sort", params.sort);
  const qs = q.toString();
  return apiGet<UnifiedRaiRulesResponse>(`/v1/rai-rules${qs ? `?${qs}` : ""}`);
}

export function getPolicyLibrary(params?: {
  search?: string;
  source_type?: string;
  authority?: string;
  jurisdiction?: string;
  policy_type?: string;
  status?: string;
  limit?: number;
  offset?: number;
}) {
  const q = new URLSearchParams();
  if (params?.search) q.set("search", params.search);
  if (params?.source_type) q.set("source_type", params.source_type);
  if (params?.authority) q.set("authority", params.authority);
  if (params?.jurisdiction) q.set("jurisdiction", params.jurisdiction);
  if (params?.policy_type) q.set("policy_type", params.policy_type);
  if (params?.status) q.set("status", params.status);
  if (params?.limit != null) q.set("limit", String(params.limit));
  if (params?.offset != null) q.set("offset", String(params.offset));
  const qs = q.toString();
  return apiGet<PolicyLibraryListResponse>(`/v1/policy-library${qs ? `?${qs}` : ""}`);
}

export function getPolicySource(sourceId: string) {
  return apiGet<PolicySourceDetail>(`/v1/policy-library/${sourceId}`);
}

export function createPolicySource(payload: {
  title: string;
  source_type: string;
  authority?: string;
  owner?: string;
  jurisdiction?: string;
  policy_type?: string;
  version?: string;
  effective_date?: string;
  source_uri?: string;
  content_text?: string;
  content_ref?: string;
  crawl_metadata?: Record<string, unknown>;
}) {
  return apiPost<PolicySourceSummary>("/v1/policy-library", payload);
}

export function createContentRule(
  systemId: string,
  payload: {
    title: string;
    content: string;
    effect: string;
    enabled?: boolean;
    required_approver_role?: string;
    applies_to?: string;
    category?: string;
    severity?: string;
    source_policy_id?: string;
    source_obligation_id?: string;
  },
) {
  return apiPost<ContentRuleSummary>(`/v1/ai-systems/${systemId}/policies/content-rules`, payload);
}

export function updateContentRule(
  ruleId: string,
  payload: {
    title?: string;
    content?: string;
    effect?: string;
    enabled?: boolean;
    required_approver_role?: string;
    applies_to?: string;
    category?: string;
    severity?: string;
    ai_system_id?: string;
  },
) {
  return apiPatch<ContentRuleSummary>(`/v1/policies/content-rules/${ruleId}`, payload);
}

export function deleteContentRule(ruleId: string) {
  return apiDelete<void>(`/v1/policies/content-rules/${ruleId}`);
}

export function createToolRule(
  systemId: string,
  payload: {
    title: string;
    description?: string;
    mcp_server_id?: string;
    tool_id: string;
    match_mode?: string;
    effect: string;
    enabled?: boolean;
    required_approver_role?: string;
    severity?: string;
    category?: string;
    source_policy_id?: string;
    source_obligation_id?: string;
    conditions?: ToolRuleConditionSummary[];
  },
) {
  return apiPost<ToolRuleSummary>(`/v1/ai-systems/${systemId}/policies/tool-rules`, payload);
}

export function updateToolRule(
  ruleId: string,
  payload: {
    title?: string;
    description?: string;
    mcp_server_id?: string;
    clear_mcp_server_id?: boolean;
    tool_id?: string;
    match_mode?: string;
    effect?: string;
    enabled?: boolean;
    required_approver_role?: string;
    severity?: string;
    category?: string;
    conditions?: ToolRuleConditionSummary[];
    ai_system_id?: string;
  },
) {
  return apiPatch<ToolRuleSummary>(`/v1/policies/tool-rules/${ruleId}`, payload);
}

export function deleteToolRule(ruleId: string) {
  return apiDelete<void>(`/v1/policies/tool-rules/${ruleId}`);
}

// Runtime enforcement (WP4)

export function getEnforcementReceipts(params?: {
  ai_system_id?: string;
  agent_id?: string;
  runtime_identity_id?: string;
  tool_id?: string;
  enforcement_decision?: string;
  execution_status?: string;
  enforcement_mode?: string;
  approval_request_id?: string;
  client_type?: string;
  started_after?: string;
  started_before?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams();
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.agent_id) query.set("agent_id", params.agent_id);
  if (params?.runtime_identity_id) query.set("runtime_identity_id", params.runtime_identity_id);
  if (params?.tool_id) query.set("tool_id", params.tool_id);
  if (params?.enforcement_decision) query.set("enforcement_decision", params.enforcement_decision);
  if (params?.execution_status) query.set("execution_status", params.execution_status);
  if (params?.enforcement_mode) query.set("enforcement_mode", params.enforcement_mode);
  if (params?.approval_request_id) query.set("approval_request_id", params.approval_request_id);
  if (params?.client_type) query.set("client_type", params.client_type);
  if (params?.started_after) query.set("started_after", params.started_after);
  if (params?.started_before) query.set("started_before", params.started_before);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<EnforcementReceiptSummary[]>(`/v1/runtime/enforcement/receipts${suffix}`);
}

export function getEnforcementReceipt(receiptId: string) {
  return apiGet<EnforcementReceiptDetail>(`/v1/runtime/enforcement/receipts/${receiptId}`);
}

export function getRuntimeExecutions(params?: {
  execution_status?: string;
  enforcement_mode?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams();
  if (params?.execution_status) query.set("execution_status", params.execution_status);
  if (params?.enforcement_mode) query.set("enforcement_mode", params.enforcement_mode);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<
    Array<{
      receipt_id: string;
      tool_name?: string | null;
      tool_id?: string | null;
      integration_name?: string | null;
      action_digest?: string | null;
      execution_source?: string | null;
      execution_status?: string | null;
      enforcement_decision?: string | null;
      enforcement_mode?: string | null;
      started_at?: string | null;
      completed_at?: string | null;
      reported_at?: string | null;
      duration_ms?: number | null;
      safe_result_metadata?: Record<string, unknown> | null;
      runtime_identity_name?: string | null;
      ai_system_name?: string | null;
      agent_name?: string | null;
    }>
  >(`/v1/runtime/executions${suffix}`);
}

async function runtimePost<T>(
  path: string,
  credentialSecret: string,
  body: unknown,
): Promise<ApiResponse<T>> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-RAI-Agent-Key": credentialSecret,
    },
    body: JSON.stringify(body),
  });
  const traceId = response.headers.get("x-trace-id") ?? undefined;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message =
      typeof payload?.detail === "object"
        ? (payload.detail?.message ?? JSON.stringify(payload.detail))
        : (payload?.detail ?? payload?.message ?? response.statusText);
    throw new ApiError(String(message), response.status, traceId);
  }
  return { data: payload as T, traceId };
}

export function authorizeRuntimeAction(credentialSecret: string, payload: RuntimeTestRequest) {
  return runtimePost<RuntimeActionResult>(
    "/v1/runtime/actions/authorize",
    credentialSecret,
    payload,
  );
}

export function executeRuntimeAction(credentialSecret: string, payload: RuntimeTestRequest) {
  return runtimePost<RuntimeActionResult>("/v1/runtime/actions/execute", credentialSecret, payload);
}

// Client hook integrations (WP4 extension)

export function getClientIntegrations(identityId: string) {
  return apiGet<ClientIntegrationSummary[]>(
    `/v1/runtime-identities/${identityId}/client-integrations`,
  );
}

export function setupClientIntegration(identityId: string, clientType: string) {
  return apiPost<ClientIntegrationSetup>(
    `/v1/runtime-identities/${identityId}/client-integrations/${clientType}/setup`,
    {},
  );
}

export function testClientIntegration(
  identityId: string,
  clientType: string,
  credentialSecret: string,
) {
  return apiPost<{ ok: boolean; message: string; checks?: Record<string, unknown> }>(
    `/v1/runtime-identities/${identityId}/client-integrations/${clientType}/test`,
    { credential_secret: credentialSecret },
  );
}

export function disconnectClientIntegration(identityId: string, clientType: string) {
  return apiPost<ClientIntegrationSummary>(
    `/v1/runtime-identities/${identityId}/client-integrations/${clientType}/disconnect`,
    {},
  );
}

// WP5 trajectories / evidence

export function getTrajectories(params?: {
  ai_system_id?: string;
  agent_id?: string;
  runtime_identity_id?: string;
  client_integration_id?: string;
  status?: string;
  started_after?: string;
  started_before?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams();
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.agent_id) query.set("agent_id", params.agent_id);
  if (params?.runtime_identity_id) query.set("runtime_identity_id", params.runtime_identity_id);
  if (params?.client_integration_id) {
    query.set("client_integration_id", params.client_integration_id);
  }
  if (params?.status) query.set("status", params.status);
  if (params?.started_after) query.set("started_after", params.started_after);
  if (params?.started_before) query.set("started_before", params.started_before);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<TrajectoryListResponse>(`/v1/trajectories${suffix}`);
}

export function getObservedPrompts(params?: { limit?: number; offset?: number }) {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: ObservedPromptSummary[]; limit: number; offset: number }>(
    `/v1/observed-prompts${suffix}`,
  );
}

export function getObservedPrompt(eventId: string) {
  return apiGet<ObservedPromptDetail>(`/v1/observed-prompts/${eventId}`);
}

export function getTrajectory(trajectoryId: string) {
  return apiGet<TrajectoryDetail>(`/v1/trajectories/${trajectoryId}`);
}

export function getTrajectoryLifecycle(trajectoryId: string) {
  return apiGet<TrajectoryLifecycle>(`/v1/trajectories/${trajectoryId}/lifecycle`);
}

export function getTrajectoryRiskFindings(trajectoryId: string) {
  return apiGet<TrajectoryRiskFindings>(`/v1/trajectories/${trajectoryId}/risk-findings`);
}

export function getConversations(params?: {
  ai_system_id?: string;
  agent_id?: string;
  runtime_identity_id?: string;
  client_integration_id?: string;
  status?: string;
  risk_level?: string;
  principal?: string;
  conversation_id?: string;
  started_after?: string;
  started_before?: string;
  cursor?: string;
  limit?: number;
}) {
  const query = new URLSearchParams();
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.agent_id) query.set("agent_id", params.agent_id);
  if (params?.runtime_identity_id) query.set("runtime_identity_id", params.runtime_identity_id);
  if (params?.client_integration_id) {
    query.set("client_integration_id", params.client_integration_id);
  }
  if (params?.status) query.set("status", params.status);
  if (params?.risk_level) query.set("risk_level", params.risk_level);
  if (params?.principal) query.set("principal", params.principal);
  if (params?.conversation_id) query.set("conversation_id", params.conversation_id);
  if (params?.started_after) query.set("started_after", params.started_after);
  if (params?.started_before) query.set("started_before", params.started_before);
  if (params?.cursor) query.set("cursor", params.cursor);
  if (params?.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<ConversationListResponse>(`/v1/conversations${suffix}`);
}

export function getConversation(conversationId: string) {
  return apiGet<RuntimeConversationSummary>(`/v1/conversations/${conversationId}`);
}

export function getConversationTrajectories(
  conversationId: string,
  params?: { cursor?: string; limit?: number },
) {
  const query = new URLSearchParams();
  if (params?.cursor) query.set("cursor", params.cursor);
  if (params?.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{
    conversation_id: string;
    items: TrajectorySummary[];
    next_cursor?: string | null;
    has_more: boolean;
    limit: number;
  }>(`/v1/conversations/${conversationId}/trajectories${suffix}`);
}

export function getConversationPolicyTriggers(
  conversationId: string,
  params?: { limit?: number; offset?: number },
) {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{
    conversation_id: string;
    items: ConversationPolicyTrigger[];
    total: number;
    limit: number;
    offset: number;
  }>(`/v1/conversations/${conversationId}/policy-triggers${suffix}`);
}

export function searchRuntimeAudit(params: {
  date_from?: string;
  date_to?: string;
  entity_types?: string;
  ai_system_id?: string;
  agent_id?: string;
  runtime_identity_id?: string;
  delegation_id?: string;
  integration_id?: string;
  conversation_id?: string;
  trajectory_id?: string;
  tool_id?: string;
  decision?: string;
  execution_status?: string;
  assurance?: string;
  correlation_id?: string;
  receipt_id?: string;
  event_type?: string;
  /** INPUT | OUTPUT | MODEL_REQUEST | MODEL_RESPONSE */
  record_kind?: string;
  principal?: string;
  channel?: string;
  /** Requires evidence:content:read; matches stored content fields only. */
  content_search?: string;
  cursor?: string;
  limit?: number;
}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<AuditSearchResponse>(`/v1/runtime-audit/search${suffix}`);
}

export function getTrajectoryEvents(
  trajectoryId: string,
  params?: { limit?: number; offset?: number },
) {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ trajectory_id: string; items: EvidenceEvent[]; limit: number; offset: number }>(
    `/v1/trajectories/${trajectoryId}/events${suffix}`,
  );
}

export function getTrajectoryEvent(trajectoryId: string, eventId: string) {
  return apiGet<EvidenceEventDetail>(`/v1/trajectories/${trajectoryId}/events/${eventId}`);
}

export function getTrajectoryArtifact(trajectoryId: string, artifactId: string) {
  return apiGet<EvidenceArtifact>(`/v1/trajectories/${trajectoryId}/artifacts/${artifactId}`);
}

export function getTrajectoryGraph(trajectoryId: string) {
  return apiGet<TrajectoryGraph>(`/v1/trajectories/${trajectoryId}/graph`);
}

export function getTrajectoryFindings(trajectoryId: string) {
  return apiGet<{ trajectory_id: string; items: EvidenceFinding[] }>(
    `/v1/trajectories/${trajectoryId}/findings`,
  );
}

export function getTrajectoryArtifacts(trajectoryId: string) {
  return apiGet<{ trajectory_id: string; items: EvidenceArtifact[] }>(
    `/v1/trajectories/${trajectoryId}/artifacts`,
  );
}

export function exportTrajectory(trajectoryId: string) {
  return apiPost<Record<string, unknown>>(`/v1/trajectories/${trajectoryId}/export`, {});
}

// WP6 risk intelligence

export function getRiskOverview(aiSystemId?: string) {
  const query = aiSystemId ? `?ai_system_id=${aiSystemId}` : "";
  return apiGet<RiskOverview>(`/v1/risk/overview${query}`);
}

export function getRiskFindings(params?: {
  ai_system_id?: string;
  trajectory_id?: string;
  severity?: string;
  status?: string;
  finding_type?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams();
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.trajectory_id) query.set("trajectory_id", params.trajectory_id);
  if (params?.severity) query.set("severity", params.severity);
  if (params?.status) query.set("status", params.status);
  if (params?.finding_type) query.set("finding_type", params.finding_type);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: RuntimeRiskFinding[]; total?: number; limit: number; offset: number }>(
    `/v1/risk/findings${suffix}`,
  );
}

export function getRiskFinding(findingId: string) {
  return apiGet<RuntimeRiskFinding>(`/v1/risk/findings/${findingId}`);
}

export function getRiskMonitors(params?: {
  ai_system_id?: string;
  status?: string;
  limit?: number;
}) {
  const query = new URLSearchParams();
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.status) query.set("status", params.status);
  if (params?.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: RiskMonitor[]; limit: number; offset: number }>(
    `/v1/risk/monitors${suffix}`,
  );
}

export function getRiskInterventions(params?: {
  ai_system_id?: string;
  trajectory_id?: string;
  status?: string;
  limit?: number;
}) {
  const query = new URLSearchParams();
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.trajectory_id) query.set("trajectory_id", params.trajectory_id);
  if (params?.status) query.set("status", params.status);
  if (params?.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: InterventionDecision[]; limit: number; offset: number }>(
    `/v1/risk/interventions${suffix}`,
  );
}

export function confirmRiskIntervention(interventionId: string) {
  return apiPost<InterventionDecision>(`/v1/risk/interventions/${interventionId}/confirm`, {});
}

export function cancelRiskIntervention(interventionId: string) {
  return apiPost<InterventionDecision>(`/v1/risk/interventions/${interventionId}/cancel`, {});
}

export function getPolicyRecommendations(params?: {
  ai_system_id?: string;
  status?: string;
  limit?: number;
}) {
  const query = new URLSearchParams();
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.status) query.set("status", params.status);
  if (params?.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: PolicyRecommendation[]; limit: number; offset: number }>(
    `/v1/risk/recommendations${suffix}`,
  );
}

export function acceptPolicyRecommendation(recommendationId: string) {
  return apiPost<{ recommendation: PolicyRecommendation; draft_rule_id: string; enabled: boolean }>(
    `/v1/risk/recommendations/${recommendationId}/accept`,
    {},
  );
}

export function dismissPolicyRecommendation(recommendationId: string, reject = false) {
  return apiPost<PolicyRecommendation>(
    `/v1/risk/recommendations/${recommendationId}/dismiss?reject=${reject}`,
    {},
  );
}

export function getContentEvaluatorConfig(aiSystemId?: string) {
  const query = aiSystemId ? `?ai_system_id=${aiSystemId}` : "";
  return apiGet<ContentEvaluatorConfig>(`/v1/content-evaluator/config${query}`);
}

export function upsertContentEvaluatorConfig(payload: {
  ai_system_id?: string | null;
  provider: string;
  model: string;
  enabled?: boolean;
  api_key?: string | null;
  temperature?: number;
  timeout_seconds?: number;
  max_rules_per_call?: number;
  confidence_threshold?: number;
  minimum_confidence_to_mark?: number;
  minimum_confidence_to_monitor?: number;
  minimum_confidence_to_intervene?: number;
  fail_closed?: boolean;
  fallback_provider?: string | null;
}) {
  return apiPut<ContentEvaluatorConfig>(`/v1/content-evaluator/config`, payload);
}

export function testContentEvaluator(payload: {
  ai_system_id: string;
  content: string;
  content_type?: string;
}) {
  return apiPost<Record<string, unknown>>(`/v1/content-evaluator/test`, payload);
}

export function getTrajectoryRisk(trajectoryId: string) {
  return apiGet<TrajectoryRiskBundle>(`/v1/risk/trajectories/${trajectoryId}`);
}

// --- WP7 Evaluation / Assurance ---------------------------------------------

export function listEvaluationSuites(params?: {
  ai_system_id?: string;
  published_only?: boolean;
  limit?: number;
}) {
  const query = new URLSearchParams();
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.published_only) query.set("published_only", "true");
  if (params?.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: EvaluationSuite[]; limit: number; offset: number }>(
    `/v1/evaluation-suites${suffix}`,
  );
}

export function getEvaluationSuite(suiteId: string) {
  return apiGet<EvaluationSuiteDetail>(`/v1/evaluation-suites/${suiteId}`);
}

export function createEvaluationSuite(payload: {
  ai_system_id: string;
  suite_key: string;
  name: string;
  category: string;
  description?: string;
  runner_type?: string;
}) {
  return apiPost<EvaluationSuite>(`/v1/evaluation-suites`, payload);
}

export function publishEvaluationSuite(suiteId: string) {
  return apiPost<EvaluationSuite>(`/v1/evaluation-suites/${suiteId}/publish`, {});
}

export function addEvaluationCase(
  suiteId: string,
  payload: {
    case_key: string;
    name: string;
    input_fixture: Record<string, unknown>;
    expected_behavior: Record<string, unknown>;
    scoring_method?: string;
    threshold?: number;
    failure_severity?: string;
  },
) {
  return apiPost<EvaluationCase>(`/v1/evaluation-suites/${suiteId}/cases`, payload);
}

export function listEvaluationRequirements(params?: {
  ai_system_id?: string;
  environment?: string;
}) {
  const query = new URLSearchParams();
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.environment) query.set("environment", params.environment);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: EvaluationRequirement[] }>(`/v1/evaluation-requirements${suffix}`);
}

export function createEvaluationRequirement(payload: {
  ai_system_id: string;
  name: string;
  category: string;
  evaluation_suite_id: string;
  minimum_score?: number;
  maximum_failed_critical_cases?: number;
  required?: boolean;
  validity_days?: number | null;
  environment_scope?: string;
}) {
  return apiPost<EvaluationRequirement>(`/v1/evaluation-requirements`, payload);
}

export function listEvaluationPlans(versionId: string) {
  return apiGet<{ items: EvaluationPlan[] }>(`/v1/agent-versions/${versionId}/evaluation-plans`);
}

export function createEvaluationPlan(
  versionId: string,
  payload?: { target_environment?: string; categories?: string[] },
) {
  return apiPost<EvaluationPlan>(
    `/v1/agent-versions/${versionId}/evaluation-plans`,
    payload ?? { target_environment: "PRODUCTION" },
  );
}

export function startEvaluationPlanRuns(
  planId: string,
  payload?: { idempotency_key?: string; execute_inline?: boolean },
) {
  return apiPost<{ items: EvaluationRun[] }>(
    `/v1/evaluation-plans/${planId}/runs`,
    payload ?? { idempotency_key: "default", execute_inline: true },
  );
}

export function listEvaluationRuns(params?: {
  agent_version_id?: string;
  ai_system_id?: string;
  plan_id?: string;
  limit?: number;
}) {
  const query = new URLSearchParams();
  if (params?.agent_version_id) query.set("agent_version_id", params.agent_version_id);
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.plan_id) query.set("plan_id", params.plan_id);
  if (params?.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: EvaluationRun[]; limit: number; offset: number }>(
    `/v1/evaluation-runs${suffix}`,
  );
}

export function getEvaluationRun(runId: string) {
  return apiGet<EvaluationRunDetail>(`/v1/evaluation-runs/${runId}`);
}

export function listDeploymentGates(params?: { ai_system_id?: string; environment?: string }) {
  const query = new URLSearchParams();
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.environment) query.set("environment", params.environment);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: DeploymentGate[] }>(`/v1/deployment-gates${suffix}`);
}

export function createDeploymentGate(payload: {
  ai_system_id: string;
  name: string;
  environment?: string;
  description?: string;
  auto_from_requirements?: boolean;
}) {
  return apiPost<DeploymentGate>(`/v1/deployment-gates`, payload);
}

export function evaluateDeploymentGate(
  versionId: string,
  payload?: { environment?: string; gate_id?: string; plan_id?: string },
) {
  return apiPost<DeploymentGateEvaluationResult>(
    `/v1/agent-versions/${versionId}/deployment-gates/evaluate`,
    payload ?? { environment: "PRODUCTION" },
  );
}

export function getVersionAssurance(
  versionId: string,
  params?: { environment?: string; include_history?: boolean },
) {
  const query = new URLSearchParams();
  if (params?.environment) query.set("environment", params.environment);
  if (params?.include_history) query.set("include_history", "true");
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<VersionAssurance>(`/v1/agent-versions/${versionId}/assurance${suffix}`);
}

export function getDeploymentReadiness(versionId: string, environment = "PRODUCTION") {
  return apiGet<DeploymentReadiness>(
    `/v1/agent-versions/${versionId}/deployment-readiness?environment=${environment}`,
  );
}

export function listEvaluationWaivers(params?: {
  agent_version_id?: string;
  ai_system_id?: string;
  status?: string;
}) {
  const query = new URLSearchParams();
  if (params?.agent_version_id) query.set("agent_version_id", params.agent_version_id);
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.status) query.set("status", params.status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: EvaluationWaiver[] }>(`/v1/evaluation-waivers${suffix}`);
}

export function requestEvaluationWaiver(payload: {
  agent_version_id: string;
  justification: string;
  failed_condition: Record<string, unknown>;
  environment?: string;
  compensating_controls?: Record<string, unknown> | unknown[];
  validity_days?: number;
  gate_evaluation_id?: string;
}) {
  return apiPost<EvaluationWaiver>(`/v1/evaluation-waivers`, payload);
}

export function approveEvaluationWaiver(waiverId: string, decision_reason?: string) {
  return apiPost<EvaluationWaiver>(`/v1/evaluation-waivers/${waiverId}/approve`, {
    decision_reason,
  });
}

export function rejectEvaluationWaiver(waiverId: string, decision_reason?: string) {
  return apiPost<EvaluationWaiver>(`/v1/evaluation-waivers/${waiverId}/reject`, {
    decision_reason,
  });
}

export function revokeEvaluationWaiver(waiverId: string, decision_reason?: string) {
  return apiPost<EvaluationWaiver>(`/v1/evaluation-waivers/${waiverId}/revoke`, {
    decision_reason,
  });
}
export function getRiskBudgets(params?: {
  ai_system_id?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams();
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: RuntimeBudget[]; limit: number; offset: number }>(
    `/v1/risk/budgets${suffix}`,
  );
}

export function createRiskBudget(payload: {
  ai_system_id?: string;
  name: string;
  scope_type?: string;
  scope_id?: string;
  metric: string;
  tool_name?: string;
  resource_filter?: Record<string, unknown>;
  limit_value: number;
  window_seconds?: number;
  window?: string;
  warning_threshold?: number;
  effect_on_exceed?: string;
  amount_parameter_path?: string;
  enabled?: boolean;
}) {
  return apiPost<RuntimeBudget>(`/v1/risk/budgets`, payload);
}

export function getEffectiveRiskBudgets(params?: {
  ai_system_id?: string;
  agent_id?: string;
  runtime_identity_id?: string;
  delegation_id?: string;
  model?: string;
  tool_name?: string;
}) {
  const query = new URLSearchParams();
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.agent_id) query.set("agent_id", params.agent_id);
  if (params?.runtime_identity_id) query.set("runtime_identity_id", params.runtime_identity_id);
  if (params?.delegation_id) query.set("delegation_id", params.delegation_id);
  if (params?.model) query.set("model", params.model);
  if (params?.tool_name) query.set("tool_name", params.tool_name);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: RuntimeBudget[] }>(`/v1/risk/budgets/effective${suffix}`);
}

export function updateRiskBudget(
  budgetId: string,
  payload: {
    name?: string;
    scope_id?: string | null;
    tool_name?: string | null;
    tool_id?: string | null;
    limit_value?: number;
    window_seconds?: number;
    window?: string;
    warning_threshold?: number;
    effect_on_exceed?: string;
    amount_parameter_path?: string | null;
    enforcement_mode?: string;
    enabled?: boolean;
  },
) {
  return apiPatch<RuntimeBudget>(`/v1/risk/budgets/${budgetId}`, payload);
}

export function getRiskBudget(budgetId: string) {
  return apiGet<RuntimeBudget>(`/v1/risk/budgets/${budgetId}`);
}

export function getRiskBudgetChecks(
  budgetId: string,
  params?: {
    status?: string;
    triggers_only?: boolean;
    limit?: number;
    offset?: number;
  },
) {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.triggers_only) query.set("triggers_only", "true");
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{
    items: RuntimeBudgetCheck[];
    total: number;
    limit: number;
    offset: number;
  }>(`/v1/risk/budgets/${budgetId}/checks${suffix}`);
}

export function getRiskAnomalies(params?: {
  ai_system_id?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams();
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: RuntimeRiskFinding[]; limit: number; offset: number }>(
    `/v1/risk/anomalies${suffix}`,
  );
}

export function emergencySuspendRuntimeIdentity(
  identityId: string,
  reason: string,
  confirm = true,
) {
  return apiPost<{ id: string; status: string; reason: string }>(
    `/v1/risk/emergency/runtime-identities/${identityId}/suspend`,
    { reason, confirm },
  );
}

export function emergencyReactivateRuntimeIdentity(
  identityId: string,
  reason: string,
  confirm = true,
) {
  return apiPost<{ id: string; status: string; reason: string }>(
    `/v1/risk/emergency/runtime-identities/${identityId}/reactivate`,
    { reason, confirm },
  );
}

// --- WP8 Pilot & Governance -------------------------------------------------

export async function listOrganizations(_params?: { limit?: number; offset?: number }) {
  const profile = await apiGet<OrganizationGovernanceProfile>(
    "/v1/organization/governance-profile",
  );
  const org: Organization = {
    id: profile.data.id,
    org_key: "instance",
    name: profile.data.name || profile.data.legal_name || "Organization",
    description: profile.data.description ?? null,
    status: "ACTIVE",
    created_by: "system",
    created_at: null,
    updated_at: profile.data.updated_at,
  };
  return { ...profile, data: { items: [org] } };
}

export function getOrganization(_organizationId: string) {
  return listOrganizations().then((response) => ({
    ...response,
    data: response.data.items[0],
  }));
}

export function createOrganization(payload: {
  org_key: string;
  name: string;
  description?: string;
  organization_type?: string;
  legal_name?: string;
  sector?: string;
  jurisdiction?: string;
}) {
  return apiPost<Organization>(`/v1/organizations`, payload);
}

export function deleteOrganization(organizationId: string) {
  return apiDelete<{
    id: string;
    org_key: string;
    name: string;
    deleted: boolean;
    ai_systems_deleted: number;
    agents_deleted: number;
    agent_versions_deleted: number;
    runtime_identities_deleted: number;
  }>(`/v1/organizations/${organizationId}`);
}

export function getGovernanceProfile(_organizationId?: string) {
  return apiGet<OrganizationGovernanceProfile>("/v1/organization/governance-profile");
}

export function patchGovernanceProfile(
  _organizationId: string,
  payload: Partial<{
    legal_name: string;
    organization_type: string;
    sector: string;
    jurisdiction: string;
    regulatory_context: Record<string, unknown>;
    risk_appetite: string;
    governance_owner: string;
    assurance_owner: string;
    incident_owner: string;
    default_review_frequency_days: number;
    evidence_retention_policy: Record<string, unknown>;
    pilot_status: string;
  }>,
) {
  return apiPatch<OrganizationGovernanceProfile>("/v1/organization/governance-profile", payload);
}

export function listMemberships(
  _organizationId: string,
  params?: { status?: string; limit?: number; offset?: number },
) {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.limit != null) query.set("limit", String(params.limit));
  if (params?.offset != null) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: OrganizationMembership[] }>(`/v1/organization/memberships${suffix}`);
}

export function createMembership(
  _organizationId: string,
  payload: { user_id: string; role: string; status?: string; valid_until?: string },
) {
  return apiPost<OrganizationMembership>("/v1/organization/memberships", payload);
}

export function inviteOrganizationMember(
  _organizationId: string,
  payload: { email: string; full_name: string; role: string; department_id?: string },
) {
  return apiPost<{
    user: { user_id: string; email: string; name: string; created: boolean };
    membership: OrganizationMembership;
    temporary_password: string | null;
    verification_email_sent: boolean;
    verification_email_error?: string | null;
  }>(`/v1/organization/members/invite`, payload);
}

export type OrganizationInviteResult = {
  user: { user_id: string; email: string; name: string; created: boolean };
  membership: OrganizationMembership;
  temporary_password: string | null;
  verification_email_sent: boolean;
  verification_email_error?: string | null;
};

/** Members of the active organization. The server uses X-Organization-ID and membership. */
export function listOrganizationTeam(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.limit != null) query.set("limit", String(params.limit));
  if (params?.offset != null) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: OrganizationMembership[]; organization_id: string }>(
    `/v1/organization/members${suffix}`,
  );
}

/** Departments of the active organization. Defaults are created the first time this is read. */
export function listOrganizationDepartments() {
  return apiGet<{ items: Department[]; organization_id: string }>("/v1/organization/departments");
}

/** Invite into the active organization only. Organization id is not accepted from the client. */
export function inviteOrganizationTeammate(payload: {
  email: string;
  full_name: string;
  role: string;
  department_id?: string;
}) {
  return apiPost<OrganizationInviteResult>(`/v1/organization/members/invite`, payload);
}

export function updateOrganizationMembership(
  membershipId: string,
  payload: { role?: string; status?: string },
) {
  return apiPatch<OrganizationMembership>(`/v1/organization/members/${membershipId}`, payload);
}

export function deleteOrganizationMembership(membershipId: string) {
  return apiDelete<{ id: string; organization_id: string; deleted: boolean }>(
    `/v1/organization/members/${membershipId}`,
  );
}

export function removeOrganizationPerson(userId: string) {
  return apiDelete<{ user_id: string; organization_id: string; deleted: number }>(
    `/v1/organization/people/${encodeURIComponent(userId)}`,
  );
}

export function attachAiSystemsToOrganization(
  organizationId: string,
  payload?: { include_from_other_orgs?: boolean; system_ids?: string[] },
) {
  return apiPost<{
    organization_id: string;
    org_key: string;
    attached_count: number;
    skipped_count: number;
    attached: Array<{
      id: string;
      system_key: string;
      name: string;
      previous_organization_id: string | null;
    }>;
    skipped: Array<{ id: string; system_key: string; reason: string }>;
  }>(`/v1/organizations/${organizationId}/ai-systems/attach`, payload ?? {});
}

export function getAccountability(aiSystemId: string, _organizationId?: string) {
  return apiGet<AISystemAccountability>(`/v1/ai-systems/${aiSystemId}/accountability`);
}

export function upsertAccountability(
  aiSystemId: string,
  payload: {
    organization_id: string;
    business_owner_membership_id?: string | null;
    technical_owner_membership_id?: string | null;
    rai_officer_membership_id?: string | null;
    risk_owner_membership_id?: string | null;
    incident_owner_membership_id?: string | null;
    enforce_sod?: boolean;
  },
) {
  return apiPost<AISystemAccountability>(`/v1/ai-systems/${aiSystemId}/accountability`, payload);
}

export function listControlFrameworks(params?: { limit?: number; offset?: number }) {
  const query = new URLSearchParams();
  if (params?.limit != null) query.set("limit", String(params.limit));
  if (params?.offset != null) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: ControlFramework[] }>(`/v1/control-frameworks${suffix}`);
}

export function listControlAssessments(
  aiSystemId: string,
  params?: { organization_id?: string; agent_version_id?: string; limit?: number; offset?: number },
) {
  const query = new URLSearchParams();
  if (params?.organization_id) query.set("organization_id", params.organization_id);
  if (params?.agent_version_id) query.set("agent_version_id", params.agent_version_id);
  if (params?.limit != null) query.set("limit", String(params.limit));
  if (params?.offset != null) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: ControlAssessment[] }>(
    `/v1/ai-systems/${aiSystemId}/control-assessments${suffix}`,
  );
}

export function refreshControlAssessments(
  aiSystemId: string,
  payload: { organization_id: string; agent_version_id?: string },
) {
  return apiPost<{ items: ControlAssessment[] }>(
    `/v1/ai-systems/${aiSystemId}/control-assessments/refresh`,
    payload,
  );
}

export function listGovernanceReviews(params?: {
  organization_id?: string;
  ai_system_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams();
  if (params?.organization_id) query.set("organization_id", params.organization_id);
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.status) query.set("status", params.status);
  if (params?.limit != null) query.set("limit", String(params.limit));
  if (params?.offset != null) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: GovernanceReview[] }>(`/v1/governance-reviews${suffix}`);
}

export function getGovernanceReview(reviewId: string) {
  return apiGet<GovernanceReview>(`/v1/governance-reviews/${reviewId}`);
}

export function createGovernanceReview(payload: {
  organization_id: string;
  ai_system_id: string;
  review_type: string;
  agent_version_id?: string;
  due_at?: string;
}) {
  return apiPost<GovernanceReview>(`/v1/governance-reviews`, payload);
}

export function decideGovernanceReview(
  reviewId: string,
  payload: {
    decision: string;
    decision_reason: string;
    conditions?: Record<string, unknown> | unknown[];
  },
) {
  return apiPost<GovernanceReview>(`/v1/governance-reviews/${reviewId}/decide`, payload);
}

export function listGovernanceExceptions(params?: {
  organization_id?: string;
  ai_system_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams();
  if (params?.organization_id) query.set("organization_id", params.organization_id);
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.status) query.set("status", params.status);
  if (params?.limit != null) query.set("limit", String(params.limit));
  if (params?.offset != null) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: GovernanceException[] }>(`/v1/governance-exceptions${suffix}`);
}

export function requestGovernanceException(payload: {
  organization_id: string;
  ai_system_id: string;
  business_justification: string;
  control_requirement_id?: string;
  agent_version_id?: string;
  scope?: Record<string, unknown>;
  risk?: string;
  compensating_controls?: Record<string, unknown> | unknown[];
  evidence_refs?: Record<string, unknown> | unknown[];
  valid_until?: string;
}) {
  return apiPost<GovernanceException>(`/v1/governance-exceptions`, payload);
}

export function approveGovernanceException(exceptionId: string, decision_reason?: string) {
  return apiPost<GovernanceException>(`/v1/governance-exceptions/${exceptionId}/approve`, {
    decision_reason,
  });
}

export function rejectGovernanceException(exceptionId: string, decision_reason?: string) {
  return apiPost<GovernanceException>(`/v1/governance-exceptions/${exceptionId}/reject`, {
    decision_reason,
  });
}

export function revokeGovernanceException(exceptionId: string, decision_reason?: string) {
  return apiPost<GovernanceException>(`/v1/governance-exceptions/${exceptionId}/revoke`, {
    decision_reason,
  });
}

export function listIncidents(params?: {
  organization_id?: string;
  ai_system_id?: string;
  status?: string;
  severity?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams();
  if (params?.organization_id) query.set("organization_id", params.organization_id);
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.status) query.set("status", params.status);
  if (params?.severity) query.set("severity", params.severity);
  if (params?.limit != null) query.set("limit", String(params.limit));
  if (params?.offset != null) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: AIIncident[] }>(`/v1/incidents${suffix}`);
}

export function getIncident(incidentId: string) {
  return apiGet<AIIncident>(`/v1/incidents/${incidentId}`);
}

export function createIncident(payload: {
  organization_id: string;
  ai_system_id: string;
  title: string;
  severity?: string;
  category?: string;
  description?: string;
  source?: string;
  agent_version_id?: string;
}) {
  return apiPost<AIIncident>(`/v1/incidents`, payload);
}

export function transitionIncident(
  incidentId: string,
  payload: { to_status: string; reason?: string; metadata?: Record<string, unknown> },
) {
  return apiPost<AIIncident>(`/v1/incidents/${incidentId}/transition`, payload);
}

export function containIncident(
  incidentId: string,
  payload: {
    containment_action: string;
    containment_ref?: Record<string, unknown> | unknown[];
    reason?: string;
  },
) {
  return apiPost<AIIncident>(`/v1/incidents/${incidentId}/contain`, payload);
}

export function addCorrectiveAction(
  incidentId: string,
  payload: { description: string; owner: string; due_at?: string },
) {
  return apiPost<IncidentCorrectiveAction>(
    `/v1/incidents/${incidentId}/corrective-actions`,
    payload,
  );
}

export function listEvidencePackages(params?: {
  organization_id?: string;
  ai_system_id?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams();
  if (params?.organization_id) query.set("organization_id", params.organization_id);
  if (params?.ai_system_id) query.set("ai_system_id", params.ai_system_id);
  if (params?.limit != null) query.set("limit", String(params.limit));
  if (params?.offset != null) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: GovernanceEvidencePackage[] }>(`/v1/evidence-packages${suffix}`);
}

export function getEvidencePackage(packageId: string) {
  return apiGet<GovernanceEvidencePackage>(`/v1/evidence-packages/${packageId}`);
}

export function generateEvidencePackage(payload: {
  organization_id: string;
  ai_system_id?: string;
  agent_id?: string;
  agent_version_id?: string;
  review_id?: string;
  incident_id?: string;
  period_start?: string;
  period_end?: string;
  include_html?: boolean;
}) {
  return apiPost<GovernanceEvidencePackage>(`/v1/evidence-packages`, payload);
}

export function listPilots(params?: { organization_id?: string; limit?: number; offset?: number }) {
  const query = new URLSearchParams();
  if (params?.organization_id) query.set("organization_id", params.organization_id);
  if (params?.limit != null) query.set("limit", String(params.limit));
  if (params?.offset != null) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<{ items: Pilot[] }>(`/v1/pilots${suffix}`);
}

export function getPilot(pilotId: string) {
  return apiGet<Pilot>(`/v1/pilots/${pilotId}`);
}

export function createPilot(payload: {
  organization_id: string;
  name: string;
  description?: string;
  sponsor?: string;
  start_at?: string;
  end_at?: string;
  success_criteria?: Record<string, unknown> | unknown[];
}) {
  return apiPost<Pilot>(`/v1/pilots`, payload);
}

export function transitionPilot(
  pilotId: string,
  payload: { to_status: string; readiness_evaluation_id?: string },
) {
  return apiPost<Pilot>(`/v1/pilots/${pilotId}/transition`, payload);
}

export function getPilotDashboard(params: { organization_id?: string; pilot_id?: string }) {
  if (params.pilot_id) {
    return apiGet<PilotDashboard>(`/v1/pilots/${params.pilot_id}/dashboard`);
  }
  return apiGet<PilotDashboard>("/v1/pilot-dashboard");
}

export function evaluatePilotReadiness(payload: {
  organization_id: string;
  ai_system_id: string;
  agent_version_id?: string;
  pilot_id?: string;
}) {
  return apiPost<PilotReadinessResult>(`/v1/pilot-readiness/evaluate`, payload);
}

export function getOrgDueWork(_organizationId: string) {
  return apiGet<DueWork>("/v1/due-work");
}

export function linkAiSystemToOrganization(_organizationId: string, aiSystemId: string) {
  return apiPost<{ id: string; system_key?: string; name?: string }>(
    `/v1/ai-systems/${aiSystemId}/link`,
    {},
  );
}

export function getGovernanceClassification(aiSystemId: string, _organizationId?: string) {
  return apiGet<GovernanceClassification>(`/v1/ai-systems/${aiSystemId}/governance-classification`);
}

export function upsertGovernanceClassification(
  aiSystemId: string,
  payload: {
    organization_id: string;
    business_criticality?: string | null;
    data_sensitivity?: string | null;
    customer_citizen_impact?: string | null;
    financial_impact?: string | null;
    autonomy_level?: string | null;
    external_facing?: boolean;
    consequential_actions?: boolean;
    personal_data?: boolean;
    regulated_process?: boolean;
    human_oversight_requirement?: string | null;
    production?: boolean;
  },
) {
  return apiPut<GovernanceClassification>(
    `/v1/ai-systems/${aiSystemId}/governance-classification`,
    payload,
  );
}

export function addAiSystemToPilot(
  pilotId: string,
  payload: { ai_system_id: string; agent_version_id?: string; organization_id?: string },
) {
  return apiPost<Pilot>(`/v1/pilots/${pilotId}/ai-systems`, payload);
}

export function createGovernanceAttestation(payload: {
  organization_id: string;
  attestation_type: string;
  statement: string;
  ai_system_id?: string;
  agent_version_id?: string;
  actor_role?: string;
  valid_until?: string;
}) {
  return apiPost<Record<string, unknown>>(`/v1/governance-attestations`, payload);
}

export function createPeriodicReviewSchedule(payload: {
  organization_id: string;
  ai_system_id: string;
  frequency_days?: number;
}) {
  return apiPost<Record<string, unknown>>(`/v1/periodic-review-schedules`, payload);
}

export function processDuePeriodicReviews(_organizationId?: string) {
  return apiPost<{ items?: unknown[]; created?: unknown[] }>(
    "/v1/periodic-reviews/process-due",
    {},
  );
}

export function seedReferencePilots() {
  return apiPost<Record<string, unknown>>(`/v1/governance/seed-reference-pilots`, {});
}

// --- WP9 Portfolio Transparency & Executive Oversight ---

function portfolioOrgQuery(
  organizationId: string,
  extra?: Record<string, string | number | undefined>,
) {
  const query = new URLSearchParams({ organization_id: organizationId });
  if (extra) {
    for (const [key, value] of Object.entries(extra)) {
      if (value !== undefined && value !== "") query.set(key, String(value));
    }
  }
  return `?${query.toString()}`;
}

export function getPortfolioSummary(organizationId: string) {
  return apiGet<PortfolioSummary>(`/v1/portfolio/summary${portfolioOrgQuery(organizationId)}`);
}

export function getPortfolioDashboard(organizationId: string) {
  return apiGet<PortfolioDashboard>(`/v1/portfolio/dashboard${portfolioOrgQuery(organizationId)}`);
}

export function getPortfolioAiSystems(
  organizationId: string,
  filters?: {
    business_unit?: string;
    owner?: string;
    lifecycle?: string;
    risk?: string;
    assurance?: string;
    control_status?: string;
    incident_state?: string;
    pilot_state?: string;
  },
) {
  return apiGet<PortfolioInventoryResponse>(
    `/v1/portfolio/ai-systems${portfolioOrgQuery(organizationId, filters)}`,
  );
}

export function getPortfolioRisk(organizationId: string) {
  return apiGet<PortfolioRiskPosture>(`/v1/portfolio/risk${portfolioOrgQuery(organizationId)}`);
}

export function getPortfolioAssurance(organizationId: string) {
  return apiGet<PortfolioAssurancePosture>(
    `/v1/portfolio/assurance${portfolioOrgQuery(organizationId)}`,
  );
}

export function getPortfolioControls(organizationId: string) {
  return apiGet<PortfolioControlPosture>(
    `/v1/portfolio/controls${portfolioOrgQuery(organizationId)}`,
  );
}

export function getPortfolioIncidents(organizationId: string) {
  return apiGet<PortfolioIncidentPosture>(
    `/v1/portfolio/incidents${portfolioOrgQuery(organizationId)}`,
  );
}

export function getPortfolioRuntimeActivity(organizationId: string, periodDays = 30) {
  return apiGet<PortfolioRuntimeActivity>(
    `/v1/portfolio/runtime-activity${portfolioOrgQuery(organizationId, {
      period_days: periodDays,
    })}`,
  );
}

export function getPortfolioEvidence(organizationId: string) {
  return apiGet<PortfolioEvidenceResponse>(
    `/v1/portfolio/evidence${portfolioOrgQuery(organizationId)}`,
  );
}

export function getPortfolioOwnership(organizationId: string) {
  return apiGet<PortfolioOwnershipResponse>(
    `/v1/portfolio/ownership${portfolioOrgQuery(organizationId)}`,
  );
}

export function getPortfolioAttention(organizationId: string, limit = 200) {
  return apiGet<PortfolioAttentionQueue>(
    `/v1/portfolio/attention${portfolioOrgQuery(organizationId, { limit })}`,
  );
}

export function getPortfolioTrends(organizationId: string, periodDays = 30) {
  return apiGet<PortfolioTrendsResponse>(
    `/v1/portfolio/trends${portfolioOrgQuery(organizationId, { period_days: periodDays })}`,
  );
}

export function getPortfolioChanges(
  organizationId: string,
  params?: { period_days?: number; limit?: number },
) {
  return apiGet<PortfolioChangesResponse>(
    `/v1/portfolio/changes${portfolioOrgQuery(organizationId, {
      period_days: params?.period_days,
      limit: params?.limit,
    })}`,
  );
}

export function exportPortfolio(organizationId: string) {
  return apiGet<PortfolioExportResponse>(
    `/v1/portfolio/export${portfolioOrgQuery(organizationId)}`,
  );
}

export function listPortfolioReports(
  organizationId: string,
  params?: { limit?: number; offset?: number },
) {
  return apiGet<PortfolioReportListResponse>(
    `/v1/portfolio/reports${portfolioOrgQuery(organizationId, {
      limit: params?.limit,
      offset: params?.offset,
    })}`,
  );
}

export function generatePortfolioReport(payload: {
  organization_id: string;
  scope_type?: string;
  scope_id?: string;
  period_start?: string;
  period_end?: string;
  period_days?: number;
  include_html?: boolean;
}) {
  return apiPost<PortfolioReport>(`/v1/portfolio/reports`, payload);
}

export function getPortfolioReport(
  reportId: string,
  params?: { organization_id?: string; include_html?: boolean },
) {
  const query = new URLSearchParams();
  if (params?.organization_id) query.set("organization_id", params.organization_id);
  if (params?.include_html != null) query.set("include_html", String(params.include_html));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<PortfolioReport>(`/v1/portfolio/reports/${reportId}${suffix}`);
}

export function listPortfolioReportSchedules(organizationId: string) {
  return apiGet<PortfolioReportScheduleListResponse>(
    `/v1/portfolio/report-schedules${portfolioOrgQuery(organizationId)}`,
  );
}

export function createPortfolioReportSchedule(payload: {
  organization_id: string;
  cadence: string;
  scope_type?: string;
  scope_id?: string;
  enabled?: boolean;
  delivery?: Record<string, unknown>;
}) {
  return apiPost<PortfolioReportSchedule>(`/v1/portfolio/report-schedules`, payload);
}

export function patchPortfolioReportSchedule(
  scheduleId: string,
  organizationId: string,
  payload: { enabled?: boolean; delivery?: Record<string, unknown> },
) {
  return apiPatch<PortfolioReportSchedule>(
    `/v1/portfolio/report-schedules/${scheduleId}${portfolioOrgQuery(organizationId)}`,
    payload,
  );
}

export function listPortfolioDecisions(
  organizationId: string,
  params?: { limit?: number; offset?: number },
) {
  return apiGet<ExecutiveGovernanceDecisionListResponse>(
    `/v1/portfolio/decisions${portfolioOrgQuery(organizationId, {
      limit: params?.limit,
      offset: params?.offset,
    })}`,
  );
}

export function createPortfolioDecision(payload: {
  organization_id: string;
  scope_type: string;
  scope_id: string;
  decision: string;
  reason: string;
  evidence_refs?: unknown;
}) {
  return apiPost<ExecutiveGovernanceDecision>(`/v1/portfolio/decisions`, payload);
}

// ============================================================================
// Reporting & Analytics APIs
// ============================================================================

export interface ReportingQueryParams {
  ai_system_id?: string;
  agent_id?: string;
  period_start?: string;
  period_end?: string;
  risk_severity?: string[];
  risk_category?: string[];
  finding_status?: string[];
  effect?: string;
  budget_metric?: string;
}

function buildReportingQuery(params?: ReportingQueryParams): string {
  if (!params) return "";
  const queryParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      if (Array.isArray(value)) {
        value.forEach((v) => queryParams.append(key, v));
      } else {
        queryParams.append(key, String(value));
      }
    }
  });
  const query = queryParams.toString();
  return query ? `?${query}` : "";
}

export function getReportSummary(params?: ReportingQueryParams) {
  return apiGet<ReportSummary>(`/v1/reports/summary${buildReportingQuery(params)}`);
}

export function getRiskReport(params?: ReportingQueryParams) {
  return apiGet<RiskReport>(`/v1/reports/risk${buildReportingQuery(params)}`);
}

export function getPolicyReport(params?: ReportingQueryParams) {
  return apiGet<PolicyReport>(`/v1/reports/policies${buildReportingQuery(params)}`);
}

export function getBudgetReport(params?: ReportingQueryParams) {
  return apiGet<BudgetReport>(`/v1/reports/budgets${buildReportingQuery(params)}`);
}

export function getRuntimeReport(params?: ReportingQueryParams) {
  return apiGet<RuntimeReport>(`/v1/reports/runtime${buildReportingQuery(params)}`);
}

export function getAssuranceReport(params?: ReportingQueryParams) {
  return apiGet<AssuranceReport>(`/v1/reports/assurance${buildReportingQuery(params)}`);
}

export function getAiSystemReport(aiSystemId: string, params?: ReportingQueryParams) {
  return apiGet<AISystemReport>(
    `/v1/reports/ai-systems/${aiSystemId}${buildReportingQuery(params)}`,
  );
}

export function getConversationReport(conversationId: string) {
  return apiGet<ConversationReport>(`/v1/reports/conversations/${conversationId}`);
}

export function createReportSnapshot(payload: {
  report_type: string;
  scope_type?: string;
  scope_id?: string;
  filters: ReportFilters;
}) {
  return apiPost<ReportSnapshot>(`/v1/reports/snapshots`, payload);
}

export function listReportSnapshots(params?: {
  report_type?: string;
  scope_type?: string;
  limit?: number;
  offset?: number;
}) {
  return apiGet<ReportSnapshot[]>(`/v1/reports/snapshots${buildReportingQuery(params as any)}`);
}

export function getReportSnapshot(snapshotId: string) {
  return apiGet<ReportSnapshot>(`/v1/reports/snapshots/${snapshotId}`);
}

export interface FinOpsQuery {
  period_start?: string;
  period_end?: string;
  ai_system_id?: string;
  agent_id?: string;
  provider?: string;
  model?: string;
  environment?: string;
  delegation_id?: string;
  cost_state?: string;
  dimension?: string;
  limit?: number;
  offset?: number;
}

export function getFinOpsDashboard(params?: FinOpsQuery) {
  return apiGet<import("@/lib/types").FinOpsDashboard>(
    `/v1/finops/dashboard${buildReportingQuery(params as never)}`,
  );
}

export function getFinOpsTimeseries(params?: FinOpsQuery) {
  return apiGet<{
    points: Array<{ timestamp: string; cost: number; tokens: number; trajectories: number }>;
  }>(`/v1/finops/timeseries${buildReportingQuery(params as never)}`);
}

export function getFinOpsBreakdown(params?: FinOpsQuery) {
  return apiGet<{ items: import("@/lib/types").FinOpsBreakdownItem[] }>(
    `/v1/finops/breakdown${buildReportingQuery(params as never)}`,
  );
}

export function getTrajectoryEconomics(trajectoryId: string) {
  return apiGet<import("@/lib/types").TrajectoryEconomics>(
    `/v1/trajectories/${trajectoryId}/economics`,
  );
}

export function listWebhookEndpoints() {
  return apiGet<{ items: import("@/lib/types").WebhookEndpointSummary[] }>(
    "/v1/productization/webhooks",
  );
}

export function createWebhookEndpoint(payload: {
  name: string;
  url: string;
  event_types: string[];
}) {
  return apiPost<{
    endpoint: import("@/lib/types").WebhookEndpointSummary;
    secret: string;
  }>("/v1/productization/webhooks", payload);
}

export function rotateWebhookEndpoint(endpointId: string) {
  return apiPost<{
    endpoint: import("@/lib/types").WebhookEndpointSummary;
    secret: string;
  }>(`/v1/productization/webhooks/${endpointId}/rotate`, {});
}

export function listWebhookDeliveries(limit = 50) {
  return apiGet<{ items: import("@/lib/types").WebhookDeliverySummary[] }>(
    `/v1/productization/webhooks/deliveries?limit=${limit}`,
  );
}
