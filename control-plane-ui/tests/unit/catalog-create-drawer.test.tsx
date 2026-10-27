import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CatalogCreateDrawer } from "@/components/registry/catalog-create-drawer";

vi.mock("@/lib/api", () => ({
  createDataSource: vi.fn(),
  createExternalService: vi.fn(),
  createMCPServer: vi.fn(),
  createModel: vi.fn(),
}));

describe("CatalogCreateDrawer", () => {
  it("slugifies the MCP server key from the name until the key is edited", async () => {
    render(<CatalogCreateDrawer open onClose={() => undefined} onCreated={() => undefined} />);

    const name = await screen.findByRole("textbox", { name: "Name *" });
    fireEvent.change(name, { target: { value: "GitHub MCP" } });

    const serverKey = screen.getByRole("textbox", { name: /server key/i });
    expect(serverKey).toHaveValue("github-mcp");

    fireEvent.change(name, { target: { value: "GitHub MCP Server" } });
    expect(serverKey).toHaveValue("github-mcp-server");

    fireEvent.change(serverKey, { target: { value: "custom-key" } });
    fireEvent.change(name, { target: { value: "Another Name" } });
    expect(serverKey).toHaveValue("custom-key");
  });

  it("resumes slugifying the server key after it is cleared", async () => {
    render(<CatalogCreateDrawer open onClose={() => undefined} onCreated={() => undefined} />);

    const name = await screen.findByRole("textbox", { name: "Name *" });
    const serverKey = screen.getByRole("textbox", { name: /server key/i });

    fireEvent.change(name, { target: { value: "GitHub MCP" } });
    fireEvent.change(serverKey, { target: { value: "" } });
    fireEvent.change(name, { target: { value: "Slack Bot" } });

    await waitFor(() => {
      expect(serverKey).toHaveValue("slack-bot");
    });
  });
});
