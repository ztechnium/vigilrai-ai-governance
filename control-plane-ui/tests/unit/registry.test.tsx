import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useParams: () => ({}),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  getAISystems: vi.fn().mockResolvedValue({
    data: [
      {
        id: "sys-1",
        system_key: "procurement-ai",
        name: "Procurement AI",
        business_unit: "Procurement",
        owner_id: "owner-1",
        status: "APPROVED",
        risk_tier: "HIGH",
        agent_count: 2,
      },
    ],
  }),
  createAISystem: vi.fn(),
}));

import RegistryPage from "@/app/(app)/governance/registry/page";

describe("RegistryPage", () => {
  it("renders systems list", async () => {
    render(<RegistryPage />);
    expect(await screen.findByText("Procurement AI")).toBeInTheDocument();
    expect(screen.getByText("AI Systems")).toBeInTheDocument();
  });

  it("opens create AI system in a side drawer", async () => {
    render(<RegistryPage />);
    expect(await screen.findByText("Procurement AI")).toBeInTheDocument();

    expect(screen.queryByTestId("create-ai-system-drawer")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "+ New AI System" }));

    const drawer = await screen.findByTestId("create-ai-system-drawer");
    expect(drawer).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Create AI System" })).toBeInTheDocument();
    expect(drawer).toHaveTextContent("System Key");
    expect(drawer).toHaveTextContent("Display Name");
    expect(drawer).toHaveTextContent("Business Unit");
    expect(drawer).toHaveTextContent("Owner ID");
    expect(drawer).toHaveTextContent("Risk Tier");
    expect(drawer).toHaveTextContent("Business Purpose");
  });

  it("slugifies the system key from the display name until the key is edited", async () => {
    render(<RegistryPage />);
    expect(await screen.findByText("Procurement AI")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "+ New AI System" }));

    const name = await screen.findByRole("textbox", { name: "Display Name *" });
    fireEvent.change(name, { target: { value: "Procurement AI" } });

    const systemKey = screen.getByRole("textbox", { name: /system key/i });
    expect(systemKey).toHaveValue("procurement-ai");

    fireEvent.change(systemKey, { target: { value: "custom-key" } });
    fireEvent.change(name, { target: { value: "Finance AI" } });
    expect(systemKey).toHaveValue("custom-key");
  });
});
