"use client";

import { WelcomeWizard } from "@/components/onboarding/welcome-wizard";
import { useOrganization } from "@/lib/hooks/use-auth";

export default function WelcomePage() {
  const { activeOrganization, isLoading } = useOrganization();

  if (isLoading || !activeOrganization) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-ink-500">
        Loading your organization…
      </div>
    );
  }

  return <WelcomeWizard organizationId={activeOrganization.id} />;
}
