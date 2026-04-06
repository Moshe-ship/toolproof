"""Cross-reference agent claims against execution receipts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from toolproof.receipt import Receipt, ReceiptStore


class Verdict(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    TAMPERED = "tampered"


@dataclass
class VerificationResult:
    """Result of verifying a single agent claim."""

    claim_tool: str
    claim_arguments: dict
    claim_response: Any
    verdict: Verdict
    matching_receipt: Optional[Receipt] = None
    details: str = ""

    def to_dict(self) -> dict:
        return {
            "claim_tool": self.claim_tool,
            "claim_arguments": self.claim_arguments,
            "claim_response": self.claim_response,
            "verdict": self.verdict.value,
            "matching_receipt_id": self.matching_receipt.id if self.matching_receipt else None,
            "details": self.details,
        }


@dataclass
class AgentClaim:
    """A claim an agent makes about a tool call it performed."""

    tool_name: str
    arguments: dict = field(default_factory=dict)
    response: Any = None

    @classmethod
    def from_dict(cls, data: dict) -> AgentClaim:
        return cls(
            tool_name=data.get("tool_name", data.get("name", "")),
            arguments=data.get("arguments", data.get("args", {})),
            response=data.get("response", data.get("result", data.get("output", None))),
        )


def _normalize(value: Any) -> str:
    """Normalize a value for comparison."""
    if isinstance(value, str):
        return value.strip().lower()
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _args_match(claimed: dict, actual: dict, threshold: float = 0.8) -> tuple[bool, float]:
    """Check if claimed arguments match actual arguments.

    Returns (match, similarity_score).
    """
    if not claimed and not actual:
        return True, 1.0

    all_keys = set(list(claimed.keys()) + list(actual.keys()))
    if not all_keys:
        return True, 1.0

    matches = 0
    for key in all_keys:
        c_val = _normalize(claimed.get(key))
        a_val = _normalize(actual.get(key))
        if c_val == a_val:
            matches += 1

    score = matches / len(all_keys)
    return score >= threshold, score


def _response_match(claimed: Any, actual: Any) -> tuple[bool, str]:
    """Check if claimed response matches actual response."""
    if claimed is None:
        return True, "no response claimed"

    c_norm = _normalize(claimed)
    a_norm = _normalize(actual)

    if c_norm == a_norm:
        return True, "exact match"

    # Check structural match for complex nested structures only
    # Flat dicts with scalar values must match exactly — schema match is too lenient
    if isinstance(claimed, dict) and isinstance(actual, dict):
        if set(claimed.keys()) == set(actual.keys()):
            has_nested = any(
                isinstance(v, (dict, list)) for v in claimed.values()
            ) or any(
                isinstance(v, (dict, list)) for v in actual.values()
            )
            if has_nested:
                return True, "schema match (keys identical, nested structure)"

    if isinstance(claimed, list) and isinstance(actual, list):
        if len(claimed) == len(actual) and len(claimed) > 3:
            return True, "schema match (same length list)"

    return False, "mismatch"


class Verifier:
    """Verify agent claims against receipt store."""

    def __init__(self, store: ReceiptStore, secret: Optional[str] = None):
        self.store = store
        self.secret = secret

    def verify_claim(self, claim: AgentClaim) -> VerificationResult:
        """Verify a single agent claim against receipts."""
        candidates = self.store.find_by_tool(claim.tool_name)

        if not candidates:
            return VerificationResult(
                claim_tool=claim.tool_name,
                claim_arguments=claim.arguments,
                claim_response=claim.response,
                verdict=Verdict.UNVERIFIED,
                details=f"no receipts found for tool '{claim.tool_name}'",
            )

        # Find best matching receipt
        best_receipt = None
        best_score = -1.0

        for receipt in candidates:
            # Check receipt integrity first
            if self.secret and not receipt.verify_integrity(self.secret):
                continue

            args_ok, args_score = _args_match(claim.arguments, receipt.arguments)
            if args_score > best_score:
                best_score = args_score
                best_receipt = receipt

        if best_receipt is None:
            return VerificationResult(
                claim_tool=claim.tool_name,
                claim_arguments=claim.arguments,
                claim_response=claim.response,
                verdict=Verdict.UNVERIFIED,
                details="receipts exist but all failed integrity check",
            )

        # Check argument match
        args_ok, args_score = _args_match(claim.arguments, best_receipt.arguments)
        if not args_ok:
            return VerificationResult(
                claim_tool=claim.tool_name,
                claim_arguments=claim.arguments,
                claim_response=claim.response,
                verdict=Verdict.TAMPERED,
                matching_receipt=best_receipt,
                details=f"arguments differ (similarity: {args_score:.1%})",
            )

        # Check response match if claimed
        if claim.response is not None:
            resp_ok, resp_detail = _response_match(claim.response, best_receipt.response)
            if not resp_ok:
                return VerificationResult(
                    claim_tool=claim.tool_name,
                    claim_arguments=claim.arguments,
                    claim_response=claim.response,
                    verdict=Verdict.TAMPERED,
                    matching_receipt=best_receipt,
                    details=f"response {resp_detail}",
                )

        return VerificationResult(
            claim_tool=claim.tool_name,
            claim_arguments=claim.arguments,
            claim_response=claim.response,
            verdict=Verdict.VERIFIED,
            matching_receipt=best_receipt,
            details="claim matches receipt",
        )

    def verify_claims(self, claims: list[AgentClaim]) -> list[VerificationResult]:
        """Verify multiple claims."""
        return [self.verify_claim(c) for c in claims]

    def verify_text(self, text: str) -> list[VerificationResult]:
        """Extract and verify tool call claims from agent text output.

        Looks for patterns like:
        - "I called search_database with query='users'"
        - "The search returned 5 results"
        - JSON tool_use blocks
        """
        claims = []
        claims.extend(self._extract_json_claims(text))
        claims.extend(self._extract_natural_claims(text))

        if not claims:
            return []

        return self.verify_claims(claims)

    def _extract_json_claims(self, text: str) -> list[AgentClaim]:
        """Extract claims from JSON blocks in text."""
        claims = []
        # Match JSON objects that look like tool calls
        json_pattern = r'\{[^{}]*"(?:tool_name|name|function)"[^{}]*\}'
        for match in re.finditer(json_pattern, text):
            try:
                data = json.loads(match.group())
                claims.append(AgentClaim.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue
        return claims

    def _extract_natural_claims(self, text: str) -> list[AgentClaim]:
        """Extract claims from natural language.

        Matches patterns like:
        - "I called <tool> with <args>"
        - "I used <tool> to"
        - "I ran <tool>"
        """
        claims = []
        receipts_tools = {r.tool_name for r in self.store.all()}

        patterns = [
            r"(?:called|used|ran|executed|invoked)\s+(\w+)",
            r"(?:search|query|fetch|get|read|write|delete|update|create)_(\w+)",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                tool_name = match.group(1) if "(" not in pattern else match.group(0)
                # Only create claim if we have receipts for this tool
                full_name = match.group(0).split()[-1] if " " in match.group(0) else match.group(0)
                for known_tool in receipts_tools:
                    if known_tool in text:
                        claims.append(AgentClaim(tool_name=known_tool))
                        break

        # Deduplicate
        seen = set()
        unique = []
        for c in claims:
            key = c.tool_name
            if key not in seen:
                seen.add(key)
                unique.append(c)

        return unique
