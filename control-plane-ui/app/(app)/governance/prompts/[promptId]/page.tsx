"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { getObservedPrompt } from "@/lib/api";

/**
 * Compatibility: isolated prompt detail pages are retired.
 * Redirect observed PROMPT_OBSERVED events into their owning trajectory lifecycle.
 */
export default function ObservedPromptRedirectPage() {
  const { promptId } = useParams<{ promptId: string }>();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getObservedPrompt(promptId)
      .then((res) => {
        if (!active) return;
        const trajectoryId = res.data.trajectory_id;
        const eventId = res.data.id;
        if (!trajectoryId) {
          setError("This observed prompt is not linked to a trajectory.");
          return;
        }
        const focus = eventId ? `?event=${encodeURIComponent(eventId)}` : "";
        router.replace(`/runtime/trajectories/${trajectoryId}${focus}`);
      })
      .catch((err: Error) => {
        if (!active) return;
        setError(err.message);
      });
    return () => {
      active = false;
    };
  }, [promptId, router]);

  if (error) {
    return (
      <div className="space-y-3 rounded-xl bg-danger-50 p-6 text-sm text-danger-600">
        <p>{error}</p>
        <p>
          Observed prompts now live under{" "}
          <Link href="/runtime/trajectories" className="underline">
            Runtime → Trajectories
          </Link>
          .
        </p>
      </div>
    );
  }

  return (
    <div className="p-8 text-center text-sm text-ink-500">Redirecting to trajectory lifecycle…</div>
  );
}
