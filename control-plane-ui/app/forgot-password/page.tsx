"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { Input } from "@/components/ui/input";
import { forgotPassword } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const response = await forgotPassword(email.trim());
      setMessage(
        response.data.message ||
          "If an account exists for this email, password reset instructions have been sent.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to request password reset");
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

        <h1 className="mt-4 text-xl font-semibold text-ink-900">Reset password</h1>
        <p className="mt-1 text-sm text-ink-500">
          Enter your work email and we will send reset instructions if an account exists.
        </p>

        {message ? (
          <div className="mt-6 space-y-4">
            <div className="rounded-lg border border-accent-600/20 bg-accent-50 p-3 text-sm text-ink-700">
              {message}
            </div>
            <Link
              href="/login"
              className="inline-flex w-full items-center justify-center rounded-lg bg-accent-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-accent-500"
            >
              Return to sign in
            </Link>
          </div>
        ) : (
          <form className="mt-6 space-y-4" onSubmit={onSubmit} autoComplete="off">
            <div>
              <label htmlFor="email" className="mb-1 block text-sm font-medium text-ink-700">
                Email
              </label>
              <Input
                id="email"
                name="reset-email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                autoComplete="email"
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
              {loading ? "Sending…" : "Send reset link"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
