/**
 * Phase 19: Frontend Auth / Tenant Context Refactor
 *
 * This file provides the core authentication and authorization context for the frontend.
 * It replaces the legacy X-Admin-Role system with server-derived permissions.
 */

import { createContext } from "react";

export interface User {
  id: string;
  email: string;
  name: string;
  email_verified: boolean;
}

export interface OrganizationMembershipRef {
  id: string;
  role: string;
}

export interface Organization {
  id: string;
  org_key: string;
  name: string;
  status: string;
  roles: string[];
  welcome_completed?: boolean;
  memberships?: OrganizationMembershipRef[];
}

export interface AuthContextValue {
  user: User | null;
  organizations: Organization[];
  platformRoles: string[];
  isAuthenticated: boolean;
  isLoading: boolean;
  isPlatformAdmin: boolean;
  logout: () => void;
  refreshAuth: () => Promise<void>;
}

export interface OrganizationContextValue {
  activeOrganization: Organization | null;
  setActiveOrganization: (orgId: string) => void;
  isLoading: boolean;
}

export interface TenantPermissions {
  canRead: boolean;
  canWrite: boolean;
  canApprove: boolean;
  canManageGovernance: boolean;
  canManageIncidents: boolean;
  canAudit: boolean;
  roles: string[];
  permissions: string[];
}

export interface PermissionContextValue {
  tenant: TenantPermissions | null;
  platform: {
    roles: string[];
    isPlatformAdmin: boolean;
  };
  isLoading: boolean;
  refreshPermissions: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);
export const OrganizationContext = createContext<OrganizationContextValue | undefined>(undefined);
export const PermissionContext = createContext<PermissionContextValue | undefined>(undefined);
