"""Regression: MTG evidence fields must be integrity-protected by evidence_hash.

Prior to 0.5.1, Receipt.sign() only hashed the legacy core (tool/args/response/
error/timestamp), so mtg_violations, outcome, dialect_*, arabic_preserved, and
arg_integrity_score could be tampered with verify_integrity() returning True.
"""

from toolproof.mtg_bridge import receipt_from_mtg_run
from toolproof.receipt import Receipt


def _build_mtg_receipt() -> Receipt:
    guards = {
        "message": {
            "spec": {"script": "ar", "dialect_expected": "gulf"},
            "surface": "أبي أحجز",
            "analysis": {
                "script_detected": "ar",
                "dialect_detected": "gulf",
                "dialect_confidence": 0.91,
            },
            "pre_call_violations": [],
            "post_call_violations": [],
            "mode": "advisory",
        },
    }
    return receipt_from_mtg_run(tool="send_message", guards=guards)


def test_mtg_receipt_has_evidence_hash():
    receipt = _build_mtg_receipt()
    assert receipt.evidence_hash, "evidence_hash should be non-empty for MTG receipts"
    assert receipt.verify_integrity()


def test_legacy_receipt_without_mtg_has_empty_evidence_hash():
    """Pre-MTG receipts stay hash-compatible with 0.4.x."""
    r = Receipt(
        tool_name="t",
        arguments={"x": 1},
        response={"ok": True},
        timestamp=1700000000.0,
    )
    r.sign()
    assert r.evidence_hash == ""
    assert r.verify_integrity()


def test_tampering_outcome_breaks_verify():
    receipt = _build_mtg_receipt()
    assert receipt.verify_integrity()
    receipt.outcome = "pass"  # was fail/partial — tampered
    # If the original was already 'pass' the test is vacuous; assert it isn't
    # (build_mtg_receipt has no violations so outcome='pass' legitimately,
    # so we tamper to something else to make the test real).
    receipt.outcome = "fail"
    assert not receipt.verify_integrity(), (
        "tampering with outcome should break verify_integrity"
    )


def test_tampering_mtg_violations_breaks_verify():
    receipt = _build_mtg_receipt()
    receipt.mtg_violations = [{"code": "INJECTED", "severity": "high", "phase": "pre", "message": "m", "details": {}}]
    assert not receipt.verify_integrity()


def test_tampering_arabic_preserved_breaks_verify():
    receipt = _build_mtg_receipt()
    original = receipt.arabic_preserved
    receipt.arabic_preserved = (not original) if original is not None else True
    assert not receipt.verify_integrity()


def test_tampering_dialect_observed_breaks_verify():
    receipt = _build_mtg_receipt()
    receipt.dialect_observed = "egy"  # was "gulf"
    assert not receipt.verify_integrity()


def test_tampering_arg_integrity_score_breaks_verify():
    receipt = _build_mtg_receipt()
    receipt.arg_integrity_score = 0.0  # was 1.0
    assert not receipt.verify_integrity()


def test_tampering_hash_prev_breaks_verify():
    receipt = _build_mtg_receipt()
    receipt.hash_prev = "a" * 64
    assert not receipt.verify_integrity()


def test_tampering_legacy_fields_still_caught():
    """Regression: the legacy hash protection must still work."""
    receipt = _build_mtg_receipt()
    receipt.tool_name = "different_tool"
    assert not receipt.verify_integrity()


def test_hmac_with_secret_covers_both_regions(monkeypatch):
    receipt = _build_mtg_receipt()
    receipt.sign(secret="shared")
    assert receipt.verify_integrity(secret="shared")

    # Tampering either region fails HMAC verification
    receipt.outcome = "fail"  # MTG-region tamper
    assert not receipt.verify_integrity(secret="shared")


def test_legacy_hash_unchanged_for_04_compat():
    """A receipt with no MTG fields populated produces the same legacy `hash`
    as the 0.4.x implementation did."""
    r = Receipt(
        tool_name="t",
        arguments={"x": 1},
        response={"ok": True},
        error=None,
        timestamp=1700000000.0,
    )
    r.sign()

    # Manually compute what 0.4.x would have produced (legacy payload)
    import hashlib
    import json
    expected = hashlib.sha256(
        json.dumps(
            {"tool_name": "t", "arguments": {"x": 1}, "response": {"ok": True},
             "error": None, "timestamp": 1700000000.0},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert r.hash == expected
