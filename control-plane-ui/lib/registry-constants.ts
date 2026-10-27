export const BUSINESS_UNITS = [
  "Procurement",
  "Finance",
  "Human Resources",
  "Customer Support",
  "Legal & Compliance",
  "Information Technology",
  "Operations",
  "Fraud & Risk",
  "Engineering",
] as const;

export const RISK_TIERS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;

export const RESOURCE_TYPES = [
  { value: "tool", label: "Tool" },
  { value: "mcp_server", label: "MCP Server" },
  { value: "data_source", label: "Data Source" },
  { value: "model", label: "Model" },
  { value: "external_service", label: "External Service" },
] as const;
