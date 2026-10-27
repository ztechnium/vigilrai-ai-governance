/** Shared helpers for WP5 evidence content display. */

import type { EvidenceEvent } from "@/lib/types";

const CONTENT_KEYS = ["prompt", "output", "content", "text", "result"] as const;

export function humanEventLabel(eventType: string): string {
  return eventType
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function extractEventContent(event: EvidenceEvent): string | null {
  const payload = event.payload;
  if (!payload) return null;
  for (const key of CONTENT_KEYS) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

export function contentStatusMessage(event: EvidenceEvent): string | null {
  const status = event.content_status;
  const mode = event.content_handling_mode;
  if (status === "AVAILABLE" || extractEventContent(event)) {
    return null;
  }
  if (status === "INTENTIONALLY_NOT_RETAINED" || mode === "DO_NOT_STORE") {
    return `Content intentionally not retained\nHandling policy: ${mode}`;
  }
  if (status === "DIGEST_ONLY" || mode === "HASH_ONLY") {
    return `Digest only\nHandling policy: ${mode}`;
  }
  if (status === "NOT_STORED" || mode === "METADATA_ONLY") {
    return `Content not stored\nHandling policy: ${mode}`;
  }
  if (event.redaction_status === "FAILED") {
    return `Content unavailable (redaction failed)\nHandling policy: ${mode}`;
  }
  return `Content: NOT_AVAILABLE\nHandling policy: ${mode}`;
}

export function eventContentPreview(event: EvidenceEvent, maxLen = 120): string | null {
  if (event.content_preview) return event.content_preview;
  const full = extractEventContent(event);
  if (!full) return null;
  const collapsed = full.replace(/\s+/g, " ").trim();
  if (collapsed.length <= maxLen) return collapsed;
  return `${collapsed.slice(0, maxLen - 1).trimEnd()}…`;
}
