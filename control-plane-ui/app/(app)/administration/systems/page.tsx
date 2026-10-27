import { redirect } from "next/navigation";

export default function LegacySystemsPage() {
  redirect("/governance/registry");
}
