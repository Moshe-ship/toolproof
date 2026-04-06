"""Tests for HTML report generation."""

import tempfile
from pathlib import Path

from toolproof.receipt import Receipt, ReceiptStore
from toolproof.html_report import generate_html_report
from toolproof.trust import TrustReport
from toolproof.verifier import Verdict, VerificationResult


def _make_store(receipts: list[Receipt]) -> ReceiptStore:
    tmpdir = tempfile.mkdtemp()
    store = ReceiptStore(Path(tmpdir) / "test.jsonl")
    for r in receipts:
        r.sign()
        store.add(r)
    return store


def test_html_report_basic():
    store = _make_store([
        Receipt(tool_name="search", arguments={"q": "test"}, response="ok", duration_ms=142),
        Receipt(tool_name="write", arguments={"f": "a"}, response="ok", duration_ms=50),
    ])
    html = generate_html_report(store)

    assert "<!DOCTYPE html>" in html
    assert "ToolProof" in html
    assert "search" in html
    assert "write" in html
    assert "2 receipts" in html


def test_html_report_with_verification():
    store = _make_store([
        Receipt(tool_name="search", arguments={"q": "test"}, response="ok"),
    ])

    results = [
        VerificationResult(
            claim_tool="search",
            claim_arguments={"q": "test"},
            claim_response="ok",
            verdict=Verdict.VERIFIED,
            details="exact match",
        ),
        VerificationResult(
            claim_tool="delete",
            claim_arguments={"id": 1},
            claim_response=None,
            verdict=Verdict.UNVERIFIED,
            details="no receipt found",
        ),
    ]
    report = TrustReport(results=results)
    html = generate_html_report(store, report=report)

    assert "VERIFIED" in html
    assert "UNVERIFIED" in html
    assert "50.0%" in html  # Trust score


def test_html_report_empty_store():
    store = _make_store([])
    html = generate_html_report(store)
    assert "<!DOCTYPE html>" in html
    assert "0 receipts" in html


def test_html_report_dark_theme():
    """Verify the report uses dark theme (black background)."""
    store = _make_store([Receipt(tool_name="x", arguments={}, response="ok")])
    html = generate_html_report(store)
    assert "#0a0a0a" in html  # Dark background
    assert "#e5e5e5" in html  # Light text
