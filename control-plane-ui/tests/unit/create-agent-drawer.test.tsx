import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useParams: () => ({ systemId: "sys-1" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", () => ({
  createAgent: vi.fn(),
  getAISystem: vi.fn().mockResolvedValue({
    data: {
      id: "sys-1",
      system_key: "procurement-ai",
      name: "Procurement AI",
      status: "APPROVED",
      agent_count: 0,
    },
  }),
  getAISystemHierarchy: vi.fn().mockResolvedValue({
    data: {
      system: {
        id: "sys-1",
        system_key: "procurement-ai",
        name: "Procurement AI",
        status: "APPROVED",
      },
      agents: [],
    },
  }),
  getAISystemConfigurationProvenance: vi.fn().mockResolvedValue({
    data: { ai_system_id: "sys-1", found: false },
  }),
  getRuntimeIdentities: vi.fn().mockResolvedValue({ data: [] }),
  getTrajectories: vi.fn().mockResolvedValue({ data: { items: [], total: 0 } }),
  transitionAISystem: vi.fn(),
  updateAISystem: vi.fn(),
}));

import AISystemDetailPage from "@/app/(app)/governance/registry/[systemId]/page";

describe("Create Agent drawer", () => {
  it("slugifies the agent key from the name until the key is edited", async () => {
    render(<AISystemDetailPage />);
    expect(await screen.findByRole("button", { name: "+ Create Agent" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "+ Create Agent" }));

    const name = await screen.findByRole("textbox", { name: "Name *" });
    fireEvent.change(name, { target: { value: "PO Assistant" } });

    const agentKey = screen.getByRole("textbox", { name: /agent key/i });
    expect(agentKey).toHaveValue("po-assistant");

    fireEvent.change(agentKey, { target: { value: "custom-key" } });
    fireEvent.change(name, { target: { value: "Finance Bot" } });
    expect(agentKey).toHaveValue("custom-key");
  });
});
