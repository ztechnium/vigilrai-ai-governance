import { describe, expect, it } from "vitest";
import {
  contentStatusMessage,
  eventContentPreview,
  extractEventContent,
} from "@/lib/evidence-content";
import type { EvidenceEvent } from "@/lib/types";

function baseEvent(overrides: Partial<EvidenceEvent> = {}): EvidenceEvent {
  return {
    id: "e1",
    trajectory_id: "t1",
    event_type: "PROMPT_OBSERVED",
    sequence_number: 1,
    source_type: "CLIENT_OBSERVED",
    source_reference: "observe:cursor:beforeSubmitPrompt:g1",
    assurance_level: "LOW",
    content_handling_mode: "REDACTED",
    redaction_status: "APPLIED",
    payload: {},
    ...overrides,
  };
}

describe("evidence content helpers", () => {
  it("extracts and previews retained prompt content", () => {
    const event = baseEvent({
      payload: { prompt: "Search Jira for all Mahally issues updated this week" },
      content_status: "AVAILABLE",
    });
    expect(extractEventContent(event)).toContain("Mahally");
    expect(eventContentPreview(event)).toContain("Mahally");
    expect(contentStatusMessage(event)).toBeNull();
  });

  it("explains METADATA_ONLY and DO_NOT_STORE", () => {
    const meta = baseEvent({
      content_handling_mode: "METADATA_ONLY",
      content_status: "NOT_STORED",
      payload: { client_type: "cursor" },
    });
    expect(contentStatusMessage(meta)).toContain("Content not stored");
    expect(contentStatusMessage(meta)).toContain("METADATA_ONLY");

    const omitted = baseEvent({
      content_handling_mode: "DO_NOT_STORE",
      content_status: "INTENTIONALLY_NOT_RETAINED",
      payload: null,
    });
    expect(contentStatusMessage(omitted)).toContain("intentionally not retained");
  });

  it("explains HASH_ONLY as digest only", () => {
    const hashed = baseEvent({
      content_handling_mode: "HASH_ONLY",
      content_status: "DIGEST_ONLY",
      payload: { content_digest: "abc" },
    });
    expect(contentStatusMessage(hashed)).toContain("Digest only");
  });
});
