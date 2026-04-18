"""Tests for the MTG → ToolProof bridge."""

from toolproof.mtg_bridge import (
    SEVERITY_TO_OUTCOME,
    from_mtg_violation,
    receipt_from_mtg_run,
)
from toolproof.receipt import Receipt


def _v(code: str, severity: str, phase: str = "pre", message: str = "", **details) -> dict:
    return {
        "code": code,
        "severity": severity,
        "phase": phase,
        "message": message or f"{code} test",
        "details": details,
    }


def test_severity_mapping_contract():
    assert SEVERITY_TO_OUTCOME["high"] == "fail"
    assert SEVERITY_TO_OUTCOME["medium"] == "partial"
    assert SEVERITY_TO_OUTCOME["low"] == "pass"
    assert SEVERITY_TO_OUTCOME["info"] == "pass"


def test_from_mtg_violation_high_severity_is_fail():
    violation = _v("SCRIPT_VIOLATION", "high")
    receipt = from_mtg_violation(violation, tool="book_service")
    assert isinstance(receipt, Receipt)
    assert receipt.outcome == "fail"
    assert receipt.tool_name == "book_service"
    assert receipt.mtg_violations == [violation]
    assert receipt.source == "mtg"


def test_from_mtg_violation_medium_is_partial():
    violation = _v("DIALECT_DRIFT", "medium")
    receipt = from_mtg_violation(violation, tool="t")
    assert receipt.outcome == "partial"


def test_from_mtg_violation_low_is_pass():
    violation = _v("MORPH_AMBIGUITY", "low")
    receipt = from_mtg_violation(violation, tool="t")
    assert receipt.outcome == "pass"


def test_from_mtg_violation_info_is_pass():
    violation = _v("BACKEND_DISAGREEMENT", "info")
    receipt = from_mtg_violation(violation, tool="t")
    assert receipt.outcome == "pass"


def test_receipt_from_mtg_run_worst_outcome_wins():
    guards = {
        "param_a": {
            "surface": "أبي أحجز",
            "analysis": {"dialect_detected": "gulf", "script_detected": "ar"},
            "pre_call_violations": [_v("MORPH_AMBIGUITY", "low")],
            "post_call_violations": [],
            "mode": "advisory",
        },
        "param_b": {
            "surface": "book a hotel",
            "analysis": {"dialect_detected": "unknown", "script_detected": "latn"},
            "pre_call_violations": [_v("SCRIPT_VIOLATION", "high")],
            "post_call_violations": [],
            "mode": "advisory",
        },
    }
    receipt = receipt_from_mtg_run(tool="t", guards=guards)
    assert receipt.outcome == "fail"
    assert len(receipt.mtg_violations) == 2
    assert receipt.arabic_preserved is False
    # arg_integrity_score — worst guard is high severity = 1 - 3/3 = 0.0
    assert receipt.arg_integrity_score == 0.0


def test_receipt_from_mtg_run_all_pass():
    guards = {
        "param_a": {
            "surface": "أبي أحجز",
            "analysis": {"dialect_detected": "gulf", "script_detected": "ar"},
            "pre_call_violations": [],
            "post_call_violations": [],
            "mode": "advisory",
        },
    }
    receipt = receipt_from_mtg_run(tool="t", guards=guards)
    assert receipt.outcome == "pass"
    assert receipt.arabic_preserved is True
    assert receipt.dialect_observed == "gulf"
    assert receipt.arg_integrity_score == 1.0


def test_receipt_round_trip_preserves_mtg_fields():
    guards = {
        "p": {
            "surface": "مرحبا",
            "analysis": {"dialect_detected": "msa", "script_detected": "ar"},
            "pre_call_violations": [],
            "post_call_violations": [],
            "mode": "advisory",
        },
    }
    r = receipt_from_mtg_run(tool="t", guards=guards, prev_receipt_hash="abc123")
    d = r.to_dict()
    r2 = Receipt.from_dict(d)
    assert r2.outcome == r.outcome
    assert r2.arabic_preserved == r.arabic_preserved
    assert r2.dialect_observed == r.dialect_observed
    assert r2.arg_integrity_score == r.arg_integrity_score
    assert r2.mtg_violations == r.mtg_violations
    assert r2.hash_prev == "abc123"
    assert r2.source == "mtg"


def test_signature_unaffected_by_mtg_fields():
    """Receipt.sign() hashes tool_name/arguments/response/error/timestamp only.

    Adding MTG fields must not change existing signatures on 0.4.0 receipts.
    """
    receipt_a = Receipt(
        tool_name="t",
        arguments={"x": 1},
        response={"ok": True},
        error=None,
        timestamp=1700000000.0,
    )
    receipt_a.sign()

    receipt_b = Receipt(
        tool_name="t",
        arguments={"x": 1},
        response={"ok": True},
        error=None,
        timestamp=1700000000.0,
        outcome="fail",
        dialect_expected="gulf",
        arabic_preserved=False,
        mtg_violations=[_v("SCRIPT_VIOLATION", "high")],
    )
    receipt_b.sign()

    assert receipt_a.hash == receipt_b.hash, (
        "MTG fields leaked into canonical hash — breaks backward compatibility"
    )


def test_dataclass_instance_violation_coerces_to_dict():
    """Accepts MTG Violation dataclass (has .to_dict()) without hard dep on mtg."""

    class FakeViolation:
        def __init__(self) -> None:
            self.code = "SCRIPT_VIOLATION"
            self.severity = "high"
            self.phase = "pre"
            self.message = "test"
            self.details = {}

        def to_dict(self) -> dict:
            return {
                "code": self.code,
                "severity": self.severity,
                "phase": self.phase,
                "message": self.message,
                "details": self.details,
            }

    receipt = from_mtg_violation(FakeViolation(), tool="t")
    assert receipt.outcome == "fail"
    assert receipt.mtg_violations[0]["code"] == "SCRIPT_VIOLATION"
