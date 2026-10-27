import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  DelegationScopeBuilder,
  EMPTY_SCOPE,
} from "@/components/registry/delegation-scope-builder";
import type { DelegationResourceCatalog } from "@/lib/types";

const catalog: DelegationResourceCatalog = {
  version_id: "version-1",
  models: [
    {
      id: "model-1",
      label: "Claude Sonnet",
      provider: "anthropic",
      model_name: "claude-sonnet",
    },
  ],
  data_sources: [{ id: "ds-1", label: "Engineering KB", data_source_key: "eng-kb" }],
  mcp_servers: [
    {
      id: "mcp-1",
      server_key: "github",
      name: "GitHub MCP",
      tools: [
        { id: "tool-1", tool_key: "read_repository", name: "read_repository" },
        { id: "tool-2", tool_key: "create_branch", name: "create_branch" },
      ],
    },
  ],
};

vi.mock("@/lib/api", () => ({
  getDelegationResources: vi.fn(() =>
    Promise.resolve({
      data: catalog,
    }),
  ),
}));

describe("DelegationScopeBuilder", () => {
  it("loads catalog and toggles model selection", async () => {
    const onChange = vi.fn();

    render(
      <DelegationScopeBuilder versionId="version-1" value={EMPTY_SCOPE} onChange={onChange} />,
    );

    const modelButton = await screen.findByText("Claude Sonnet");
    fireEvent.click(modelButton);

    expect(onChange).toHaveBeenCalledWith({
      ...EMPTY_SCOPE,
      model_ids: ["model-1"],
    });
  });

  it("expands MCP tree and toggles individual tools", async () => {
    const onChange = vi.fn();

    render(
      <DelegationScopeBuilder versionId="version-1" value={EMPTY_SCOPE} onChange={onChange} />,
    );

    await screen.findByText("Claude Sonnet");

    const checkbox = screen.getByRole("checkbox", { name: /read_repository/ });
    fireEvent.click(checkbox);

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          tool_ids: ["tool-1"],
        }),
      );
    });
  });

  it("disables resources outside parent scope", async () => {
    render(
      <DelegationScopeBuilder
        versionId="version-1"
        value={EMPTY_SCOPE}
        onChange={vi.fn()}
        parentScope={{
          model_ids: [],
          data_source_ids: ["ds-1"],
        }}
      />,
    );

    const modelButton = await screen.findByText("Claude Sonnet");
    expect(modelButton).toBeDisabled();
    expect(screen.getByText("Engineering KB")).not.toBeDisabled();
  });
});
