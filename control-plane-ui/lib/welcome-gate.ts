export function welcomeDestination(input: {
  isPlatform: boolean;
  welcomeCompleted: boolean | null;
  pathname: string;
}): string | null {
  if (input.isPlatform) {
    return input.pathname === "/welcome" ? "/dashboard" : null;
  }
  if (input.welcomeCompleted === null) return null;
  if (!input.welcomeCompleted && input.pathname !== "/welcome") return "/welcome";
  if (input.welcomeCompleted && input.pathname === "/welcome") return "/app/onboarding";
  return null;
}

export function postLoginPath(isPlatform: boolean, welcomeCompleted: boolean): string {
  if (isPlatform) return "/dashboard";
  return welcomeCompleted ? "/app/onboarding" : "/welcome";
}

function storageKey(organizationId: string) {
  return `rai_welcome_done_${organizationId}`;
}

export function markWelcomeDoneLocally(organizationId: string) {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(storageKey(organizationId), "1");
}

export function readWelcomeDoneLocally(organizationId: string): boolean {
  if (typeof window === "undefined") return false;
  return window.sessionStorage.getItem(storageKey(organizationId)) === "1";
}
