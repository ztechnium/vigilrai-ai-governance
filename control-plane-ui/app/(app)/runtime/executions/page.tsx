import { redirect } from "next/navigation";

/** Compatibility: Executions list moved into Audit Explorer. */
export default function ExecutionsListRedirect() {
  redirect("/runtime/audit?type=execution");
}
