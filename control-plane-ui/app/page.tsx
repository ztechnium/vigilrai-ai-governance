"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import {
  ADMIN_AUTH_TOKEN_STORAGE_KEY,
  PLATFORM_ADMIN_STORAGE_KEY,
  adminLogin,
  persistSessionTokens,
  saasLogin,
} from "@/lib/api";
import { hasPlatformOperatorAccess } from "@/lib/platform-roles";
import { postLoginPath } from "@/lib/welcome-gate";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const sessionToken = window.localStorage.getItem(ADMIN_AUTH_TOKEN_STORAGE_KEY);
    if (sessionToken) {
      router.replace("/dashboard");
    }
  }, [router]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      try {
        const response = await saasLogin({ email, password });
        const data = response.data;
        persistSessionTokens(data.access_token, data.refresh_token);

        const platformRoles = data.platform_roles ?? [];
        const isPlatform = hasPlatformOperatorAccess(platformRoles);
        window.localStorage.setItem(PLATFORM_ADMIN_STORAGE_KEY, isPlatform ? "1" : "0");

        router.replace(postLoginPath(isPlatform, data.welcome_completed !== false));
        return;
      } catch {
        // Legacy bootstrap admin path.
      }

      const response = await adminLogin({ email, password });
      persistSessionTokens(response.data.access_token);
      const roles = response.data.user.roles || [];
      const isPlatform = hasPlatformOperatorAccess(roles) || roles.length > 0;
      window.localStorage.setItem(PLATFORM_ADMIN_STORAGE_KEY, isPlatform ? "1" : "0");
      router.replace("/dashboard");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Login failed";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-md rounded-xl border border-base-200 bg-white/90 p-6 shadow-panel">
        <h1 className="text-xl font-semibold text-ink-900">Sign In</h1>
        <p className="mt-1 text-sm text-ink-500">Sign in with your work email and password.</p>

        <form
          className="mt-6 space-y-4"
          onSubmit={onSubmit}
          autoComplete="off"
          data-1p-ignore
          data-lpignore="true"
          data-form-type="other"
        >
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-ink-700">
              Email
            </label>
            <Input
              id="email"
              name="rai-signin-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="none"
              spellCheck={false}
              data-1p-ignore
              data-lpignore="true"
            />
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between gap-3">
              <label htmlFor="password" className="block text-sm font-medium text-ink-700">
                Password
              </label>
              <Link
                href="/forgot-password"
                className="text-sm font-medium text-accent-600 hover:text-accent-500"
              >
                Forgot password?
              </Link>
            </div>
            <Input
              id="password"
              name="rai-signin-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              autoComplete="new-password"
              data-1p-ignore
              data-lpignore="true"
            />
          </div>

          {error ? (
            <div className="rounded-lg border border-danger-600/20 bg-danger-100 p-2 text-sm text-danger-600">
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-accent-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-accent-500 disabled:opacity-60"
          >
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
