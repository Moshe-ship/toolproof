"""MTG (Morphological Type Guards) → ToolProof bridge.

Converts MTG violations and pipeline-run output into ToolProof receipts.
Does NOT hard-depend on the `mtg` package — the bridge accepts plain dicts
that match the MTG receipt shape (see mtg/spec/receipt.schema.json). If
callers happen to have `mtg` imported, the real Violation / GuardResult
dataclasses pass through `to_dict()` transparently.

Severity → outcome mapping:
- high         → fail
- medium       → partial
- low | info   → pass (logged)

Fields populated on the Receipt:
- mtg_violations
- outcome
- hash_prev
- dialect_expected
- dialect_observed
- arabic_preserved
- arg_integrity_score
"""

from __future__ import annotations

import uuid
from typing import Any, Iterable, Optional

from toolproof.receipt import Receipt

SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1, "info": 0}

SEVERITY_TO_OUTCOME = {
    "high": "fail",
    "medium": "partial",
    "low": "pass",
    "info": "pass",
}


def _as_dict(obj: Any) -> dict:
    """Coerce an MTG Violation / GuardResult dataclass or dict to a dict."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    raise TypeError(f"cannot coerce {type(obj).__name__} to dict")


def _worst_severity(violations: Iterable[dict]) -> str:
    worst = "info"
    for v in violations:
        sev = v.get("severity", "info")
        if SEVERITY_ORDER.get(sev, 0) > SEVERITY_ORDER.get(worst, 0):
            worst = sev
    return worst


def _outcome_from_violations(violations: Iterable[dict]) -> str:
    violations = list(violations)
    if not violations:
        return "pass"
    return SEVERITY_TO_OUTCOME[_worst_severity(violations)]


def from_mtg_violation(
    violation: Any,
    tool: str,
    call_id: Optional[str] = None,
    prev_receipt_hash: Optional[str] = None,
    arguments: Optional[dict] = None,
    response: Any = None,
) -> Receipt:
    """Convert a single MTG violation into a ToolProof receipt.

    Minimal path — useful when you only have one violation to record.
    For full-pipeline output, prefer `receipt_from_mtg_run`.
    """
    v = _as_dict(violation)
    outcome = SEVERITY_TO_OUTCOME.get(v.get("severity", "info"), "pass")
    receipt = Receipt(
        id=call_id or str(uuid.uuid4()),
        tool_name=tool,
        arguments=arguments or {},
        response=response,
        source="mtg",
        mtg_violations=[v],
        outcome=outcome,
        hash_prev=prev_receipt_hash,
    )
    receipt.sign()
    return receipt


def receipt_from_mtg_run(
    tool: str,
    guards: dict[str, Any],
    violations: Optional[list[Any]] = None,
    call_id: Optional[str] = None,
    prev_receipt_hash: Optional[str] = None,
    arguments: Optional[dict] = None,
    response: Any = None,
) -> Receipt:
    """Build a ToolProof receipt from a full MTG pipeline run.

    `guards` is a mapping of parameter-name → GuardResult-dict (or a
    GuardResult dataclass with .to_dict()). Each guard result contributes
    its violations, dialect expectations, and morph analysis to the
    receipt's MTG fields.

    If `violations` is provided explicitly, it augments the per-guard
    violations (useful when callers have top-level, non-parameter-scoped
    violations).
    """
    per_param: dict[str, dict] = {k: _as_dict(v) for k, v in guards.items()}
    collected: list[dict] = []
    dialect_expected: Optional[str] = None
    dialect_observed: Optional[str] = None
    arabic_preserved: Optional[bool] = None
    integrity_scores: list[float] = []

    for guard in per_param.values():
        pre = guard.get("pre_call_violations", []) or []
        post = guard.get("post_call_violations", []) or []
        for item in list(pre) + list(post):
            collected.append(_as_dict(item))

        analysis = guard.get("analysis") or {}
        det = analysis.get("dialect_detected")
        if det and dialect_observed is None:
            dialect_observed = det

        # arabic_preserved: any SCRIPT_VIOLATION or SURFACE_CORRUPTION implies False
        codes = {v.get("code") for v in list(pre) + list(post)}
        if codes & {"SCRIPT_VIOLATION", "SURFACE_CORRUPTION_POST_CALL", "TRANSLITERATION_VIOLATION"}:
            arabic_preserved = False
        elif arabic_preserved is None:
            # keep track; set to True only if the slot had any Arabic expectation
            if det or (analysis.get("script_detected") == "ar"):
                arabic_preserved = True

        # arg_integrity_score: 1.0 - (worst_severity_rank / max_rank) per guard
        worst = _worst_severity(list(pre) + list(post))
        score = 1.0 - (SEVERITY_ORDER.get(worst, 0) / 3.0)
        integrity_scores.append(score)

    if violations:
        collected.extend(_as_dict(v) for v in violations)

    # Extract dialect_expected from any guard whose mode was declared —
    # MTG stores it in the spec, not the guard result. Callers that want
    # this field set explicitly should pass it as part of the guard result.
    for guard in per_param.values():
        de = guard.get("dialect_expected") or (guard.get("spec") or {}).get("dialect_expected")
        if de and de != "any":
            dialect_expected = de
            break

    outcome = _outcome_from_violations(collected)
    integrity = min(integrity_scores) if integrity_scores else 1.0

    receipt = Receipt(
        id=call_id or str(uuid.uuid4()),
        tool_name=tool,
        arguments=arguments or {},
        response=response,
        source="mtg",
        mtg_violations=collected,
        outcome=outcome,
        hash_prev=prev_receipt_hash,
        dialect_expected=dialect_expected,
        dialect_observed=dialect_observed,
        arabic_preserved=arabic_preserved,
        arg_integrity_score=round(integrity, 4),
    )
    receipt.sign()
    return receipt


__all__ = [
    "from_mtg_violation",
    "receipt_from_mtg_run",
    "SEVERITY_TO_OUTCOME",
]
