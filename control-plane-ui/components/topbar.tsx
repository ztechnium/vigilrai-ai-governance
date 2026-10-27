"use client";

import { Badge } from "@/components/ui/badge";
import { useAuth, usePermissions } from "@/lib/hooks/use-auth";

export function Topbar() {
  const { user, logout, isPlatformAdmin } = useAuth();
  const { tenant } = usePermissions();
  const displayRole = tenant?.roles[0] || "Member";
  const displayName = user?.name || user?.email || "Signed in";

  return (
    <header className="flex h-12 w-full items-center justify-end gap-2">
      <div className="mr-auto pl-10 text-xs text-ink-400 lg:pl-0">
        <span className="font-medium text-ink-700">Observe.</span> Evaluate. Enforce.
      </div>
      {user && (
        <div className="flex items-center gap-2">
          <Badge variant="neutral">{displayRole}</Badge>
          {isPlatformAdmin && <Badge variant="neutral">Platform Admin</Badge>}
        </div>
      )}
      <div className="mx-1 hidden h-5 w-px bg-base-200 sm:block" />
      <span className="hidden max-w-[180px] truncate text-xs text-ink-700 sm:inline">
        {displayName}
      </span>
      <button
        type="button"
        onClick={logout}
        className="rounded-md px-2 py-1 text-xs text-ink-500 hover:bg-base-700 hover:text-ink-900"
      >
        Sign Out
      </button>
    </header>
  );
}
