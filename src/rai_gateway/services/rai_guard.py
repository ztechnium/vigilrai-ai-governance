"""RAI Guard Service - Responsible AI policy enforcement."""

import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from rai_gateway.core.config import settings
from rai_gateway.core.observability import log_guard_decision, logger


class GuardDecision(str, Enum):
    """Possible RAI Guard decisions."""

    ALLOW = "allow"
    BLOCK = "block"
    REDACT = "redact"
    FLAG = "flag"
    UNCERTAIN = "uncertain"


class GuardResult(BaseModel):
    """Result from RAI Guard evaluation."""

    decision: GuardDecision
    reason_codes: List[str] = []
    rule_ids: List[str] = []
    redactions: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = {}


class RaiDetector:
    """Base class for RAI detectors."""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config

    async def detect(self, text: str, context: Dict[str, Any] = None) -> GuardResult:
        """Detect policy violations in text."""
        raise NotImplementedError


class PIIDetector(RaiDetector):
    """Detect personally identifiable information."""

    # Basic PII patterns - in production, use specialized libraries
    PII_PATTERNS = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "credit_card": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
    }

    async def detect(self, text: str, context: Dict[str, Any] = None) -> GuardResult:
        """Detect PII in text."""
        detected_types = []

        for pii_type, pattern in self.PII_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                detected_types.append(pii_type)

        if detected_types:
            return GuardResult(
                decision=GuardDecision.BLOCK,
                reason_codes=[f"pii_{pii_type}" for pii_type in detected_types],
                rule_ids=["pii_detection"],
                metadata={"detected_pii_types": detected_types},
            )

        return GuardResult(decision=GuardDecision.ALLOW)


class SecurityDetector(RaiDetector):
    """Detect security threats like prompt injection."""

    INJECTION_PATTERNS = [
        r"ignore\s+previous\s+instructions",
        r"forget\s+everything\s+above",
        r"you\s+are\s+now\s+a\s+different",
        r"system\s*:\s*[^.]*override",
        r"jailbreak",
        r"act\s+as\s+if\s+you\s+are",
    ]

    async def detect(self, text: str, context: Dict[str, Any] = None) -> GuardResult:
        """Detect prompt injection attempts."""
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return GuardResult(
                    decision=GuardDecision.BLOCK,
                    reason_codes=["prompt_injection"],
                    rule_ids=["security_injection"],
                    metadata={"matched_pattern": pattern},
                )

        return GuardResult(decision=GuardDecision.ALLOW)


class SafetyDetector(RaiDetector):
    """Detect safety concerns like violence or self-harm."""

    SAFETY_KEYWORDS = [
        "suicide",
        "self-harm",
        "violence",
        "murder",
        "terrorism",
        "bomb",
        "weapon",
        "drug manufacturing",
        "illegal activities",
    ]

    async def detect(self, text: str, context: Dict[str, Any] = None) -> GuardResult:
        """Detect safety violations."""
        text_lower = text.lower()
        triggered_keywords = [kw for kw in self.SAFETY_KEYWORDS if kw in text_lower]

        if triggered_keywords:
            return GuardResult(
                decision=GuardDecision.BLOCK,
                reason_codes=["safety_violation"],
                rule_ids=["safety_content"],
                metadata={"triggered_keywords": triggered_keywords},
            )

        return GuardResult(decision=GuardDecision.ALLOW)


class EthicsDetector(RaiDetector):
    """Detect ethical concerns like bias or stereotypes."""

    BIAS_PATTERNS = [
        r"all\s+(men|women|blacks|whites|muslims|christians|jews)\s+are",
        r"(men|women|blacks|whites)\s+can't",
        r"typical\s+(man|woman|black|white|muslim|christian)",
    ]

    async def detect(self, text: str, context: Dict[str, Any] = None) -> GuardResult:
        """Detect bias and stereotypes."""
        for pattern in self.BIAS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return GuardResult(
                    decision=GuardDecision.FLAG,  # Flag for review rather than block
                    reason_codes=["potential_bias"],
                    rule_ids=["ethics_bias"],
                    metadata={"matched_pattern": pattern},
                )

        return GuardResult(decision=GuardDecision.ALLOW)


class DefamationDetector(RaiDetector):
    """Detect potentially defamatory or unsupported accusatory statements."""

    DEFAMATION_PATTERNS = [
        r"committed\s+fraud",
        r"is\s+a\s+fraudster",
        r"embezzled",
        r"money\s+launder",
        r"criminal\s+record",
        r"stole\s+from",
    ]

    async def detect(self, text: str, context: Dict[str, Any] = None) -> GuardResult:
        for pattern in self.DEFAMATION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return GuardResult(
                    decision=GuardDecision.FLAG,
                    reason_codes=["defamation_claim"],
                    rule_ids=["defamation_risk"],
                    metadata={"matched_pattern": pattern},
                )

        return GuardResult(decision=GuardDecision.ALLOW)


class RaiGuardService:
    """RAI Guard Service - Central policy enforcement."""

    def __init__(self):
        self.detectors = self._initialize_detectors()

    def _initialize_detectors(self) -> List[RaiDetector]:
        """Initialize available detectors based on configuration."""
        detectors = [
            PIIDetector("pii", {}),
            SecurityDetector("security", {}),
            SafetyDetector("safety", {}),
        ]

        # Add ethics detector if enabled
        if settings.enable_ethics_eval:
            detectors.append(EthicsDetector("ethics", {}))
            detectors.append(DefamationDetector("defamation", {}))

        return detectors

    async def precheck(
        self, prompt_config: Dict[str, Any], input_vars: Dict[str, Any], trace_id: str
    ) -> GuardResult:
        """
        Precheck input before LLM generation.

        Evaluates input variables and rendered prompt against policies.
        """
        # Combine all input text for evaluation
        input_text = " ".join([str(v) for v in input_vars.values()])

        # Add rendered prompt template (simplified for demo)
        template = prompt_config.get("template", "")

        combined_text = f"{template} {input_text}"

        # Run all detectors
        all_results = []
        for detector in self.detectors:
            try:
                result = await detector.detect(combined_text, {"type": "input"})
                all_results.append(result)
            except Exception as e:
                logger.error(
                    "detector_error",
                    detector=detector.name,
                    error=str(e),
                    trace_id=trace_id,
                )
                # Fail-closed: treat detector errors as uncertain
                all_results.append(
                    GuardResult(
                        decision=GuardDecision.UNCERTAIN,
                        reason_codes=["detector_error"],
                        rule_ids=[f"error_{detector.name}"],
                    )
                )

        # Aggregate results (most restrictive decision wins)
        final_decision = self._aggregate_decisions(all_results)

        log_guard_decision(
            trace_id=trace_id,
            guard_type="precheck",
            decision=final_decision.decision,
            rule_ids=final_decision.rule_ids,
            reason_codes=final_decision.reason_codes,
        )

        return final_decision

    async def postcheck(
        self, output: str, prompt_config: Dict[str, Any], trace_id: str
    ) -> GuardResult:
        """
        Postcheck LLM output before returning to client.

        Evaluates generated output against policies.
        """
        # Run all detectors on output
        all_results = []
        for detector in self.detectors:
            try:
                result = await detector.detect(output, {"type": "output"})
                all_results.append(result)
            except Exception as e:
                logger.error(
                    "detector_error",
                    detector=detector.name,
                    error=str(e),
                    trace_id=trace_id,
                )
                # Fail-closed: treat detector errors as uncertain
                all_results.append(
                    GuardResult(
                        decision=GuardDecision.UNCERTAIN,
                        reason_codes=["detector_error"],
                        rule_ids=[f"error_{detector.name}"],
                    )
                )

        # Aggregate results
        final_decision = self._aggregate_decisions(all_results)

        log_guard_decision(
            trace_id=trace_id,
            guard_type="postcheck",
            decision=final_decision.decision,
            rule_ids=final_decision.rule_ids,
            reason_codes=final_decision.reason_codes,
        )

        return final_decision

    def _aggregate_decisions(self, results: List[GuardResult]) -> GuardResult:
        """
        Aggregate multiple detector results into final decision.

        Decision priority: BLOCK > UNCERTAIN > FLAG > REDACT > ALLOW
        """
        # Collect all reason codes and rule IDs
        all_reason_codes = []
        all_rule_ids = []
        all_metadata = {}

        # Decision hierarchy (most restrictive first)
        decision_priority = [
            GuardDecision.BLOCK,
            GuardDecision.UNCERTAIN,
            GuardDecision.FLAG,
            GuardDecision.REDACT,
            GuardDecision.ALLOW,
        ]

        final_decision = GuardDecision.ALLOW

        for result in results:
            all_reason_codes.extend(result.reason_codes)
            all_rule_ids.extend(result.rule_ids)
            all_metadata.update(result.metadata)

            # Update final decision if this one is more restrictive
            if decision_priority.index(result.decision) < decision_priority.index(
                final_decision
            ):
                final_decision = result.decision

        return GuardResult(
            decision=final_decision,
            reason_codes=list(set(all_reason_codes)),  # Deduplicate
            rule_ids=list(set(all_rule_ids)),
            metadata=all_metadata,
        )
