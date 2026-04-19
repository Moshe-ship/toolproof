"""Cross-repo integration smoke: mtg + toolproof + hurmoz.

Exercises the guard_tool -> receipt_from_mtg_run path end-to-end against
the committed Hurmoz dialect-specialized send_message variants. Mirrors
the logic in mtg/scripts/cross_repo_smoke.sh but runs as pytest so the
same invariants gate toolproof's own test matrix.

Skips gracefully if mtg or hurmoz are not importable / locatable — the
test is only meaningful when all three repos are installed (or checked
out as siblings).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

try:
    import mtg
    from mtg.adapters.openai import guard_tool
except ImportError:  # pragma: no cover
    pytest.skip("mtg not installed", allow_module_level=True)

from toolproof.mtg_bridge import receipt_from_mtg_run


def _find_hurmoz_schemas() -> Path | None:
    """Locate the Hurmoz tool-schemas directory.

    Checks $HURMOZ/tool-schemas first, then sibling checkouts.
    """
    if "HURMOZ" in os.environ:
        candidate = Path(os.environ["HURMOZ"]) / "tool-schemas"
        if candidate.is_dir():
            return candidate
    here = Path(__file__).resolve().parent.parent
    for candidate in (
        here.parent / "hurmoz" / "tool-schemas",
        here.parent.parent / "hurmoz" / "tool-schemas",
    ):
        if candidate.is_dir():
            return candidate
    return None


HURMOZ_SCHEMAS = _find_hurmoz_schemas()


def _load_variant(name: str) -> dict:
    assert HURMOZ_SCHEMAS is not None
    return json.loads((HURMOZ_SCHEMAS / name).read_text(encoding="utf-8"))


@pytest.mark.skipif(HURMOZ_SCHEMAS is None, reason="hurmoz checkout not found")
def test_public_schema_accessor_matches_expected_shape():
    schema = mtg.get_schema()
    assert schema["type"] == "object"
    assert "slot_type" in schema["properties"]
    assert "inflected_request_form" in schema["properties"]["slot_type"]["enum"]


@pytest.mark.skipif(HURMOZ_SCHEMAS is None, reason="hurmoz checkout not found")
@pytest.mark.parametrize(
    "variant,expected_outcome",
    [
        ("gulf", "pass"),
        ("egy", "partial"),
        ("lev", "partial"),
        ("msa", "partial"),
    ],
)
def test_dialect_variant_produces_expected_receipt(variant: str, expected_outcome: str):
    """Gulf-content message should pass only the Gulf variant."""
    tool = _load_variant(f"send_message_{variant}.json")
    wrapped = guard_tool(tool)
    gulf_content = "أبي أحجز فندق في دبي"
    report = wrapped.validate_call(
        {"arguments": {"recipient": "أحمد", "platform": "whatsapp", "message": gulf_content}}
    )
    guards = report.to_dict()["per_param"]
    receipt = receipt_from_mtg_run(
        tool=f"send_message_{variant}",
        guards=guards,
        arguments={"message": gulf_content},
    )
    assert receipt.dialect_expected == variant
    assert receipt.outcome == expected_outcome
    assert receipt.verify_integrity() is True


@pytest.mark.skipif(HURMOZ_SCHEMAS is None, reason="hurmoz checkout not found")
def test_evidence_tampering_trips_verify_integrity():
    """Mutating mtg_violations after signing must break verify_integrity."""
    tool = _load_variant("send_message_gulf.json")
    wrapped = guard_tool(tool)
    report = wrapped.validate_call(
        {"arguments": {"recipient": "أحمد", "platform": "whatsapp", "message": "أبي أحجز"}}
    )
    receipt = receipt_from_mtg_run(
        tool="send_message_gulf",
        guards=report.to_dict()["per_param"],
        arguments={"message": "أبي أحجز"},
    )
    assert receipt.verify_integrity()
    # Tamper with evidence fields — verify_integrity must trip.
    receipt.outcome = "fail" if receipt.outcome != "fail" else "pass"
    assert not receipt.verify_integrity()
