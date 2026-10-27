export interface ExecutionAuditSummary {
  execution_id: string;
  trace_id: string;
  prompt_id: string;
  prompt_version: number;
  system_id: string;
  module?: string | null;
  decision: string;
  reason_codes: string[];
  rule_ids?: string[];
  llm_model?: string | null;
  cache_hit?: boolean;
  latency_ms?: number | null;
  tokens_in?: number | null;
  tokens_out?: number | null;
  created_at: string;
}

export interface ExecutionExplainability {
  execution_id: string;
  trace_id: string;
  decision: string;
  reason_codes: string[];
  policy_version?: string;
  guard_version?: string;
  input_hash?: string;
  output_hash?: string;
  rule_ids?: string[];
  llm_model?: string;
  cache_hit?: boolean;
  latency_ms?: number;
  tokens_in?: number;
  tokens_out?: number;
  created_at?: string;
}

export interface PromptSummary {
  prompt_id: string;
  name: string;
  status: string;
  owner_system_id?: string;
}

export interface PromptDetail {
  prompt_id: string;
  name: string;
  domain?: string;
  status: string;
  owner_system_id?: string;
  created_at?: string;
}

export interface PromptVersionSummary {
  version: number;
  status: string;
  approved_by?: string;
  approved_at?: string;
  created_at?: string;
}

export interface AllowlistEntry {
  system_id: string;
  module: string;
  allowed: boolean;
}

export interface RaiRuleSummary {
  rule_id: string;
  name: string;
  type: string;
  severity: string;
  action: string;
  active: boolean;
}

export interface PromptRuleSummary {
  rule_id: string;
  name: string;
  type: string;
  severity: string;
  action: string;
  enabled: boolean;
}

export interface AuditLogEntry {
  trace_id: string;
  actor: string;
  action: string;
  resource: string;
  created_at: string;
}

export interface ApiKeySummary {
  api_key_id: string;
  system_id: string;
  scopes: string[];
  status?: string;
  created_at: string;
  revoked_at?: string | null;
  expires_at?: string | null;
}

export interface IssuedApiKey {
  api_key_id: string;
  system_id: string;
  scopes: string[];
  api_key: string;
  note?: string;
}

export interface FeatureFlagSummary {
  key: string;
  enabled: boolean;
}

export interface SystemSummary {
  system_id: string;
  name: string;
  owner: string;
  status?: string;
  registered?: boolean;
  execution_count?: number;
}

export interface ProviderSettings {
  default_provider: string;
  default_model: string;
  llm_provider_url?: string;
  llm_provider_api_key?: string | null;
  azure_openai_api_key?: string | null;
  azure_openai_endpoint?: string | null;
  azure_openai_deployment?: string | null;
  azure_openai_api_version?: string | null;
  anthropic_api_key?: string | null;
  aws_region?: string | null;
  gcp_project_id?: string | null;
  gcp_location?: string | null;
  ollama_endpoint?: string | null;
}

export interface ProviderStatus {
  provider: string;
  configured: boolean;
  default_model?: string | null;
  notes?: string;
  sdk_installed?: boolean;
  is_primary?: boolean;
}

export interface ProviderModelListResponse {
  provider: string;
  models: string[];
  source: "live" | "fallback";
}

export interface ProviderTestResult {
  ok: boolean;
  provider: string;
  model: string;
  usage: Record<string, unknown>;
  sample_output: string;
}

export interface PolicyDocumentSummary {
  doc_id: string;
  country: string;
  authority: string;
  doc_type: string;
  version?: string;
  effective_date?: string;
  created_at?: string;
}

export interface PolicyDocumentDetail {
  doc_id: string;
  country: string;
  authority: string;
  doc_type: string;
  version?: string;
  effective_date?: string;
  content_ref?: string;
  created_at?: string;
}

export interface PolicyObligation {
  obligation_id: string;
  doc_id: string;
  section_ref?: string;
}

export interface RagSourceSummary {
  source_id: string;
  source_name: string;
  source_type?: string;
  access_url?: string;
  leakage_risk_level?: string;
  status?: string;
  created_at?: string;
}

export interface RagDomainSummary {
  domain_id: string;
  name: string;
  description?: string;
  country?: string;
  owner_email?: string;
  status?: string;
  approval_required?: boolean;
  created_at?: string;
}

export interface RagDomainDetail {
  domain_id: string;
  name: string;
  description?: string;
  country?: string;
  owner_email?: string;
  status?: string;
  approval_required?: boolean;
  sources?: RagSourceSummary[];
  created_at?: string;
}

export interface CaseSummary {
  case_id: string;
  execution_id: string;
  status?: string;
  owner?: string;
  reason_codes?: string[];
  resolution?: string;
  created_at?: string;
  updated_at?: string;
}

export interface CaseDetail {
  case_id: string;
  execution_id: string;
  execution?: {
    system_id?: string;
    module?: string;
    decision?: string;
  };
  status?: string;
  owner?: string;
  reason_codes?: string[];
  actions?: Record<string, unknown>;
  resolution?: string;
  created_at?: string;
  updated_at?: string;
}

export interface UserSummary {
  user_id: string;
  email: string;
  name: string;
  status: string;
  roles: string[];
  created_at?: string;
  updated_at?: string;
}

export interface RoleSummary {
  role_id: string;
  name: string;
  description?: string;
  is_system?: boolean;
  permissions: string[];
  created_at?: string;
}

export interface RbacContext {
  selected_role: string;
  permissions: string[];
  available_roles: Array<{
    role_id: string;
    name: string;
    description?: string;
  }>;
}

export interface AdminMe {
  email: string;
  user_id: string;
  roles: string[];
}

export interface AdminLoginResponse {
  access_token: string;
  token_type: "bearer";
  user: AdminMe;
}

export interface ComplianceReportSummary {
  report_id: string;
  doc_id: string;
  title: string;
  report_type: string;
  generated_at: string;
  period: {
    start_at?: string | null;
    end_at?: string | null;
  };
  status: string;
  compliance_score: number;
}

export interface ComplianceReportDetail {
  report_id: string;
  doc_id: string;
  title: string;
  report_type: string;
  status: string;
  generated_at: string;
  period: {
    start_at?: string | null;
    end_at?: string | null;
  };
  framework: {
    country?: string;
    authority?: string;
    doc_type?: string;
    version?: string;
  };
  summary: {
    compliance_score: number;
    obligations_total: number;
    obligations_pass: number;
    obligations_partial: number;
    obligations_fail: number;
    evidence: {
      executions_total: number;
      executions_blocked: number;
      admin_events_total: number;
      cases_total: number;
      cases_resolved: number;
    };
  };
  obligations: Array<{
    obligation_id: string;
    section_ref?: string;
    topic?: string;
    constraint_action?: string;
    status: "PASS" | "PARTIAL" | "FAIL";
    controls: string[];
    covered_controls: string[];
  }>;
}

// WP1 Registry
export interface AISystemSummary {
  id: string;
  system_key: string;
  name: string;
  description?: string | null;
  business_purpose?: string | null;
  business_unit?: string | null;
  owner_id?: string | null;
  status: string;
  risk_tier?: string | null;
  agent_count: number;
  updated_at?: string | null;
}

/** Application-reported external configuration (not RAI-owned prompts). */
export interface AISystemConfigurationProvenance {
  ai_system_id: string;
  found: boolean;
  configuration_id?: string | null;
  configuration_version?: string | null;
  configuration_digest?: string | null;
  configuration_source?: string | null;
  configuration_environment?: string | null;
  deployment_id?: string | null;
  release_id?: string | null;
  observed_model?: string | null;
  source?: string | null;
  assurance?: string | null;
  last_seen_at?: string | null;
  trajectory_id?: string | null;
  conversation_id?: string | null;
  message?: string | null;
}

export interface AgentSummary {
  id: string;
  agent_key: string;
  ai_system_id: string;
  name: string;
  description?: string | null;
  business_purpose?: string | null;
  owner_id?: string | null;
  avatar?: string | null;
  status: string;
  current_version_id?: string | null;
}

export interface AgentVersionSummary {
  id: string;
  agent_id: string;
  version_number: number;
  change_summary?: string | null;
  lifecycle_status: string;
  risk_tier?: string | null;
  material_change_status: string;
  approved_at?: string | null;
  configuration_digest?: string | null;
}

export interface VersionDependency {
  id: string;
  resource_type: string;
  resource_id: string;
  usage_purpose?: string | null;
  access_mode?: string | null;
  capability_declaration?: string | null;
  required: boolean;
}

export interface MaterialChange {
  change_category: string;
  change_description: string;
  is_material: boolean;
  reason?: string | null;
  previous_value?: string | null;
  current_value?: string | null;
}

export interface ToolResourceSummary {
  id: string;
  tool_key: string;
  name: string;
  consequential_action: boolean;
  status: string;
  mcp_server_id?: string | null;
  mcp_server_key?: string | null;
}

export interface MCPServerSummary {
  id: string;
  server_key: string;
  name: string;
  description?: string | null;
  provider?: string | null;
  vendor?: string | null;
  environment?: string | null;
  endpoint_reference?: string | null;
  trust_classification?: string | null;
  status?: string;
  source_type?: string | null;
  native_aliases?: string[];
  category?: string | null;
  tool_count?: number;
  tools?: Array<{
    id: string;
    tool_key: string;
    name: string;
    description?: string | null;
    category?: string | null;
    consequential_action?: boolean;
    status?: string;
    native_name?: string | null;
    capability_type?: string | null;
    side_effect?: string | null;
    default_risk?: string | null;
    default_requires_approval?: boolean | null;
  }>;
}

export interface DataSourceSummary {
  id: string;
  data_source_key: string;
  name: string;
  classification?: string | null;
  contains_personal_data?: boolean;
  contains_sensitive_data?: boolean;
}

export interface ModelResourceSummary {
  id: string;
  provider: string;
  model_name: string;
  model_version?: string | null;
  deployment_reference?: string | null;
  hosting_type?: string | null;
  status: string;
}

export interface ExternalServiceSummary {
  id: string;
  service_key: string;
  name: string;
  provider?: string | null;
  environment?: string | null;
  sensitivity?: string | null;
  trust_classification?: string | null;
  status?: string;
}

export interface RiskAssessmentSummary {
  id: string;
  status: string;
  risk_tier?: string | null;
  overall_score?: number | null;
}

export interface HierarchyVersionNode {
  id: string;
  version_number: number;
  lifecycle_status: string;
  risk_tier?: string | null;
  material_change_status: string;
  change_summary?: string | null;
  approved_at?: string | null;
  is_current: boolean;
  model?: {
    id: string;
    provider: string;
    model_name: string;
    label: string;
  } | null;
  dependency_counts: {
    models: number;
    tools: number;
    mcp_servers: number;
    data_sources: number;
    external_services: number;
  };
}

export interface HierarchyAgentNode {
  id: string;
  agent_key: string;
  name: string;
  status: string;
  current_version_id?: string | null;
  versions: HierarchyVersionNode[];
}

export interface AISystemHierarchy {
  system: {
    id: string;
    system_key: string;
    name: string;
    status: string;
    risk_tier?: string | null;
    business_unit?: string | null;
  };
  agents: HierarchyAgentNode[];
}

export interface RuntimeIdentitySummary {
  id: string;
  identity_key: string;
  agent_id: string;
  agent_version_id: string;
  name: string;
  identity_type: string;
  auth_provider?: string | null;
  external_subject?: string | null;
  environment?: string | null;
  status: string;
  created_at?: string | null;
  created_by: string;
  updated_at?: string | null;
  expires_at?: string | null;
  last_authenticated_at?: string | null;
  revoked_at?: string | null;
  revocation_reason?: string | null;
}

export interface RuntimeCredentialSummary {
  id: string;
  credential_key: string;
  credential_type: string;
  status: string;
  issued_at?: string | null;
  expires_at?: string | null;
  last_used_at?: string | null;
  revoked_at?: string | null;
  plaintext_secret?: string;
}

export interface DelegationScope {
  model_ids?: string[];
  data_source_ids?: string[];
  mcp_server_ids?: string[];
  tool_ids?: string[];
  tool_keys?: string[];
  environment?: string | null;
}

export interface DelegationResourceCatalog {
  version_id: string;
  models: Array<{
    id: string;
    label: string;
    provider: string;
    model_name: string;
  }>;
  data_sources: Array<{
    id: string;
    label: string;
    data_source_key: string;
  }>;
  mcp_servers: Array<{
    id: string;
    server_key: string;
    name: string;
    tools: Array<{
      id: string;
      tool_key: string;
      name: string;
      mcp_server_id?: string | null;
    }>;
  }>;
  standalone_tools?: Array<{
    id: string;
    tool_key: string;
    name: string;
    mcp_server_id?: string | null;
  }>;
  declared_tools?: Array<{
    id: string;
    tool_key: string;
    name: string;
    mcp_server_id?: string | null;
  }>;
}

export interface DelegationScopeSelection {
  model_ids: string[];
  data_source_ids: string[];
  mcp_server_ids: string[];
  tool_ids: string[];
}

export interface EffectiveDelegationScope {
  model_ids?: string[];
  data_source_ids?: string[];
  mcp_server_ids?: string[];
  tool_ids?: string[];
  models?: Array<{ id: string; label: string }>;
  data_sources?: Array<{ id: string; label: string }>;
  mcp_servers?: Array<{
    id: string;
    server_key: string;
    name: string;
    tools: Array<{ id: string; tool_key: string; name: string }>;
  }>;
  environment?: string | null;
}

export interface DelegationSummary {
  id: string;
  delegator_type: string;
  delegator_id: string;
  delegate_runtime_identity_id: string;
  parent_delegation_id?: string | null;
  status: string;
  scope: DelegationScope;
  valid_from?: string | null;
  expires_at?: string | null;
  created_by: string;
  created_at?: string | null;
  revoked_at?: string | null;
  revocation_reason?: string | null;
}

export interface ApprovalDecisionSummary {
  id: string;
  decision: string;
  decided_by: string;
  decision_reason?: string | null;
  authentication_assurance?: string | null;
  decided_at?: string | null;
  correlation_id?: string | null;
}

export interface ApprovalViewerCapabilities {
  can_approve: boolean;
  can_reject: boolean;
  can_cancel: boolean;
  can_create_standing_authorization: boolean;
  decision_block_reason?: string | null;
}

export interface ApprovalRequestSummary {
  id: string;
  ai_system_id: string;
  agent_id: string;
  agent_version_id: string;
  runtime_identity_id: string;
  delegation_id?: string | null;
  initiating_principal?: string | null;
  action_type: string;
  integration_type: string;
  integration_id?: string | null;
  integration_name?: string | null;
  tool_id?: string | null;
  tool_name?: string | null;
  tool_key?: string | null;
  model_id?: string | null;
  data_source_id?: string | null;
  target_type?: string | null;
  target_identifier?: string | null;
  parameters: Record<string, unknown>;
  business_reason?: string | null;
  risk_tier?: string | null;
  risk_score?: number | null;
  requirement_reason?: string | null;
  approval_policy_reference?: string | null;
  status: string;
  created_at?: string | null;
  expires_at?: string | null;
  decided_at?: string | null;
  consumed_at?: string | null;
  action_digest: string;
  correlation_id?: string | null;
  created_by?: string | null;
  runtime_idempotency_key?: string | null;
  human_summary?: string | null;
  viewer_capabilities?: ApprovalViewerCapabilities | null;
  decisions: ApprovalDecisionSummary[];
  plan?: ApprovalPlanSummary | null;
}

export interface ApprovalPlanStageDecision {
  id: string;
  decision: string;
  decided_by: string;
  approver_role?: string | null;
  decision_reason?: string | null;
  decided_at?: string | null;
}

export interface ApprovalPlanStage {
  id: string;
  stage_index: number;
  name?: string | null;
  mode?: string | null;
  required_roles?: string[] | null;
  quorum_count?: number | null;
  status: string;
  decisions?: ApprovalPlanStageDecision[];
}

export interface ApprovalPlanSummary {
  id: string;
  approval_request_id: string;
  action_digest: string;
  status: string;
  current_stage_index: number;
  stages: ApprovalPlanStage[];
}

export interface ApprovalRequestDetail extends ApprovalRequestSummary {
  identity?: {
    ai_system: { id: string; name: string; system_key: string };
    agent: { id: string; name: string; agent_key: string };
    agent_version: { id: string; version_number: number; risk_tier?: string | null };
    runtime_identity: {
      id: string;
      name: string;
      identity_key: string;
      environment?: string | null;
    };
    initiating_principal?: string | null;
    delegation_chain: Array<{
      delegation_id: string;
      delegator_type: string;
      delegator_id: string;
      scope: DelegationScope;
    }>;
  };
  effective_scope?: EffectiveDelegationScope;
  identity_unavailable?: string | null;
  identity_unavailable_reason?: string | null;
  related_enforcement_receipts?: Array<{
    id: string;
    enforcement_decision: string;
    execution_status: string;
    execution_source?: string | null;
    started_at?: string | null;
    href: string;
  }>;
  related_enforcement_receipt_details?: Array<Record<string, unknown>>;
  canonical_action_payload?: Record<string, unknown> | null;
}

export type PolicyEffectValue = "ALLOW" | "MARK" | "MONITOR" | "REQUIRE_APPROVAL" | "DENY";

export interface PolicyCollectionSummary {
  id: string;
  ai_system_id: string;
  name: string;
  description?: string | null;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ContentRuleSummary {
  id: string;
  policy_collection_id: string;
  title: string;
  content: string;
  effect: PolicyEffectValue;
  enabled: boolean;
  applies_to?: "INPUT" | "OUTPUT" | "BOTH" | string;
  rule_version?: number;
  category?: string | null;
  severity?: string | null;
  required_approver_role?: string | null;
  evaluation_type?: string | null;
  evaluator_profile_id?: string | null;
  intervention_points?: string[];
  content_targets?: {
    mode?: string;
    paths?: string[];
    [key: string]: unknown;
  } | null;
  minimum_confidence?: number | null;
  failure_mode?: string | null;
  remediation_type?: string | null;
  remediation_config?: Record<string, unknown> | null;
  inline_enforcement_required?: boolean;
  evaluation_timeout_ms?: number | null;
  coverage_status?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ToolRuleConditionSummary {
  id?: string;
  parameter_path: string;
  operator: string;
  value_type: string;
  value?: unknown;
  sort_order?: number;
}

export interface ToolRuleSummary {
  id: string;
  policy_collection_id: string;
  title: string;
  description?: string | null;
  mcp_server_id?: string | null;
  tool_id: string;
  match_mode: "ALL" | "ANY";
  effect: PolicyEffectValue;
  enabled: boolean;
  required_approver_role?: string | null;
  severity?: string | null;
  category?: string | null;
  conditions: ToolRuleConditionSummary[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PolicyCollectionDetail {
  collection: PolicyCollectionSummary;
  content_rules: ContentRuleSummary[];
  tool_rules: ToolRuleSummary[];
}

export type EnforcementDecisionValue = "ALLOW" | "DENY" | "REQUIRE_APPROVAL" | "MONITOR";

export interface EnforcementReceiptSummary {
  id: string;
  runtime_identity_id: string;
  runtime_identity_name?: string | null;
  ai_system_id: string;
  ai_system_name?: string | null;
  agent_id: string;
  agent_name?: string | null;
  agent_avatar?: string | null;
  agent_version_id: string;
  agent_version_number?: number | null;
  delegation_id?: string | null;
  enforcement_mode: string;
  deployment_control?: string | null;
  verification_status?: string | null;
  integration_type: string;
  integration_id?: string | null;
  integration_name?: string | null;
  tool_id?: string | null;
  tool_name?: string | null;
  action_digest: string;
  action_summary?: Record<string, unknown> | null;
  policy_effect?: string | null;
  policy_decision?: Record<string, unknown> | null;
  matched_rule_ids: string[];
  approval_request_id?: string | null;
  approval_consumed: boolean;
  approval_status?: string | null;
  enforcement_decision: EnforcementDecisionValue;
  reason_code?: string | null;
  human_explanation?: string | null;
  execution_attempted: boolean;
  execution_status: string;
  execution_source?: string | null;
  downstream_reference?: string | null;
  monitor: boolean;
  monitoring_instruction?: string | null;
  client_type?: string | null;
  correlation_id?: string | null;
  trace_id?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  reported_at?: string | null;
  duration_ms?: number | null;
}

export interface EnforcementReceiptDetail {
  id: string;
  decision: EnforcementDecisionValue;
  reason?: string | null;
  reason_code?: string | null;
  identity: {
    ai_system_id: string;
    ai_system_name?: string | null;
    agent_id: string;
    agent_name?: string | null;
    agent_avatar?: string | null;
    agent_version_id: string;
    agent_version_number?: number | null;
    runtime_identity_id: string;
    runtime_identity_name?: string | null;
    delegation_id?: string | null;
  };
  client_context?: {
    client_type?: string | null;
    client_version?: string | null;
    hook_event?: string | null;
    session_id?: string | null;
    conversation_id?: string | null;
    generation_id?: string | null;
    workspace?: string[] | null;
    observed_model?: string | null;
    observed_client_user?: string | null;
  } | null;
  action: {
    integration_type: string;
    integration_id?: string | null;
    integration_name?: string | null;
    tool_id?: string | null;
    tool_name?: string | null;
    target?: unknown;
    parameters?: Record<string, unknown>;
    action_digest: string;
    idempotency_key?: string | null;
    action_summary?: Record<string, unknown> | null;
  };
  policy_evaluation: {
    final_effect?: string | null;
    matched_rule_ids: string[];
    matched_rules?: Array<{
      rule_id: string;
      title?: string | null;
      effect?: string | null;
      matched?: boolean;
      conditions?: Array<{
        parameter_path?: string;
        operator?: string;
        matched?: boolean;
        detail?: unknown;
      }>;
    }>;
    condition_details?: unknown[];
    precedence?: string;
    explanation?: string | null;
    content_rule_enforcement?: { status: string; reason?: string };
    tool_rule_enforcement?: { status: string; mode?: string };
  };
  approval: {
    required: boolean;
    status?: string;
    approval_request_id?: string | null;
    required_approver_role?: string | null;
    requested_at?: string | null;
    decision_time?: string | null;
    approver?: string | null;
    action_digest?: string | null;
    consumed_at?: string | null;
    consumed?: boolean;
  };
  execution: {
    attempted: boolean;
    status: string;
    source?: string | null;
    downstream_reference?: string | null;
    duration_ms?: number | null;
    report?: Record<string, unknown> | null;
    reported_at?: string | null;
  };
  assurance: {
    enforcement_mode: string;
    deployment_control?: string | null;
    verification_status?: string | null;
    execution_evidence?: string | null;
    notes?: string | null;
  };
  trace: {
    receipt_id: string;
    correlation_id?: string | null;
    trace_id?: string | null;
    session_id?: string | null;
    conversation_id?: string | null;
    generation_id?: string | null;
    approval_request_id?: string | null;
    execution_id?: string | null;
    reason_code?: string | null;
  };
  timestamps: {
    started_at?: string | null;
    completed_at?: string | null;
    reported_at?: string | null;
  };
}

export interface RuntimeActionResult {
  allowed: boolean;
  effect: EnforcementDecisionValue;
  reason_code?: string | null;
  human_explanation: string;
  runtime_identity_id?: string | null;
  agent_version_id?: string | null;
  action_digest?: string | null;
  policy_decision?: Record<string, unknown> | null;
  approval_request_id?: string | null;
  approval_consumed: boolean;
  monitor: boolean;
  monitoring_instruction?: string | null;
  execution_attempted: boolean;
  execution_status: string;
  correlation_id?: string | null;
  trace_id?: string | null;
  receipt_id?: string | null;
  downstream_reference?: string | null;
  enforcement_mode?: string | null;
}

export interface RuntimeTestRequest {
  integration_type?: string;
  integration_id?: string;
  tool_id?: string;
  target?: { type: string; id?: string };
  parameters?: Record<string, unknown>;
  approval_request_id?: string;
  idempotency_key?: string;
  delegation_id?: string;
}

export interface ClientIntegrationSummary {
  id: string | null;
  runtime_identity_id: string;
  client_type: string;
  enforcement_mode: string;
  deployment_control?: string | null;
  verification_status?: string | null;
  status: string;
  client_version?: string | null;
  bridge_version?: string | null;
  protocol_version?: string | null;
  configuration_status?: string | null;
  coverage?: Record<string, string>;
  coverage_disclaimer?: string | null;
  last_seen_at?: string | null;
  last_decision_at?: string | null;
  last_decision_effect?: string | null;
}

export interface ClientIntegrationSetup {
  integration_id: string;
  client_type: string;
  enforcement_mode: string;
  status: string;
  coverage: Record<string, string>;
  protocol_version: number;
  bridge_version: string;
  hook_config: Record<string, unknown>;
  environment: Record<string, string>;
  install_steps: string[];
}

// WP5 trajectory evidence

export type TrajectoryStatusValue = "ACTIVE" | "COMPLETED" | "INCOMPLETE" | "FAILED";

export interface TrajectorySummary {
  id: string;
  ai_system_id: string;
  ai_system_name?: string | null;
  agent_id: string;
  agent_name?: string | null;
  agent_avatar?: string | null;
  agent_version_id: string;
  agent_version_number?: number | null;
  runtime_identity_id: string;
  runtime_identity_name?: string | null;
  client_integration_id?: string | null;
  client_type?: string | null;
  delegation_id?: string | null;
  /** Embedded delegation grant when trajectory.delegation_id is set. */
  delegation?: DelegationSummary | null;
  session_key: string;
  conversation_id?: string | null;
  runtime_conversation_id?: string | null;
  client_session_id?: string | null;
  correlation_id?: string | null;
  trajectory_semantics?: string | null;
  started_at?: string | null;
  last_event_at?: string | null;
  ended_at?: string | null;
  status: TrajectoryStatusValue | string;
  enforcement_mode?: string | null;
  deployment_control?: string | null;
  assurance_summary?: {
    highest?: string;
    has_client_reported?: boolean;
    has_authoritative?: boolean;
  } | null;
  coverage_summary?: Record<string, string> | null;
  event_count: number;
  finding_count: number;
  completeness_pct?: number | null;
  eligible_for_purge_at?: string | null;
  legal_hold?: boolean;
  retention_days?: number | null;
  economics?: {
    total_cost: number | null;
    currency: string;
    cost_state: string;
    metering_source?: string;
    total_tokens: number;
    model_calls: number;
    tool_calls: number;
    duration_ms?: number | null;
  } | null;
}

export interface EvidenceEvent {
  id: string;
  trajectory_id: string;
  event_type: string;
  occurred_at?: string | null;
  recorded_at?: string | null;
  sequence_number: number;
  source_type: string;
  source_reference: string;
  assurance_level: string;
  correlation_id?: string | null;
  trace_id?: string | null;
  payload?: Record<string, unknown> | null;
  payload_digest?: string | null;
  content_handling_mode: string;
  redaction_status: string;
  content_preview?: string | null;
  content_status?: string | null;
}

export type ContentHandlingModeValue =
  "FULL" | "REDACTED" | "HASH_ONLY" | "METADATA_ONLY" | "DO_NOT_STORE";

export interface EvidenceEventDetail extends EvidenceEvent {
  artifacts: EvidenceArtifact[];
  related_events: Array<{
    id: string;
    event_type: string;
    occurred_at?: string | null;
    sequence_number: number;
    source_type: string;
    assurance_level: string;
  }>;
  trajectory?: {
    id: string;
    conversation_id?: string | null;
    client_session_id?: string | null;
    correlation_id?: string | null;
    deployment_control?: string | null;
    ai_system_name?: string | null;
    agent_name?: string | null;
    agent_version_number?: number | null;
    runtime_identity_name?: string | null;
    client_type?: string | null;
  };
}

export interface EvidenceRelation {
  id: string;
  trajectory_id: string;
  source_entity_type: string;
  source_entity_id: string;
  relation_type: string;
  target_entity_type: string;
  target_entity_id: string;
  created_at?: string | null;
}

export interface EvidenceFinding {
  id: string;
  trajectory_id: string;
  finding_type: string;
  severity: string;
  title: string;
  description?: string | null;
  source_event_ids: string[];
  status: string;
  created_at?: string | null;
}

export interface EvidenceArtifact {
  id: string;
  trajectory_id: string;
  event_id?: string | null;
  artifact_type: string;
  source_type: string;
  content_location?: string | null;
  inline_content?: string | null;
  content_digest?: string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
  content_handling_mode: string;
  sensitivity_classification?: string | null;
  encrypted: boolean;
  created_at?: string | null;
}

export interface TrajectoryDetail extends TrajectorySummary {
  events: EvidenceEvent[];
  relations: EvidenceRelation[];
  findings: EvidenceFinding[];
  artifacts: EvidenceArtifact[];
}

export interface TrajectoryGraph {
  trajectory_id: string;
  nodes: Array<{
    id: string;
    entity_type: string;
    label: string;
    source_type?: string;
    assurance_level?: string;
    occurred_at?: string | null;
    severity?: string;
    title?: string;
  }>;
  edges: EvidenceRelation[];
}

export interface TrajectoryListResponse {
  items: TrajectorySummary[];
  total?: number;
  limit: number;
  offset: number;
}

export interface LifecycleContentBlock {
  availability: string;
  preview?: string | null;
  reason?: string | null;
}

export interface LifecycleEvidenceBlock {
  source: string;
  assurance: string;
}

export interface LifecycleStage {
  id: string;
  type: "INPUT" | "MODEL" | "ACTION" | "OUTPUT" | "COMPLETED" | string;
  label: string;
  status: string;
  occurred_at?: string | null;
  event_ids: string[];
  content?: LifecycleContentBlock;
  evidence?: LifecycleEvidenceBlock;
  model?: { observed_model?: string | null; observational?: boolean };
  authority?: {
    status: string;
    runtime_identity?: { id: string; name?: string | null };
    delegation?: {
      id: string;
      status?: string;
      delegator_type?: string;
      delegator_id?: string;
    } | null;
  };
  policy?: {
    status: string;
    decision?: string | null;
    matched_rules?: Array<{ id?: string; name?: string | null }>;
  };
  approval?: { required: boolean; status?: string };
  enforcement?: {
    decision?: string | null;
    mode?: string | null;
    assurance?: string | null;
    status?: string;
  };
  execution?: {
    status: string;
    duration_ms?: number | null;
    error?: string | null;
  };
  result?: LifecycleContentBlock;
}

export interface TrajectoryLifecycle {
  trajectory_id: string;
  conversation_id?: string | null;
  runtime_conversation_id?: string | null;
  status: string;
  summary: {
    started_at?: string | null;
    completed_at?: string | null;
    duration_ms?: number | null;
    risk_level?: string | null;
    assurance?: string | null;
    event_count?: number;
    ai_system_name?: string | null;
    agent_name?: string | null;
    agent_version_number?: number | null;
    coverage_summary?: Record<string, string> | null;
    completeness_pct?: number | null;
  };
  /** Application-reported config identifiers — not RAI-owned prompts/persona. */
  configuration_provenance?: {
    configuration_id?: string | null;
    configuration_version?: string | null;
    configuration_digest?: string | null;
    configuration_source?: string | null;
    configuration_environment?: string | null;
    deployment_id?: string | null;
    release_id?: string | null;
    source?: string | null;
    assurance?: string | null;
  } | null;
  stages: LifecycleStage[];
}

export interface TrajectoryRiskFindings {
  trajectory_id: string;
  highest_risk_level?: string | null;
  evidence_findings: EvidenceFinding[];
  risk: TrajectoryRiskBundle;
}

export interface RuntimeConversationSummary {
  id: string;
  organization_id: string;
  conversation_key: string;
  external_conversation_id: string;
  client_integration_id?: string | null;
  runtime_identity_id?: string | null;
  ai_system_id?: string | null;
  primary_agent_id?: string | null;
  principal_reference?: string | null;
  channel?: string | null;
  started_at?: string | null;
  last_activity_at?: string | null;
  status: string;
  trajectory_count: number;
  event_count: number;
  action_count: number;
  finding_count: number;
  highest_risk_level?: string | null;
  highest_assurance_level?: string | null;
  last_trajectory_id?: string | null;
  ai_system_name?: string | null;
  agent_name?: string | null;
  runtime_identity_name?: string | null;
  client_type?: string | null;
  economics?: {
    total_cost: number | null;
    currency?: string;
    cost_state?: string;
    total_tokens?: number;
    average_cost_per_turn?: number | null;
    model_calls?: number;
    duration_ms?: number | null;
  } | null;
}

export interface ConversationPolicyTrigger {
  id: string;
  kind: "event" | "evidence_finding" | "risk_finding" | string;
  category: "budget" | "tool" | "content" | "finding" | "governance" | "policy" | string;
  event_type: string;
  title: string;
  summary?: string | null;
  severity?: string | null;
  status?: string | null;
  trajectory_id?: string | null;
  occurred_at?: string | null;
  payload?: Record<string, unknown>;
}

export interface ConversationListResponse {
  items: RuntimeConversationSummary[];
  next_cursor?: string | null;
  has_more: boolean;
  limit: number;
}

export interface AuditRecord {
  id: string;
  record_type: "ENFORCEMENT" | "EXECUTION" | "EVIDENCE_EVENT" | string;
  occurred_at?: string | null;
  conversation_id?: string | null;
  trajectory_id?: string | null;
  action?: string | null;
  decision?: string | null;
  execution_status?: string | null;
  status?: string | null;
  principal?: string | null;
  agent_id?: string | null;
  agent_name?: string | null;
  ai_system_id?: string | null;
  ai_system_name?: string | null;
  runtime_identity_id?: string | null;
  runtime_identity_name?: string | null;
  delegation_id?: string | null;
  correlation_id?: string | null;
  assurance?: string | null;
  risk?: string | null;
  detail_reference?: string | null;
}

export interface AuditSearchResponse {
  items: AuditRecord[];
  next_cursor?: string | null;
  has_more: boolean;
  limit: number;
  filters?: {
    date_from?: string;
    date_to?: string;
    entity_types?: string[];
  };
}

export interface ObservedPromptSummary {
  id: string;
  trajectory_id: string;
  occurred_at?: string | null;
  content_preview?: string | null;
  content_bytes?: number | null;
  content_handling_mode?: string | null;
  content_status?: string | null;
  trajectory_score?: number | null;
  trajectory_status?: string | null;
  enforcement_status?: string | null;
  execution_status?: string | null;
  event_count: number;
  ai_system_id?: string | null;
  ai_system_name?: string | null;
  agent_id?: string | null;
  agent_name?: string | null;
  agent_avatar?: string | null;
  runtime_identity_id?: string | null;
  runtime_identity_name?: string | null;
  client_type?: string | null;
  correlation_id?: string | null;
}

export interface ObservedPromptDetail extends ObservedPromptSummary {
  user_prompt?: string | null;
  client_user_email?: string | null;
  observed_model?: string | null;
  ai_identity?: {
    runtime_identity_id: string;
    runtime_identity_name?: string | null;
    ai_system_id: string;
    ai_system_name?: string | null;
    agent_id: string;
    agent_name?: string | null;
    agent_avatar?: string | null;
    agent_version_id: string;
  };
  model_responses: EvidenceEvent[];
  agent_outputs: EvidenceEvent[];
  policy_evaluations: EvidenceEvent[];
  rejections: EvidenceEvent[];
  events: EvidenceEvent[];
  findings: EvidenceFinding[];
}

// WP6 risk intelligence

export interface RiskOverview {
  active_findings: number;
  critical_findings: number;
  high_critical_risks?: number;
  monitored_scopes: number;
  budgets_near_limit?: number;
  budgets_exceeded?: number;
  recent_anomalies?: number;
  suspended_runtime_identities?: number;
  pending_interventions: number;
  recent_interventions?: number;
  open_recommendations: number;
  evaluator: ContentEvaluatorConfig;
  window_presets?: Record<string, number>;
}

export interface RuntimeBudget {
  id: string;
  organization_id?: string | null;
  ai_system_id?: string | null;
  name: string;
  scope_type: string;
  scope_id?: string | null;
  metric: string;
  tool_name?: string | null;
  tool_id?: string | null;
  resource_filter?: Record<string, unknown> | null;
  limit_value: number;
  window_seconds: number;
  warning_threshold: number;
  effect_on_exceed: string;
  amount_parameter_path?: string | null;
  enabled: boolean;
  current_usage?: number;
  remaining?: number;
  utilization_pct?: number;
  status?: string;
  window_start?: string;
  effect?: string;
  created_at?: string | null;
  /** Total budget evaluations recorded. */
  check_count?: number;
  /** WARNING + EXCEEDED evaluations (policy triggered). */
  trigger_count?: number;
  warning_count?: number;
  exceeded_count?: number;
}

export interface RuntimeBudgetCheck {
  id: string;
  budget_id: string;
  ai_system_id?: string | null;
  ai_system_name?: string | null;
  agent_id?: string | null;
  agent_name?: string | null;
  agent_avatar?: string | null;
  runtime_identity_id?: string | null;
  trajectory_id?: string | null;
  conversation_id?: string | null;
  runtime_conversation_id?: string | null;
  metric: string;
  window_seconds: number;
  usage_before: number;
  attempted_increment: number;
  projected_usage: number;
  limit_value: number;
  status: string;
  decision: string;
  effect?: string | null;
  economics?: {
    total_cost: number | null;
    currency: string;
    cost_state: string;
    metering_source?: string;
    total_tokens: number;
  } | null;
  created_at?: string | null;
}

export interface RuntimeRiskFinding {
  id: string;
  trajectory_id?: string | null;
  ai_system_id: string;
  ai_system_name?: string | null;
  agent_id?: string | null;
  agent_name?: string | null;
  agent_version_id?: string | null;
  agent_version_number?: number | null;
  model_name?: string | null;
  runtime_identity_id?: string | null;
  finding_type: string;
  /** Mapped policy surface: tool | content | budget | governance */
  policy_kind?: string | null;
  title: string;
  description?: string | null;
  severity: string;
  confidence: number;
  sensitivity: string;
  category?: string | null;
  dimensions?: Record<string, unknown> | null;
  signal_ids?: string[] | null;
  evidence_refs?: unknown[] | null;
  policy_rule_ids?: string[] | null;
  intervention_effect?: string | null;
  status: string;
  explanation?: Record<string, unknown> | null;
  created_at?: string | null;
}

export interface RiskMonitor {
  id: string;
  ai_system_id: string;
  monitor_rule_id?: string | null;
  scope_type: string;
  scope_id: string;
  reason?: string | null;
  status: string;
  current_count: number;
  current_sum: number;
  threshold?: number | null;
  started_at?: string | null;
  expires_at?: string | null;
}

export interface InterventionDecision {
  id: string;
  trajectory_id?: string | null;
  ai_system_id: string;
  scope_type: string;
  scope_id: string;
  effect: string;
  reason?: string | null;
  risk_level?: string | null;
  confidence?: number | null;
  finding_id?: string | null;
  status: string;
  automatic: boolean;
  explanation?: Record<string, unknown> | null;
  executed_at?: string | null;
  executed_by?: string | null;
  created_at?: string | null;
}

export interface PolicyRecommendation {
  id: string;
  ai_system_id: string;
  recommendation_type: string;
  title: string;
  rationale?: string | null;
  proposed_rule?: Record<string, unknown> | null;
  confidence: number;
  status: string;
  draft_rule_id?: string | null;
  created_at?: string | null;
}

export interface ContentEvaluatorConfig {
  id?: string;
  ai_system_id?: string | null;
  status: string;
  enabled?: boolean;
  provider?: string;
  model?: string;
  reason?: string;
  health_status?: string;
  has_api_key?: boolean;
  temperature?: number;
  timeout_seconds?: number;
  max_rules_per_call?: number;
  confidence_threshold?: number;
  minimum_confidence_to_mark?: number;
  minimum_confidence_to_monitor?: number;
  minimum_confidence_to_intervene?: number;
  fail_closed?: boolean;
  fallback_provider?: string | null;
  last_success_at?: string | null;
  last_error_at?: string | null;
  latency_ms_avg?: number | null;
  error_rate?: number | null;
}

export interface TrajectoryRiskBundle {
  signals: Array<Record<string, unknown>>;
  findings: RuntimeRiskFinding[];
  interventions: InterventionDecision[];
  evaluations: Array<Record<string, unknown>>;
  risk_state?: Record<string, unknown> | null;
}

// --- WP7 Evaluation / Assurance ---------------------------------------------

export interface EvaluationSuite {
  id: string;
  ai_system_id: string;
  suite_key: string;
  name: string;
  category: string;
  version: number;
  description?: string | null;
  published: boolean;
  published_at?: string | null;
  runner_type: string;
  created_by: string;
  created_at?: string | null;
}

export interface EvaluationCase {
  id: string;
  suite_id: string;
  case_key: string;
  name: string;
  description?: string | null;
  input_fixture: Record<string, unknown>;
  expected_behavior: Record<string, unknown>;
  scoring_method: string;
  threshold: number;
  failure_severity: string;
  enabled: boolean;
  sort_order: number;
}

export interface EvaluationSuiteDetail extends EvaluationSuite {
  cases: EvaluationCase[];
}

export interface EvaluationRequirement {
  id: string;
  ai_system_id: string;
  name: string;
  category: string;
  evaluation_suite_id: string;
  minimum_score: number;
  maximum_failed_critical_cases: number;
  required: boolean;
  validity_days?: number | null;
  environment_scope: string;
  enabled: boolean;
  created_by: string;
  created_at?: string | null;
}

export interface EvaluationPlan {
  id: string;
  ai_system_id: string;
  agent_id: string;
  agent_version_id: string;
  target_environment: string;
  requirement_snapshot: EvaluationRequirement[];
  agent_config_digest?: string | null;
  dependency_digest?: string | null;
  plan_digest: string;
  status: string;
  created_by: string;
  created_at?: string | null;
}

export interface EvaluationCaseResult {
  id: string;
  case_key: string;
  case_id?: string | null;
  status: string;
  score: number;
  severity?: string | null;
  explanation?: string | null;
  actual_output?: unknown;
  evidence_refs?: Record<string, unknown> | null;
}

export interface EvaluationRun {
  id: string;
  plan_id: string;
  ai_system_id: string;
  agent_version_id: string;
  suite_id: string;
  suite_version: number;
  requirement_id?: string | null;
  runner_type: string;
  runner_version: string;
  status: string;
  score?: number | null;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  critical_failures: number;
  evidence?: Record<string, unknown> | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_by: string;
  created_at?: string | null;
}

export interface EvaluationRunDetail extends EvaluationRun {
  case_results: EvaluationCaseResult[];
}

export interface DeploymentGate {
  id: string;
  ai_system_id: string;
  name: string;
  environment: string;
  description?: string | null;
  conditions: Array<Record<string, unknown>>;
  enabled: boolean;
  created_by: string;
  created_at?: string | null;
}

export interface AssuranceRecord {
  id: string;
  ai_system_id: string;
  agent_version_id: string;
  environment: string;
  status: string;
  valid_from?: string | null;
  valid_until?: string | null;
  gate_evaluation_id?: string | null;
  evaluation_plan_id?: string | null;
  config_digest?: string | null;
  evidence_refs?: string[] | null;
  reason?: string | null;
  superseded_at?: string | null;
  created_by: string;
  created_at?: string | null;
}

export interface DeploymentGateEvaluationResult {
  id: string;
  gate_id?: string | null;
  ai_system_id: string;
  agent_version_id: string;
  evaluation_plan_id?: string | null;
  environment: string;
  decision: string;
  condition_results: Array<Record<string, unknown>>;
  reason?: string | null;
  evidence_refs?: string[] | null;
  evaluated_by: string;
  evaluated_at?: string | null;
  assurance?: AssuranceRecord | null;
  score_summary?: Record<string, number>;
}

export interface VersionAssurance {
  agent_version_id: string;
  environment: string;
  current: AssuranceRecord | null;
  history: AssuranceRecord[];
  reassessment_required: boolean;
  deployment_eligible: boolean;
}

export interface DeploymentReadiness {
  agent_version_id: string;
  environment: string;
  checks: Array<{ name: string; result: string; detail: string }>;
  eligible: boolean;
  assurance?: AssuranceRecord | null;
  reassessment_required?: boolean;
  open_failures: Array<{ name: string; result: string; detail: string }>;
}

export interface EvaluationWaiver {
  id: string;
  ai_system_id: string;
  agent_version_id: string;
  gate_evaluation_id?: string | null;
  environment: string;
  failed_condition: Record<string, unknown>;
  justification: string;
  compensating_controls?: Record<string, unknown> | unknown[] | null;
  status: string;
  requester: string;
  approver?: string | null;
  decision_reason?: string | null;
  valid_until?: string | null;
  created_at?: string | null;
  decided_at?: string | null;
  revoked_at?: string | null;
}

export interface AllPolicyRulesResponse {
  content_rules: Array<
    ContentRuleSummary & { ai_system_id?: string | null; ai_system_name?: string | null }
  >;
  tool_rules: Array<
    ToolRuleSummary & { ai_system_id?: string | null; ai_system_name?: string | null }
  >;
}

export type CatalogResourceType = "MODEL" | "MCP" | "DATA_SOURCE" | "SERVICE";

export interface CatalogAiSystemRef {
  id: string;
  name: string;
}

export interface ResourceCatalogItem {
  id: string;
  resource_type: CatalogResourceType | string;
  key: string;
  name: string;
  provider?: string | null;
  environment?: string | null;
  status: string;
  scope: string;
  details?: string | null;
  tool_count?: number | null;
  used_by_ai_systems: CatalogAiSystemRef[];
  dependency_count: number;
}

export interface ResourceCatalogResponse {
  items: ResourceCatalogItem[];
  total: number;
  limit: number;
  offset: number;
}

export type RaiRuleType = "CONTENT" | "TOOL";

export interface RaiRuleSourcePolicy {
  id: string;
  title: string;
  obligation_id?: string | null;
}

export interface UnifiedRaiRuleItem {
  id: string;
  rule_type: RaiRuleType | string;
  title: string;
  ai_system_id?: string | null;
  ai_system_name?: string | null;
  effect: string;
  enabled: boolean;
  status: string;
  severity?: string | null;
  category?: string | null;
  applies_to?: string | null;
  target?: string | null;
  intervention_points?: string[];
  evaluation_type?: string | null;
  coverage_status?: string | null;
  failure_mode?: string | null;
  remediation_type?: string | null;
  content?: string | null;
  description?: string | null;
  tool_id?: string | null;
  tool_name?: string | null;
  mcp_server_id?: string | null;
  match_mode?: string | null;
  required_approver_role?: string | null;
  rule_version?: number;
  conditions?: ToolRuleConditionSummary[];
  source_policy?: RaiRuleSourcePolicy | null;
  updated_at?: string | null;
  created_at?: string | null;
}

export interface UnifiedRaiRulesResponse {
  items: UnifiedRaiRuleItem[];
  total: number;
  limit: number;
  offset: number;
}

export type PolicySourceType = "FILE" | "URL" | "MANUAL_TEXT";

export interface PolicySourceSummary {
  id: string;
  scope?: "PLATFORM" | "ORGANIZATION" | string | null;
  source_key?: string | null;
  organization_id?: string | null;
  title: string;
  source_type: PolicySourceType | string;
  authority?: string | null;
  owner?: string | null;
  jurisdiction?: string | null;
  policy_type?: string | null;
  version?: string | null;
  effective_date?: string | null;
  status: string;
  source_uri?: string | null;
  content_digest?: string | null;
  ingestion_status: string;
  crawl_metadata?: Record<string, unknown> | null;
  obligation_count?: number;
  derived_rule_count?: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PolicySourceObligation {
  id: string;
  policy_source_id: string;
  section_ref?: string | null;
  topic?: string | null;
  scope?: string | null;
  constraint_action?: string | null;
  text?: string | null;
  status: string;
  structured?: Record<string, unknown> | null;
  created_at?: string | null;
}

export interface PolicySourceDetail extends PolicySourceSummary {
  content_text?: string | null;
  obligations: PolicySourceObligation[];
  derived_rules: Array<{
    id: string;
    rule_type: string;
    rule_id: string;
    obligation_id?: string | null;
    relationship_type: string;
  }>;
}

export interface PolicyLibraryListResponse {
  items: PolicySourceSummary[];
  total: number;
  limit: number;
  offset: number;
}

// --- WP8 Pilot & Governance -------------------------------------------------

export interface OrganizationGovernanceProfile {
  id: string;
  name?: string | null;
  description?: string | null;
  logo?: string | null;
  organization_id?: string;
  legal_name: string | null;
  organization_type: string;
  sector: string | null;
  jurisdiction: string | null;
  regulatory_context: Record<string, unknown> | null;
  risk_appetite: string | null;
  governance_owner: string | null;
  assurance_owner: string | null;
  incident_owner: string | null;
  default_review_frequency_days: number;
  evidence_retention_policy: Record<string, unknown> | null;
  pilot_status: string;
  updated_by: string | null;
  updated_at: string | null;
}

export interface Organization {
  id: string;
  org_key: string;
  name: string;
  description: string | null;
  status: string;
  created_by: string;
  created_at: string | null;
  updated_at: string | null;
  governance_profile?: OrganizationGovernanceProfile | null;
}

export interface OrganizationMembership {
  id: string;
  organization_id: string;
  user_id: string;
  user_name?: string | null;
  user_email?: string | null;
  role: string;
  status: string;
  valid_from: string | null;
  valid_until: string | null;
  created_by: string;
  created_at: string | null;
  department_id?: string | null;
  department_name?: string | null;
}

export interface Department {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  sort_order: number;
}

export interface AISystemAccountability {
  id: string;
  organization_id: string;
  ai_system_id: string;
  business_owner_membership_id: string | null;
  technical_owner_membership_id: string | null;
  rai_officer_membership_id: string | null;
  risk_owner_membership_id: string | null;
  incident_owner_membership_id: string | null;
  effective_from: string | null;
  effective_until: string | null;
  created_by: string;
  created_at: string | null;
  updated_at: string | null;
  missing_required_roles?: string[] | null;
}

export interface GovernanceClassification {
  id: string;
  organization_id: string;
  ai_system_id: string;
  business_criticality: string | null;
  data_sensitivity: string | null;
  customer_citizen_impact: string | null;
  financial_impact: string | null;
  autonomy_level: string | null;
  external_facing: boolean;
  consequential_actions: boolean;
  personal_data: boolean;
  regulated_process: boolean;
  human_oversight_requirement: string | null;
  production: boolean;
  updated_by: string | null;
  updated_at: string | null;
}

export interface ControlFramework {
  id: string;
  framework_key: string;
  name: string;
  version: string;
  description: string | null;
  is_internal: boolean;
  published: boolean;
  created_by: string;
  created_at: string | null;
  objectives?: Array<{
    id: string;
    code: string;
    title: string;
    category: string;
    description: string | null;
  }> | null;
}

export interface ControlAssessment {
  id: string;
  organization_id: string;
  ai_system_id: string;
  agent_version_id: string | null;
  control_requirement_id: string;
  applicability: string;
  applicability_reason: string | null;
  status: string;
  assessment_method: string;
  evidence_refs: Record<string, unknown> | unknown[] | null;
  assessed_by: string | null;
  assessed_at: string | null;
  valid_until: string | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface GovernanceReview {
  id: string;
  organization_id: string;
  ai_system_id: string;
  agent_version_id: string | null;
  review_type: string;
  status: string;
  requested_by: string;
  due_at: string | null;
  decision: string | null;
  decision_reason: string | null;
  conditions: Record<string, unknown> | unknown[] | null;
  evidence_snapshot: Record<string, unknown> | null;
  checklist: Record<string, unknown> | null;
  completed_at: string | null;
  decided_by: string | null;
  created_at: string | null;
  assignments?: Array<{
    id: string;
    review_id: string;
    membership_id: string | null;
    reviewer_user_id: string;
    role: string | null;
    assigned_at: string | null;
  }> | null;
}

export interface GovernanceException {
  id: string;
  organization_id: string;
  ai_system_id: string;
  agent_version_id: string | null;
  control_requirement_id: string | null;
  scope: Record<string, unknown> | null;
  business_justification: string;
  risk: string | null;
  compensating_controls: Record<string, unknown> | unknown[] | null;
  evidence_refs: Record<string, unknown> | unknown[] | null;
  status: string;
  requester: string;
  approver: string | null;
  decision_reason: string | null;
  valid_until: string | null;
  created_at: string | null;
  decided_at: string | null;
  revoked_at: string | null;
}

export interface IncidentCorrectiveAction {
  id: string;
  incident_id: string;
  description: string;
  owner: string;
  due_at: string | null;
  status: string;
  evidence: Record<string, unknown> | unknown[] | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface AIIncident {
  id: string;
  organization_id: string;
  ai_system_id: string;
  agent_version_id: string | null;
  runtime_identity_id: string | null;
  trajectory_id: string | null;
  severity: string;
  category: string;
  status: string;
  title: string;
  description: string | null;
  source: string;
  source_ref: string | null;
  detected_at: string | null;
  reported_by: string;
  incident_manager: string | null;
  containment_action: string | null;
  containment_ref: Record<string, unknown> | unknown[] | null;
  root_cause: string | null;
  corrective_actions_summary: string | null;
  evidence_refs: Record<string, unknown> | unknown[] | null;
  external_ticket_ref: string | null;
  closed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  corrective_actions?: IncidentCorrectiveAction[] | null;
  transitions?: Array<{
    id: string;
    from_status: string | null;
    to_status: string;
    actor: string;
    reason: string | null;
    metadata: Record<string, unknown> | null;
    created_at: string | null;
  }> | null;
}

export interface GovernanceEvidencePackage {
  id: string;
  organization_id: string;
  ai_system_id: string | null;
  agent_id: string | null;
  agent_version_id: string | null;
  review_id: string | null;
  incident_id: string | null;
  period_start: string | null;
  period_end: string | null;
  generated_by: string;
  generated_at: string | null;
  package_digest: string;
  has_report_html?: boolean;
  manifest?: Record<string, unknown> | null;
  report_html?: string | null;
}

export interface Pilot {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  sponsor: string | null;
  start_at: string | null;
  end_at: string | null;
  status: string;
  success_criteria: Record<string, unknown> | unknown[] | null;
  readiness_gate_id: string | null;
  created_by: string;
  created_at: string | null;
  updated_at: string | null;
  ai_systems?: Array<{
    id: string;
    pilot_id: string;
    ai_system_id: string;
    agent_version_id: string | null;
    added_at: string | null;
  }> | null;
}

export interface PilotReadinessResult {
  id?: string | null;
  organization_id?: string | null;
  pilot_id?: string | null;
  ai_system_id?: string | null;
  agent_version_id?: string | null;
  decision: string;
  dimensions: Array<Record<string, unknown>> | Record<string, Record<string, unknown>>;
  gaps: Array<Record<string, unknown>>;
  conditions?: Array<Record<string, unknown>> | null;
  evaluated_by?: string | null;
  evaluated_at?: string | null;
}

export interface PilotDashboard {
  organization_id: string;
  pilot: Pilot | null;
  pilot_status: string | null;
  readiness: {
    decision: string | null;
    evaluated_at: string | null;
    id: string | null;
  };
  kpis: {
    ai_systems_in_scope?: number;
    open_incidents?: number;
    critical_open_incidents?: number;
    open_critical_risks?: number;
    pending_reviews?: number;
    expiring_exceptions?: number;
    control_gaps?: number;
    control_coverage?: number | string | null;
  };
}

export interface DueWork {
  organization_id: string;
  reviews_due: GovernanceReview[];
  exceptions_expiring: GovernanceException[];
  assurance_expiring: Array<Record<string, unknown>>;
  corrective_actions_overdue: IncidentCorrectiveAction[];
  open_incidents: AIIncident[];
}

// --- WP9 Portfolio Transparency & Executive Oversight ---

export interface PortfolioFreshnessMeta {
  freshness: string;
  last_refreshed_at: string | null;
}

export interface PortfolioSummaryMetrics {
  total_ai_systems: number;
  active_ai_systems: number;
  production_versions: number;
  pilot_systems: number;
  suspended_systems: number;
  retired_systems: number;
  high_risk_systems: number;
  critical_risk_systems: number;
  open_critical_findings: number;
  valid_assurance: number;
  conditional_assurance: number;
  expired_assurance: number;
  failed_assurance: number;
  open_incidents: number;
  critical_incidents: number;
  open_exceptions: number;
  expiring_exceptions: number;
  active_waivers: number;
  expiring_waivers: number;
  pending_reviews: number;
  overdue_reviews: number;
  evidence_incomplete_systems: number;
}

export interface PortfolioSummary extends PortfolioFreshnessMeta {
  organization_id: string;
  metrics: PortfolioSummaryMetrics;
}

export interface PortfolioInventoryDrillDown {
  registry: string;
  risk: string;
  assurance: string;
  incidents: string;
  exceptions: string;
}

export interface PortfolioInventoryItem {
  ai_system_id: string;
  system_key: string;
  name: string;
  business_unit: string | null;
  owner_id: string | null;
  criticality: string | null;
  lifecycle: string;
  production_version_id: string | null;
  risk: string;
  assurance: string;
  assurance_valid_until: string | null;
  controls: string;
  open_incidents: number;
  open_exceptions: number;
  runtime_status: string;
  last_review_at: string | null;
  next_review_at: string | null;
  pilot_status: string | null;
  missing_accountability: boolean;
  drill_down: PortfolioInventoryDrillDown;
}

export interface PortfolioInventoryResponse extends PortfolioFreshnessMeta {
  organization_id: string;
  count: number;
  items: PortfolioInventoryItem[];
}

export interface PortfolioHeatmapCell {
  x: string;
  y: string;
  count: number;
}

export interface PortfolioRiskPosture extends PortfolioFreshnessMeta {
  organization_id: string;
  by_system: Array<{
    ai_system_id: string;
    name: string;
    business_unit: string | null;
    risk: string;
    drill_down: string;
  }>;
  by_business_unit: Record<string, Record<string, number>>;
  by_severity: Record<string, number>;
  by_category: Record<string, number>;
  heatmaps: {
    business_criticality_x_risk: PortfolioHeatmapCell[];
    data_sensitivity_x_runtime_risk: PortfolioHeatmapCell[];
    assurance_status_x_risk_severity: PortfolioHeatmapCell[];
    business_unit_x_critical_findings: PortfolioHeatmapCell[];
  };
  methodology: {
    aggregate_score: number | null;
    drivers: string[];
    note: string;
  };
}

export interface PortfolioAssuranceItem {
  ai_system_id: string;
  name: string | null;
  assurance_id: string;
  status: string;
  environment: string | null;
  valid_until: string | null;
  drill_down: string;
}

export interface PortfolioAssurancePosture extends PortfolioFreshnessMeta {
  organization_id: string;
  by_status: Record<string, number>;
  items: PortfolioAssuranceItem[];
  invalid_or_expired_production: PortfolioAssuranceItem[];
  expiring_in_7_days: PortfolioAssuranceItem[];
  expiring_in_30_days: PortfolioAssuranceItem[];
  expiring_in_90_days: PortfolioAssuranceItem[];
  active_waivers: Array<{
    waiver_id: string;
    ai_system_id: string;
    valid_until: string | null;
    drill_down: string;
  }>;
  disclaimer: string;
}

export interface PortfolioControlPosture extends PortfolioFreshnessMeta {
  organization_id: string;
  by_status: Record<string, number>;
  by_system: Record<string, Record<string, number>>;
  by_category: Record<string, number>;
  by_assessment_source: Record<string, number>;
  repeated_control_gaps: Array<{ requirement_key: string; systems_affected: number }>;
  external_mappings_sample: Array<{
    external_framework: string;
    external_requirement_id: string;
    external_requirement_title: string | null;
    internal_requirement_id: string;
  }>;
  disclaimer: string;
}

export interface PortfolioIncidentItem {
  id: string;
  ai_system_id: string;
  title: string;
  severity: string;
  status: string;
  category: string;
  detected_at: string | null;
  drill_down: string;
}

export interface PortfolioIncidentPosture extends PortfolioFreshnessMeta {
  organization_id: string;
  open_incidents: number;
  critical_incidents: number;
  average_incident_age_hours: number | null;
  average_time_to_contain_hours: number | null;
  average_time_to_resolve_hours: number | null;
  sla_compliance_claimed: boolean;
  by_category: Record<string, number>;
  systems_with_repeated_incidents: Array<{ ai_system_id: string; open_count: number }>;
  active_exceptions: number;
  expiring_exceptions: number;
  active_evaluation_waivers: number;
  expiring_waivers: number;
  repeated_exceptions_on_same_control: Array<{
    control_requirement_id: string;
    count: number;
  }>;
  items: PortfolioIncidentItem[];
}

export interface PortfolioRuntimeMetrics {
  governed_actions?: number;
  ALLOW?: number;
  DENY?: number;
  REQUIRE_APPROVAL?: number;
  approvals_requested?: number;
  approvals_approved?: number;
  approvals_rejected?: number;
  executions_succeeded?: number;
  executions_failed?: number;
  budget_exceeded_events?: number;
  runtime_suspensions?: number;
  content_violations?: number;
  anomalies?: number;
  [key: string]: number | undefined;
}

export interface PortfolioRuntimeActivity extends PortfolioFreshnessMeta {
  organization_id: string;
  period_days: number;
  metrics: PortfolioRuntimeMetrics;
  note?: string;
}

export interface PortfolioAttentionItem {
  type: string;
  severity: string;
  title: string;
  organization_id: string;
  ai_system_id: string | null;
  agent_version_id: string | null;
  source_type: string;
  source_id: string;
  due_at: string | null;
  reason: string;
  recommended_action: string;
  drill_down: string | null;
  created_at: string | null;
}

export interface PortfolioAttentionQueue extends PortfolioFreshnessMeta {
  organization_id: string;
  count: number;
  items: PortfolioAttentionItem[];
}

export interface PortfolioChangeItem {
  type?: string;
  title?: string;
  occurred_at?: string | null;
  ai_system_id?: string | null;
  source_type?: string;
  source_id?: string;
  drill_down?: string | null;
  [key: string]: unknown;
}

export interface PortfolioChangesResponse extends PortfolioFreshnessMeta {
  organization_id: string;
  period_days?: number;
  items: PortfolioChangeItem[];
}

export interface PortfolioTrendsResponse extends PortfolioFreshnessMeta {
  organization_id: string;
  period_days: number;
  trends?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface PortfolioEvidenceResponse extends PortfolioFreshnessMeta {
  organization_id: string;
  metrics?: Record<string, number>;
  items?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface PortfolioOwnershipResponse extends PortfolioFreshnessMeta {
  organization_id: string;
  by_business_unit?: Array<Record<string, unknown>>;
  by_owner?: Array<Record<string, unknown>>;
  missing_accountability?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface PortfolioDashboardKpis {
  ai_systems: number;
  critical_risk: number;
  invalid_assurance: number;
  critical_incidents: number;
  attention: number;
}

export interface PortfolioDashboard {
  organization_id: string;
  freshness: string;
  last_refreshed_at: string | null;
  period_days: number;
  kpis: PortfolioDashboardKpis;
  summary: PortfolioSummary;
  risk_posture: {
    by_severity: Record<string, number>;
    heatmaps: PortfolioRiskPosture["heatmaps"];
  };
  assurance_posture: {
    by_status: Record<string, number>;
    expiring_in_30_days: PortfolioAssuranceItem[];
  };
  control_coverage: {
    by_status: Record<string, number>;
  };
  runtime_activity: PortfolioRuntimeMetrics;
  attention: PortfolioAttentionQueue;
  recent_changes: PortfolioChangeItem[];
  upcoming_expiries: PortfolioAttentionItem[];
}

export interface PortfolioReportSummary {
  id: string;
  title: string;
  scope_type: string;
  scope_id: string | null;
  generated_at: string | null;
  generated_by: string;
  content_digest: string;
  schema_version: string;
}

export interface PortfolioReportListResponse {
  organization_id: string;
  total: number;
  limit: number;
  offset: number;
  items: PortfolioReportSummary[];
}

export interface PortfolioReport {
  id: string;
  organization_id: string;
  scope_type: string;
  scope_id: string | null;
  period_start: string | null;
  period_end: string | null;
  generated_at: string | null;
  generated_by: string;
  schema_version: string;
  title: string;
  content_digest: string;
  data_snapshot: Record<string, unknown> | null;
  source_manifest: Record<string, unknown> | null;
  freshness: string;
  report_html?: string | null;
}

export interface PortfolioReportSchedule {
  id: string;
  organization_id: string;
  cadence: string;
  scope_type: string;
  scope_id: string | null;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  last_report_id: string | null;
  delivery: Record<string, unknown> | null;
  created_by: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface PortfolioReportScheduleListResponse {
  organization_id: string;
  items: PortfolioReportSchedule[];
}

export interface ExecutiveGovernanceDecision {
  id: string;
  organization_id: string;
  scope_type: string;
  scope_id: string;
  decision: string;
  reason: string;
  actor: string;
  actor_role: string | null;
  evidence_refs: unknown;
  recommended_domain_actions: string[] | null;
  created_at: string | null;
  note?: string;
}

export interface ExecutiveGovernanceDecisionListResponse {
  organization_id: string;
  total: number;
  items: ExecutiveGovernanceDecision[];
}

export interface PortfolioExportResponse {
  organization_id: string;
  exported_at: string | null;
  exported_by: string;
  summary: PortfolioSummary;
  inventory: PortfolioInventoryResponse;
  attention: PortfolioAttentionQueue;
}

// ============================================================================
// Reporting & Analytics Types
// ============================================================================

export interface ReportScope {
  organization_id: string;
  ai_system_id?: string | null;
  agent_id?: string | null;
  runtime_identity_id?: string | null;
}

export interface ReportPeriod {
  start: string;
  end: string;
}

export interface Freshness {
  mode: "LIVE" | "NEAR_REAL_TIME" | "SNAPSHOT";
  last_refreshed_at: string;
}

export interface ComparisonMetric {
  value: number;
  previous_value?: number | null;
  change_pct?: number | null;
  trend_direction?: string | null;
}

export interface KpiMetric {
  title: string;
  value: number;
  previous_value?: number | null;
  change_pct?: number | null;
  trend_direction?: string | null;
  status_tone?: string | null;
  link?: string | null;
}

export interface SeverityDistribution {
  critical: number;
  high: number;
  medium: number;
  low: number;
  info?: number;
}

export interface EffectDistribution {
  allow: number;
  monitor: number;
  require_approval: number;
  deny: number;
  suspend: number;
}

export interface AttentionItem {
  type: string;
  severity: string;
  title: string;
  ai_system_id?: string | null;
  source_type: string;
  source_id: string;
  reason: string;
  recommended_action?: string | null;
  due_at?: string | null;
  created_at: string;
}

export interface TimeSeriesPoint {
  timestamp: string;
  value: number;
  label?: string | null;
}

export interface RankedItem {
  id: string;
  name: string;
  value: number;
  secondary_value?: number | null;
  severity?: string | null;
  link?: string | null;
}

export interface ReportSummary {
  scope: ReportScope;
  period: ReportPeriod;
  freshness: Freshness;
  ai_systems_governed: ComparisonMetric;
  governed_actions: ComparisonMetric;
  current_risk_exposure: ComparisonMetric;
  policy_intervention_rate: ComparisonMetric;
  budget_utilization_pct: ComparisonMetric;
  assurance_coverage_pct: ComparisonMetric;
  open_critical_findings: ComparisonMetric;
  risk_by_severity: SeverityDistribution;
  policy_effects: EffectDistribution;
  attention: AttentionItem[];
}

export interface RiskReport {
  scope: ReportScope;
  period: ReportPeriod;
  freshness: Freshness;
  open_findings: number;
  new_findings: number;
  resolved_findings: number;
  critical_findings: number;
  high_findings: number;
  mean_time_to_resolution_hours?: number | null;
  severity_distribution: SeverityDistribution;
  category_distribution: Record<string, number>;
  status_distribution: Record<string, number>;
  risk_by_ai_system: RankedItem[];
  risk_by_agent: RankedItem[];
  risk_by_tool: RankedItem[];
  risk_by_model: RankedItem[];
  finding_trends: TimeSeriesPoint[];
  attention: AttentionItem[];
}

export interface PolicyReport {
  scope: ReportScope;
  period: ReportPeriod;
  freshness: Freshness;
  evaluations: number;
  triggers: number;
  trigger_rate: number;
  intervention_rate: number;
  deny_rate: number;
  effects: EffectDistribution;
  top_policies: RankedItem[];
  evaluation_trends: TimeSeriesPoint[];
  trigger_trends: TimeSeriesPoint[];
}

export interface BudgetStatus {
  id: string;
  name: string;
  metric: string;
  current_usage: number;
  limit_value: number;
  warning_threshold: number;
  utilization_pct: number;
  status: string;
  window: string;
  warning_events: number;
  exceeded_events: number;
}

export interface BudgetReport {
  scope: ReportScope;
  period: ReportPeriod;
  freshness: Freshness;
  total_budgets: number;
  budgets_warning: number;
  budgets_exceeded: number;
  total_cost: number;
  total_tokens: number;
  budgets: BudgetStatus[];
  cost_trends: TimeSeriesPoint[];
  token_trends: TimeSeriesPoint[];
}

export interface RuntimeReport {
  scope: ReportScope;
  period: ReportPeriod;
  freshness: Freshness;
  governed_actions: number;
  executions: number;
  conversations: number;
  execution_success_rate: number;
  policy_evaluations: number;
  interventions: number;
  approvals_required: number;
  denied: number;
  runtime_suspensions: number;
}

export interface AssuranceReport {
  scope: ReportScope;
  period: ReportPeriod;
  freshness: Freshness;
  assurance_coverage_pct: number;
  valid_assurance: number;
  conditional_assurance: number;
  expired_assurance: number;
  failed_assurance: number;
  evaluation_pass_rate: number;
  failed_deployment_gates: number;
  active_waivers: number;
  expiring_waivers: number;
  open_exceptions: number;
  expiring_exceptions: number;
}

export interface AISystemReport {
  scope: ReportScope;
  period: ReportPeriod;
  freshness: Freshness;
  executions: number;
  conversations: number;
  governed_actions: number;
  execution_success_rate: number;
  open_findings: number;
  critical_findings: number;
  risk_score?: number | null;
  risk_trend?: string | null;
  policy_trigger_rate: number;
  deny_rate: number;
  approval_rate: number;
  budget_usage: number;
  token_usage: number;
  cost: number;
  assurance_status?: string | null;
  evidence_completeness_pct?: number | null;
  incidents: number;
  exceptions: number;
  evaluation_waivers: number;
  risk_by_agent: RankedItem[];
  risk_by_tool: RankedItem[];
  risk_by_model: RankedItem[];
}

export interface ConversationReport {
  scope: ReportScope;
  period: ReportPeriod;
  freshness: Freshness;
  turns: number;
  actions: number;
  tool_calls: number;
  policy_evaluations: number;
  policy_triggers: number;
  findings: number;
  highest_risk?: string | null;
  approvals_requested: number;
  approvals_approved: number;
  approvals_rejected: number;
  denied_actions: number;
  budget_events: number;
  token_usage?: number | null;
  cost?: number | null;
  evidence_completeness_pct?: number | null;
  events: unknown[];
}

export interface ReportSnapshot {
  id: string;
  organization_id: string;
  report_type: string;
  scope_type: string;
  scope_id?: string | null;
  period_start: string;
  period_end: string;
  filters_json: Record<string, unknown>;
  generated_at: string;
  generated_by: string;
  schema_version: string;
  data_snapshot: Record<string, unknown>;
  source_manifest?: Record<string, string[]> | null;
  content_digest: string;
}

export interface ReportFilters {
  period_start?: string | null;
  period_end?: string | null;
  business_unit?: string | null;
  ai_system_id?: string | null;
  agent_id?: string | null;
  agent_version_id?: string | null;
  runtime_identity_id?: string | null;
  environment?: string | null;
  conversation_id?: string | null;
  trajectory_id?: string | null;
  policy_type?: string | null;
  policy_id?: string | null;
  effect?: string | null;
  decision?: string | null;
  risk_severity?: string[] | null;
  risk_category?: string[] | null;
  finding_status?: string[] | null;
  model_id?: string | null;
  tool_id?: string | null;
  mcp_server_id?: string | null;
  data_source_id?: string | null;
  budget_id?: string | null;
  budget_metric?: string | null;
}

export interface FinOpsTotals {
  total_cost: number | null;
  billed_cost?: number;
  metered_cost?: number;
  actual_cost: number;
  estimated_cost: number;
  unavailable_cost_count: number;
  currency: string;
  cost_state: string;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  reasoning_tokens: number;
  model_calls: number;
  tool_calls: number;
  trajectories: number;
  conversations: number;
  avg_cost_per_trajectory: number | null;
  avg_cost_per_conversation: number | null;
  avg_tokens_per_trajectory: number | null;
}

export interface FinOpsDashboard {
  period: { start: string; end: string };
  totals: FinOpsTotals;
  comparison: { total_cost_change_pct: number | null; total_tokens_change_pct: number | null };
  coverage: {
    span_count: number;
    cost_coverage_pct: number;
    billed_pct?: number;
    metered_pct?: number;
    actual_pct: number;
    estimated_pct: number;
    unavailable_pct: number;
    token_coverage_pct: number;
    model_attribution_pct: number;
    tenant_attribution_pct: number;
  };
  budget_pressure: { healthy: number; warning: number; exceeded: number };
  risk_associated_spend: number;
  prevented_estimated_spend: number;
}

export interface FinOpsBreakdownItem {
  key: string | null;
  label: string | null;
  cost: number;
  tokens: number;
  trajectories: number;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  avg_cost_per_call: number | null;
}

export interface TrajectoryEconomics {
  trajectory_id: string;
  conversation_id?: string | null;
  summary: {
    total_cost: number | null;
    currency: string;
    cost_state: string;
    metering_source?: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    model_calls: number;
    tool_calls: number;
  };
  spans: Array<{
    id: string;
    span_type: string;
    operation?: string | null;
    provider?: string | null;
    model?: string | null;
    total_tokens?: number | null;
    cost?: number | null;
    currency?: string;
    cost_state: string;
    metering_source?: string;
    duration_ms?: number | null;
  }>;
}

export interface WebhookEndpointSummary {
  id: string;
  organization_id: string;
  name: string;
  url: string;
  secret_prefix: string;
  event_types: string[];
  enabled: boolean;
  status: string;
  created_by: string;
  created_at?: string | null;
  last_rotated_at?: string | null;
}

export interface WebhookDeliverySummary {
  id: string;
  endpoint_id: string;
  event_type: string;
  event_id: string;
  status: string;
  attempt_count: number;
  last_error?: string | null;
  delivered_at?: string | null;
  created_at?: string | null;
}
