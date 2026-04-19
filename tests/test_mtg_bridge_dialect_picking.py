"""Regression: receipt_from_mtg_run must pick dialect_observed from the Arabic
slot with highest dialect_confidence, not the first seen. Also must read
dialect_expected from each guard's nested `spec` dict (review finding #5)."""

from toolproof.mtg_bridge import receipt_from_mtg_run


def test_dialect_observed_picks_arabic_slot_over_english_slot():
    """Real send_message flow — recipient='Ahmed' (latn slot) came first but
    message (ar slot) carries the actual dialect signal. Bridge previously
    picked recipient's dialect_detected ('unknown' or 'msa') as observed."""
    guards = {
        "recipient": {
            "spec": {"script": "mixed", "dialect_expected": "any"},
            "surface": "Ahmed",
            "analysis": {
                "script_detected": "latn",
                "dialect_detected": "msa",
                "dialect_confidence": 0.45,
            },
            "pre_call_violations": [],
            "post_call_violations": [],
            "mode": "advisory",
        },
        "platform": {
            "spec": {"script": "latn", "dialect_expected": "any"},
            "surface": "whatsapp",
            "analysis": {
                "script_detected": "latn",
                "dialect_detected": None,
                "dialect_confidence": 0.0,
            },
            "pre_call_violations": [],
            "post_call_violations": [],
            "mode": "advisory",
        },
        "message": {
            "spec": {"script": "ar", "dialect_expected": "gulf"},
            "surface": "أبي أحجز فندق في دبي",
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
    receipt = receipt_from_mtg_run(tool="send_message", guards=guards)
    # Must pick the Arabic slot's dialect, not recipient's (latn)
    assert receipt.dialect_observed == "gulf"
    # And must read dialect_expected from the message slot's spec
    assert receipt.dialect_expected == "gulf"


def test_dialect_observed_prefers_higher_confidence_arabic_slot():
    """Two Arabic slots: one low-confidence MSA, one high-confidence Gulf.
    Pick the high-confidence one."""
    guards = {
        "arabic_a": {
            "spec": {"script": "ar", "dialect_expected": "any"},
            "surface": "مرحبا",
            "analysis": {
                "script_detected": "ar",
                "dialect_detected": "msa",
                "dialect_confidence": 0.40,
            },
            "pre_call_violations": [],
            "post_call_violations": [],
            "mode": "advisory",
        },
        "arabic_b": {
            "spec": {"script": "ar", "dialect_expected": "gulf"},
            "surface": "أبي أحجز",
            "analysis": {
                "script_detected": "ar",
                "dialect_detected": "gulf",
                "dialect_confidence": 0.95,
            },
            "pre_call_violations": [],
            "post_call_violations": [],
            "mode": "advisory",
        },
    }
    receipt = receipt_from_mtg_run(tool="t", guards=guards)
    assert receipt.dialect_observed == "gulf"
    assert receipt.dialect_expected == "gulf"


def test_no_spec_fallback_to_first_seen():
    """If no specs provided (legacy callers), fall back to first non-unknown."""
    guards = {
        "a": {
            "surface": "hi",
            "analysis": {"dialect_detected": "gulf", "dialect_confidence": 0.8},
            "pre_call_violations": [],
            "post_call_violations": [],
            "mode": "advisory",
        },
    }
    receipt = receipt_from_mtg_run(tool="t", guards=guards)
    assert receipt.dialect_observed == "gulf"
