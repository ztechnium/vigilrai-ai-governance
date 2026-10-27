import { SectionHeader } from "@/components/section-header";

export function PlaceholderPage({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="space-y-6">
      <SectionHeader title={title} subtitle={subtitle} />
      <div className="rounded-xl border border-base-200 bg-base-100 p-5 text-sm text-ink-500">
        This view is wired for the MVP shell. Data integration will use metadata-only APIs.
      </div>
    </div>
  );
}
