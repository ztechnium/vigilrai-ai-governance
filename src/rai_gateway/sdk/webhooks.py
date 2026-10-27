"""Signed outbound webhooks with retry + delivery log."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from rai_gateway.core.config import settings
from rai_gateway.models.productization import WebhookDelivery, WebhookEndpoint
from rai_gateway.sdk.auth import hash_webhook_secret
from rai_gateway.sdk.domain import SdkErrorCode, WebhookDeliveryStatus
from rai_gateway.sdk.errors import SdkError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sign_webhook_payload(secret: str, *, timestamp: str, body: bytes) -> str:
    """HMAC-SHA256 over `{timestamp}.{body}`."""
    message = timestamp.encode("utf-8") + b"." + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_webhook_signature(
    secret: str,
    *,
    timestamp: str,
    body: bytes,
    signature: str,
    max_skew_seconds: int = 300,
) -> bool:
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(int(time.time()) - ts) > max_skew_seconds:
        return False
    expected = sign_webhook_payload(secret, timestamp=timestamp, body=body)
    provided = signature.removeprefix("v1=")
    return hmac.compare_digest(expected, provided)


def _fernet():
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(settings.evidence_encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_webhook_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_webhook_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def validate_webhook_url(url: str) -> None:
    """Reject non-HTTPS (unless allowed) and private / link-local SSRF targets."""
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    host = parsed.hostname
    if not host:
        raise SdkError(SdkErrorCode.INVALID_REQUEST, "Webhook URL host is required")
    if scheme == "http":
        if not settings.webhook_allow_http and settings.environment == "production":
            raise SdkError(
                SdkErrorCode.INVALID_REQUEST,
                "Webhook endpoints must use HTTPS in production",
            )
        if not settings.webhook_allow_http and not settings.webhook_allow_private_hosts:
            raise SdkError(
                SdkErrorCode.INVALID_REQUEST,
                "HTTP webhook endpoints are disabled",
            )
    elif scheme != "https":
        raise SdkError(SdkErrorCode.INVALID_REQUEST, "Webhook URL must be http(s)")

    if settings.webhook_allow_private_hosts:
        return

    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SdkError(
            SdkErrorCode.INVALID_REQUEST, f"Webhook host cannot be resolved: {host}"
        ) from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            raise SdkError(
                SdkErrorCode.INVALID_REQUEST,
                "Webhook URL resolves to a private or link-local address",
            )


class WebhookService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create_endpoint(
        self,
        *,
        name: str,
        url: str,
        event_types: list[str],
        created_by: str,
    ) -> tuple[dict[str, Any], str]:
        validate_webhook_url(url)
        plaintext = f"whsec_{secrets.token_urlsafe(32)}"
        endpoint = WebhookEndpoint(
            name=name,
            url=url,
            secret_hash=hash_webhook_secret(plaintext),
            secret_prefix=plaintext[:12],
            secret_ciphertext=encrypt_webhook_secret(plaintext),
            event_types=event_types,
            enabled=True,
            status="ACTIVE",
            created_by=created_by,
        )
        self._db.add(endpoint)
        self._db.flush()
        return self._serialize(endpoint), plaintext

    def rotate_secret(self, endpoint_id: UUID) -> tuple[dict[str, Any], str]:
        endpoint = self._get_endpoint(endpoint_id)
        plaintext = f"whsec_{secrets.token_urlsafe(32)}"
        endpoint.secret_hash = hash_webhook_secret(plaintext)
        endpoint.secret_prefix = plaintext[:12]
        endpoint.secret_ciphertext = encrypt_webhook_secret(plaintext)
        endpoint.last_rotated_at = _utcnow()
        self._db.flush()
        return self._serialize(endpoint), plaintext

    def enqueue(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        event_id: str | None = None,
    ) -> list[UUID]:
        endpoints = (
            self._db.query(WebhookEndpoint)
            .filter(
                WebhookEndpoint.enabled.is_(True),
                WebhookEndpoint.status == "ACTIVE",
            )
            .all()
        )
        delivery_ids: list[UUID] = []
        eid = event_id or str(uuid4())
        for endpoint in endpoints:
            types = endpoint.event_types or []
            if (
                event_type not in types
                and "*" not in types
                and not self._legacy_decided_match(event_type, types)
            ):
                continue
            delivery = WebhookDelivery(
                endpoint_id=endpoint.id,
                event_type=event_type,
                event_id=eid,
                payload=payload,
                status=WebhookDeliveryStatus.PENDING.value,
                attempt_count=0,
                next_attempt_at=_utcnow(),
            )
            self._db.add(delivery)
            self._db.flush()
            delivery_ids.append(delivery.id)
        return delivery_ids

    @staticmethod
    def _legacy_decided_match(event_type: str, types: list[str]) -> bool:
        if "approval.decided" not in types:
            return False
        return event_type in {
            "approval.approved",
            "approval.rejected",
            "approval.cancelled",
        }

    def process_pending(self, *, limit: int = 50) -> int:
        """Attempt delivery for pending webhooks (inline worker)."""
        now = _utcnow()
        rows = (
            self._db.query(WebhookDelivery)
            .filter(
                WebhookDelivery.status == WebhookDeliveryStatus.PENDING.value,
                (WebhookDelivery.next_attempt_at.is_(None))
                | (WebhookDelivery.next_attempt_at <= now),
            )
            .order_by(WebhookDelivery.created_at.asc())
            .limit(limit)
            .all()
        )
        processed = 0
        for row in rows:
            self._attempt_delivery(row)
            processed += 1
        return processed

    def _signing_secret(self, endpoint: WebhookEndpoint) -> str:
        if endpoint.secret_ciphertext:
            try:
                return decrypt_webhook_secret(endpoint.secret_ciphertext)
            except Exception:  # noqa: BLE001
                pass
        # Legacy rows without ciphertext: prefix is not the full secret.
        return endpoint.secret_prefix

    def _attempt_delivery(self, row: WebhookDelivery) -> None:
        import httpx

        endpoint = (
            self._db.query(WebhookEndpoint)
            .filter(WebhookEndpoint.id == row.endpoint_id)
            .first()
        )
        if not endpoint or not endpoint.enabled:
            row.status = WebhookDeliveryStatus.DEAD_LETTER.value
            row.last_error = "Endpoint missing or disabled"
            return

        try:
            validate_webhook_url(endpoint.url)
        except SdkError as exc:
            row.status = WebhookDeliveryStatus.DEAD_LETTER.value
            row.last_error = exc.message
            return

        body = json.dumps(
            {
                "id": row.event_id,
                "type": row.event_type,
                "created_at": _utcnow().isoformat(),
                "data": row.payload,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        timestamp = str(int(time.time()))
        secret = self._signing_secret(endpoint)
        signature = sign_webhook_payload(secret, timestamp=timestamp, body=body)
        headers = {
            "Content-Type": "application/json",
            "X-RAI-Event-Id": row.event_id,
            "X-RAI-Event-Type": row.event_type,
            "X-RAI-Timestamp": timestamp,
            "X-RAI-Signature": f"v1={signature}",
            # Back-compat aliases
            "X-RAI-Webhook-Id": row.event_id,
            "X-RAI-Webhook-Timestamp": timestamp,
            "X-RAI-Webhook-Signature": f"v1={signature}",
        }
        row.attempt_count = (row.attempt_count or 0) + 1
        try:
            with httpx.Client(timeout=10.0, follow_redirects=False) as client:
                resp = client.post(endpoint.url, content=body, headers=headers)
            if 200 <= resp.status_code < 300:
                row.status = WebhookDeliveryStatus.DELIVERED.value
                row.delivered_at = _utcnow()
                row.last_error = None
            else:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:  # noqa: BLE001 — record and retry
            row.last_error = str(exc)[:1000]
            if row.attempt_count >= 8:
                row.status = WebhookDeliveryStatus.DEAD_LETTER.value
            else:
                row.status = WebhookDeliveryStatus.PENDING.value
                # immediate, 1m, 5m, 15m, 1h, 6h, 24h-ish schedule
                delays = [0, 60, 300, 900, 3600, 21600, 86400]
                idx = min(row.attempt_count - 1, len(delays) - 1)
                row.next_attempt_at = _utcnow() + timedelta(seconds=delays[idx])
        self._db.flush()

    def _get_endpoint(self, endpoint_id: UUID) -> WebhookEndpoint:
        endpoint = (
            self._db.query(WebhookEndpoint)
            .filter(WebhookEndpoint.id == endpoint_id)
            .first()
        )
        if not endpoint:
            raise SdkError(SdkErrorCode.INVALID_REQUEST, "Webhook endpoint not found")
        return endpoint

    def list_endpoints(self) -> list[dict[str, Any]]:
        rows = (
            self._db.query(WebhookEndpoint)
            .order_by(WebhookEndpoint.created_at.desc())
            .all()
        )
        return [self._serialize(r) for r in rows]

    def list_deliveries(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = (
            self._db.query(WebhookDelivery)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": str(r.id),
                "endpoint_id": str(r.endpoint_id),
                "event_type": r.event_type,
                "event_id": r.event_id,
                "status": r.status,
                "attempt_count": r.attempt_count,
                "last_error": r.last_error,
                "delivered_at": r.delivered_at.isoformat() if r.delivered_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def _serialize(self, endpoint: WebhookEndpoint) -> dict[str, Any]:
        return {
            "id": str(endpoint.id),
            "name": endpoint.name,
            "url": endpoint.url,
            "secret_prefix": endpoint.secret_prefix,
            "event_types": endpoint.event_types,
            "enabled": endpoint.enabled,
            "status": endpoint.status,
            "created_by": endpoint.created_by,
            "created_at": endpoint.created_at.isoformat()
            if endpoint.created_at
            else None,
            "last_rotated_at": endpoint.last_rotated_at.isoformat()
            if endpoint.last_rotated_at
            else None,
        }
