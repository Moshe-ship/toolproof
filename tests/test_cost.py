"""Tests for token cost tracking."""

from toolproof.receipt import Receipt, estimate_cost


def test_estimate_cost_defaults():
    # Sonnet 4.6: $3/M in, $15/M out
    cost = estimate_cost(tokens_in=1000, tokens_out=500)
    assert cost > 0
    expected = (1000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0
    assert abs(cost - expected) < 0.000001


def test_estimate_cost_with_cache():
    cost = estimate_cost(tokens_in=1000, tokens_out=500, cache_read=5000)
    cost_no_cache = estimate_cost(tokens_in=1000, tokens_out=500)
    assert cost > cost_no_cache


def test_estimate_cost_custom_pricing():
    pricing = {"input_per_m": 1.0, "output_per_m": 5.0, "cache_read_per_m": 0.10}
    cost = estimate_cost(tokens_in=1_000_000, tokens_out=1_000_000, pricing=pricing)
    assert cost == 6.0  # $1 in + $5 out


def test_receipt_has_cost_fields():
    r = Receipt(
        tool_name="test",
        arguments={},
        response="ok",
        tokens_in=500,
        tokens_out=100,
        cost_usd=0.0047,
    )
    assert r.tokens_in == 500
    assert r.tokens_out == 100
    assert r.cost_usd == 0.0047


def test_receipt_cost_in_serialization():
    r = Receipt(
        tool_name="test",
        arguments={},
        response="ok",
        tokens_in=1000,
        tokens_out=200,
        cost_usd=0.006,
        source="claude",
        session_id="abc",
    )
    r.sign()
    data = r.to_dict()
    assert data["tokens_in"] == 1000
    assert data["tokens_out"] == 200
    assert data["cost_usd"] == 0.006
    assert data["source"] == "claude"

    r2 = Receipt.from_dict(data)
    assert r2.tokens_in == 1000
    assert r2.cost_usd == 0.006
    assert r2.source == "claude"


def test_zero_tokens_zero_cost():
    cost = estimate_cost(tokens_in=0, tokens_out=0)
    assert cost == 0.0
