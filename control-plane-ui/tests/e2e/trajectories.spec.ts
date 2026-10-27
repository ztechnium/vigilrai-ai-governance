import { expect, test, type Page } from "@playwright/test";

const TRAJ_MAIN = "aaaaaaaa-bbbb-4ccc-8ddd-111111111111";
const TRAJ_DENY = "aaaaaaaa-bbbb-4ccc-8ddd-222222222222";
const TRAJ_MISSING = "aaaaaaaa-bbbb-4ccc-8ddd-333333333333";
const TRAJ_PROMPT = "aaaaaaaa-bbbb-4ccc-8ddd-444444444444";

const RECEIPT_ID = "11111111-2222-4333-8444-555555555555";
const APPROVAL_ID = "99999999-aaaa-4bbb-8ccc-dddddddddddd";
const RULE_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";

function event(
  id: string,
  trajectoryId: string,
  eventType: string,
  sequence: number,
  sourceType: string,
  sourceReference: string,
  payload: Record<string, unknown> = {},
  assurance = "HIGH",
  handling = "METADATA_ONLY",
  extras: Record<string, unknown> = {},
) {
  return {
    id,
    trajectory_id: trajectoryId,
    event_type: eventType,
    sequence_number: sequence,
    source_type: sourceType,
    source_reference: sourceReference,
    assurance_level: assurance,
    content_handling_mode: handling,
    redaction_status: handling === "REDACTED" || handling === "FULL" ? "APPLIED" : "APPLIED",
    occurred_at: `2026-09-06T10:00:${String(sequence).padStart(2, "0")}.000Z`,
    payload_digest: `digest-${id}`,
    payload,
    ...extras,
  };
}

const mainEvents = [
  event(
    "e1",
    TRAJ_MAIN,
    "PROMPT_OBSERVED",
    1,
    "CLIENT_OBSERVED",
    "observe:cursor:beforeSubmitPrompt:gen-1",
    {
      client_type: "cursor",
      hook_event: "beforeSubmitPrompt",
      prompt: "Search Jira for all Mahally issues updated this week",
    },
    "LOW",
    "REDACTED",
    {
      content_preview: "Search Jira for all Mahally issues updated this week",
      content_status: "AVAILABLE",
    },
  ),
  event(
    "e2",
    TRAJ_MAIN,
    "MODEL_REQUEST_OBSERVED",
    2,
    "CLIENT_OBSERVED",
    "observe:cursor:beforeSubmitPrompt:gen-1:model",
    { observed_model: "claude-sonnet", client_type: "cursor" },
    "LOW",
  ),
  event(
    "e3",
    TRAJ_MAIN,
    "TOOL_ATTEMPTED",
    3,
    "RAI_AUTHORITATIVE",
    `receipt:${RECEIPT_ID}:attempt`,
    { receipt_id: RECEIPT_ID, tool_name: "searchJiraIssuesUsingJql" },
  ),
  event(
    "e4",
    TRAJ_MAIN,
    "POLICY_EVALUATED",
    4,
    "RAI_AUTHORITATIVE",
    `receipt:${RECEIPT_ID}:policy`,
    {
      receipt_id: RECEIPT_ID,
      final_effect: "REQUIRE_APPROVAL",
      matched_rule_ids: [RULE_ID],
    },
  ),
  event(
    "e5",
    TRAJ_MAIN,
    "APPROVAL_REQUESTED",
    5,
    "RAI_AUTHORITATIVE",
    `approval:${APPROVAL_ID}:requested`,
    { approval_request_id: APPROVAL_ID },
  ),
  event(
    "e6",
    TRAJ_MAIN,
    "APPROVAL_DECIDED",
    6,
    "RAI_AUTHORITATIVE",
    `approval:${APPROVAL_ID}:decided`,
    { approval_request_id: APPROVAL_ID, decision: "APPROVED" },
  ),
  event(
    "e7",
    TRAJ_MAIN,
    "APPROVAL_CONSUMED",
    7,
    "RAI_AUTHORITATIVE",
    `approval:${APPROVAL_ID}:consumed`,
    { approval_request_id: APPROVAL_ID, receipt_id: RECEIPT_ID },
  ),
  event(
    "e8",
    TRAJ_MAIN,
    "ACTION_ALLOWED",
    8,
    "RAI_AUTHORITATIVE",
    `receipt:${RECEIPT_ID}:decision`,
    { receipt_id: RECEIPT_ID, decision: "ALLOW" },
  ),
  event(
    "e9",
    TRAJ_MAIN,
    "TOOL_EXECUTION_SUCCEEDED",
    9,
    "CLIENT_REPORTED",
    `receipt:${RECEIPT_ID}:execution`,
    { receipt_id: RECEIPT_ID, execution_status: "SUCCEEDED" },
    "MEDIUM",
  ),
  event(
    "e10",
    TRAJ_MAIN,
    "AGENT_OUTPUT_OBSERVED",
    10,
    "CLIENT_OBSERVED",
    "observe:cursor:afterAgentResponse:gen-1",
    {
      client_type: "cursor",
      hook_event: "afterAgentResponse",
      output: "Found 4 Mahally issues updated this week.",
    },
    "LOW",
    "REDACTED",
    {
      content_preview: "Found 4 Mahally issues updated this week.",
      content_status: "AVAILABLE",
    },
  ),
];

const metaOnlyPromptEvent = event(
  "meta-prompt",
  TRAJ_PROMPT,
  "PROMPT_OBSERVED",
  5,
  "CLIENT_OBSERVED",
  "observe:cursor:beforeSubmitPrompt:gen-meta",
  { client_type: "cursor", hook_event: "beforeSubmitPrompt" },
  "LOW",
  "METADATA_ONLY",
  { content_status: "NOT_STORED" },
);

const denyEvents = [
  event(
    "d1",
    TRAJ_DENY,
    "TOOL_ATTEMPTED",
    1,
    "RAI_AUTHORITATIVE",
    `receipt:${RECEIPT_ID}:attempt`,
    { receipt_id: RECEIPT_ID, tool_name: "searchJiraIssuesUsingJql" },
  ),
  event(
    "d2",
    TRAJ_DENY,
    "POLICY_EVALUATED",
    2,
    "RAI_AUTHORITATIVE",
    `receipt:${RECEIPT_ID}:policy`,
    { receipt_id: RECEIPT_ID, final_effect: "DENY", matched_rule_ids: [RULE_ID] },
  ),
  event(
    "d3",
    TRAJ_DENY,
    "ACTION_DENIED",
    3,
    "RAI_AUTHORITATIVE",
    `receipt:${RECEIPT_ID}:decision`,
    { receipt_id: RECEIPT_ID, decision: "DENY" },
  ),
];

const missingEvents = [
  event(
    "m1",
    TRAJ_MISSING,
    "TOOL_ATTEMPTED",
    1,
    "RAI_AUTHORITATIVE",
    `receipt:${RECEIPT_ID}:attempt`,
    { receipt_id: RECEIPT_ID },
  ),
  event(
    "m2",
    TRAJ_MISSING,
    "POLICY_EVALUATED",
    2,
    "RAI_AUTHORITATIVE",
    `receipt:${RECEIPT_ID}:policy`,
    { receipt_id: RECEIPT_ID, final_effect: "ALLOW" },
  ),
  event(
    "m3",
    TRAJ_MISSING,
    "ACTION_ALLOWED",
    3,
    "RAI_AUTHORITATIVE",
    `receipt:${RECEIPT_ID}:decision`,
    { receipt_id: RECEIPT_ID, decision: "ALLOW" },
  ),
];

const promptNaEvents = [
  event(
    "p1",
    TRAJ_PROMPT,
    "TOOL_ATTEMPTED",
    1,
    "RAI_AUTHORITATIVE",
    `receipt:${RECEIPT_ID}:attempt`,
    { receipt_id: RECEIPT_ID },
  ),
  event(
    "p2",
    TRAJ_PROMPT,
    "POLICY_EVALUATED",
    2,
    "RAI_AUTHORITATIVE",
    `receipt:${RECEIPT_ID}:policy`,
    { receipt_id: RECEIPT_ID, final_effect: "ALLOW" },
  ),
  event(
    "p3",
    TRAJ_PROMPT,
    "ACTION_ALLOWED",
    3,
    "RAI_AUTHORITATIVE",
    `receipt:${RECEIPT_ID}:decision`,
    { receipt_id: RECEIPT_ID, decision: "ALLOW" },
  ),
  event(
    "p4",
    TRAJ_PROMPT,
    "TOOL_EXECUTION_SUCCEEDED",
    4,
    "CLIENT_REPORTED",
    `receipt:${RECEIPT_ID}:execution`,
    { receipt_id: RECEIPT_ID },
    "MEDIUM",
  ),
  metaOnlyPromptEvent,
];

function summaryFrom(
  id: string,
  status: string,
  eventCount: number,
  findingCount: number,
  completeness: number,
  coverage: Record<string, string>,
) {
  return {
    id,
    ai_system_id: "sys-1",
    ai_system_name: "Demo System",
    agent_id: "agent-1",
    agent_name: "Demo Agent",
    agent_version_id: "ver-1",
    agent_version_number: 1,
    runtime_identity_id: "ri-1",
    runtime_identity_name: "Demo Runtime",
    session_key: `conv:demo-${id.slice(-4)}|ri:ri-1|ci:_`,
    conversation_id: `demo-${id.slice(-4)}`,
    correlation_id: `corr-${id.slice(-4)}`,
    client_type: "cursor",
    status,
    event_count: eventCount,
    finding_count: findingCount,
    completeness_pct: completeness,
    assurance_summary: { highest: "HIGH", has_authoritative: true },
    coverage_summary: coverage,
    started_at: "2026-09-06T10:00:00.000Z",
    last_event_at: "2026-09-06T10:00:10.000Z",
    enforcement_mode: "HOOK_ENFORCED",
    deployment_control: "LOCAL_HOOK",
  };
}

const catalogs: Record<
  string,
  {
    summary: ReturnType<typeof summaryFrom>;
    events: ReturnType<typeof event>[];
    findings: Array<Record<string, unknown>>;
    graph: {
      nodes: Array<Record<string, unknown>>;
      edges: Array<Record<string, unknown>>;
    };
  }
> = {
  [TRAJ_MAIN]: {
    summary: summaryFrom(TRAJ_MAIN, "COMPLETED", 10, 0, 100, {
      identity: "COMPLETE",
      authority: "COMPLETE",
      policy: "COMPLETE",
      approval: "COMPLETE",
      execution: "COMPLETE",
      prompt: "OBSERVED",
      output: "OBSERVED",
      model: "OBSERVED",
    }),
    events: mainEvents,
    findings: [],
    graph: {
      nodes: [
        {
          id: "e3",
          entity_type: "EVENT",
          label: "TOOL_ATTEMPTED",
          source_type: "RAI_AUTHORITATIVE",
          assurance_level: "HIGH",
        },
        {
          id: RECEIPT_ID,
          entity_type: "RECEIPT",
          label: "Enforcement Receipt",
          source_type: "RAI_AUTHORITATIVE",
          assurance_level: "HIGH",
        },
        {
          id: APPROVAL_ID,
          entity_type: "APPROVAL",
          label: "Approval Request",
          source_type: "RAI_AUTHORITATIVE",
          assurance_level: "HIGH",
        },
      ],
      edges: [
        {
          id: "rel-1",
          trajectory_id: TRAJ_MAIN,
          source_entity_type: "EVENT",
          source_entity_id: "e3",
          relation_type: "PRODUCED",
          target_entity_type: "RECEIPT",
          target_entity_id: RECEIPT_ID,
        },
        {
          id: "rel-2",
          trajectory_id: TRAJ_MAIN,
          source_entity_type: "EVENT",
          source_entity_id: "e5",
          relation_type: "TRIGGERED",
          target_entity_type: "APPROVAL",
          target_entity_id: APPROVAL_ID,
        },
      ],
    },
  },
  [TRAJ_DENY]: {
    summary: summaryFrom(TRAJ_DENY, "COMPLETED", 3, 0, 100, {
      identity: "COMPLETE",
      authority: "COMPLETE",
      policy: "COMPLETE",
      approval: "NOT_REQUIRED",
      execution: "NOT_ATTEMPTED",
      prompt: "NOT_AVAILABLE",
      output: "NOT_AVAILABLE",
      model: "NOT_AVAILABLE",
    }),
    events: denyEvents,
    findings: [],
    graph: { nodes: [], edges: [] },
  },
  [TRAJ_MISSING]: {
    summary: summaryFrom(TRAJ_MISSING, "INCOMPLETE", 3, 1, 75, {
      identity: "COMPLETE",
      authority: "COMPLETE",
      policy: "COMPLETE",
      approval: "NOT_REQUIRED",
      execution: "MISSING",
      prompt: "NOT_AVAILABLE",
      output: "NOT_AVAILABLE",
      model: "NOT_AVAILABLE",
    }),
    events: missingEvents,
    findings: [
      {
        id: "f-missing",
        trajectory_id: TRAJ_MISSING,
        finding_type: "MISSING_EXECUTION_RESULT",
        severity: "HIGH",
        title: "Missing execution result",
        description: "ALLOW decision recorded without post-execution evidence.",
        source_event_ids: ["m3"],
        status: "OPEN",
      },
    ],
    graph: { nodes: [], edges: [] },
  },
  [TRAJ_PROMPT]: {
    summary: summaryFrom(TRAJ_PROMPT, "COMPLETED", 5, 0, 100, {
      identity: "COMPLETE",
      authority: "COMPLETE",
      policy: "COMPLETE",
      approval: "NOT_REQUIRED",
      execution: "COMPLETE",
      prompt: "OBSERVED",
      output: "NOT_AVAILABLE",
      model: "NOT_AVAILABLE",
    }),
    events: promptNaEvents,
    findings: [],
    graph: { nodes: [], edges: [] },
  },
};

const mockReceiptDetail = {
  id: RECEIPT_ID,
  decision: "ALLOW",
  reason: "Approved and allowed",
  reason_code: "ALLOWED",
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
    observed_model: "claude-sonnet",
    observed_client_user: "ops@example.com",
  },
  action: {
    integration_type: "mcp",
    integration_id: "mcp-1",
    integration_name: "Atlassian",
    tool_id: "tool-1",
    tool_name: "searchJiraIssuesUsingJql",
    target: { type: "issue", id: null },
    parameters: { jql: "project = DEMO" },
    action_digest: "digest-abc",
    idempotency_key: null,
  },
  policy_evaluation: {
    final_effect: "ALLOW",
    matched_rule_ids: [RULE_ID],
    matched_rules: [
      {
        rule_id: RULE_ID,
        title: "Allow Atlassian JQL",
        effect: "ALLOW",
        matched: true,
        conditions: [],
      },
    ],
    condition_details: [],
    precedence: "DENY > REQUIRE_APPROVAL > MONITOR > ALLOW",
    explanation: "ALLOW after approval",
    content_rule_enforcement: {
      status: "NOT_ACTIVE",
      reason: "CONTENT_EVALUATOR_NOT_CONFIGURED",
    },
    tool_rule_enforcement: { status: "ACTIVE", mode: "DETERMINISTIC" },
  },
  approval: { required: true, status: "Consumed", approval_request_id: APPROVAL_ID },
  execution: {
    attempted: true,
    status: "SUCCEEDED",
    source: "CLIENT_REPORTED",
    downstream_reference: null,
    duration_ms: 120,
    report: null,
    reported_at: "2026-09-06T10:00:09.000Z",
  },
  assurance: {
    enforcement_mode: "HOOK_ENFORCED",
    deployment_control: "LOCAL_HOOK",
    verification_status: "DECLARED",
    execution_evidence: "CLIENT_REPORTED",
    notes: "Local hooks may be modified or removed by users with sufficient local access.",
  },
  trace: {
    receipt_id: RECEIPT_ID,
    correlation_id: "corr-1",
    trace_id: "trace-1",
    session_id: "sess-1",
    conversation_id: "conv-1",
    generation_id: "gen-1",
    approval_request_id: APPROVAL_ID,
    execution_id: RECEIPT_ID,
    reason_code: "ALLOWED",
  },
  timestamps: {
    started_at: "2026-09-06T10:00:00.000Z",
    completed_at: "2026-09-06T10:00:09.000Z",
    reported_at: "2026-09-06T10:00:09.000Z",
  },
};

async function seedAdminSession(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("rai.cp.adminAuthToken", "e2e-test-token");
    window.localStorage.setItem("rai.cp.activeAdminRole", "General Admin");
  });
}

async function mockTrajectoryApis(page: Page) {
  await page.route(/\/v1\/trajectories(\/|$|\?)/, async (route) => {
    const url = route.request().url();
    const method = route.request().method();

    if (method === "GET" && /\/v1\/trajectories\/[^/]+\/export/.test(url)) {
      const trajId = url.match(/\/v1\/trajectories\/([^/]+)\/export/)?.[1] ?? TRAJ_MAIN;
      const entry = catalogs[trajId];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          trajectory: entry?.summary ?? {},
          events: entry?.events ?? [],
          findings: entry?.findings ?? [],
        }),
      });
      return;
    }

    if (method === "GET" && /\/v1\/trajectories\/[^/]+\/graph/.test(url)) {
      const trajId = url.match(/\/v1\/trajectories\/([^/]+)\/graph/)?.[1] ?? TRAJ_MAIN;
      const entry = catalogs[trajId];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          trajectory_id: trajId,
          nodes: entry?.graph.nodes ?? [],
          edges: entry?.graph.edges ?? [],
        }),
      });
      return;
    }

    if (method === "GET" && /\/v1\/trajectories\/[^/]+\/events\/[^/]+/.test(url)) {
      const match = url.match(/\/v1\/trajectories\/([^/]+)\/events\/([^/?]+)/);
      const trajId = match?.[1];
      const eventId = match?.[2];
      const entry = trajId ? catalogs[trajId] : undefined;
      const event = entry?.events.find((e) => e.id === eventId);
      if (!entry || !event) {
        await route.fulfill({ status: 404, body: "not found" });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...event,
          artifacts: [],
          related_events: entry.events
            .filter((e) => e.id !== eventId)
            .slice(0, 5)
            .map((e) => ({
              id: e.id,
              event_type: e.event_type,
              sequence_number: e.sequence_number,
              source_type: e.source_type,
              assurance_level: e.assurance_level,
              occurred_at: e.occurred_at,
            })),
          trajectory: {
            id: trajId,
            conversation_id: entry.summary.conversation_id,
            client_type: entry.summary.client_type,
          },
        }),
      });
      return;
    }

    if (method === "GET" && /\/v1\/trajectories\/[0-9a-f-]{36}(\?|$)/i.test(url)) {
      const trajId = url.match(/\/v1\/trajectories\/([0-9a-f-]{36})/i)?.[1];
      const entry = trajId ? catalogs[trajId] : undefined;
      if (!entry) {
        await route.fulfill({ status: 404, body: "not found" });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...entry.summary,
          events: entry.events,
          relations: entry.graph.edges,
          findings: entry.findings,
          artifacts: [],
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: Object.values(catalogs).map((c) => c.summary),
        limit: 100,
        offset: 0,
      }),
    });
  });

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
      body: JSON.stringify([]),
    });
  });

  await page.route(/\/v1\/approvals(\/|$|\?)/, async (route) => {
    const url = route.request().url();
    if (url.includes(APPROVAL_ID)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: APPROVAL_ID,
          status: "CONSUMED",
          decision: "APPROVED",
          ai_system_name: "Demo System",
          agent_name: "Demo Agent",
          tool_name: "searchJiraIssuesUsingJql",
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
}

test.describe("Trajectory operator flows", () => {
  test.beforeEach(async ({ page }) => {
    await seedAdminSession(page);
    await mockTrajectoryApis(page);
  });

  test("main flow: list → overview → timeline → receipt → findings", async ({ page }) => {
    await page.goto("/runtime/trajectories");
    await expect(page.getByTestId("trajectories-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Trajectories", exact: true })).toBeVisible();
    await expect(page.getByTestId(`trajectory-row-${TRAJ_MAIN}`)).toBeVisible();

    await page.getByTestId(`trajectory-row-${TRAJ_MAIN}`).click();
    await expect(page).toHaveURL(new RegExp(`/runtime/trajectories/${TRAJ_MAIN}$`));
    await expect(page.getByTestId("trajectory-detail-page")).toBeVisible();
    await expect(page.getByTestId("trajectory-overview")).toBeVisible();
    await expect(page.getByTestId("trajectory-overview")).toContainText("Demo System");
    await expect(page.getByTestId("trajectory-overview")).toContainText("Demo Runtime");
    await expect(page.getByTestId("trajectory-overview")).toContainText("cursor");
    await expect(page.getByTestId("trajectory-overview")).toContainText("OBSERVED");

    await page.getByRole("button", { name: "Timeline" }).click();
    await expect(page.getByTestId("trajectory-timeline")).toBeVisible();
    await expect(page.getByTestId("trajectory-timeline")).toContainText("Prompt Observed");
    await expect(page.getByTestId("trajectory-timeline")).toContainText("Policy Evaluated");
    await expect(page.getByTestId("trajectory-timeline")).toContainText("Approval Consumed");
    await expect(page.getByTestId("trajectory-timeline")).toContainText("Tool Execution Succeeded");
    await expect(page.getByTestId("trajectory-timeline")).toContainText("RAI_AUTHORITATIVE");
    await expect(page.getByTestId("trajectory-timeline")).toContainText("CLIENT_OBSERVED");
    await expect(page.getByTestId("trajectory-timeline")).toContainText("CLIENT_REPORTED");

    const policyEvent = page.getByTestId("timeline-event").filter({ hasText: "Policy Evaluated" });
    await policyEvent.click();
    await expect(policyEvent.getByRole("link", { name: "Open enforcement receipt" })).toBeVisible();
    await policyEvent.getByRole("link", { name: "Open enforcement receipt" }).click();
    await expect(page).toHaveURL(new RegExp(`/runtime/enforcement/${RECEIPT_ID}$`));
    await expect(page.getByTestId("enforcement-detail-page")).toBeVisible();

    await page.goto(`/runtime/trajectories/${TRAJ_MAIN}`);
    await page.getByRole("button", { name: "Timeline" }).click();
    const approvalEvent = page
      .getByTestId("timeline-event")
      .filter({ hasText: "Approval Requested" });
    await approvalEvent.click();
    await expect(approvalEvent.getByRole("link", { name: "Open approval" })).toBeVisible();

    await page.getByRole("button", { name: "Evidence" }).click();
    await expect(page.getByTestId("trajectory-evidence")).toBeVisible();
    await expect(page.getByTestId("trajectory-evidence")).toContainText("RAI_AUTHORITATIVE");

    await page.getByRole("button", { name: "Findings" }).click();
    await expect(page.getByTestId("trajectory-findings")).toBeVisible();
    await expect(page.getByTestId("trajectory-findings")).toContainText(
      "No findings for this trajectory",
    );

    await page.getByRole("button", { name: "Graph" }).click();
    await expect(page.getByTestId("trajectory-graph")).toBeVisible();
    await expect(page.getByTestId("trajectory-graph")).toContainText("Enforcement Receipt");
  });

  test("DENY trajectory has no successful tool execution", async ({ page }) => {
    await page.goto(`/runtime/trajectories/${TRAJ_DENY}`);
    await page.getByRole("button", { name: "Timeline" }).click();
    await expect(page.getByTestId("trajectory-timeline")).toContainText("Tool Attempted");
    await expect(page.getByTestId("trajectory-timeline")).toContainText("Policy Evaluated");
    await expect(page.getByTestId("trajectory-timeline")).toContainText("Action Denied");
    await expect(page.getByTestId("trajectory-timeline")).not.toContainText(
      "Tool Execution Succeeded",
    );
  });

  test("missing execution evidence shows finding and incomplete coverage", async ({ page }) => {
    await page.goto(`/runtime/trajectories/${TRAJ_MISSING}`);
    await expect(page.getByTestId("trajectory-overview")).toContainText("MISSING");
    await expect(page.getByTestId("trajectory-overview")).toContainText("75%");
    await page.getByRole("button", { name: "Findings" }).click();
    await expect(page.getByTestId("trajectory-findings")).toContainText("MISSING_EXECUTION_RESULT");
    await expect(page.getByTestId("trajectory-findings")).toContainText("Missing execution result");
  });

  test("prompt/output NOT_AVAILABLE is explicit when unsupported", async ({ page }) => {
    await page.goto(`/runtime/trajectories/${TRAJ_PROMPT}`);
    await expect(page.getByTestId("trajectory-overview")).toContainText("NOT_AVAILABLE");
    await expect(page.getByTestId("trajectory-overview")).toContainText("prompt");
    await expect(page.getByTestId("trajectory-overview")).toContainText("output");
  });

  test("prompt and agent output details show retained redacted content", async ({ page }) => {
    await page.goto(`/runtime/trajectories/${TRAJ_MAIN}`);
    await page.getByRole("button", { name: "Timeline" }).click();
    await expect(page.getByTestId("trajectory-timeline")).toContainText("Mahally");

    const promptEvent = page.getByTestId("timeline-event").filter({ hasText: "Prompt Observed" });
    await promptEvent.click();
    await promptEvent.getByTestId("view-evidence-details").click();
    await expect(page).toHaveURL(new RegExp(`/runtime/trajectories/${TRAJ_MAIN}/evidence/e1$`));
    await expect(page.getByTestId("evidence-event-detail-page")).toBeVisible();
    await expect(page.getByTestId("evidence-event-content")).toContainText(
      "Search Jira for all Mahally issues updated this week",
    );
    await expect(page.getByTestId("evidence-event-detail-page")).toContainText("REDACTED");
    await expect(page.getByTestId("evidence-event-detail-page")).toContainText("CLIENT_OBSERVED");

    await page.goto(`/runtime/trajectories/${TRAJ_MAIN}`);
    await page.getByRole("button", { name: "Evidence" }).click();
    const outputRow = page.getByTestId("evidence-row").filter({ hasText: "Agent Output Observed" });
    await expect(outputRow).toContainText("Found 4 Mahally");
    await outputRow.getByTestId("view-evidence-details").click();
    await expect(page.getByTestId("evidence-event-content")).toContainText(
      "Found 4 Mahally issues updated this week.",
    );
  });

  test("metadata-only prompt explains content was not stored", async ({ page }) => {
    await page.goto(`/runtime/trajectories/${TRAJ_PROMPT}/evidence/meta-prompt`);
    await expect(page.getByTestId("evidence-event-detail-page")).toBeVisible();
    await expect(page.getByTestId("evidence-content-unavailable")).toContainText(
      "Content not stored",
    );
    await expect(page.getByTestId("evidence-content-unavailable")).toContainText("METADATA_ONLY");
  });
});
