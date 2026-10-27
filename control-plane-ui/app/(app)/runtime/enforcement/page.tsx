import { redirect } from "next/navigation";

/** Compatibility: Enforcement list moved into Audit Explorer. */
export default function EnforcementListRedirect() {
  redirect("/runtime/audit?type=enforcement");
}
