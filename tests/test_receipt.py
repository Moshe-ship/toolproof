"""Tests for receipt module."""

import json
import tempfile
from pathlib import Path

from toolproof.receipt import Receipt, ReceiptStore


def test_receipt_sign_and_verify():
    r = Receipt(tool_name="search", arguments={"q": "test"}, response={"count": 5})
    r.sign()
    assert r.hash
    assert r.verify_integrity()


def test_receipt_sign_with_secret():
    r = Receipt(tool_name="search", arguments={"q": "test"}, response={"count": 5})
    r.sign(secret="my-key")
    assert r.hash
    assert r.hmac_sig
    assert r.verify_integrity(secret="my-key")


def test_receipt_tamper_detection():
    r = Receipt(tool_name="search", arguments={"q": "test"}, response={"count": 5})
    r.sign()
    r.response = {"count": 999}
    assert not r.verify_integrity()


def test_receipt_hmac_tamper_detection():
    r = Receipt(tool_name="search", arguments={"q": "test"}, response={"count": 5})
    r.sign(secret="my-key")
    r.response = {"count": 999}
    assert not r.verify_integrity(secret="my-key")


def test_receipt_serialization():
    r = Receipt(tool_name="fetch", arguments={"url": "https://example.com"}, response="ok")
    r.sign()
    data = r.to_dict()
    r2 = Receipt.from_dict(data)
    assert r2.tool_name == "fetch"
    assert r2.hash == r.hash


def test_receipt_store_add_and_find():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ReceiptStore(Path(tmpdir) / "test.jsonl")
        r = Receipt(tool_name="search", arguments={"q": "hello"}, response=[1, 2, 3])
        r.sign()
        store.add(r)

        assert store.count() == 1
        assert store.find_by_tool("search") == [r]
        assert store.find_by_id(r.id) == r
        assert store.find_by_hash(r.hash) == r


def test_receipt_store_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.jsonl"

        store1 = ReceiptStore(path)
        r = Receipt(tool_name="write", arguments={"file": "a.txt"}, response="ok")
        r.sign()
        store1.add(r)

        store2 = ReceiptStore(path)
        assert store2.count() == 1
        loaded = store2.find_by_id(r.id)
        assert loaded is not None
        assert loaded.tool_name == "write"


def test_receipt_store_clear():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ReceiptStore(Path(tmpdir) / "test.jsonl")
        r = Receipt(tool_name="x", arguments={}, response=None)
        r.sign()
        store.add(r)
        assert store.count() == 1
        store.clear()
        assert store.count() == 0
