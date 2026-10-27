"use client";

import { usePermissions } from "@/lib/hooks/use-auth";

/**
 * RoleGuard - UI-level permission guard
 *
 * This is for UX only. Backend authorization remains the source of truth.
 * The component checks server-derived permissions from PermissionProvider.
 */
export function RoleGuard({
  roles,
  requirePlatform = false,
  children,
}: {
  roles?: string[];
  requirePlatform?: boolean;
  children: React.ReactNode;
}) {
  const { tenant, platform } = usePermissions();

  // Platform admin check
  if (requirePlatform && !platform.isPlatformAdmin) {
    return (
      <div className="rounded-xl border border-base-200 bg-base-100 p-6 text-sm text-ink-500">
        Access restricted. This section requires platform administrator permissions.
      </div>
    );
  }

  // Tenant role check
  if (roles && roles.length > 0) {
    const hasRequiredRole = roles.some((requiredRole) =>
      tenant?.roles.some(
        (userRole) =>
          userRole.toLowerCase().includes(requiredRole.toLowerCase()) ||
          requiredRole.toLowerCase().includes(userRole.toLowerCase()),
      ),
    );

    if (!hasRequiredRole && !platform.isPlatformAdmin) {
      return (
        <div className="rounded-xl border border-base-200 bg-base-100 p-6 text-sm text-ink-500">
          Access restricted. This section requires elevated permissions.
        </div>
      );
    }
  }

  return <>{children}</>;
}
