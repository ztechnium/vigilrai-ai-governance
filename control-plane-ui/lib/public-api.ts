import {
  ACTIVE_ORG_STORAGE_KEY,
  ADMIN_AUTH_TOKEN_STORAGE_KEY,
  PLATFORM_ADMIN_STORAGE_KEY,
  persistSessionTokens,
  refreshAccessTokenIfNeeded,
} from "@/lib/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export { ACTIVE_ORG_STORAGE_KEY };

export interface RegisterCompanyPayload {
  full_name: string;
  work_email: string;
  password: string;
  company_name: string;
  industry?: string;
  sector?: string;
  country: string;
  company_size?: string;
  primary_use_case?: string;
  terms_accepted: boolean;
}

export interface RegisterCompanyResponse {
  access_token: string;
  refresh_token?: string;
  token_type: "bearer";
  user: {
    email: string;
    user_id: string;
    roles: string[];
  };
  organization: {
    id: string;
    org_key: string;
    name: string;
  };
  onboarding: {
    status: string;
    current_step: string;
    completed_steps: string[];
  };
  verification_email_sent?: boolean;
  verification_email_error?: string | null;
}

export interface OnboardingStep {
  id: string;
  label: string;
  done: boolean;
  blocked?: boolean;
  blocked_reason?: string | null;
  href?: string;
}

export interface OnboardingResponse {
  organization_id: string;
  organization_status: string;
  onboarding: {
    organization_id: string;
    current_step: string;
    completed_steps: string[];
    first_ai_system_id: string | null;
    first_integration_id: string | null;
    first_trajectory_id: string | null;
    status: string;
  };
  steps: OnboardingStep[];
  complete: boolean;
  progress: { completed: number; total: number };
  next_recommended_action: string | null;
}

export class PublicApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

function authHeaders(_organizationId?: string): HeadersInit {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  if (typeof window !== "undefined") {
    const token = window.localStorage.getItem(ADMIN_AUTH_TOKEN_STORAGE_KEY);
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as {
      message?: string;
      detail?: string | { message?: string; error?: string };
    };
    if (body.message) return body.message;
    if (typeof body.detail === "string") return body.detail;
    if (body.detail && typeof body.detail === "object" && body.detail.message) {
      return body.detail.message;
    }
  } catch {
    // ignore
  }
  return fallback;
}

export function storeAuthSession(token: string, organizationId?: string, refreshToken?: string) {
  if (typeof window === "undefined") return;
  persistSessionTokens(token, refreshToken);
  // Public registration creates tenant users — never platform admins.
  window.localStorage.setItem(PLATFORM_ADMIN_STORAGE_KEY, "0");
  if (organizationId) {
    window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, organizationId);
  }
}

async function fetchWithAuthRetry(url: string, init: RequestInit): Promise<Response> {
  let response = await fetch(url, init);
  if (response.status === 401) {
    const refreshed = await refreshAccessTokenIfNeeded();
    if (refreshed) {
      // Rebuild headers so Authorization picks up the new access token.
      const headers = new Headers(init.headers);
      const token =
        typeof window !== "undefined"
          ? window.localStorage.getItem(ADMIN_AUTH_TOKEN_STORAGE_KEY)
          : null;
      if (token) headers.set("Authorization", `Bearer ${token}`);
      response = await fetch(url, { ...init, headers });
    }
  }
  return response;
}

export async function fetchOnboarding(organizationId: string): Promise<OnboardingResponse> {
  const response = await fetchWithAuthRetry(`${API_BASE_URL}/v1/productization/onboarding`, {
    headers: authHeaders(organizationId),
  });
  if (!response.ok) {
    throw new PublicApiError(
      await parseError(response, `Failed to load onboarding: ${response.status}`),
      response.status,
    );
  }
  return response.json() as Promise<OnboardingResponse>;
}

export async function patchOnboarding(
  organizationId: string,
  body: {
    current_step?: string;
    complete_step?: string;
    completed_steps?: string[];
    first_ai_system_id?: string;
    first_integration_id?: string;
    first_trajectory_id?: string;
    status?: string;
  },
): Promise<OnboardingResponse> {
  const response = await fetchWithAuthRetry(`${API_BASE_URL}/v1/productization/onboarding`, {
    method: "PATCH",
    headers: authHeaders(organizationId),
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new PublicApiError(
      await parseError(response, `Failed to update onboarding: ${response.status}`),
      response.status,
    );
  }
  return response.json() as Promise<OnboardingResponse>;
}

export interface SdkIntegrationSummary {
  id: string;
  organization_id: string;
  integration_key: string;
  name: string;
  integration_type: string;
  runtime_identity_id: string;
  environment: string;
  auth_method: string;
  protocol_version?: number;
  sdk_version?: string | null;
  enforcement_mode: string;
  deployment_control?: string | null;
  verification_status?: string | null;
  certification_status?: string | null;
  capability_matrix?: Record<string, boolean>;
  fail_closed: boolean;
  status: string;
  last_heartbeat_at?: string | null;
  created_at?: string | null;
}

export interface CreateSdkIntegrationPayload {
  organization_id: string;
  integration_key: string;
  name: string;
  runtime_identity_id: string;
  integration_type?: string;
  environment?: string;
  auth_method?: string;
  enforcement_mode?: string;
  fail_closed?: boolean;
  capability_matrix?: Record<string, boolean>;
  metadata?: Record<string, unknown>;
}

export async function listSdkIntegrations(organizationId: string): Promise<{
  items: SdkIntegrationSummary[];
}> {
  const response = await fetchWithAuthRetry(`${API_BASE_URL}/v1/productization/integrations`, {
    headers: authHeaders(organizationId),
  });
  if (!response.ok) {
    throw new PublicApiError(
      await parseError(response, `Failed to list integrations: ${response.status}`),
      response.status,
    );
  }
  return response.json() as Promise<{ items: SdkIntegrationSummary[] }>;
}

export async function createSdkIntegration(
  payload: CreateSdkIntegrationPayload,
): Promise<SdkIntegrationSummary> {
  const response = await fetchWithAuthRetry(`${API_BASE_URL}/v1/productization/integrations`, {
    method: "POST",
    headers: authHeaders(payload.organization_id),
    body: JSON.stringify({
      integration_type: "SDK",
      environment: "production",
      auth_method: "API_KEY",
      enforcement_mode: "HOOK_ENFORCED",
      fail_closed: true,
      ...payload,
    }),
  });
  if (!response.ok) {
    throw new PublicApiError(
      await parseError(response, `Failed to create integration: ${response.status}`),
      response.status,
    );
  }
  return response.json() as Promise<SdkIntegrationSummary>;
}

export interface WelcomeTemplate {
  key: string;
  name: string;
  description: string;
  risk_tier?: string | null;
  agent_name?: string | null;
  model_name?: string | null;
  tools: string[];
}

export interface WelcomeSetup {
  template_key?: string | null;
  ai_system_id?: string | null;
  integration_id?: string | null;
  tool_name?: string | null;
}

export interface WelcomeState {
  welcome_completed: boolean;
  welcome_completed_at?: string | null;
  organization: {
    id?: string;
    org_key?: string;
    name: string;
    logo?: string | null;
    industry?: string | null;
    description?: string | null;
    legal_name?: string | null;
  };
  setup: WelcomeSetup | null;
  templates: WelcomeTemplate[];
  seeded?: {
    template_key: string;
    system_name: string;
    ai_system_id: string;
    integration_id: string;
    tool_name: string;
  };
}

export async function fetchWelcome(organizationId: string): Promise<WelcomeState> {
  const response = await fetchWithAuthRetry(`${API_BASE_URL}/v1/productization/welcome`, {
    headers: authHeaders(organizationId),
  });
  if (!response.ok) {
    throw new PublicApiError(
      await parseError(response, `Failed to load welcome: ${response.status}`),
      response.status,
    );
  }
  return response.json() as Promise<WelcomeState>;
}

export async function saveWelcomeProfile(
  organizationId: string,
  body: { name: string; industry: string; logo?: string | null },
): Promise<WelcomeState> {
  const response = await fetchWithAuthRetry(`${API_BASE_URL}/v1/productization/welcome/profile`, {
    method: "PATCH",
    headers: authHeaders(organizationId),
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new PublicApiError(
      await parseError(response, `Failed to save organization profile: ${response.status}`),
      response.status,
    );
  }
  return response.json() as Promise<WelcomeState>;
}

export async function seedWelcomeTemplate(
  organizationId: string,
  templateKey: string,
): Promise<WelcomeState> {
  const response = await fetchWithAuthRetry(`${API_BASE_URL}/v1/productization/welcome/seed`, {
    method: "POST",
    headers: authHeaders(organizationId),
    body: JSON.stringify({ template_key: templateKey }),
  });
  if (!response.ok) {
    throw new PublicApiError(
      await parseError(response, `Failed to seed the example: ${response.status}`),
      response.status,
    );
  }
  return response.json() as Promise<WelcomeState>;
}

export async function completeWelcome(organizationId: string): Promise<WelcomeState> {
  const response = await fetchWithAuthRetry(`${API_BASE_URL}/v1/productization/welcome/complete`, {
    method: "POST",
    headers: authHeaders(organizationId),
  });
  if (!response.ok) {
    throw new PublicApiError(
      await parseError(response, `Failed to finish welcome: ${response.status}`),
      response.status,
    );
  }
  return response.json() as Promise<WelcomeState>;
}
