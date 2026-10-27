"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  AuthContext,
  type AuthContextValue,
  type Organization,
  type User,
} from "@/lib/auth-context";
import { ADMIN_AUTH_TOKEN_STORAGE_KEY, clearSessionTokens, getAuthMe } from "@/lib/api";
import { hasPlatformAdminAccess } from "@/lib/platform-roles";

/**
 * AuthProvider
 *
 * Manages user authentication state by loading /v1/auth/me.
 * This provider is the source of truth for:
 * - Current authenticated user
 * - User's organizations and their tenant roles
 * - User's platform roles
 *
 * This replaces the legacy X-Admin-Role system with server-derived authentication.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [platformRoles, setPlatformRoles] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const loadAuth = useCallback(async () => {
    const token = window.localStorage.getItem(ADMIN_AUTH_TOKEN_STORAGE_KEY);
    if (!token) {
      setIsLoading(false);
      return;
    }

    try {
      const response = await getAuthMe();
      setUser(response.data.user);
      const roles = response.data.roles ?? [];
      setOrganizations(
        roles.length
          ? [
              {
                id: "instance",
                org_key: "instance",
                name: "Organization",
                status: "ACTIVE",
                roles,
                welcome_completed: response.data.welcome_completed,
                memberships: response.data.memberships,
              },
            ]
          : [],
      );
      setPlatformRoles(response.data.platform_roles || []);
    } catch (error) {
      console.error("Failed to load auth:", error);
      // Clear stale token on auth failure
      clearSessionTokens();
      setUser(null);
      setOrganizations([]);
      setPlatformRoles([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAuth();
  }, [loadAuth]);

  const logout = useCallback(() => {
    clearSessionTokens();
    setUser(null);
    setOrganizations([]);
    setPlatformRoles([]);
    router.replace("/");
  }, [router]);

  // Match gateway Principal.is_platform_admin(): admin | platform_admin
  const isPlatformAdmin = useMemo(() => hasPlatformAdminAccess(platformRoles), [platformRoles]);

  const value: AuthContextValue = useMemo(
    () => ({
      user,
      organizations,
      platformRoles,
      isAuthenticated: !!user,
      isLoading,
      isPlatformAdmin,
      logout,
      refreshAuth: loadAuth,
    }),
    [user, organizations, platformRoles, isLoading, isPlatformAdmin, logout, loadAuth],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
