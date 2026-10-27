import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => ({ trajectoryId: "traj-1" }),
  useSearchParams: () => new URLSearchParams(""),
}));

vi.mock("@/lib/api", () => ({
  getTrajectories: vi.fn().mockResolvedValue({
    data: {
      items: [
        {
          id: "traj-1",
          ai_system_id: "sys-1",
          ai_system_name: "Coding AI",
          agent_id: "agent-1",
          agent_name: "Cursor Agent",
          agent_avatar: "https://example.com/cursor-agent.png",
          agent_version_id: "ver-1",
          runtime_identity_id: "ri-1",
          runtime_identity_name: "cursor.atlassian",
          session_key: "conv:abc|ri:ri-1|ci:_",
          conversation_id: "abc",
          status: "ACTIVE",
          event_count: 8,
          finding_count: 0,
          completeness_pct: 83,
          assurance_summary: { highest: "HIGH" },
          client_type: "cursor",
          started_at: "2026-09-06T10:00:00Z",
        },
      ],
      limit: 100,
      offset: 0,
    },
  }),
  getTrajectory: vi.fn().mockResolvedValue({
    data: {
      id: "traj-1",
      ai_system_id: "sys-1",
      ai_system_name: "Coding AI",
      agent_id: "agent-1",
      agent_name: "Cursor Agent",
      agent_avatar: "https://example.com/cursor-agent.png",
      agent_version_id: "ver-1",
      runtime_identity_id: "ri-1",
      runtime_identity_name: "cursor.atlassian",
      session_key: "conv:abc|ri:ri-1|ci:_",
      conversation_id: "abc",
      runtime_conversation_id: "rt-conv-1",
      status: "ACTIVE",
      event_count: 2,
      finding_count: 0,
      completeness_pct: 83,
      assurance_summary: { highest: "HIGH" },
      client_type: "cursor",
      delegation_id: "del-1",
      delegation: {
        id: "del-1",
        delegator_type: "HUMAN",
        delegator_id: "user-1",
        delegate_runtime_identity_id: "ri-1",
        status: "ACTIVE",
        scope: { model_ids: [], tool_ids: [], mcp_server_ids: [], data_source_ids: [] },
        created_by: "admin",
        valid_from: "2026-09-01T00:00:00Z",
        expires_at: null,
      },
      coverage_summary: {
        identity: "COMPLETE",
        policy: "COMPLETE",
        execution: "COMPLETE",
        approval: "NOT_REQUIRED",
        prompt: "NOT_OBSERVED",
        output: "NOT_OBSERVED",
        model: "NOT_OBSERVED",
      },
      events: [
        {
          id: "evt-1",
          trajectory_id: "traj-1",
          event_type: "TOOL_ATTEMPTED",
          sequence_number: 1,
          source_type: "RAI_AUTHORITATIVE",
          source_reference: "receipt:r1:attempt",
          assurance_level: "HIGH",
          content_handling_mode: "METADATA_ONLY",
          redaction_status: "APPLIED",
          occurred_at: "2026-09-06T10:00:01Z",
          payload: { receipt_id: "r1" },
        },
      ],
      relations: [],
      findings: [],
      artifacts: [],
    },
  }),
  getTrajectoryLifecycle: vi.fn().mockResolvedValue({
    data: {
      trajectory_id: "traj-1",
      conversation_id: "abc",
      runtime_conversation_id: "rt-conv-1",
      status: "ACTIVE",
      summary: {
        started_at: "2026-09-06T10:00:00Z",
        completed_at: null,
        duration_ms: 1200,
        risk_level: "LOW",
        assurance: "HIGH",
        event_count: 2,
        completeness_pct: 83,
      },
      configuration_provenance: {
        configuration_id: "lapeep-agent",
        configuration_version: "42",
        configuration_digest: "sha256:abc",
        release_id: "9f219e",
        source: "APPLICATION_REPORTED",
        assurance: "APPLICATION_REPORTED",
      },
      stages: [
        {
          id: "stage-input",
          type: "INPUT",
          label: "User Request",
          status: "CAPTURED",
          occurred_at: "2026-09-06T10:00:00Z",
          event_ids: ["evt-prompt"],
          content: { availability: "PREVIEW", preview: "Hello", reason: null },
          evidence: { source: "CLIENT_OBSERVED", assurance: "MEDIUM" },
        },
        {
          id: "stage-action",
          type: "ACTION",
          label: "list_appointments",
          status: "ALLOWED",
          occurred_at: "2026-09-06T10:00:01Z",
          event_ids: ["evt-1"],
          authority: {
            status: "ACTIVE",
            runtime_identity: { id: "ri-1", name: "cursor.atlassian" },
            delegation: {
              id: "del-1",
              status: "ACTIVE",
              delegator_type: "HUMAN",
              delegator_id: "user-1",
            },
          },
          policy: { status: "EVALUATED", decision: "ALLOW", matched_rules: [] },
          approval: { required: false, status: "NOT_REQUIRED" },
          enforcement: { decision: "ALLOW", mode: "ENFORCE", assurance: "HIGH", status: "APPLIED" },
          execution: { status: "SUCCEEDED", duration_ms: 40, error: null },
        },
      ],
    },
  }),
  getTrajectoryRiskFindings: vi.fn().mockResolvedValue({
    data: {
      trajectory_id: "traj-1",
      highest_risk_level: null,
      evidence_findings: [],
      risk: {
        signals: [],
        findings: [],
        interventions: [],
        evaluations: [],
        risk_state: null,
      },
    },
  }),
  getTrajectoryEvent: vi.fn().mockResolvedValue({
    data: {
      id: "evt-prompt",
      trajectory_id: "traj-1",
      event_type: "PROMPT_OBSERVED",
      sequence_number: 0,
      source_type: "CLIENT_OBSERVED",
      assurance_level: "MEDIUM",
      content_handling_mode: "FULL",
      redaction_status: "NONE",
      occurred_at: "2026-09-06T10:00:00Z",
      payload: { prompt: "Hello full content", configuration_digest: "sha256:abc" },
      payload_digest: "sha256:payload",
      correlation_id: "corr-1",
      artifacts: [],
      related_events: [],
    },
  }),
  getTrajectoryGraph: vi.fn().mockResolvedValue({
    data: {
      trajectory_id: "traj-1",
      nodes: [
        {
          id: "evt-1",
          entity_type: "EVENT",
          label: "TOOL_ATTEMPTED",
          source_type: "RAI_AUTHORITATIVE",
          assurance_level: "HIGH",
        },
      ],
      edges: [],
    },
  }),
  getDelegationResources: vi.fn().mockResolvedValue({
    data: {
      models: [],
      data_sources: [],
      mcp_servers: [],
      standalone_tools: [],
    },
  }),
  getTrajectoryEconomics: vi.fn().mockResolvedValue({
    data: {
      trajectory_id: "traj-1",
      summary: {
        total_cost: 0.0012,
        currency: "USD",
        cost_state: "ESTIMATED",
        total_tokens: 1200,
        model_calls: 2,
        metering_source: "RAI",
      },
    },
  }),
  exportTrajectory: vi.fn().mockResolvedValue({ data: { schema_version: "wp5.evidence.v1" } }),
}));

import TrajectoriesPage from "@/app/(app)/runtime/trajectories/page";
import TrajectoryDetailPage from "@/app/(app)/runtime/trajectories/[trajectoryId]/page";

describe("Trajectory pages", () => {
  it("renders trajectory list", async () => {
    render(<TrajectoriesPage />);
    expect(await screen.findByRole("heading", { name: "Trajectories" })).toBeInTheDocument();
    expect(await screen.findByText("Coding AI")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Cursor Agent logo" })).toHaveAttribute(
      "src",
      "https://example.com/cursor-agent.png",
    );
    expect(screen.getByText("Recent Trajectories")).toBeInTheDocument();
  });

  it("renders trajectory detail investigation workspace", async () => {
    render(<TrajectoryDetailPage />);
    expect(await screen.findByRole("heading", { name: "Runtime Trajectory" })).toBeInTheDocument();
    expect(screen.getByTestId("trajectory-overview")).toBeInTheDocument();
    expect(screen.getByTestId("investigation-workspace")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Investigation" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Timeline" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Evidence" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Flow" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "More" })).not.toBeInTheDocument();
    expect(screen.getAllByText("TOOL ATTEMPTED").length).toBeGreaterThan(0);
    expect(screen.getByText("Selected Event")).toBeInTheDocument();
    expect(screen.getByText("Export Evidence")).toBeInTheDocument();
  });

  it("renders lifecycle timeline tab", async () => {
    render(<TrajectoryDetailPage />);
    expect(await screen.findByRole("heading", { name: "Runtime Trajectory" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Timeline" }));
    expect(await screen.findByTestId("trajectory-timeline-tab")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("trajectory-lifecycle-timeline")).toBeInTheDocument();
    });
    expect(screen.getByText("Trajectory lifecycle timeline")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-span-search")).toBeInTheDocument();
  });
});
