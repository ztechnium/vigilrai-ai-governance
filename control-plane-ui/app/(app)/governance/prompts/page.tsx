import { redirect } from "next/navigation";

/**
 * Compatibility: observed prompts are runtime evidence, not governance config.
 * Primary home is Runtime → Trajectories.
 */
export default function PromptsRedirectPage() {
  redirect("/runtime/trajectories");
}
