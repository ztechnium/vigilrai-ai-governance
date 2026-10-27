"""Structured serialization for WP4 enforcement receipts."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.models.identity import AgentRuntimeIdentity
from rai_gateway.models.policy_engine import ToolRule
from rai_gateway.models.registry import (
    Agent,
    AgentVersion,
    AISystem,
    MCPServer,
    ToolResource,
)
from rai_gateway.runtime_enforcement.domain import (
    POLICY_EFFECT_PRECEDENCE,
    normalize_execution_status,
)

# Paths that must never appear in normal operator UI.
_SENSITIVE_CONTEXT_KEYS = frozenset(
    {
        "transcript_path",
        "transcriptPath",
        "authorization",
        "rai_agent_key",
        "RAI_AGENT_KEY",
        "api_key",
        "apiKey",
        "token",
        "password",
        "private_key",
        "secret",
    }
)


def _safe_client_context(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        if key in _SENSITIVE_CONTEXT_KEYS or any(
            token in key.lower()
            for token in ("token", "secret", "password", "authorization", "credential")
        ):
            continue
        cleaned[key] = value
    return cleaned or None


def _content_rule_enforcement(db: Session, receipt: Any) -> dict[str, Any]:
    from rai_gateway.policy.content_evaluator import content_enforcement_status

    ai_system_id = None
    try:
        if getattr(receipt, "runtime_identity_id", None):
            identity = (
                db.query(AgentRuntimeIdentity)
                .filter(AgentRuntimeIdentity.id == receipt.runtime_identity_id)
                .first()
            )
            if identity:
                agent = db.query(Agent).filter(Agent.id == identity.agent_id).first()
                if agent:
                    ai_system_id = agent.ai_system_id
    except Exception:
        ai_system_id = None
    return content_enforcement_status(db, ai_system_id)


def _rule_titles(db: Session, rule_ids: list[str]) -> dict[str, str]:
    if not rule_ids:
        return {}
    uuids: list[UUID] = []
    for rid in rule_ids:
        try:
            uuids.append(UUID(str(rid)))
        except (TypeError, ValueError):
            continue
    if not uuids:
        return {}
    rows = db.query(ToolRule).filter(ToolRule.id.in_(uuids)).all()
    return {str(r.id): r.title for r in rows}


def _matched_rules_structured(
    db: Session, policy_decision: dict[str, Any] | None
) -> list[dict[str, Any]]:
    decision = policy_decision or {}
    rule_ids = [str(r) for r in (decision.get("matched_rule_ids") or [])]
    titles = _rule_titles(db, rule_ids)
    condition_details = list(decision.get("condition_details") or [])
    by_rule: dict[str, list[dict[str, Any]]] = {}
    for detail in condition_details:
        rid = str(detail.get("rule_id") or "")
        by_rule.setdefault(rid, []).append(detail)

    # Prefer per-rule effect annotations when present; otherwise share final effect.
    final_effect = decision.get("effect")
    structured: list[dict[str, Any]] = []
    for rid in rule_ids:
        conditions = by_rule.get(rid, [])
        matched = True if not conditions else any(c.get("matched") for c in conditions)
        structured.append(
            {
                "rule_id": rid,
                "title": titles.get(rid),
                "effect": final_effect,
                "matched": matched,
                "conditions": conditions,
            }
        )
    return structured


def _serialize_approval_summary(
    db: Session, approval_request_id: UUID | None
) -> dict[str, Any]:
    if not approval_request_id:
        return {"required": False, "status": "Not Required"}

    from rai_gateway.models.approval import ApprovalDecision, ApprovalRequest

    request = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.id == approval_request_id)
        .first()
    )
    if not request:
        return {
            "required": True,
            "approval_request_id": str(approval_request_id),
            "status": "UNKNOWN",
        }

    decisions = (
        db.query(ApprovalDecision)
        .filter(ApprovalDecision.approval_request_id == request.id)
        .order_by(ApprovalDecision.decided_at.asc())
        .all()
    )
    latest = decisions[-1] if decisions else None
    return {
        "required": True,
        "approval_request_id": str(request.id),
        "status": request.status,
        "required_approver_role": request.approval_policy_reference,
        "requested_at": request.created_at.isoformat() if request.created_at else None,
        "decision_time": (
            latest.decided_at.isoformat()
            if latest and latest.decided_at
            else (request.decided_at.isoformat() if request.decided_at else None)
        ),
        "approver": latest.decided_by if latest else None,
        "action_digest": request.action_digest,
        "consumed_at": request.consumed_at.isoformat() if request.consumed_at else None,
        "consumed": request.status == "CONSUMED" or bool(request.consumed_at),
    }


def serialize_receipt_summary(receipt, db: Session) -> dict[str, Any]:
    """Flat summary for list views (backward compatible)."""
    detail = serialize_receipt_detail(receipt, db)
    flat = {
        "id": detail["id"],
        "runtime_identity_id": detail["identity"]["runtime_identity_id"],
        "runtime_identity_name": detail["identity"]["runtime_identity_name"],
        "ai_system_id": detail["identity"]["ai_system_id"],
        "ai_system_name": detail["identity"]["ai_system_name"],
        "agent_id": detail["identity"]["agent_id"],
        "agent_name": detail["identity"]["agent_name"],
        "agent_avatar": detail["identity"].get("agent_avatar"),
        "agent_version_id": detail["identity"]["agent_version_id"],
        "agent_version_number": detail["identity"]["agent_version_number"],
        "delegation_id": detail["identity"]["delegation_id"],
        "enforcement_mode": detail["assurance"]["enforcement_mode"],
        "deployment_control": detail["assurance"]["deployment_control"],
        "verification_status": detail["assurance"]["verification_status"],
        "integration_type": detail["action"]["integration_type"],
        "integration_id": detail["action"]["integration_id"],
        "integration_name": detail["action"]["integration_name"],
        "tool_id": detail["action"]["tool_id"],
        "tool_name": detail["action"]["tool_name"],
        "action_digest": detail["action"]["action_digest"],
        "action_summary": detail["action"].get("action_summary"),
        "policy_effect": detail["policy_evaluation"]["final_effect"],
        "policy_decision": receipt.policy_decision,
        "matched_rule_ids": detail["policy_evaluation"]["matched_rule_ids"],
        "approval_request_id": detail["approval"].get("approval_request_id"),
        "approval_consumed": bool(detail["approval"].get("consumed")),
        "approval_status": detail["approval"].get("status"),
        "enforcement_decision": detail["decision"],
        "reason_code": detail["reason_code"],
        "human_explanation": detail["reason"],
        "execution_attempted": detail["execution"]["attempted"],
        "execution_status": detail["execution"]["status"],
        "execution_source": detail["execution"]["source"],
        "downstream_reference": detail["execution"]["downstream_reference"],
        "monitor": receipt.monitor,
        "monitoring_instruction": receipt.monitoring_instruction,
        "client_type": (detail["client_context"] or {}).get("client_type"),
        "correlation_id": detail["trace"]["correlation_id"],
        "trace_id": detail["trace"]["trace_id"],
        "started_at": detail["timestamps"]["started_at"],
        "completed_at": detail["timestamps"]["completed_at"],
        "reported_at": detail["timestamps"]["reported_at"],
        "duration_ms": detail["execution"]["duration_ms"],
    }
    # Keep structured sections for detail consumers of the same payload.
    flat["identity"] = detail["identity"]
    flat["client_context"] = detail["client_context"]
    flat["action"] = detail["action"]
    flat["policy_evaluation"] = detail["policy_evaluation"]
    flat["approval"] = detail["approval"]
    flat["execution"] = detail["execution"]
    flat["assurance"] = detail["assurance"]
    flat["trace"] = detail["trace"]
    flat["timestamps"] = detail["timestamps"]
    return flat


def serialize_receipt_detail(receipt, db: Session) -> dict[str, Any]:
    """Sectioned receipt detail for operators (doc §1 / §13)."""
    tool = None
    mcp = None
    if receipt.tool_id:
        tool = db.query(ToolResource).filter(ToolResource.id == receipt.tool_id).first()
    if receipt.integration_id and receipt.integration_type == "mcp":
        mcp = db.query(MCPServer).filter(MCPServer.id == receipt.integration_id).first()

    identity = (
        db.query(AgentRuntimeIdentity)
        .filter(AgentRuntimeIdentity.id == receipt.runtime_identity_id)
        .first()
    )
    agent = db.query(Agent).filter(Agent.id == receipt.agent_id).first()
    system = db.query(AISystem).filter(AISystem.id == receipt.ai_system_id).first()
    version = (
        db.query(AgentVersion)
        .filter(AgentVersion.id == receipt.agent_version_id)
        .first()
    )

    duration_ms = receipt.duration_ms
    if duration_ms is None and receipt.started_at and receipt.completed_at:
        duration_ms = int(
            (receipt.completed_at - receipt.started_at).total_seconds() * 1000
        )

    action_summary = dict(receipt.action_summary or {})
    # Never leak transcript paths from nested summaries.
    post = action_summary.get("post_execution")
    if isinstance(post, dict):
        action_summary["post_execution"] = {
            k: v for k, v in post.items() if k not in _SENSITIVE_CONTEXT_KEYS
        }

    client_context = _safe_client_context(receipt.client_context)
    policy_decision = receipt.policy_decision or {}
    matched_rule_ids = [str(r) for r in (receipt.matched_rule_ids or [])]
    approval = _serialize_approval_summary(db, receipt.approval_request_id)
    if receipt.approval_consumed:
        approval["consumed"] = True

    execution_status = normalize_execution_status(receipt.execution_status)
    schema_version = getattr(receipt, "receipt_schema_version", None) or 1
    snapshot = getattr(receipt, "authority_snapshot", None)
    controls = []
    try:
        from rai_gateway.models.runtime_enforcement import RuntimeControlDecision

        rows = (
            db.query(RuntimeControlDecision)
            .filter(RuntimeControlDecision.receipt_id == receipt.id)
            .order_by(RuntimeControlDecision.sequence.asc())
            .all()
        )
        controls = [
            {
                "sequence": row.sequence,
                "control_type": row.control_type,
                "policy_domain": row.policy_domain,
                "status": row.status,
                "effect": row.effect,
                "reason_code": row.reason_code,
                "human_explanation": row.human_explanation,
                "matched_rule_ids": row.matched_rule_ids,
            }
            for row in rows
        ]
    except Exception:
        controls = []

    return {
        "id": str(receipt.id),
        "receipt_schema_version": schema_version,
        "decision": receipt.enforcement_decision,
        "reason": receipt.human_explanation,
        "reason_code": receipt.reason_code,
        "decision_phase": getattr(receipt, "decision_phase", None),
        "decision_digest": getattr(receipt, "decision_digest", None),
        "decision_finalized_at": (
            receipt.decision_finalized_at.isoformat()
            if getattr(receipt, "decision_finalized_at", None)
            else None
        ),
        "authority_snapshot_available": bool(snapshot),
        "authority_digest": getattr(receipt, "authority_digest", None),
        "authority_snapshot": snapshot if schema_version >= 2 else None,
        "control_summary": getattr(receipt, "control_summary", None),
        "control_decisions": controls,
        "decision_chain_id": str(receipt.decision_chain_id)
        if getattr(receipt, "decision_chain_id", None)
        else None,
        "resume_of_receipt_id": str(receipt.resume_of_receipt_id)
        if getattr(receipt, "resume_of_receipt_id", None)
        else None,
        "identity": {
            "ai_system_id": str(receipt.ai_system_id),
            "ai_system_name": system.name if system else None,
            "agent_id": str(receipt.agent_id),
            "agent_name": agent.name if agent else None,
            "agent_avatar": agent.avatar if agent else None,
            "agent_version_id": str(receipt.agent_version_id),
            "agent_version_number": version.version_number if version else None,
            "runtime_identity_id": str(receipt.runtime_identity_id),
            "runtime_identity_name": identity.name if identity else None,
            "delegation_id": str(receipt.delegation_id)
            if receipt.delegation_id
            else None,
        },
        "client_context": client_context,
        "action": {
            "integration_type": receipt.integration_type,
            "integration_id": str(receipt.integration_id)
            if receipt.integration_id
            else None,
            "integration_name": mcp.name if mcp else None,
            "tool_id": str(receipt.tool_id) if receipt.tool_id else None,
            "tool_name": tool.name if tool else None,
            "target": action_summary.get("target"),
            "parameters": action_summary.get("parameters") or {},
            "action_digest": receipt.action_digest,
            "idempotency_key": receipt.idempotency_key,
            "action_summary": action_summary,
        },
        "policy_evaluation": {
            "final_effect": receipt.policy_effect or policy_decision.get("effect"),
            "matched_rule_ids": matched_rule_ids,
            "matched_rules": _matched_rules_structured(db, policy_decision),
            "condition_details": policy_decision.get("condition_details") or [],
            "precedence": POLICY_EFFECT_PRECEDENCE,
            "explanation": policy_decision.get("human_explanation")
            or receipt.human_explanation,
            "content_rule_enforcement": _content_rule_enforcement(db, receipt),
            "tool_rule_enforcement": {
                "status": "ACTIVE",
                "mode": "DETERMINISTIC",
            },
        },
        "approval": approval,
        "execution": {
            "attempted": receipt.execution_attempted,
            "status": execution_status,
            "source": receipt.execution_source,
            "downstream_reference": receipt.downstream_reference,
            "duration_ms": duration_ms,
            "report": receipt.execution_report,
            "reported_at": receipt.reported_at.isoformat()
            if receipt.reported_at
            else None,
        },
        "assurance": {
            "enforcement_mode": receipt.enforcement_mode,
            "deployment_control": receipt.deployment_control,
            "verification_status": receipt.verification_status,
            "execution_evidence": receipt.execution_source,
            "notes": (
                "Local hooks may be modified or removed by users with sufficient local access."
                if receipt.deployment_control == "LOCAL_HOOK"
                else None
            ),
        },
        "trace": {
            "receipt_id": str(receipt.id),
            "correlation_id": receipt.correlation_id,
            "trace_id": receipt.trace_id,
            "session_id": (client_context or {}).get("session_id"),
            "conversation_id": (client_context or {}).get("conversation_id"),
            "generation_id": (client_context or {}).get("generation_id"),
            "approval_request_id": str(receipt.approval_request_id)
            if receipt.approval_request_id
            else None,
            "execution_id": str(receipt.id),
            "reason_code": receipt.reason_code,
        },
        "timestamps": {
            "started_at": receipt.started_at.isoformat()
            if receipt.started_at
            else None,
            "completed_at": receipt.completed_at.isoformat()
            if receipt.completed_at
            else None,
            "reported_at": receipt.reported_at.isoformat()
            if receipt.reported_at
            else None,
        },
    }
