/** Official TypeScript SDK for RAI Control Plane /sdk/v1 */

export const SDK_VERSION = "0.2.0";
export const API_RANGE = ">=1.0.0,<2.0.0";

export class RAIError extends Error {
  code: string;
  retryable: boolean;
  details: Record<string, unknown>;
  statusCode?: number;

  constructor(
    code: string,
    message: string,
    opts?: {
      retryable?: boolean;
      details?: Record<string, unknown>;
      statusCode?: number;
    }
  ) {
    super(`${code}: ${message}`);
    this.name = "RAIError";
    this.code = code;
    this.retryable = opts?.retryable ?? false;
    this.details = opts?.details ?? {};
    this.statusCode = opts?.statusCode;
  }
}

export interface DecisionData {
  decision: string;
  decision_id?: string | null;
  reason_code?: string | null;
  human_message?: string | null;
  machine_reason?: string | null;
  approval_request_id?: string | null;
  enforcement_receipt_id?: string | null;
  retryable?: boolean;
  allowed?: boolean;
  approval?: { approval_request_id?: string | null; [key: string]: unknown };
  [key: string]: unknown;
}

export class Decision {
  decision: string;
  decisionId?: string | null;
  reasonCode?: string | null;
  humanMessage?: string | null;
  machineReason?: string | null;
  approvalRequestId?: string | null;
  enforcementReceiptId?: string | null;
  retryable: boolean;
  raw: DecisionData;

  constructor(data: DecisionData) {
    const approval = data.approval ?? {};
    this.decision = data.decision;
    this.decisionId = data.decision_id;
    this.reasonCode = data.reason_code;
    this.humanMessage = data.human_message;
    this.machineReason = data.machine_reason;
    this.approvalRequestId =
      data.approval_request_id ?? approval.approval_request_id ?? null;
    this.enforcementReceiptId = data.enforcement_receipt_id;
    this.retryable = Boolean(data.retryable);
    this.raw = data;
  }

  get allowed(): boolean {
    return this.decision === "ALLOW";
  }

  async reportExecution(
    client: RAIClient,
    opts: {
      status: string;
      externalExecutionId?: string;
      resultMetadata?: Record<string, unknown>;
      errorMetadata?: Record<string, unknown>;
      usage?: Record<string, unknown>;
      cost?: Record<string, unknown>;
    }
  ): Promise<Record<string, unknown>> {
    if (!this.decisionId) {
      throw new RAIError("INVALID_REQUEST", "Decision has no decision_id");
    }
    return client.reportExecution(this.decisionId, opts);
  }
}

export interface ConfigurationProvenanceMetadata {
  /** External application configuration id (not a RAI prompt template). */
  configuration_id?: string;
  configuration_version?: string;
  /** Application-computed SHA-256 of canonicalized config snapshot. */
  configuration_digest?: string;
  configuration_source?: string;
  configuration_environment?: string;
  deployment_id?: string;
  release_id?: string;
  generation_id?: string;
  turn_id?: string;
}

export interface RecordUsageOptions {
  spanType?: string;
  provider?: string;
  model?: string;
  operation?: string;
  inputTokens?: number;
  outputTokens?: number;
  cachedInputTokens?: number;
  cacheWriteTokens?: number;
  reasoningTokens?: number;
  totalTokens?: number;
  /** Explicit billed amount (maps to cost.amount with source EXPLICIT_COST). */
  cost?: number;
  /** Provider-reported amount (preferred over cost when both set). */
  providerCost?: number;
  currency?: string;
  costSource?: string;
  startedAt?: string;
  completedAt?: string;
  externalSpanId?: string;
  parentSpanId?: string;
  trajectoryId?: string;
  metadata?: Record<string, unknown>;
  tokensAreEstimated?: boolean;
}

export class Session {
  raiSessionId: string;
  trajectoryId?: string | null;
  correlationId?: string | null;
  raw: Record<string, unknown>;
  private client: RAIClient;

  constructor(client: RAIClient, data: Record<string, unknown>) {
    this.client = client;
    this.raiSessionId = String(data.rai_session_id);
    this.trajectoryId = (data.trajectory_id as string | null) ?? null;
    this.correlationId = (data.correlation_id as string | null) ?? null;
    this.raw = data;
  }

  observeInput(opts: {
    content?: string;
    contentType?: string;
    observedModel?: string;
    principal?: Record<string, unknown>;
    /**
     * Optional observation metadata. Prefer ConfigurationProvenanceMetadata keys
     * (configuration_id/version/digest, deployment_id, release_id, turn_id).
     * Do not upload the full system prompt / persona body.
     */
    metadata?: ConfigurationProvenanceMetadata & Record<string, unknown>;
  }): Promise<Record<string, unknown>> {
    return this.client.request(
      "POST",
      `/sdk/v1/sessions/${this.raiSessionId}/input`,
      {
        content: opts.content,
        content_type: opts.contentType ?? "text",
        observed_model: opts.observedModel,
        principal: opts.principal,
        metadata: opts.metadata ?? {},
      }
    );
  }

  async authorizeAction(opts: {
    tool?: string;
    toolId?: string;
    target?: Record<string, unknown>;
    parameters?: Record<string, unknown>;
    amount?: number;
    currency?: string;
    idempotencyKey?: string;
    metadata?: Record<string, unknown>;
    approvalRequestId?: string;
  }): Promise<Decision> {
    const data = (await this.client.request(
      "POST",
      `/sdk/v1/sessions/${this.raiSessionId}/actions/authorize`,
      {
        tool: opts.tool,
        tool_id: opts.toolId,
        target: opts.target,
        parameters: opts.parameters ?? {},
        amount: opts.amount,
        currency: opts.currency,
        idempotency_key: opts.idempotencyKey,
        metadata: opts.metadata ?? {},
        approval_request_id: opts.approvalRequestId,
      },
      opts.idempotencyKey
        ? { "Idempotency-Key": opts.idempotencyKey }
        : undefined
    )) as DecisionData;
    return new Decision(data);
  }

  /**
   * Authorize / mask structured data before it reaches the model.
   * Projects DATA_SOURCE_ACCESSED onto the session trajectory when a catalog
   * data_source_id is provided.
   */
  authorizeDataAccess(opts: {
    resource: string;
    fields?: string[];
    payload?: Record<string, unknown> | unknown[];
    purpose?: string;
    accessMode?: string;
    dataSourceId?: string;
    toolId?: string;
    target?: string;
    rowFilter?: Record<string, unknown>;
  }): Promise<Record<string, unknown>> {
    return this.client.request(
      "POST",
      `/sdk/v1/sessions/${this.raiSessionId}/data-access/authorize`,
      {
        resource: opts.resource,
        fields: opts.fields ?? [],
        payload: opts.payload,
        purpose: opts.purpose,
        access_mode: opts.accessMode ?? "READ",
        data_source_id: opts.dataSourceId,
        tool_id: opts.toolId,
        target: opts.target,
        row_filter: opts.rowFilter ?? {},
      }
    );
  }

  observeOutput(opts: {
    content?: string;
    contentType?: string;
    observedModel?: string;
    /** Prefer configuration_* / generation_id / turn_id — not full prompt bodies. */
    metadata?: ConfigurationProvenanceMetadata & Record<string, unknown>;
  }): Promise<Record<string, unknown>> {
    return this.client.request(
      "POST",
      `/sdk/v1/sessions/${this.raiSessionId}/output`,
      {
        content: opts.content,
        content_type: opts.contentType ?? "text",
        observed_model: opts.observedModel,
        metadata: opts.metadata ?? {},
      }
    );
  }

  end(): Promise<Record<string, unknown>> {
    return this.client.request(
      "POST",
      `/sdk/v1/sessions/${this.raiSessionId}/end`
    );
  }

  recordUsage(opts: RecordUsageOptions = {}): Promise<Record<string, unknown>> {
    const money =
      opts.providerCost !== undefined ? opts.providerCost : opts.cost;
    const costBody =
      money === undefined && !opts.costSource
        ? undefined
        : {
            amount: money,
            currency: opts.currency ?? "USD",
            source:
              opts.costSource ??
              (opts.providerCost !== undefined
                ? "PROVIDER_RESPONSE"
                : "EXPLICIT_COST"),
          };

    const usage: Record<string, number> = {};
    if (opts.inputTokens !== undefined) usage.input_tokens = opts.inputTokens;
    if (opts.outputTokens !== undefined) usage.output_tokens = opts.outputTokens;
    if (opts.cachedInputTokens !== undefined) {
      usage.cached_input_tokens = opts.cachedInputTokens;
    }
    if (opts.cacheWriteTokens !== undefined) {
      usage.cache_write_tokens = opts.cacheWriteTokens;
    }
    if (opts.reasoningTokens !== undefined) {
      usage.reasoning_tokens = opts.reasoningTokens;
    }
    if (opts.totalTokens !== undefined) usage.total_tokens = opts.totalTokens;

    return this.client.request(
      "POST",
      `/sdk/v1/sessions/${this.raiSessionId}/metering/spans`,
      {
        span_type: opts.spanType ?? "MODEL_CALL",
        provider: opts.provider,
        model: opts.model,
        operation: opts.operation,
        usage,
        cost: costBody,
        started_at: opts.startedAt,
        completed_at: opts.completedAt,
        external_span_id: opts.externalSpanId,
        parent_span_id: opts.parentSpanId,
        trajectory_id: opts.trajectoryId,
        metadata: opts.metadata ?? {},
        tokens_are_estimated: opts.tokensAreEstimated ?? false,
      }
    );
  }

  /** Preferred alias — report tokens; VigilRAI prices them. */
  reportModelUsage(
    opts: Omit<RecordUsageOptions, "spanType"> = {}
  ): Promise<Record<string, unknown>> {
    return this.recordUsage({ ...opts, spanType: "MODEL_CALL" });
  }

  recordModelCall(
    opts: Omit<RecordUsageOptions, "spanType"> = {}
  ): Promise<Record<string, unknown>> {
    return this.recordUsage({ ...opts, spanType: "MODEL_CALL" });
  }

  completeMeteringSpan(
    spanId: string,
    opts: RecordUsageOptions = {}
  ): Promise<Record<string, unknown>> {
    const money =
      opts.providerCost !== undefined ? opts.providerCost : opts.cost;
    const costBody =
      money === undefined && !opts.costSource
        ? undefined
        : {
            amount: money,
            currency: opts.currency ?? "USD",
            source:
              opts.costSource ??
              (opts.providerCost !== undefined
                ? "PROVIDER_RESPONSE"
                : "EXPLICIT_COST"),
          };

    const usage: Record<string, number> = {};
    if (opts.inputTokens !== undefined) usage.input_tokens = opts.inputTokens;
    if (opts.outputTokens !== undefined) usage.output_tokens = opts.outputTokens;
    if (opts.cachedInputTokens !== undefined) {
      usage.cached_input_tokens = opts.cachedInputTokens;
    }
    if (opts.cacheWriteTokens !== undefined) {
      usage.cache_write_tokens = opts.cacheWriteTokens;
    }
    if (opts.reasoningTokens !== undefined) {
      usage.reasoning_tokens = opts.reasoningTokens;
    }
    if (opts.totalTokens !== undefined) usage.total_tokens = opts.totalTokens;

    return this.client.request(
      "PATCH",
      `/sdk/v1/sessions/${this.raiSessionId}/metering/spans/${spanId}`,
      {
        span_type: opts.spanType ?? "MODEL_CALL",
        provider: opts.provider,
        model: opts.model,
        operation: opts.operation,
        usage,
        cost: costBody,
        started_at: opts.startedAt,
        completed_at: opts.completedAt,
        external_span_id: opts.externalSpanId,
        parent_span_id: opts.parentSpanId,
        trajectory_id: opts.trajectoryId,
        metadata: opts.metadata ?? {},
        tokens_are_estimated: opts.tokensAreEstimated ?? false,
      }
    );
  }
}

export interface RAIClientOptions {
  baseUrl: string;
  apiKey: string;
  integrationId: string;
  timeoutMs?: number;
  failClosed?: boolean;
  sdkVersion?: string;
}

export class RAIClient {
  baseUrl: string;
  apiKey: string;
  integrationId: string;
  timeoutMs: number;
  failClosed: boolean;
  sdkVersion: string;

  constructor(opts: RAIClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/$/, "");
    this.apiKey = opts.apiKey;
    this.integrationId = opts.integrationId;
    this.timeoutMs = opts.timeoutMs ?? 30_000;
    this.failClosed = opts.failClosed ?? true;
    this.sdkVersion = opts.sdkVersion ?? SDK_VERSION;
  }

  health(): Promise<Record<string, unknown>> {
    return this.request("GET", "/sdk/v1/health", undefined, undefined, false);
  }

  heartbeat(
    capabilityMatrix?: Record<string, boolean>
  ): Promise<Record<string, unknown>> {
    return this.request("POST", "/sdk/v1/heartbeat", {
      integration_id: this.integrationId,
      sdk_version: this.sdkVersion,
      protocol_version: 1,
      capability_matrix: capabilityMatrix,
    });
  }

  async startSession(opts?: {
    externalSessionId?: string;
    /** Stable conversation / thread id (grouping only; not a trajectory key). */
    externalConversationId?: string;
    principal?: string;
    channel?: string;
    /** Tenant-scoped delegation grant bound to this session/turn. */
    delegationId?: string;
    /**
     * Opt-in migration flag. Ended sessions are not reopened by default;
     * hosts must use a unique externalSessionId per AI turn.
     */
    allowEndedSessionReuse?: boolean;
    /**
     * Session metadata. Prefer ConfigurationProvenanceMetadata keys so RAI can
     * record which external config produced this turn without owning prompts.
     */
    metadata?: ConfigurationProvenanceMetadata & Record<string, unknown>;
  }): Promise<Session> {
    const data = await this.request("POST", "/sdk/v1/sessions", {
      integration_id: this.integrationId,
      external_session_id: opts?.externalSessionId,
      external_conversation_id: opts?.externalConversationId,
      principal: opts?.principal,
      channel: opts?.channel,
      delegation_id: opts?.delegationId,
      allow_ended_session_reuse: opts?.allowEndedSessionReuse ?? false,
      metadata: opts?.metadata ?? {},
    });
    return new Session(this, data);
  }

  reportExecution(
    decisionId: string,
    opts: {
      status: string;
      externalExecutionId?: string;
      resultMetadata?: Record<string, unknown>;
      errorMetadata?: Record<string, unknown>;
      usage?: Record<string, unknown>;
      cost?: Record<string, unknown>;
    }
  ): Promise<Record<string, unknown>> {
    return this.request("POST", `/sdk/v1/actions/${decisionId}/execution`, {
      status: opts.status,
      external_execution_id: opts.externalExecutionId,
      result_metadata: opts.resultMetadata ?? {},
      error_metadata: opts.errorMetadata,
      usage: opts.usage,
      cost: opts.cost,
    });
  }

  async getDecision(decisionId: string): Promise<Decision> {
    const data = (await this.request(
      "GET",
      `/sdk/v1/decisions/${decisionId}`
    )) as DecisionData;
    return new Decision(data);
  }

  getApprovalStatus(
    approvalRequestId: string
  ): Promise<Record<string, unknown>> {
    return this.request("GET", `/sdk/v1/approvals/${approvalRequestId}`);
  }

  async request(
    method: string,
    path: string,
    body?: Record<string, unknown>,
    extraHeaders?: Record<string, string>,
    auth = true
  ): Promise<Record<string, unknown>> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const headers: Record<string, string> = {
        Accept: "application/json",
        "User-Agent": `rai-sdk-ts/${this.sdkVersion}`,
        "X-RAI-SDK-Version": this.sdkVersion,
        ...(extraHeaders ?? {}),
      };
      if (auth) {
        headers["X-RAI-Agent-Key"] = this.apiKey;
      }
      if (body !== undefined) {
        headers["Content-Type"] = "application/json";
      }
      const resp = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
      const responseText = await resp.text();
      if (!resp.ok) {
        let detail: Record<string, unknown> = {};
        try {
          const payload = responseText
            ? (JSON.parse(responseText) as Record<string, unknown>)
            : {};
          detail = (payload.detail as Record<string, unknown>) ?? payload;
        } catch {
          detail = { message: responseText || resp.statusText };
        }
        throw new RAIError(
          String(detail.error ?? "INVALID_REQUEST"),
          String(detail.message ?? resp.statusText),
          {
            retryable: Boolean(detail.retryable),
            details: (detail.details as Record<string, unknown>) ?? {},
            statusCode: resp.status,
          }
        );
      }
      if (resp.status === 204 || !responseText) return {};
      return JSON.parse(responseText) as Record<string, unknown>;
    } catch (err) {
      if (err instanceof RAIError) throw err;
      if (this.failClosed) {
        throw new RAIError("RAI_UNAVAILABLE", `RAI unavailable: ${String(err)}`, {
          retryable: true,
        });
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }
}
