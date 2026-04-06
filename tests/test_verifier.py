"""Tests for verifier module."""

import tempfile
from pathlib import Path

from toolproof.receipt import Receipt, ReceiptStore
from toolproof.verifier import Verifier, AgentClaim, Verdict


def _make_store(receipts: list[Receipt]) -> ReceiptStore:
    """Create a temp store with pre-loaded receipts."""
    tmpdir = tempfile.mkdtemp()
    store = ReceiptStore(Path(tmpdir) / "test.jsonl")
    for r in receipts:
        r.sign()
        store.add(r)
    return store


def test_verify_exact_match():
    r = Receipt(tool_name="search", arguments={"q": "users"}, response={"count": 5})
    store = _make_store([r])
    verifier = Verifier(store)

    claim = AgentClaim(tool_name="search", arguments={"q": "users"}, response={"count": 5})
    result = verifier.verify_claim(claim)
    assert result.verdict == Verdict.VERIFIED


def test_verify_no_receipt():
    store = _make_store([])
    verifier = Verifier(store)

    claim = AgentClaim(tool_name="search", arguments={"q": "users"})
    result = verifier.verify_claim(claim)
    assert result.verdict == Verdict.UNVERIFIED


def test_verify_tampered_arguments():
    r = Receipt(tool_name="search", arguments={"q": "users"}, response={"count": 5})
    store = _make_store([r])
    verifier = Verifier(store)

    claim = AgentClaim(
        tool_name="search",
        arguments={"q": "admins", "limit": 100},
        response={"count": 5},
    )
    result = verifier.verify_claim(claim)
    assert result.verdict == Verdict.TAMPERED


def test_verify_tampered_response():
    r = Receipt(tool_name="search", arguments={"q": "users"}, response={"count": 5})
    store = _make_store([r])
    verifier = Verifier(store)

    claim = AgentClaim(
        tool_name="search",
        arguments={"q": "users"},
        response={"count": 500},
    )
    result = verifier.verify_claim(claim)
    assert result.verdict == Verdict.TAMPERED


def test_verify_no_response_claimed():
    r = Receipt(tool_name="delete", arguments={"id": 1}, response="ok")
    store = _make_store([r])
    verifier = Verifier(store)

    claim = AgentClaim(tool_name="delete", arguments={"id": 1})
    result = verifier.verify_claim(claim)
    assert result.verdict == Verdict.VERIFIED


def test_verify_multiple_claims():
    receipts = [
        Receipt(tool_name="search", arguments={"q": "a"}, response=[1]),
        Receipt(tool_name="write", arguments={"file": "b"}, response="ok"),
    ]
    store = _make_store(receipts)
    verifier = Verifier(store)

    claims = [
        AgentClaim(tool_name="search", arguments={"q": "a"}),
        AgentClaim(tool_name="write", arguments={"file": "b"}),
        AgentClaim(tool_name="delete", arguments={"id": 99}),
    ]
    results = verifier.verify_claims(claims)
    assert results[0].verdict == Verdict.VERIFIED
    assert results[1].verdict == Verdict.VERIFIED
    assert results[2].verdict == Verdict.UNVERIFIED


def test_verify_schema_match_nested():
    """Schema match only applies to dicts with nested structures."""
    r = Receipt(
        tool_name="search",
        arguments={"q": "test"},
        response={"results": ["a", "b"], "total": 2},
    )
    store = _make_store([r])
    verifier = Verifier(store)

    claim = AgentClaim(
        tool_name="search",
        arguments={"q": "test"},
        response={"results": ["x", "y"], "total": 5},
    )
    result = verifier.verify_claim(claim)
    # Schema match: same keys, has nested list values
    assert result.verdict == Verdict.VERIFIED


def test_verify_flat_dict_no_schema_match():
    """Flat dicts with only scalar values must match exactly."""
    r = Receipt(
        tool_name="search",
        arguments={"q": "test"},
        response={"count": 5, "status": "ok"},
    )
    store = _make_store([r])
    verifier = Verifier(store)

    claim = AgentClaim(
        tool_name="search",
        arguments={"q": "test"},
        response={"count": 999, "status": "error"},
    )
    result = verifier.verify_claim(claim)
    assert result.verdict == Verdict.TAMPERED


def test_agent_claim_from_dict():
    claim = AgentClaim.from_dict({
        "name": "search",
        "args": {"q": "hello"},
        "result": [1, 2],
    })
    assert claim.tool_name == "search"
    assert claim.arguments == {"q": "hello"}
    assert claim.response == [1, 2]
