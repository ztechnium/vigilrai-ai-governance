import { expect, test, type Page } from "@playwright/test";

const RECEIPT_ID = "11111111-2222-4333-8444-555555555555";
const RULE_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";

const mockReceiptDetail = {
  id: RECEIPT_ID,
  decision: "DENY",
  reason: "Blocked by matched tool rule",
  reason_code: "POLICY_DENIED",
  identity: {
    ai_system_id: "sys-1",
    ai_system_name: "Demo System",
    agent_id: "agent-1",
    agent_name: "Demo Agent",
    agent_version_id: "ver-1",
    agent_version_number: 1,
    runtime_identity_id: "ri-1",
    runtime_identity_name: "Demo Runtime",
    delegation_id: null,
  },
  client_context: {
    client_type: "cursor",
    client_version: "1.0.0",
    hook_event: "beforeMCPExecution",
    session_id: "sess-1",
    conversation_id: "conv-1",
    generation_id: "gen-1",
    observed_model: "default",
    observed_client_user: "ops@example.com",
  },
  action: {
    integration_type: "mcp",
    integration_id: "mcp-1",
    integration_name: "Atlassian",
    tool_id: "tool-1",
    tool_name: "searchJiraIssuesUsingJql",
    target: { type: "issue", id: null },
    parameters: { jql: "project = DEMO AND text ~ community" },
    action_digest: "digest-abc",
    idempotency_key: null,
  },
  policy_evaluation: {
    final_effect: "DENY",
    matched_rule_ids: [RULE_ID],
    matched_rules: [
      {
        rule_id: RULE_ID,
        title: "Block Atlassian JQL containing Community",
        effect: "DENY",
        matched: true,
        conditions: [
          {
            parameter_path: "jql",
            operator: "REGEX",
            matched: true,
            detail: "(?i).*community.*",
          },
        ],
      },
    ],
    condition_details: [],
    precedence: "DENY > REQUIRE_APPROVAL > MONITOR > ALLOW",
    explanation: "DENY rule matched",
    content_rule_enforcement: {
      status: "NOT_ACTIVE",
      reason: "CONTENT_EVALUATOR_NOT_CONFIGURED",
    },
    tool_rule_enforcement: { status: "ACTIVE", mode: "DETERMINISTIC" },
  },
  approval: { required: false, status: "Not Required" },
  execution: {
    attempted: false,
    status: "NOT_ATTEMPTED",
    source: null,
    downstream_reference: null,
    duration_ms: null,
    report: null,
    reported_at: null,
  },
  assurance: {
    enforcement_mode: "HOOK_ENFORCED",
    deployment_control: "LOCAL_HOOK",
    verification_status: "DECLARED",
    execution_evidence: null,
    notes: "Local hooks may be modified or removed by users with sufficient local access.",
  },
  trace: {
    receipt_id: RECEIPT_ID,
    correlation_id: "corr-1",
    trace_id: "trace-1",
    session_id: "sess-1",
    conversation_id: "conv-1",
    generation_id: "gen-1",
    approval_request_id: null,
    execution_id: RECEIPT_ID,
    reason_code: "POLICY_DENIED",
  },
  timestamps: {
    started_at: "2026-09-04T12:00:00.000Z",
    completed_at: null,
    reported_at: null,
  },
};

const mockReceiptSummary = {
  id: RECEIPT_ID,
  runtime_identity_id: "ri-1",
  runtime_identity_name: "Demo Runtime",
  ai_system_id: "sys-1",
  ai_system_name: "Demo System",
  agent_id: "agent-1",
  agent_name: "Demo Agent",
  agent_version_id: "ver-1",
  enforcement_mode: "HOOK_ENFORCED",
  integration_type: "mcp",
  integration_name: "Atlassian",
  tool_id: "tool-1",
  tool_name: "searchJiraIssuesUsingJql",
  action_digest: "digest-abc",
  matched_rule_ids: [RULE_ID],
  approval_request_id: null,
  approval_consumed: false,
  enforcement_decision: "DENY",
  reason_code: "POLICY_DENIED",
  human_explanation: "Blocked by matched tool rule",
  execution_attempted: false,
  execution_status: "NOT_ATTEMPTED",
  monitor: false,
  client_type: "cursor",
  correlation_id: "corr-1",
  started_at: "2026-09-04T12:00:00.000Z",
};

const mockExecutionRow = {
  receipt_id: RECEIPT_ID,
  tool_name: "searchJiraIssuesUsingJql",
  integration_name: "Atlassian",
  action_digest: "digest-abc",
  execution_source: null,
  execution_status: "NOT_ATTEMPTED",
  enforcement_decision: "DENY",
  enforcement_mode: "HOOK_ENFORCED",
  started_at: "2026-09-04T12:00:00.000Z",
  completed_at: null,
  reported_at: null,
  duration_ms: null,
  runtime_identity_name: "Demo Runtime",
  ai_system_name: "Demo System",
  agent_name: "Demo Agent",
};

async function seedAdminSession(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("rai.cp.adminAuthToken", "e2e-test-token");
    window.localStorage.setItem("rai.cp.activeAdminRole", "General Admin");
  });
}

async function mockReceiptApis(page: Page) {
  // UI calls the gateway at NEXT_PUBLIC_API_BASE_URL (default localhost:8001).
  await page.route(/\/v1\/runtime\/enforcement\/receipts(\/|$|\?)/, async (route) => {
    const url = route.request().url();
    if (url.includes(RECEIPT_ID)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockReceiptDetail),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([mockReceiptSummary]),
    });
  });

  await page.route(/\/v1\/runtime\/executions(\/|$|\?)/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([mockExecutionRow]),
    });
  });
}

async function expectDetailSections(page: Page) {
  await expect(page.getByTestId("enforcement-detail-page")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Runtime Action Detail" })).toBeVisible();
  await expect(page.getByTestId("receipt-section-summary")).toBeVisible();
  await expect(page.getByTestId("receipt-section-identity")).toBeVisible();
  await expect(page.getByTestId("receipt-section-client-context")).toBeVisible();
  await expect(page.getByTestId("receipt-section-action")).toBeVisible();
  await expect(page.getByTestId("receipt-action-parameters")).toContainText("Action Parameters");
  await expect(page.getByTestId("receipt-action-parameters")).toContainText("jql");
  await expect(page.getByTestId("receipt-section-policy")).toBeVisible();
  await expect(page.getByTestId("receipt-matched-rules")).toContainText(
    "Block Atlassian JQL containing Community",
  );
  await expect(page.getByTestId("receipt-matched-rules")).toContainText("jql REGEX");
  await expect(page.getByTestId("receipt-section-approval")).toContainText("Not Required");
  await expect(page.getByTestId("receipt-section-execution")).toContainText("Not Attempted");
  await expect(page.getByTestId("receipt-section-assurance")).toContainText("LOCAL_HOOK");
  await expect(page.getByTestId("receipt-section-trace")).toContainText(RECEIPT_ID);
}

test.describe("Enforcement receipt detail navigation", () => {
  test.beforeEach(async ({ page }) => {
    await seedAdminSession(page);
    await mockReceiptApis(page);
  });

  test("operator can navigate List → Receipt Detail via View Details", async ({ page }) => {
    await page.goto("/runtime/enforcement");
    await expect(page.getByRole("heading", { name: "Runtime Enforcement" })).toBeVisible();
    await expect(page.getByTestId(`enforcement-row-${RECEIPT_ID}`)).toBeVisible();

    await page.getByTestId(`view-details-${RECEIPT_ID}`).click();
    await expect(page).toHaveURL(new RegExp(`/runtime/enforcement/${RECEIPT_ID}$`));
    await expectDetailSections(page);
  });

  test("operator can navigate List → Receipt Detail by clicking the row", async ({ page }) => {
    await page.goto("/runtime/enforcement");
    await page.getByTestId(`enforcement-row-${RECEIPT_ID}`).click();
    await expect(page).toHaveURL(new RegExp(`/runtime/enforcement/${RECEIPT_ID}$`));
    await expectDetailSections(page);
  });

  test("operator can navigate Executions → Receipt Detail", async ({ page }) => {
    await page.goto("/runtime/executions");
    await expect(page.getByRole("heading", { name: "Runtime Executions" })).toBeVisible();
    await expect(page.getByTestId(`execution-row-${RECEIPT_ID}`)).toBeVisible();

    await page.getByTestId(`execution-receipt-${RECEIPT_ID}`).click();
    await expect(page).toHaveURL(new RegExp(`/runtime/enforcement/${RECEIPT_ID}$`));
    await expectDetailSections(page);
  });
});
