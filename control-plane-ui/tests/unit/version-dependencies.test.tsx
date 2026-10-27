import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { VersionDependencies } from "@/components/registry/version-dependencies";
import type { VersionDependency } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  getModels: vi.fn(),
  getMCPServers: vi.fn(),
  getTools: vi.fn(),
  getDataSources: vi.fn(),
  getExternalServices: vi.fn(),
  addVersionDependency: vi.fn(),
  removeVersionDependency: vi.fn(),
}));

vi.mock("@/lib/api", () => mocks);

const modelId = "model-1";
const mcpId = "mcp-1";
const toolId = "tool-1";

const baseDependencies: VersionDependency[] = [
  {
    id: "dep-model",
    resource_type: "model",
    resource_id: modelId,
    required: true,
  },
  {
    id: "dep-mcp",
    resource_type: "mcp_server",
    resource_id: mcpId,
    required: true,
  },
  {
    id: "dep-tool",
    resource_type: "tool",
    resource_id: toolId,
    required: true,
  },
];

describe("VersionDependencies", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getModels.mockResolvedValue({
      data: [
        {
          id: modelId,
          provider: "google",
          model_name: "gemini-pro",
          model_version: "1.0",
          status: "ACTIVE",
        },
      ],
    });
    mocks.getMCPServers.mockResolvedValue({
      data: [
        {
          id: mcpId,
          server_key: "frappe-mcp",
          name: "Frappe MCP",
          tools: [],
        },
      ],
    });
    mocks.getTools.mockResolvedValue({
      data: [
        {
          id: toolId,
          tool_key: "get_doc",
          name: "get_doc",
          consequential_action: false,
          status: "ACTIVE",
          mcp_server_id: mcpId,
        },
        {
          id: "tool-2",
          tool_key: "insert_doc",
          name: "insert_doc",
          consequential_action: true,
          status: "ACTIVE",
          mcp_server_id: mcpId,
        },
      ],
    });
    mocks.getDataSources.mockResolvedValue({ data: [] });
    mocks.getExternalServices.mockResolvedValue({ data: [] });
    mocks.addVersionDependency.mockResolvedValue({ data: { id: "new-dep" } });
    mocks.removeVersionDependency.mockResolvedValue({ data: { ok: true } });
  });

  it("renders grouped dependencies on version detail", async () => {
    render(
      <VersionDependencies
        versionId="version-1"
        dependencies={baseDependencies}
        editable={false}
        onChanged={vi.fn()}
      />,
    );

    expect(await screen.findByText("Models")).toBeInTheDocument();
    expect(screen.getByText(/google gemini-pro/)).toBeInTheDocument();
    expect(screen.getByText("Frappe MCP")).toBeInTheDocument();
    expect(screen.getByText("get_doc")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Manage" })).not.toBeInTheDocument();
  });

  it("associates a model on draft versions", async () => {
    const onChanged = vi.fn();

    render(
      <VersionDependencies
        versionId="version-1"
        dependencies={[]}
        editable
        onChanged={onChanged}
      />,
    );

    const manageButtons = await screen.findAllByRole("button", { name: "Manage" });
    fireEvent.click(manageButtons[0]);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: modelId } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => {
      expect(mocks.addVersionDependency).toHaveBeenCalledWith("version-1", {
        resource_type: "model",
        resource_id: modelId,
      });
      expect(onChanged).toHaveBeenCalled();
    });
  });

  it("shows MCP tools without auto-selecting all tools", async () => {
    render(
      <VersionDependencies
        versionId="version-1"
        dependencies={[
          {
            id: "dep-mcp",
            resource_type: "mcp_server",
            resource_id: mcpId,
            required: true,
          },
        ]}
        editable
        onChanged={vi.fn()}
      />,
    );

    expect(await screen.findByText("insert_doc")).toBeInTheDocument();
    expect(screen.getAllByText("✗").length).toBeGreaterThan(0);
    expect(screen.queryByText("✓")).not.toBeInTheDocument();
  });

  it("persists selected MCP tool associations via API", async () => {
    const onChanged = vi.fn();

    render(
      <VersionDependencies
        versionId="version-1"
        dependencies={[
          {
            id: "dep-mcp",
            resource_type: "mcp_server",
            resource_id: mcpId,
            required: true,
          },
        ]}
        editable
        onChanged={onChanged}
      />,
    );

    expect(await screen.findByText("get_doc")).toBeInTheDocument();

    const mcpHeading = screen.getByRole("heading", { name: /MCP Servers/ });
    const mcpSection = mcpHeading.closest("section");
    if (!mcpSection) throw new Error("MCP section not found");

    fireEvent.click(within(mcpSection).getByRole("button", { name: "Manage" }));
    const getDocRow = within(mcpSection).getByText("get_doc").closest("li");
    if (!getDocRow) throw new Error("get_doc row not found");
    fireEvent.click(within(getDocRow).getByRole("button", { name: "Select" }));

    await waitFor(() => {
      expect(mocks.addVersionDependency).toHaveBeenCalledWith("version-1", {
        resource_type: "tool",
        resource_id: toolId,
      });
      expect(onChanged).toHaveBeenCalled();
    });
  });
});
