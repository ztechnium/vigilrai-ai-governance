import type { OrganizationMembershipRef } from "@/lib/auth-context";

const ROLE_ALIASES: Record<string, string> = {
  ORGANIZATION_ADMIN: "organization_admin",
  RAI_OFFICER: "rai_officer",
  RISK_COMPLIANCE_REVIEWER: "risk_officer",
  BUSINESS_APPROVER: "business_approver",
  AUDITOR: "auditor",
  INCIDENT_MANAGER: "incident_manager",
  AI_SYSTEM_OWNER: "ai_system_owner",
  BUSINESS_OWNER: "business_owner",
  TECHNICAL_OWNER: "technical_owner",
};

function normalizeRole(role: string) {
  const compact = role
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  return ROLE_ALIASES[compact.toUpperCase()] ?? compact;
}

/** Membership the signed-in user should send as acting_membership_id. */
export function pickActingMembershipId(
  memberships: OrganizationMembershipRef[] | undefined,
  requiredRoles?: string[] | null,
): string | null {
  const options = memberships ?? [];
  if (options.length === 0) return null;
  const required = (requiredRoles ?? []).map(normalizeRole).filter(Boolean);
  if (required.length > 0) {
    const match = options.find((membership) => required.includes(normalizeRole(membership.role)));
    if (match) return match.id;
  }
  return options[0].id;
}
