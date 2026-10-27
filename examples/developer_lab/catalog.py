"""Declarative developer catalog: systems, models, MCP tools, policies, and cases.

Tool rules are deterministic. RAI applies them on `/v1/runtime/actions/execute`
and calls the local MCP endpoint only when the winning effect is ALLOW.
"""

from __future__ import annotations

MCP_SERVER_KEY = "developer-lab-mcp"
MCP_NAME = "Developer lab MCP"
# Reachable from the gateway container on Docker Desktop. Override with
# RAI_TOOL_URL=http://127.0.0.1:8765/invoke when the API runs on the host.
DEFAULT_TOOL_URL = "http://host.docker.internal:8765/invoke"

SYSTEMS: list[dict] = [
    {
        "system_key": "support-ai",
        "name": "Support AI",
        "description": "Customer support agent that opens tickets through a governed MCP tool.",
        "business_purpose": "Resolve customer issues without storing national identifiers or skipping approval on urgent tickets.",
        "risk_tier": "MEDIUM",
        "data_classification": "CONFIDENTIAL",
        "agent_key": "support-agent",
        "agent_name": "Support agent",
        "model": {
            "provider": "openai",
            "model_name": "gpt-4.1-mini",
            "model_version": "2026-04",
            "hosting_type": "EXTERNAL_API",
        },
        "policy": {
            "title": "Customer Support Handling Standard",
            "authority": "Support Operations",
            "jurisdiction": "UNSPECIFIED",
            "policy_type": "internal",
            "version": "2026.1",
            "content_text": (
                "Agents may open a normal ticket without approval. "
                "A high-priority ticket requires a business approver before it is created. "
                "Ticket notes must not contain a national identifier. "
                "Replies must not disclose a customer bank account."
            ),
        },
        "content_rules": [
            {
                "title": "Do not disclose bank accounts",
                "content": "Do not disclose a customer bank account, IBAN, or routing number.",
                "effect": "DENY",
                "applies_to": "OUTPUT",
                "category": "PRIVACY",
                "severity": "CRITICAL",
                "evaluation_type": "KEYWORD",
            }
        ],
        "tools": [
            {
                "tool_key": "create_support_ticket",
                "name": "Create support ticket",
                "description": "Open a customer support ticket.",
                "category": "support",
                "consequential_action": False,
            }
        ],
        "tool_rules": [
            {
                "title": "Block national identifiers in ticket notes",
                "description": "Derived from the support handling standard.",
                "tool_key": "create_support_ticket",
                "effect": "DENY",
                "severity": "CRITICAL",
                "category": "PRIVACY",
                "conditions": [
                    {
                        "parameter_path": "notes",
                        "operator": "contains",
                        "value_type": "string",
                        "value": "national id",
                    }
                ],
            },
            {
                "title": "High-priority tickets need approval",
                "description": "Urgent tickets wait for a business approver.",
                "tool_key": "create_support_ticket",
                "effect": "REQUIRE_APPROVAL",
                "required_approver_role": "business_approver",
                "severity": "HIGH",
                "category": "OPERATIONS",
                "conditions": [
                    {
                        "parameter_path": "priority",
                        "operator": "eq",
                        "value_type": "string",
                        "value": "high",
                    }
                ],
            },
        ],
        "cases": [
            {
                "id": "normal-ticket",
                "kind": "tool",
                "tool": "create_support_ticket",
                "parameters": {
                    "priority": "normal",
                    "summary": "Order arrived damaged",
                },
                "expect": "ALLOW",
            },
            {
                "id": "urgent-ticket",
                "kind": "tool",
                "tool": "create_support_ticket",
                "parameters": {
                    "priority": "high",
                    "summary": "Payment duplicated",
                },
                "expect": "REQUIRE_APPROVAL",
            },
            {
                "id": "national-id-in-notes",
                "kind": "tool",
                "tool": "create_support_ticket",
                "parameters": {
                    "priority": "normal",
                    "summary": "Address change",
                    "notes": "customer national id is on the letter",
                },
                "expect": "DENY",
            },
            {
                "id": "bank-account-reply",
                "kind": "content",
                "content_type": "OUTPUT",
                "content": "Refund the bank account EG12 3456 7890.",
                "expect_violated": True,
            },
            {
                "id": "safe-reply",
                "kind": "content",
                "content_type": "OUTPUT",
                "content": "I opened a ticket for the damaged order.",
                "expect_violated": False,
            },
        ],
    },
    {
        "system_key": "sales-ai",
        "name": "Sales AI",
        "description": "Sales agent that creates orders through a governed MCP tool.",
        "business_purpose": "Create customer orders inside an approval threshold.",
        "risk_tier": "HIGH",
        "data_classification": "CONFIDENTIAL",
        "agent_key": "sales-agent",
        "agent_name": "Sales agent",
        "model": {
            "provider": "openai",
            "model_name": "gpt-4.1",
            "model_version": "2026-04",
            "hosting_type": "EXTERNAL_API",
        },
        "policy": {
            "title": "Sales Order Authority Policy",
            "authority": "Revenue Operations",
            "jurisdiction": "UNSPECIFIED",
            "policy_type": "internal",
            "version": "2026.1",
            "content_text": (
                "Orders under 1000 may be created by the agent. "
                "Orders of 1000 or more require a business approver. "
                "Orders of 10000 or more are denied."
            ),
        },
        "content_rules": [],
        "tools": [
            {
                "tool_key": "create_order",
                "name": "Create order",
                "description": "Create a customer order.",
                "category": "sales",
                "consequential_action": False,
            }
        ],
        "tool_rules": [
            {
                "title": "Block orders at or above 10000",
                "tool_key": "create_order",
                "effect": "DENY",
                "severity": "CRITICAL",
                "category": "FINANCIAL",
                "conditions": [
                    {
                        "parameter_path": "amount",
                        "operator": "gte",
                        "value_type": "number",
                        "value": 10000,
                    }
                ],
            },
            {
                "title": "Approve orders at or above 1000",
                "tool_key": "create_order",
                "effect": "REQUIRE_APPROVAL",
                "required_approver_role": "business_approver",
                "severity": "HIGH",
                "category": "FINANCIAL",
                "conditions": [
                    {
                        "parameter_path": "amount",
                        "operator": "gte",
                        "value_type": "number",
                        "value": 1000,
                    }
                ],
            },
        ],
        "cases": [
            {
                "id": "small-order",
                "kind": "tool",
                "tool": "create_order",
                "parameters": {"amount": 250, "currency": "USD", "account": "Acme"},
                "expect": "ALLOW",
            },
            {
                "id": "manager-order",
                "kind": "tool",
                "tool": "create_order",
                "parameters": {"amount": 2500, "currency": "USD", "account": "Acme"},
                "expect": "REQUIRE_APPROVAL",
            },
            {
                "id": "oversized-order",
                "kind": "tool",
                "tool": "create_order",
                "parameters": {"amount": 15000, "currency": "USD", "account": "Acme"},
                "expect": "DENY",
            },
        ],
    },
    {
        "system_key": "knowledge-ai",
        "name": "Knowledge assistant",
        "description": "Retrieval agent limited to the internal HR policy collection.",
        "business_purpose": "Answer from approved internal documents and keep payroll records out of the model context.",
        "risk_tier": "MEDIUM",
        "data_classification": "INTERNAL",
        "agent_key": "knowledge-agent",
        "agent_name": "Knowledge agent",
        "model": {
            "provider": "openai",
            "model_name": "gpt-4.1",
            "model_version": "2026-04",
            "hosting_type": "EXTERNAL_API",
            "deployment_reference": "knowledge-assistant",
        },
        "policy": {
            "title": "Internal Knowledge Access Policy",
            "authority": "People Operations",
            "jurisdiction": "UNSPECIFIED",
            "policy_type": "internal",
            "version": "2026.1",
            "content_text": (
                "The assistant may retrieve the HR policy collection. "
                "Payroll records are denied."
            ),
        },
        "content_rules": [],
        "tools": [
            {
                "tool_key": "retrieve_documents",
                "name": "Retrieve documents",
                "description": "Read a document collection.",
                "category": "knowledge",
                "consequential_action": False,
            }
        ],
        "tool_rules": [
            {
                "title": "Deny payroll retrieval",
                "tool_key": "retrieve_documents",
                "effect": "DENY",
                "severity": "HIGH",
                "category": "PRIVACY",
                "conditions": [
                    {
                        "parameter_path": "collection",
                        "operator": "eq",
                        "value_type": "string",
                        "value": "payroll",
                    }
                ],
            }
        ],
        "cases": [
            {
                "id": "hr-policy",
                "kind": "tool",
                "tool": "retrieve_documents",
                "parameters": {"collection": "hr-policies"},
                "expect": "ALLOW",
            },
            {
                "id": "payroll",
                "kind": "tool",
                "tool": "retrieve_documents",
                "parameters": {"collection": "payroll"},
                "expect": "DENY",
            },
        ],
    },
    {
        "system_key": "coding-agent",
        "name": "Coding agent",
        "description": "Repository agent that may read a sandbox file. Shell and pull requests are governed.",
        "business_purpose": "Inspect project files. Do not run a shell. Opening a pull request requires approval.",
        "risk_tier": "HIGH",
        "data_classification": "INTERNAL",
        "agent_key": "coding-agent",
        "agent_name": "Coding agent",
        "model": {
            "provider": "anthropic",
            "model_name": "claude-sonnet",
            "model_version": "2026-06",
            "hosting_type": "EXTERNAL_API",
        },
        "policy": {
            "title": "Secure Coding Agent Policy",
            "authority": "Engineering",
            "jurisdiction": "UNSPECIFIED",
            "policy_type": "internal",
            "version": "2026.1",
            "content_text": (
                "The agent may read files in the lab sandbox. "
                "Shell execution is denied. "
                "Creating a pull request requires a technical approver."
            ),
        },
        "content_rules": [],
        "tools": [
            {
                "tool_key": "read_file",
                "name": "Read file",
                "description": "Read a file inside the lab sandbox.",
                "category": "code",
                "consequential_action": False,
            },
            {
                "tool_key": "run_shell",
                "name": "Run shell",
                "description": "Run a fixed local process. RAI denies this tool before execution.",
                "category": "code",
                "consequential_action": True,
            },
            {
                "tool_key": "create_pull_request",
                "name": "Create pull request",
                "description": "Record a pull request in the lab workspace.",
                "category": "code",
                "consequential_action": True,
            },
        ],
        "tool_rules": [
            {
                "title": "Deny shell execution",
                "tool_key": "run_shell",
                "effect": "DENY",
                "severity": "CRITICAL",
                "category": "SECURITY",
                "conditions": [],
            },
            {
                "title": "Pull requests need approval",
                "tool_key": "create_pull_request",
                "effect": "REQUIRE_APPROVAL",
                "required_approver_role": "technical_owner",
                "severity": "HIGH",
                "category": "CHANGE",
                "conditions": [],
            },
        ],
        "cases": [
            {
                "id": "read-sandbox",
                "kind": "tool",
                "tool": "read_file",
                "parameters": {"path": "README.md"},
                "expect": "ALLOW",
            },
            {
                "id": "shell",
                "kind": "tool",
                "tool": "run_shell",
                "parameters": {"command": "python -c print-governed"},
                "expect": "DENY",
            },
            {
                "id": "open-pr",
                "kind": "tool",
                "tool": "create_pull_request",
                "parameters": {"title": "chore: ci"},
                "expect": "REQUIRE_APPROVAL",
            },
        ],
    },
    {
        "system_key": "citizen-assistant",
        "name": "Citizen assistant",
        "description": "Public-service agent that can look up a record and must wait for approval before changing it.",
        "business_purpose": "Answer citizen questions and keep record changes behind a human approver.",
        "risk_tier": "HIGH",
        "data_classification": "RESTRICTED",
        "agent_key": "citizen-agent",
        "agent_name": "Citizen agent",
        "model": {
            "provider": "openai",
            "model_name": "gpt-4.1",
            "model_version": "2026-04",
            "hosting_type": "EXTERNAL_API",
            "deployment_reference": "citizen-assistant",
        },
        "policy": {
            "title": "Citizen Record Change Policy",
            "authority": "Public Services",
            "jurisdiction": "UNSPECIFIED",
            "policy_type": "internal",
            "version": "2026.1",
            "content_text": (
                "The assistant may look up the address on file. "
                "Changing a citizen record requires a business approver. "
                "Do not repeat a national identifier in a reply."
            ),
        },
        "content_rules": [
            {
                "title": "Do not repeat a national identifier",
                "content": "Do not disclose a social security or national identifier.",
                "effect": "DENY",
                "applies_to": "OUTPUT",
                "category": "PRIVACY",
                "severity": "CRITICAL",
                "evaluation_type": "KEYWORD",
            }
        ],
        "tools": [
            {
                "tool_key": "lookup_citizen_record",
                "name": "Lookup citizen record",
                "description": "Read the lab citizen record.",
                "category": "citizen",
                "consequential_action": False,
            },
            {
                "tool_key": "update_citizen_record",
                "name": "Update citizen record",
                "description": "Change the address on the lab citizen record.",
                "category": "citizen",
                "consequential_action": True,
            },
        ],
        "tool_rules": [
            {
                "title": "Citizen record changes need approval",
                "tool_key": "update_citizen_record",
                "effect": "REQUIRE_APPROVAL",
                "required_approver_role": "business_approver",
                "severity": "CRITICAL",
                "category": "PRIVACY",
                "conditions": [],
            }
        ],
        "cases": [
            {
                "id": "lookup",
                "kind": "tool",
                "tool": "lookup_citizen_record",
                "parameters": {"field": "address"},
                "expect": "ALLOW",
            },
            {
                "id": "change-address",
                "kind": "tool",
                "tool": "update_citizen_record",
                "parameters": {"field": "address", "value": "40 Corniche"},
                "expect": "REQUIRE_APPROVAL",
            },
            {
                "id": "national-id-reply",
                "kind": "content",
                "content_type": "OUTPUT",
                "content": "Your SSN is 123-45-6789.",
                "expect_violated": True,
            },
        ],
    },
]


def system_by_key(system_key: str) -> dict:
    for system in SYSTEMS:
        if system["system_key"] == system_key:
            return system
    known = ", ".join(system["system_key"] for system in SYSTEMS)
    raise KeyError(f"Unknown system {system_key!r}. Known: {known}")
