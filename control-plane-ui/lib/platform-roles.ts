/**
 * Platform role helpers (UX only — backend remains authoritative).
 *
 * Aligns with `Principal.is_platform_admin()` in the gateway:
 * `admin` (legacy bootstrap) and `platform_admin`.
 */

/** Roles that grant full platform-admin nav / UX privileges. */
export const PLATFORM_ADMIN_ROLE_IDS = new Set(["admin", "platform_admin"]);

/** Broader set used at login to route platform operators to the dashboard. */
export const PLATFORM_OPERATOR_ROLE_IDS = new Set([
  "admin",
  "platform_admin",
  "platform_support",
  "general_admin",
]);

export function hasPlatformAdminAccess(roles: readonly string[] | null | undefined): boolean {
  if (!roles?.length) return false;
  return roles.some((role) => PLATFORM_ADMIN_ROLE_IDS.has(role));
}

export function hasPlatformOperatorAccess(roles: readonly string[] | null | undefined): boolean {
  if (!roles?.length) return false;
  return roles.some((role) => PLATFORM_OPERATOR_ROLE_IDS.has(role));
}

/**
 * Map nav.ts display role labels → server tenant role enums.
 * Roles absent from this map are treated as open to any authenticated user.
 */
export const NAV_ROLE_TO_TENANT_ROLES: Record<string, readonly string[]> = {
  "RAI Officer": ["ORGANIZATION_ADMIN", "RAI_OFFICER"],
  "General Admin": ["ORGANIZATION_ADMIN"],
  "Risk Officer": ["RISK_MANAGER", "RISK_OFFICER"],
  Auditor: ["AUDITOR"],
  "Incident Manager": ["INCIDENT_MANAGER"],
  "Business Approver": ["BUSINESS_APPROVER", "APPROVER"],
};

export function tenantHasNavRole(requiredNavRole: string, tenantRoles: readonly string[]): boolean {
  const mapped = NAV_ROLE_TO_TENANT_ROLES[requiredNavRole];
  if (mapped) {
    return mapped.some((serverRole) => tenantRoles.includes(serverRole));
  }
  // Unmapped nav labels (Prompt Author, etc.) — visible to authenticated tenants.
  return true;
}
