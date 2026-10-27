"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { AuthProvider } from "@/providers/auth-provider";
import { OrganizationProvider } from "@/providers/organization-provider";
import { PermissionProvider } from "@/providers/permission-provider";
import { useAuth, useOrganization } from "@/lib/hooks/use-auth";
import { ADMIN_AUTH_TOKEN_STORAGE_KEY, resendVerificationEmail } from "@/lib/api";
import { fetchWelcome } from "@/lib/public-api";
import { readWelcomeDoneLocally, welcomeDestination } from "@/lib/welcome-gate";

function AppShellContent({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, isAuthenticated, isLoading, isPlatformAdmin } = useAuth();
  const { activeOrganization, isLoading: orgLoading } = useOrganization();
  const [resendMsg, setResendMsg] = useState<string | null>(null);
  const [welcomeCompleted, setWelcomeCompleted] = useState<boolean | null>(null);

  const localWelcomeDone = activeOrganization
    ? readWelcomeDoneLocally(activeOrganization.id)
    : false;

  useEffect(() => {
    if (isLoading) return;

    const sessionToken = window.localStorage.getItem(ADMIN_AUTH_TOKEN_STORAGE_KEY);
    if (!sessionToken || !isAuthenticated) {
      router.replace("/");
    }
  }, [isAuthenticated, isLoading, router]);

  useEffect(() => {
    if (!isAuthenticated || isPlatformAdmin || !activeOrganization) {
      setWelcomeCompleted(isPlatformAdmin ? true : null);
      return;
    }
    let cancelled = false;
    void fetchWelcome(activeOrganization.id)
      .then((state) => {
        if (!cancelled) setWelcomeCompleted(state.welcome_completed);
      })
      .catch(() => {
        if (!cancelled) setWelcomeCompleted(localWelcomeDone);
      });
    return () => {
      cancelled = true;
    };
  }, [activeOrganization, isAuthenticated, isPlatformAdmin, localWelcomeDone, pathname]);

  const resolvedWelcome = isPlatformAdmin
    ? true
    : welcomeCompleted === true || localWelcomeDone
      ? true
      : welcomeCompleted;
  const destination = welcomeDestination({
    isPlatform: isPlatformAdmin,
    welcomeCompleted: resolvedWelcome,
    pathname,
  });

  useEffect(() => {
    if (destination) router.replace(destination);
  }, [destination, router]);

  async function onResend() {
    if (!user?.email) return;
    try {
      await resendVerificationEmail(user.email);
      setResendMsg("Verification email sent.");
    } catch (err) {
      setResendMsg(err instanceof Error ? err.message : "Failed to resend");
    }
  }

  if (isLoading) {
    return (
      <div className="console min-h-screen bg-base-100 p-6 text-sm text-ink-500">
        Loading authentication...
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="console min-h-screen bg-base-100 p-6 text-sm text-ink-500">
        Redirecting to login...
      </div>
    );
  }

  const waitingForWelcome =
    !isPlatformAdmin &&
    (orgLoading || (Boolean(activeOrganization) && welcomeCompleted === null && !localWelcomeDone));

  if (waitingForWelcome) {
    return (
      <div className="console flex min-h-screen items-center justify-center bg-base-100 text-sm text-ink-500">
        Loading your organization…
      </div>
    );
  }

  if (pathname === "/welcome") {
    return <div className="console min-h-screen bg-base-100 text-ink-900">{children}</div>;
  }

  const emailVerified = user?.email_verified ?? true;

  return (
    <div className="console min-h-screen bg-base-100 text-ink-900">
      <Sidebar />
      <div className="min-h-screen lg:pl-60">
        <div className="sticky top-0 z-20 border-b border-base-200 bg-base-100/95 px-4 backdrop-blur">
          <Topbar />
        </div>
        {!emailVerified && (
          <div className="border-b border-warn-600/40 bg-warn-50 px-4 py-3 text-sm text-warn-700">
            Verify your email to create or change AI systems and other governed resources.{" "}
            <button
              type="button"
              className="font-semibold underline"
              onClick={() => void onResend()}
            >
              Resend verification
            </button>
            {resendMsg ? <span className="ml-2">{resendMsg}</span> : null}
          </div>
        )}
        <main className="mx-auto max-w-[1680px] animate-fadeUp p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <OrganizationProvider>
        <PermissionProvider>
          <AppShellContent>{children}</AppShellContent>
        </PermissionProvider>
      </OrganizationProvider>
    </AuthProvider>
  );
}
