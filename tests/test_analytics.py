"""Tests for analytics and feedback modules."""

import tempfile
from pathlib import Path

from toolproof.receipt import Receipt, ReceiptStore
from toolproof.analytics import Analyzer
from toolproof.feedback import FeedbackGenerator


def _make_store(receipts: list[Receipt]) -> ReceiptStore:
    tmpdir = tempfile.mkdtemp()
    store = ReceiptStore(Path(tmpdir) / "test.jsonl")
    for r in receipts:
        r.sign()
        store.add(r)
    return store


def test_analyzer_basic():
    store = _make_store([
        Receipt(tool_name="search", arguments={"q": "test"}, response="ok", cost_usd=0.01, tokens_in=500, tokens_out=100),
        Receipt(tool_name="search", arguments={"q": "foo"}, response="ok", cost_usd=0.01, tokens_in=500, tokens_out=100),
        Receipt(tool_name="write", arguments={"f": "a"}, response="ok", cost_usd=0.005),
    ])
    analyzer = Analyzer(store)
    report = analyzer.full_report()

    assert report.total_receipts == 3
    assert report.total_errors == 0
    assert report.trust_score == 1.0
    assert len(report.tool_stats) == 2
    assert report.recommendations


def test_analyzer_finds_worst_tools():
    store = _make_store([
        Receipt(tool_name="bad_tool", arguments={}, response=None, error="fail"),
        Receipt(tool_name="bad_tool", arguments={}, response=None, error="fail"),
        Receipt(tool_name="bad_tool", arguments={}, response="ok"),
        Receipt(tool_name="good_tool", arguments={}, response="ok"),
        Receipt(tool_name="good_tool", arguments={}, response="ok"),
        Receipt(tool_name="good_tool", arguments={}, response="ok"),
    ])
    analyzer = Analyzer(store)
    report = analyzer.full_report()

    assert report.worst_tools[0].name == "bad_tool"
    assert report.worst_tools[0].error_rate > 0.5


def test_analyzer_finds_cost_anomalies():
    store = _make_store([
        Receipt(tool_name="api_call", arguments={}, response="ok", cost_usd=0.001),
        Receipt(tool_name="api_call", arguments={}, response="ok", cost_usd=0.001),
        Receipt(tool_name="api_call", arguments={}, response="ok", cost_usd=0.001),
        Receipt(tool_name="api_call", arguments={}, response="ok", cost_usd=0.001),
        Receipt(tool_name="api_call", arguments={}, response="ok", cost_usd=0.001),
        Receipt(tool_name="api_call", arguments={}, response="ok", cost_usd=0.001),
        Receipt(tool_name="api_call", arguments={}, response="ok", cost_usd=0.001),
        Receipt(tool_name="api_call", arguments={}, response="ok", cost_usd=0.001),
        Receipt(tool_name="api_call", arguments={}, response="ok", cost_usd=0.001),
        Receipt(tool_name="api_call", arguments={}, response="ok", cost_usd=5.00, tokens_in=100000, cache_read=0),
    ])
    analyzer = Analyzer(store)
    report = analyzer.full_report()

    assert len(report.cost_anomalies) >= 1
    assert report.cost_anomalies[0].multiplier > 3


def test_analyzer_cache_efficiency():
    store = _make_store([
        Receipt(tool_name="a", arguments={}, response="ok", tokens_in=1000, cache_read=9000),
    ])
    analyzer = Analyzer(store)
    report = analyzer.full_report()

    assert report.cache_efficiency == 0.9  # 9000 / (1000 + 9000)


def test_feedback_generator():
    store = _make_store([
        Receipt(tool_name="good", arguments={}, response="ok"),
        Receipt(tool_name="good", arguments={}, response="ok"),
        Receipt(tool_name="bad", arguments={}, response=None, error="fail"),
        Receipt(tool_name="bad", arguments={}, response=None, error="fail"),
        Receipt(tool_name="bad", arguments={}, response="ok"),
    ])
    analyzer = Analyzer(store)
    report = analyzer.full_report()
    generator = FeedbackGenerator(report)
    feedback = generator.generate()

    assert feedback.trust_score < 1.0
    assert feedback.grade in ("A", "B", "C", "D", "F")
    assert len(feedback.tool_feedback) >= 1

    # Verify JSON serialization works
    json_str = feedback.to_json()
    assert "trust_score" in json_str


def test_feedback_writes_hermes():
    store = _make_store([
        Receipt(tool_name="tool1", arguments={}, response="ok"),
        Receipt(tool_name="tool1", arguments={}, response=None, error="fail"),
    ])
    analyzer = Analyzer(store)
    report = analyzer.full_report()
    generator = FeedbackGenerator(report)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "hermes_feedback.json"
        generator.write_hermes_feedback(path)
        assert path.exists()
        import json
        data = json.loads(path.read_text())
        assert "toolproof_feedback" in data


def test_feedback_writes_openclaw():
    store = _make_store([
        Receipt(tool_name="tool1", arguments={}, response="ok"),
    ])
    analyzer = Analyzer(store)
    report = analyzer.full_report()
    generator = FeedbackGenerator(report)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "openclaw_feedback.json"
        generator.write_openclaw_feedback(path)
        assert path.exists()
        import json
        data = json.loads(path.read_text())
        assert "toolproof" in data


def test_empty_store_report():
    store = _make_store([])
    analyzer = Analyzer(store)
    report = analyzer.full_report()

    assert report.total_receipts == 0
    assert len(report.recommendations) >= 1
