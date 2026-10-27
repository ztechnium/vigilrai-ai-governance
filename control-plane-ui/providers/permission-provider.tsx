"use client";

import { useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AuthContext,
  OrganizationContext,
  PermissionContext,
  type PermissionContextValue,
  type TenantPermissions,
} from "@/lib/auth-context";
import { apiGet } from "@/lib/api";

/**
 * PermissionProvider
 *
 * Loads server-derived permissions from /v1/auth/context.
 * These permissions are for UX purposes only (showing/hiding UI elements).
 * Backend authorization remains the source of truth.
 *
 * This provider:
 * - Loads tenant-scoped permissions for the active organization
 * - Exposes platform roles from AuthProvider
 * - Provides helper methods for permission checks
 * - Refreshes when organization changes
 */
export function PermissionProvider({ children }: { children: ReactNode }) {
  const auth = useContext(AuthContext);
  const org = useContext(OrganizationContext);
  const [tenantPermissions, setTenantPermissions] = useState<TenantPermissions | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  if (!auth) {
    throw new Error("PermissionProvider must be used within AuthProvider");
  }

  if (!org) {
    throw new Error("PermissionProvider must be used within OrganizationProvider");
  }

  const { isAuthenticated, platformRoles, isPlatformAdmin } = auth;
  const { activeOrganization } = org;

  const loadPermissions = useCallback(async () => {
    if (!isAuthenticated || !activeOrganization) {
      setTenantPermissions(null);
      return;
    }

    setIsLoading(true);
    try {
      // Load server-derived context (/v1/auth/context)
      const response = await apiGet<{
        roles: string[];
        permissions: string[];
      }>("/v1/auth/context");

      const data = response.data;
      const permissions = data.permissions || [];
      const roles = data.roles || [];

      // Derive permission flags from server-provided permissions
      setTenantPermissions({
        canRead: permissions.some((p) => p.endsWith(":read")),
        canWrite: permissions.some((p) => p.endsWith(":write") || p.endsWith(":manage")),
        canApprove:
          permissions.includes("governance:approve") || permissions.includes("review:approve"),
        canManageGovernance: permissions.includes("governance:manage"),
        canManageIncidents: permissions.includes("incident:manage"),
        canAudit: roles.includes("AUDITOR"),
        roles,
        permissions,
      });
    } catch (error) {
      console.error("Failed to load permissions:", error);
      // Fall back to membership roles from /v1/auth/me so nav stays usable.
      const fallbackRoles = activeOrganization?.roles ?? [];
      setTenantPermissions({
        canRead: fallbackRoles.length > 0,
        canWrite: fallbackRoles.some((r) => ["ORGANIZATION_ADMIN", "RAI_OFFICER"].includes(r)),
        canApprove: fallbackRoles.some((r) =>
          ["ORGANIZATION_ADMIN", "BUSINESS_APPROVER", "APPROVER"].includes(r),
        ),
        canManageGovernance: fallbackRoles.includes("ORGANIZATION_ADMIN"),
        canManageIncidents: fallbackRoles.includes("INCIDENT_MANAGER"),
        canAudit: fallbackRoles.includes("AUDITOR"),
        roles: fallbackRoles,
        permissions: [],
      });
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, activeOrganization]);

  useEffect(() => {
    void loadPermissions();
  }, [loadPermissions]);

  const value: PermissionContextValue = useMemo(
    () => ({
      tenant: tenantPermissions,
      platform: {
        roles: platformRoles,
        isPlatformAdmin,
      },
      isLoading,
      refreshPermissions: loadPermissions,
    }),
    [tenantPermissions, platformRoles, isPlatformAdmin, isLoading, loadPermissions],
  );

  return <PermissionContext.Provider value={value}>{children}</PermissionContext.Provider>;
}
