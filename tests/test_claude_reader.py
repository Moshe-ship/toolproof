"""Tests for Claude Code log reader."""

import json
import tempfile
from pathlib import Path

from toolproof.receipt import ReceiptStore
from toolproof.claude_reader import import_claude_session, _process_claude_message


def _make_session_file(entries: list[dict]) -> Path:
    """Create a temporary JSONL session file."""
    tmpdir = tempfile.mkdtemp()
    path = Path(tmpdir) / "test-session.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def test_import_tool_use_and_result():
    entries = [
        {
            "type": "assistant",
            "timestamp": "2026-04-06T10:00:00Z",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tu_123",
                        "name": "Read",
                        "input": {"file_path": "/tmp/test.py"},
                    }
                ],
            },
        },
        {
            "type": "tool_result",
            "timestamp": "2026-04-06T10:00:01Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tu_123",
                        "content": "print('hello')",
                    }
                ],
            },
        },
    ]

    session_path = _make_session_file(entries)
    tmpdir = tempfile.mkdtemp()
    store = ReceiptStore(Path(tmpdir) / "receipts.jsonl")

    receipts = import_claude_session(session_path, store)

    assert len(receipts) == 1
    assert receipts[0].tool_name == "Read"
    assert receipts[0].arguments == {"file_path": "/tmp/test.py"}
    assert receipts[0].response == "print('hello')"


def test_import_multiple_tools():
    entries = [
        {
            "type": "assistant",
            "timestamp": "2026-04-06T10:00:00Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "tu_1", "name": "Bash", "input": {"command": "ls"}},
                    {"type": "tool_use", "id": "tu_2", "name": "Read", "input": {"file_path": "/a.py"}},
                ],
            },
        },
        {
            "type": "tool_result",
            "timestamp": "2026-04-06T10:00:01Z",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_1", "content": "file1.py\nfile2.py"},
                    {"type": "tool_result", "tool_use_id": "tu_2", "content": "import os"},
                ],
            },
        },
    ]

    session_path = _make_session_file(entries)
    tmpdir = tempfile.mkdtemp()
    store = ReceiptStore(Path(tmpdir) / "receipts.jsonl")

    receipts = import_claude_session(session_path, store)

    assert len(receipts) == 2
    names = {r.tool_name for r in receipts}
    assert "Bash" in names
    assert "Read" in names


def test_import_error_result():
    entries = [
        {
            "type": "assistant",
            "timestamp": "2026-04-06T10:00:00Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "tu_err", "name": "Bash", "input": {"command": "bad_cmd"}},
                ],
            },
        },
        {
            "type": "tool_result",
            "timestamp": "2026-04-06T10:00:01Z",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_err", "content": "command not found", "is_error": True},
                ],
            },
        },
    ]

    session_path = _make_session_file(entries)
    tmpdir = tempfile.mkdtemp()
    store = ReceiptStore(Path(tmpdir) / "receipts.jsonl")

    receipts = import_claude_session(session_path, store)

    assert len(receipts) == 1
    assert receipts[0].error is not None
    assert "command not found" in receipts[0].error


def test_import_no_tool_calls():
    entries = [
        {
            "type": "assistant",
            "timestamp": "2026-04-06T10:00:00Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello!"}],
            },
        },
    ]

    session_path = _make_session_file(entries)
    tmpdir = tempfile.mkdtemp()
    store = ReceiptStore(Path(tmpdir) / "receipts.jsonl")

    receipts = import_claude_session(session_path, store)
    assert len(receipts) == 0


def test_import_signs_receipts():
    entries = [
        {
            "type": "assistant",
            "timestamp": "2026-04-06T10:00:00Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "tu_sig", "name": "Grep", "input": {"pattern": "TODO"}},
                ],
            },
        },
        {
            "type": "tool_result",
            "timestamp": "2026-04-06T10:00:01Z",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_sig", "content": "Found 3 matches"},
                ],
            },
        },
    ]

    session_path = _make_session_file(entries)
    tmpdir = tempfile.mkdtemp()
    store = ReceiptStore(Path(tmpdir) / "receipts.jsonl")

    receipts = import_claude_session(session_path, store, secret="test-key")

    assert len(receipts) == 1
    assert receipts[0].hash
    assert receipts[0].hmac_sig
    assert receipts[0].verify_integrity(secret="test-key")
