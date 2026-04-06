"""Parse Claude Code session logs and extract tool calls as receipts.

Claude Code stores conversation logs in ~/.claude/projects/ as JSONL files.
Each line is a message with tool_use and tool_result blocks.

Also reads Hermes and OpenClaw log formats.

Usage:
    # Import from Claude Code
    toolproof import-claude

    # Import specific session
    toolproof import-claude --session abc123

    # Import from Hermes
    toolproof import-hermes --profile nashir

    # Import from OpenClaw
    toolproof import-openclaw
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from toolproof.receipt import Receipt, ReceiptStore


@dataclass
class ExtractedCall:
    """A tool call extracted from agent logs."""

    tool_name: str
    arguments: dict
    response: Any
    timestamp: float
    duration_ms: float
    source: str  # "claude", "hermes", "openclaw"
    session_id: str = ""
    error: str | None = None


def import_claude_session(
    session_path: Path,
    store: ReceiptStore,
    secret: str | None = None,
) -> list[Receipt]:
    """Import tool calls from a Claude Code session JSONL file.

    Each line is a JSON object representing a message. We look for:
    - Assistant messages with tool_use content blocks
    - Tool result messages that follow them
    """
    receipts = []
    pending_calls: dict[str, dict] = {}  # tool_use_id -> call info

    with open(session_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            _process_claude_message(msg, pending_calls, receipts, store, secret, session_path.stem)

    return receipts


def _process_claude_message(
    msg: dict,
    pending_calls: dict[str, dict],
    receipts: list[Receipt],
    store: ReceiptStore,
    secret: str | None,
    session_id: str,
) -> None:
    """Process a single Claude Code message."""
    message = msg.get("message", msg)
    role = message.get("role", msg.get("type", ""))
    content = message.get("content", [])
    timestamp = msg.get("timestamp", "")

    # Parse timestamp
    ts = 0.0
    if isinstance(timestamp, str) and timestamp:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            ts = dt.timestamp()
        except (ValueError, ImportError):
            ts = time.time()
    elif isinstance(timestamp, (int, float)):
        ts = float(timestamp)

    if not isinstance(content, list):
        return

    for block in content:
        if not isinstance(block, dict):
            continue

        # Tool use (request)
        if block.get("type") == "tool_use":
            tool_id = block.get("id", "")
            pending_calls[tool_id] = {
                "tool_name": block.get("name", "unknown"),
                "arguments": block.get("input", {}),
                "timestamp": ts,
            }

        # Tool result (response)
        elif block.get("type") == "tool_result":
            tool_id = block.get("tool_use_id", "")
            call_info = pending_calls.pop(tool_id, None)
            if call_info is None:
                continue

            # Extract response content
            result_content = block.get("content", "")
            if isinstance(result_content, list):
                texts = [b.get("text", "") for b in result_content if isinstance(b, dict)]
                result_content = "\n".join(texts) if texts else str(result_content)

            error = None
            if block.get("is_error"):
                error = str(result_content)[:500]

            duration_ms = (ts - call_info["timestamp"]) * 1000 if ts > call_info["timestamp"] else 0

            receipt = Receipt(
                tool_name=call_info["tool_name"],
                arguments=call_info["arguments"],
                response=_truncate(result_content),
                error=error,
                timestamp=call_info["timestamp"],
                duration_ms=duration_ms,
            )
            receipt.sign(secret)
            store.add(receipt)
            receipts.append(receipt)


def find_claude_sessions(
    project_dir: str | None = None,
    limit: int = 10,
) -> list[Path]:
    """Find recent Claude Code session files.

    Searches ~/.claude/projects/ for JSONL session files.
    """
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return []

    sessions = []

    if project_dir:
        # Search specific project
        safe_name = project_dir.replace("/", "-").replace("\\", "-")
        project_path = claude_dir / safe_name
        if project_path.exists():
            sessions.extend(project_path.glob("*.jsonl"))
    else:
        # Search all projects
        for proj in claude_dir.iterdir():
            if proj.is_dir():
                sessions.extend(proj.glob("*.jsonl"))

    # Sort by modification time, newest first
    sessions.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return sessions[:limit]


def import_hermes_logs(
    profile: str | None = None,
    store: ReceiptStore | None = None,
    secret: str | None = None,
) -> list[Receipt]:
    """Import tool calls from Hermes agent logs.

    Hermes stores execution logs with tool calls and results.
    Profiles are stored in ~/.hermes/profiles/ or ~/hermes/
    """
    receipts = []

    # Find Hermes log locations
    hermes_dirs = [
        Path.home() / ".hermes" / "logs",
        Path.home() / "hermes" / "logs",
        Path.home() / ".config" / "hermes" / "logs",
    ]

    for hermes_dir in hermes_dirs:
        if not hermes_dir.exists():
            continue

        log_files = sorted(hermes_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)

        for log_file in log_files[:5]:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Hermes log format: {"type": "tool_call", "name": ..., "args": ..., "result": ...}
                    if entry.get("type") in ("tool_call", "skill_execution", "function_call"):
                        tool_name = entry.get("name", entry.get("skill", entry.get("function", "unknown")))
                        if profile and entry.get("profile") != profile:
                            continue

                        receipt = Receipt(
                            tool_name=f"hermes:{tool_name}",
                            arguments=entry.get("args", entry.get("arguments", entry.get("input", {}))),
                            response=_truncate(entry.get("result", entry.get("output", entry.get("response")))),
                            error=entry.get("error"),
                            timestamp=entry.get("timestamp", time.time()),
                            duration_ms=entry.get("duration_ms", entry.get("duration", 0)),
                        )
                        receipt.sign(secret)
                        if store:
                            store.add(receipt)
                        receipts.append(receipt)

    return receipts


def import_openclaw_logs(
    store: ReceiptStore | None = None,
    secret: str | None = None,
) -> list[Receipt]:
    """Import tool calls from OpenClaw skill execution logs.

    OpenClaw stores skill execution history. Mkhlab skills are of
    particular interest for Arabic tool verification.
    """
    receipts = []

    # OpenClaw log locations
    openclaw_dirs = [
        Path.home() / ".openclaw" / "logs",
        Path.home() / ".config" / "openclaw" / "logs",
        Path.home() / "openclaw" / "logs",
    ]

    for oc_dir in openclaw_dirs:
        if not oc_dir.exists():
            continue

        log_files = sorted(oc_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)

        for log_file in log_files[:5]:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if entry.get("type") in ("skill_call", "claw_execute", "tool_use"):
                        skill = entry.get("skill", entry.get("name", entry.get("command", "unknown")))

                        receipt = Receipt(
                            tool_name=f"openclaw:{skill}",
                            arguments=entry.get("args", entry.get("input", {})),
                            response=_truncate(entry.get("result", entry.get("output"))),
                            error=entry.get("error"),
                            timestamp=entry.get("timestamp", time.time()),
                            duration_ms=entry.get("duration_ms", 0),
                        )
                        receipt.sign(secret)
                        if store:
                            store.add(receipt)
                        receipts.append(receipt)

    return receipts


def import_all(
    store: ReceiptStore,
    secret: str | None = None,
    claude_limit: int = 5,
) -> dict[str, int]:
    """Import from all available sources.

    Returns count of receipts imported per source.
    """
    counts = {"claude": 0, "hermes": 0, "openclaw": 0}

    # Claude Code
    sessions = find_claude_sessions(limit=claude_limit)
    for session in sessions:
        receipts = import_claude_session(session, store, secret)
        counts["claude"] += len(receipts)

    # Hermes
    receipts = import_hermes_logs(store=store, secret=secret)
    counts["hermes"] += len(receipts)

    # OpenClaw
    receipts = import_openclaw_logs(store=store, secret=secret)
    counts["openclaw"] += len(receipts)

    return counts


def _truncate(value: Any, max_len: int = 2000) -> Any:
    """Truncate large values for storage."""
    if value is None:
        return None
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + "..."
    if isinstance(value, (dict, list)):
        serialized = json.dumps(value, ensure_ascii=False, default=str)
        if len(serialized) > max_len:
            if isinstance(value, dict):
                return {k: _truncate(v, max_len // max(len(value), 1)) for k, v in value.items()}
            return value[:10]
    return value
