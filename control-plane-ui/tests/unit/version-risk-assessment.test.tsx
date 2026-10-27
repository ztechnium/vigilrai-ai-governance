import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  updateRiskAssessmentStatus: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ versionId: "ver-1" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  createRiskAssessment: vi.fn(),
  updateRiskAssessmentStatus: mocks.updateRiskAssessmentStatus,
  getAgent: vi.fn().mockResolvedValue({
    data: {
      id: "agent-1",
      agent_key: "cursor",
      ai_system_id: "sys-1",
      name: "Cursor",
      status: "APPROVED",
    },
  }),
  getAgentVersion: vi.fn().mockResolvedValue({
    data: {
      id: "ver-1",
      agent_id: "agent-1",
      version_number: 2,
      lifecycle_status: "APPROVED",
      material_change_status: "NONE",
    },
  }),
  getDeploymentReadiness: vi.fn().mockResolvedValue(null),
  getMaterialChanges: vi.fn().mockResolvedValue({ data: [] }),
  getRuntimeIdentities: vi.fn().mockResolvedValue({ data: [] }),
  getVersionAssurance: vi.fn().mockResolvedValue(null),
  getVersionDependencies: vi.fn().mockResolvedValue({ data: [] }),
  getVersionRiskAssessments: vi.fn().mockResolvedValue({
    data: [{ id: "ra-1", status: "DRAFT", risk_tier: "MEDIUM", overall_score: 50 }],
  }),
  transitionAgentVersion: vi.fn(),
  updateAgentVersion: vi.fn(),
  addVersionDependency: vi.fn(),
  getDataSources: vi.fn().mockResolvedValue({ data: [] }),
  getExternalServices: vi.fn().mockResolvedValue({ data: [] }),
  getMCPServers: vi.fn().mockResolvedValue({ data: [] }),
  getModels: vi.fn().mockResolvedValue({ data: [] }),
  getTools: vi.fn().mockResolvedValue({ data: [] }),
  removeVersionDependency: vi.fn(),
}));

import VersionDetailPage from "@/app/(app)/governance/registry/versions/[versionId]/page";

describe("Version risk assessment status", () => {
  it("updates a recorded assessment from draft to submitted", async () => {
    mocks.updateRiskAssessmentStatus.mockResolvedValue({
      data: { id: "ra-1", status: "SUBMITTED", risk_tier: "MEDIUM", overall_score: 50 },
    });

    render(<VersionDetailPage />);

    const status = await screen.findByRole("combobox", { name: /risk assessment ra-1/i });
    expect(status).toHaveValue("DRAFT");

    fireEvent.change(status, { target: { value: "SUBMITTED" } });

    await waitFor(() => {
      expect(mocks.updateRiskAssessmentStatus).toHaveBeenCalledWith("ra-1", "SUBMITTED");
    });
    expect(status).toHaveValue("SUBMITTED");
  });
});
