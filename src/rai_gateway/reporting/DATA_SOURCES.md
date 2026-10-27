# Reporting Data Sources Documentation

This document maps reporting metrics to their authoritative source models and tables.

## Risk Intelligence

### Source Models: `risk_intelligence.py`
- **RiskSignal** - Risk signals and events
- **RiskState** - Current risk posture
- **RuntimeRiskFinding** - Runtime-generated risk findings
- **RiskMonitor** - Risk monitoring configuration
- **ContentEvaluationResult** - Content evaluation outcomes
- **EmergingRiskCandidate** - Emerging risk patterns

### Source Models: `registry.py`
- **RiskAssessment** - System-level risk assessments
- **RiskFinding** - Risk findings from assessments

### Available Metrics:
- Open findings count (by severity, category, status)
- New findings (time-based)
- Resolved findings
- Risk scores
- Risk trends
- Risk by AI system, agent, tool, model, data source

## Policy Enforcement

### Source Models: `policy_engine.py`
- **PolicyCollection** - Policy collections per AI system
- **ContentRule** - Content policy rules
- **ToolRule** - Tool policy rules
- **ToolRuleCondition** - Tool rule conditions

### Source Models: `runtime_enforcement.py`
- **RuntimeEnforcementReceipt** - Policy enforcement decisions and outcomes
  - policy_effect (ALLOW, MONITOR, REQUIRE_APPROVAL, DENY, SUSPEND)
  - enforcement_decision
  - matched_rule_ids
  - execution_status

### Available Metrics:
- Policy evaluation count
- Policy trigger count
- Trigger rate
- Effect distribution (ALLOW, MONITOR, REQUIRE_APPROVAL, DENY)
- Policy violations
- Blocked requests
- Top-triggering policies

## Budget & Cost

### Source Models: `risk_intelligence.py`
- **RuntimeBudget** - Budget definitions
  - metric (ACTION_COUNT, TOOL_COUNT, AMOUNT, TOKEN_USAGE, COST)
  - limit_value
  - warning_threshold
- **RuntimeBudgetWindow** - Budget windows/periods
  - current_usage
  - status
- **RuntimeBudgetCheck** - Budget check events
  - check_value
  - exceeded
  - warning_triggered

### Available Metrics:
- Current budget utilization
- Budget status
- Warning events
- Exceeded events
- Token usage
- Cost tracking
- Budget trends

## Runtime Execution

### Source Models: `evidence.py`
- **RuntimeTrajectory** - Execution trajectories
  - status, event_count, finding_count
- **RuntimeConversation** - Conversation projection
  - turn_count, token_count, estimated_cost
- **EvidenceEvent** - Runtime events
- **EvidenceArtifact** - Evidence artifacts
- **EvidenceFinding** - Evidence-level findings

### Source Models: `database.py`
- **ExecutionAudit** - Legacy execution audit records

### Available Metrics:
- Governed actions count
- Execution success rate
- Execution failure rate
- Conversation count
- Turn count
- Token usage
- Estimated cost

## Approvals

### Source Models: `approval.py`
- **ApprovalRequest** - Approval requests
  - status (PENDING, APPROVED, REJECTED, EXPIRED, CANCELLED)
  - risk_tier, risk_score
- **ApprovalDecision** - Approval decisions
- **ApprovalPlan** - Multi-stage approval plans
- **ApprovalStage** - Approval stages
- **ApprovalStageDecision** - Stage decisions

### Available Metrics:
- Approval requests count
- Approved count
- Rejected count
- Expired count
- Approval latency
- Approval escalation rate
- Approval acceptance rate

## Assurance & Evaluations

### Source Models: `evaluations.py`
- **AssuranceRecord** - Assurance records
  - status (VALID, EXPIRED, CONDITIONAL, FAILED)
- **EvaluationRun** - Evaluation runs
  - status, pass_rate
- **DeploymentGate** - Deployment gates
- **DeploymentGateEvaluation** - Gate evaluations
- **EvaluationWaiver** - Evaluation waivers

### Available Metrics:
- Assurance coverage
- Valid/expired/conditional/failed assurance count
- Evaluation pass rate
- Failed deployment gates
- Active waivers
- Expiring waivers

## Governance & Incidents

### Source Models: `governance.py`
- **AIIncident** - AI incidents
  - severity, status, category
- **IncidentTransition** - Incident state transitions
- **IncidentCorrectiveAction** - Corrective actions
- **GovernanceException** - Governance exceptions
  - status, expires_at
- **GovernanceReview** - Governance reviews
- **ControlAssessment** - Control assessments

### Available Metrics:
- Open incidents
- Critical incidents
- Incident trends
- Active exceptions
- Expiring exceptions
- Overdue reviews
- Control coverage

## Registry

### Source Models: `registry.py`
- **AISystem** - AI systems
- **Agent** - Agents
- **AgentVersion** - Agent versions
- **ModelResource** - Models
- **ToolResource** - Tools
- **MCPServer** - MCP servers
- **DataSource** - Data sources

### Available Metrics:
- AI systems governed count
- Active agents
- Agent versions
- Models in use
- Tools in use

## Identity

### Source Models: `governance.py`
- **OrganizationMembership** - Team members

### Source Models: `identity.py`
- **AgentRuntimeIdentity** - Runtime identities
- **DelegationGrant** - Delegations

### Available Metrics:
- Runtime identities count
- Active delegations

## Indexing Requirements

Report queries run against the single instance and should be indexed appropriately:
- created_at / occurred_at (time-series queries)
- ai_system_id (system-scoped reports)
- status (filtering by state)
- severity (risk/incident severity)
- All FK relationships used in joins
