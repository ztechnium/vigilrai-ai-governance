"use client";

import { useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AuthContext,
  OrganizationContext,
  type Organization,
  type OrganizationContextValue,
} from "@/lib/auth-context";
import { ACTIVE_ORG_STORAGE_KEY } from "@/lib/api";

/**
 * OrganizationProvider
 *
 * Manages the current organization selection.
 * The selected organization ID is sent via X-Organization-ID header,
 * but the backend remains authoritative for membership validation.
 *
 * This provider:
 * - Tracks active organization selection
 * - Persists selection to localStorage
 * - Validates selection against user's membership
 * - Auto-selects first org if none selected
 */
export function OrganizationProvider({ children }: { children: ReactNode }) {
  const auth = useContext(AuthContext);
  const [activeOrgId, setActiveOrgId] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);

  if (!auth) {
    throw new Error("OrganizationProvider must be used within AuthProvider");
  }

  const { organizations, isAuthenticated } = auth;

  // Load active organization on mount and when organizations change
  useEffect(() => {
    if (!isAuthenticated || organizations.length === 0) {
      setIsLoading(false);
      return;
    }

    const storedOrgId = window.localStorage.getItem(ACTIVE_ORG_STORAGE_KEY);

    // If stored org is in user's memberships, use it
    if (storedOrgId && organizations.some((org) => org.id === storedOrgId)) {
      setActiveOrgId(storedOrgId);
    }
    // Otherwise, auto-select first org
    else if (organizations.length > 0) {
      const firstOrgId = organizations[0].id;
      setActiveOrgId(firstOrgId);
      window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, firstOrgId);
    }

    setIsLoading(false);
  }, [organizations, isAuthenticated]);

  const setActiveOrganization = useCallback(
    (orgId: string) => {
      // Validate that the organization exists in user's memberships
      if (!organizations.some((org) => org.id === orgId)) {
        console.error("Cannot select organization: user is not a member");
        return;
      }

      setActiveOrgId(orgId);
      window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, orgId);

      // Reload page to ensure all components refetch with new org context
      window.location.reload();
    },
    [organizations],
  );

  const activeOrganization = useMemo(
    () => organizations.find((org) => org.id === activeOrgId) || null,
    [organizations, activeOrgId],
  );

  const value: OrganizationContextValue = useMemo(
    () => ({
      activeOrganization,
      setActiveOrganization,
      isLoading,
    }),
    [activeOrganization, setActiveOrganization, isLoading],
  );

  return <OrganizationContext.Provider value={value}>{children}</OrganizationContext.Provider>;
}
