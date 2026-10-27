"use client";

import Link from "next/link";
import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Input } from "@/components/ui/input";
import { resetPassword } from "@/lib/api";

function ResetPasswordInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!token) {
      setError("Missing reset token. Open the link from your email again.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      await resetPassword({ token, new_password: password });
      setDone(true);
      window.setTimeout(() => router.replace("/login"), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-md rounded-xl border border-base-200 bg-white/90 p-6 shadow-panel">
        <Link href="/login" className="text-sm font-medium text-accent-600 hover:text-accent-500">
          Back to sign in
        </Link>

        <h1 className="mt-4 text-xl font-semibold text-ink-900">Choose a new password</h1>
        <p className="mt-1 text-sm text-ink-500">
          Set a new password for your account. The reset link can only be used once.
        </p>

        {!token ? (
          <div className="mt-6 rounded-lg border border-danger-600/20 bg-danger-100 p-3 text-sm text-danger-600">
            This page requires a valid reset token from your email.
          </div>
        ) : done ? (
          <div className="mt-6 space-y-4">
            <div className="rounded-lg border border-accent-600/20 bg-accent-50 p-3 text-sm text-ink-700">
              Password updated. Redirecting you to sign in…
            </div>
            <Link
              href="/login"
              className="inline-flex w-full items-center justify-center rounded-lg bg-accent-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-accent-500"
            >
              Sign in now
            </Link>
          </div>
        ) : (
          <form className="mt-6 space-y-4" onSubmit={onSubmit} autoComplete="off">
            <div>
              <label htmlFor="password" className="mb-1 block text-sm font-medium text-ink-700">
                New password
              </label>
              <Input
                id="password"
                name="new-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
              />
            </div>
            <div>
              <label htmlFor="confirm" className="mb-1 block text-sm font-medium text-ink-700">
                Confirm password
              </label>
              <Input
                id="confirm"
                name="confirm-password"
                type="password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
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
              {loading ? "Updating…" : "Update password"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center p-6 text-sm text-ink-500">
          Loading…
        </div>
      }
    >
      <ResetPasswordInner />
    </Suspense>
  );
}
