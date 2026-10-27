import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { toolsForMcp } from "@/components/registry/tool-rule-form";
import type { MCPServerSummary, ToolResourceSummary } from "@/lib/types";

const mcps: MCPServerSummary[] = [
  {
    id: "mcp-1",
    server_key: "frappe",
    name: "Frappe MCP",
    tools: [
      { id: "tool-1", tool_key: "submit_po", name: "Submit PO" },
      { id: "tool-2", tool_key: "get_doc", name: "Get Doc" },
    ],
  },
];

const tools: ToolResourceSummary[] = [
  {
    id: "tool-standalone",
    tool_key: "ping",
    name: "Ping",
    consequential_action: false,
    status: "ACTIVE",
  },
  {
    id: "tool-1",
    tool_key: "submit_po",
    name: "Submit PO",
    consequential_action: false,
    status: "ACTIVE",
    mcp_server_id: "mcp-1",
  },
];

describe("toolsForMcp", () => {
  it("returns standalone tools when no MCP selected", () => {
    const result = toolsForMcp("", mcps, tools);
    expect(result.map((t) => t.id)).toEqual(["tool-standalone"]);
  });

  it("returns MCP nested tools when MCP selected", () => {
    const result = toolsForMcp("mcp-1", mcps, tools);
    expect(result.map((t) => t.id)).toEqual(["tool-1", "tool-2"]);
  });
});

describe("ToolRuleForm approver role visibility", () => {
  it("documents REQUIRE_APPROVAL effect constant", async () => {
    const { POLICY_EFFECT_OPTIONS } = await import("@/components/registry/tool-rule-form");
    expect(POLICY_EFFECT_OPTIONS.some((o) => o.value === "REQUIRE_APPROVAL")).toBe(true);
  });
});

describe("ContentRuleForm", () => {
  it("renders governance note", async () => {
    const { ContentRuleForm, EMPTY_CONTENT_RULE_FORM } =
      await import("@/components/registry/content-rule-form");
    render(<ContentRuleForm value={EMPTY_CONTENT_RULE_FORM} onChange={() => undefined} />);
    expect(screen.getByText(/Content rules define semantic governance/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Applies to/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Severity/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Category/i)).toBeInTheDocument();
  });

  it("shows approver role when effect is REQUIRE_APPROVAL", async () => {
    const { ContentRuleForm, EMPTY_CONTENT_RULE_FORM } =
      await import("@/components/registry/content-rule-form");
    render(
      <ContentRuleForm
        value={{ ...EMPTY_CONTENT_RULE_FORM, effect: "REQUIRE_APPROVAL" }}
        onChange={() => undefined}
      />,
    );
    expect(screen.getByLabelText(/Approver role/i)).toBeInTheDocument();
  });
});
