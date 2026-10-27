import { redirect } from "next/navigation";

/** Email / Lovable deep links use /onboarding; app route lives under /app/onboarding. */
export default function OnboardingAliasPage() {
  redirect("/app/onboarding");
}
