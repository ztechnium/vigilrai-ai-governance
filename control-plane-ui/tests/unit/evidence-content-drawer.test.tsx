import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EvidenceContentDrawer } from "@/components/trajectory/lifecycle/evidence-content-drawer";
import type { LifecycleStage } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  getTrajectoryEvent: vi.fn().mockResolvedValue({
    data: {
      id: "evt-1",
      trajectory_id: "traj-1",
      event_type: "PROMPT_OBSERVED",
      sequence_number: 1,
      source_type: "CLIENT_OBSERVED",
      assurance_level: "MEDIUM",
      content_handling_mode: "HASH_ONLY",
      redaction_status: "APPLIED",
      occurred_at: "2026-09-06T10:00:00Z",
      payload: {
        configuration_id: "lapeep-agent",
        configuration_digest: "sha256:abc",
      },
      payload_digest: "sha256:prompt",
      correlation_id: "corr-1",
      artifacts: [],
      related_events: [],
    },
  }),
}));

const inputStage: LifecycleStage = {
  id: "stage-input",
  type: "INPUT",
  label: "User Request",
  status: "HASH_ONLY",
  occurred_at: "2026-09-06T10:00:00Z",
  event_ids: ["evt-1"],
  content: {
    availability: "HASH_ONLY",
    preview: null,
    reason: "Evidence content policy = HASH_ONLY",
  },
  evidence: { source: "CLIENT_OBSERVED", assurance: "MEDIUM" },
};

describe("EvidenceContentDrawer", () => {
  it("loads content status and provenance without navigating away", async () => {
    const onClose = vi.fn();
    render(<EvidenceContentDrawer trajectoryId="traj-1" stage={inputStage} onClose={onClose} />);

    expect(screen.getByTestId("evidence-content-drawer")).toBeInTheDocument();
    expect(await screen.findByTestId("drawer-content-unavailable")).toBeInTheDocument();
    expect(screen.getByText(/configuration id/i)).toBeInTheDocument();
    expect(screen.getByText("lapeep-agent")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
