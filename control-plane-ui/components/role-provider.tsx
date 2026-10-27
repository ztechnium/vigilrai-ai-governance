/**
 * @deprecated This file is deprecated as part of Phase 19: Frontend Auth Refactor
 *
 * The legacy X-Admin-Role system has been replaced with server-derived permissions.
 * This file is kept for reference only and should not be used in new code.
 *
 * Migration:
 * - Replace RoleProvider with AuthProvider, OrganizationProvider, PermissionProvider
 * - Replace useRole() with useAuth(), useOrganization(), usePermissions()
 * - Remove X-Admin-Role header usage
 * - Use server-derived permissions from /v1/auth/context
 *
 * See:
 * - /workspace/control-plane-ui/providers/auth-provider.tsx
 * - /workspace/control-plane-ui/providers/organization-provider.tsx
 * - /workspace/control-plane-ui/providers/permission-provider.tsx
 * - /workspace/control-plane-ui/lib/hooks/use-auth.ts
 */

"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type Role =
  | "Prompt Requester"
  | "Prompt Author"
  | "Business Approver"
  | "RAI Officer"
  | "Risk Officer"
  | "Incident Manager"
  | "RAG Domain Owner"
  | "RAG Approver"
  | "General Admin"
  | "Auditor";

interface RoleContextValue {
  role: Role;
  setRole: (role: Role) => void;
}

export const ACTIVE_ADMIN_ROLE_STORAGE_KEY = "rai.cp.activeAdminRole";

const RoleContext = createContext<RoleContextValue | undefined>(undefined);

/**
 * @deprecated Use AuthProvider instead
 */
export function RoleProvider({ children }: { children: React.ReactNode }) {
  const [role, setRole] = useState<Role>("RAI Officer");

  useEffect(() => {
    const saved = window.localStorage.getItem(ACTIVE_ADMIN_ROLE_STORAGE_KEY) as Role | null;
    if (saved) {
      setRole(saved);
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(ACTIVE_ADMIN_ROLE_STORAGE_KEY, role);
  }, [role]);

  const value = useMemo(() => ({ role, setRole }), [role]);

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

/**
 * @deprecated Use useAuth(), useOrganization(), or usePermissions() instead
 */
export function useRole() {
  const context = useContext(RoleContext);
  if (!context) {
    throw new Error("useRole must be used within RoleProvider");
  }
  return context;
}
