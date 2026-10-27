"""Helpers for evidence content permission gating."""

from __future__ import annotations

from typing import Any

from rai_gateway.evidence.domain import CONTENT_PAYLOAD_FIELDS

CONTENT_READ_PERMISSION = "evidence:content:read"
CONTENT_EXPORT_PERMISSION = "evidence:content:export"


def strip_event_content(event: dict[str, Any]) -> dict[str, Any]:
    """Remove inspectable payload/preview fields for metadata-only readers."""
    out = dict(event)
    payload = out.get("payload")
    if isinstance(payload, dict):
        out["payload"] = {
            key: value
            for key, value in payload.items()
            if key not in CONTENT_PAYLOAD_FIELDS
        }
    out["content_preview"] = None
    out["content_redacted"] = True
    out["content_access"] = "DENIED"
    if "artifacts" in out and isinstance(out["artifacts"], list):
        out["artifacts"] = [strip_artifact_content(a) for a in out["artifacts"]]
    return out


def strip_artifact_content(artifact: dict[str, Any]) -> dict[str, Any]:
    out = dict(artifact)
    out["inline_content"] = None
    out["content_redacted"] = True
    out["content_access"] = "DENIED"
    return out


def strip_observed_prompt_content(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["content_preview"] = None
    if "content" in out:
        out["content"] = None
    out["content_redacted"] = True
    out["content_access"] = "DENIED"
    return out


def strip_lifecycle_content(lifecycle: dict[str, Any]) -> dict[str, Any]:
    out = dict(lifecycle)
    stages: list[dict[str, Any]] = []
    for stage in out.get("stages") or []:
        stage_out = dict(stage)
        content = stage_out.get("content")
        if isinstance(content, dict):
            content_out = dict(content)
            content_out["preview"] = None
            if content_out.get("availability") in {"CAPTURED", "FULL", "REDACTED"}:
                content_out["reason"] = (
                    content_out.get("reason")
                    or "Raw content requires evidence:content:read"
                )
            stage_out["content"] = content_out
        stages.append(stage_out)
    out["stages"] = stages
    out["content_access"] = "DENIED"
    return out


def apply_content_permission(
    payload: dict[str, Any], *, allowed: bool
) -> dict[str, Any]:
    if allowed:
        result = dict(payload)
        result["content_access"] = "ALLOWED"
        return result
    return strip_event_content(payload)


def apply_trajectory_content_permission(
    detail: dict[str, Any], *, allowed: bool
) -> dict[str, Any]:
    out = dict(detail)
    if allowed:
        out["content_access"] = "ALLOWED"
        return out
    events = out.get("events")
    if isinstance(events, list):
        out["events"] = [strip_event_content(e) for e in events]
    artifacts = out.get("artifacts")
    if isinstance(artifacts, list):
        out["artifacts"] = [strip_artifact_content(a) for a in artifacts]
    out["content_access"] = "DENIED"
    return out


def apply_export_content_permission(
    export: dict[str, Any], *, allowed: bool
) -> dict[str, Any]:
    out = dict(export)
    trajectory = out.get("trajectory")
    if isinstance(trajectory, dict):
        out["trajectory"] = apply_trajectory_content_permission(
            trajectory, allowed=allowed
        )
    out["content_access"] = "ALLOWED" if allowed else "DENIED"
    return out
