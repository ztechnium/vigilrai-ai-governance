#!/usr/bin/env python3
"""Synthetic runtime volume fixture for Phase 6 scale checks.

Creates a bounded number of conversations/trajectories/events for local
EXPLAIN ANALYZE and UI performance checks. Not run in default CI.

Usage:
  DATABASE_URL=postgresql://rai_user:rai_password@localhost:5434/rai_gateway \\
    uv run python scripts/seed_runtime_scale_fixture.py --conversations 100 --turns 5

Defaults stay small enough for a laptop; pass larger counts for load tests.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure src is importable when run as a script.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rai_gateway.evidence.conversation_projection import ConversationProjectionService
from rai_gateway.evidence.domain import EvidenceEventType, EvidenceSourceType
from rai_gateway.evidence.service import TrajectoryService
from rai_gateway.identity.service import RuntimeIdentityService
from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.service import RegistryService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversations", type=int, default=20)
    parser.add_argument(
        "--turns", type=int, default=3, help="Trajectories per conversation"
    )
    return parser.parse_args()


def _ensure_stack(db, suffix: str) -> dict:
    registry = RegistryService(db)
    system = registry.create_ai_system(
        system_key=f"scale-sys-{suffix}",
        name=f"Scale System {suffix}",
        created_by="scale-fixture",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(
            system.id, status.value, updated_by="scale-fixture"
        )
    agent = registry.create_agent(
        system.id,
        agent_key=f"scale-agent-{suffix}",
        name=f"Scale Agent {suffix}",
        created_by="scale-fixture",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="scale-fixture")
    version = registry.create_agent_version(agent.id, created_by="scale-fixture")
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(
            version.id, status.value, updated_by="scale-fixture"
        )
    identity = RuntimeIdentityService(db).create_runtime_identity(
        agent_id=agent.id,
        agent_version_id=version.id,
        name=f"scale-rt-{suffix}",
        created_by="scale-fixture",
    )
    return {
        "system": system,
        "agent": agent,
        "version": version,
        "identity": identity,
    }


def main() -> int:
    args = _parse_args()
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://rai_user:rai_password@localhost:5434/rai_gateway",
    )
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    stack = _ensure_stack(db, uuid.uuid4().hex[:8])
    svc = TrajectoryService(db)
    conversations = ConversationProjectionService(db)
    base = datetime.now(timezone.utc) - timedelta(days=1)

    created_traj = 0
    for c_idx in range(args.conversations):
        conversation_id = f"scale-conv-{uuid.uuid4().hex[:12]}"
        for t_idx in range(args.turns):
            started = base + timedelta(seconds=c_idx * 10 + t_idx)
            trajectory = svc.get_or_create_trajectory(
                ai_system_id=stack["system"].id,
                agent_id=stack["agent"].id,
                agent_version_id=stack["version"].id,
                runtime_identity_id=stack["identity"].id,
                conversation_id=conversation_id,
                client_session_id=f"{conversation_id}-turn-{t_idx}",
                correlation_id=f"corr-{conversation_id}-{t_idx}",
                started_at=started,
            )
            svc.append_event(
                trajectory,
                event_type=EvidenceEventType.PROMPT_OBSERVED.value,
                source_type=EvidenceSourceType.CLIENT_OBSERVED.value,
                source_reference=f"prompt:{conversation_id}:{t_idx}",
                payload={"prompt": f"fixture prompt {c_idx}/{t_idx}", "model": "demo"},
                content_handling_mode="METADATA_ONLY",
                occurred_at=started,
            )
            svc.append_event(
                trajectory,
                event_type=EvidenceEventType.SESSION_COMPLETED.value,
                source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
                source_reference=f"done:{conversation_id}:{t_idx}",
                payload={"status": "COMPLETED"},
                occurred_at=started + timedelta(seconds=1),
            )
            conversations.project_trajectory(trajectory)
            created_traj += 1
        if (c_idx + 1) % 10 == 0:
            db.commit()
            print(f"… {c_idx + 1}/{args.conversations} conversations")

    db.commit()
    print(
        f"Seeded conversations={args.conversations} "
        f"trajectories={created_traj} turns_per_conversation={args.turns}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
