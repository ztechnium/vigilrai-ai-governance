"use client";

import { useState } from "react";
import { downloadCatalogTemplate, importCatalogWorkbook } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function CatalogUpload({
  compact = false,
  downloadLabel = "Download template",
  onImported,
}: {
  compact?: boolean;
  downloadLabel?: string;
  onImported?: () => void;
}) {
  const [fileName, setFileName] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    setFileName(file.name);
    try {
      const result = await importCatalogWorkbook(file);
      setMessage(
        `Imported ${result.rows} rows (${result.created} created, ${result.updated} updated).`,
      );
      onImported?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={
        compact ? "space-y-2" : "space-y-3 rounded-lg border border-base-200 bg-base-50 p-4"
      }
    >
      <div>
        <div className="text-sm font-semibold text-ink-900">Catalog spreadsheet</div>
        <p className="mt-1 text-xs text-ink-500">
          Fill the Catalog sheet. type is model, mcp, tool, or service. The Example sheet in the
          download shows sample rows and is not imported. Uploading the same key again updates that
          row.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={busy}
          onClick={() =>
            void downloadCatalogTemplate().catch((err: unknown) => {
              setError(err instanceof Error ? err.message : "Download failed");
            })
          }
        >
          {downloadLabel}
        </Button>
        <label className="inline-flex h-7 cursor-pointer items-center rounded-md bg-accent-600 px-3 text-xs font-semibold text-white hover:bg-accent-500">
          {busy ? "Uploading…" : "Upload sheet"}
          <input
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            className="sr-only"
            disabled={busy}
            onChange={(event) => void onFile(event.target.files?.[0])}
          />
        </label>
        {fileName ? <span className="text-xs text-ink-500">{fileName}</span> : null}
      </div>
      {message ? <p className="text-xs text-accent-700">{message}</p> : null}
      {error ? <p className="text-xs text-danger-600">{error}</p> : null}
    </div>
  );
}
