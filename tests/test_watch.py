"""Tests for watch mode and CI check."""

import tempfile
from pathlib import Path

from toolproof.receipt import Receipt, ReceiptStore
from toolproof.watch import ReceiptWatcher, ci_check


def _make_store(receipts: list[Receipt]) -> ReceiptStore:
    tmpdir = tempfile.mkdtemp()
    store = ReceiptStore(Path(tmpdir) / "test.jsonl")
    for r in receipts:
        r.sign()
        store.add(r)
    return store


def test_watcher_initial_check():
    store = _make_store([
        Receipt(tool_name="search", arguments={"q": "test"}, response="ok"),
        Receipt(tool_name="write", arguments={"f": "a.txt"}, response="ok"),
    ])
    watcher = ReceiptWatcher(store)
    status = watcher.check()

    assert status["total"] == 2
    assert status["new"] == 2
    assert status["tools"] == 2
    assert status["errors"] == 0
    assert status["trust"] == 1.0


def test_watcher_with_errors():
    store = _make_store([
        Receipt(tool_name="ok", arguments={}, response="ok"),
        Receipt(tool_name="bad", arguments={}, response=None, error="failed"),
    ])
    watcher = ReceiptWatcher(store)
    status = watcher.check()

    assert status["total"] == 2
    assert status["errors"] == 1
    assert status["trust"] == 0.5


def test_watcher_threshold():
    store = _make_store([
        Receipt(tool_name="ok", arguments={}, response="ok"),
        Receipt(tool_name="bad", arguments={}, response=None, error="failed"),
    ])
    watcher = ReceiptWatcher(store, min_trust=0.8)
    status = watcher.check()

    assert status["below_threshold"] is True


def test_ci_check_pass():
    store = _make_store([
        Receipt(tool_name="a", arguments={}, response="ok"),
        Receipt(tool_name="b", arguments={}, response="ok"),
    ])
    exit_code = ci_check(store, min_trust=0.8, min_receipts=1)
    assert exit_code == 0


def test_ci_check_fail_trust():
    store = _make_store([
        Receipt(tool_name="ok", arguments={}, response="ok"),
        Receipt(tool_name="err", arguments={}, response=None, error="fail"),
        Receipt(tool_name="err2", arguments={}, response=None, error="fail"),
    ])
    exit_code = ci_check(store, min_trust=0.8, min_receipts=1)
    assert exit_code == 1


def test_ci_check_fail_min_receipts():
    store = _make_store([])
    exit_code = ci_check(store, min_trust=0.5, min_receipts=5)
    assert exit_code == 1


def test_ci_check_empty_store_passes_trust():
    """Empty store has trust 1.0 but fails min_receipts."""
    store = _make_store([])
    exit_code = ci_check(store, min_trust=0.5, min_receipts=0)
    assert exit_code == 0
