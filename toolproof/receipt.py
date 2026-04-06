"""Signed execution receipts for tool calls."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional


def _canonical(obj: Any) -> str:
    """Produce a canonical JSON string for hashing."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# Keys that should be redacted from receipt arguments/responses
_SENSITIVE_KEYS = re.compile(
    r"(secret|password|passwd|token|api.?key|authorization|cookie|credential|private.?key)",
    re.IGNORECASE,
)
_REDACTED = "[REDACTED]"


def redact_sensitive(data: Any) -> Any:
    """Recursively redact sensitive keys from dicts."""
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if _SENSITIVE_KEYS.search(k):
                out[k] = _REDACTED
            else:
                out[k] = redact_sensitive(v)
        return out
    if isinstance(data, list):
        return [redact_sensitive(item) for item in data]
    return data


# Default pricing per million tokens (Claude Sonnet 4.6)
DEFAULT_PRICING = {
    "input_per_m": 3.0,
    "output_per_m": 15.0,
    "cache_read_per_m": 0.30,
}


def estimate_cost(
    tokens_in: int,
    tokens_out: int,
    cache_read: int = 0,
    pricing: Optional[dict] = None,
) -> float:
    """Estimate USD cost from token counts."""
    p = pricing or DEFAULT_PRICING
    cost = (tokens_in / 1_000_000) * p.get("input_per_m", 3.0)
    cost += (tokens_out / 1_000_000) * p.get("output_per_m", 15.0)
    cost += (cache_read / 1_000_000) * p.get("cache_read_per_m", 0.30)
    return cost


@dataclass
class Receipt:
    """A signed proof that a tool was actually called."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    tool_name: str = ""
    arguments: dict = field(default_factory=dict)
    response: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    # Token cost tracking
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    cost_usd: float = 0.0
    # Cryptographic signatures
    hash: str = ""
    hmac_sig: str = ""
    # Source tracking
    source: str = ""  # "openclaw", "claude", "hermes", "proxy", "sdk"
    session_id: str = ""

    def sign(self, secret: Optional[str] = None) -> None:
        """Compute hash and optional HMAC signature."""
        payload = _canonical({
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "response": self.response,
            "error": self.error,
            "timestamp": self.timestamp,
        })
        self.hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if secret:
            self.hmac_sig = hmac.new(
                secret.encode("utf-8"),
                payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

    def verify_integrity(self, secret: Optional[str] = None) -> bool:
        """Check that the receipt has not been tampered with."""
        payload = _canonical({
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "response": self.response,
            "error": self.error,
            "timestamp": self.timestamp,
        })
        expected_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        # SECURITY: use timing-safe comparison to prevent timing oracle attacks
        if not hmac.compare_digest(expected_hash, self.hash):
            return False
        if secret and self.hmac_sig:
            expected_hmac = hmac.new(
                secret.encode("utf-8"),
                payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected_hmac, self.hmac_sig):
                return False
        return True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Receipt:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _secure_path(path: Path) -> None:
    """Set secure permissions on file and parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(str(path.parent), 0o700)
    except OSError:
        pass
    if path.exists():
        try:
            os.chmod(str(path), 0o600)
        except OSError:
            pass


class ReceiptStore:
    """Thread-safe persistent storage for execution receipts."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or Path.home() / ".toolproof" / "receipts.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._receipts: list[Receipt] = []
        self._lock = threading.Lock()
        if self.path.exists():
            self._load()
        _secure_path(self.path)

    def _load(self) -> None:
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    self._receipts.append(Receipt.from_dict(json.loads(line)))
                except (json.JSONDecodeError, TypeError):
                    continue  # Skip malformed lines instead of crashing

    def add(self, receipt: Receipt) -> None:
        with self._lock:
            self._receipts.append(receipt)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(receipt.to_dict(), ensure_ascii=False) + "\n")
            # Ensure file stays private after first write
            try:
                os.chmod(str(self.path), 0o600)
            except OSError:
                pass

    def find_by_tool(self, tool_name: str) -> list[Receipt]:
        with self._lock:
            return [r for r in self._receipts if r.tool_name == tool_name]

    def find_by_id(self, receipt_id: str) -> Optional[Receipt]:
        with self._lock:
            for r in self._receipts:
                if r.id == receipt_id:
                    return r
            return None

    def find_by_hash(self, hash_val: str) -> Optional[Receipt]:
        with self._lock:
            for r in self._receipts:
                if r.hash == hash_val:
                    return r
            return None

    def all(self) -> list[Receipt]:
        with self._lock:
            return list(self._receipts)

    def count(self) -> int:
        with self._lock:
            return len(self._receipts)

    def clear(self) -> None:
        with self._lock:
            self._receipts.clear()
            if self.path.exists():
                self.path.unlink()

    def session_receipts(self, since: float) -> list[Receipt]:
        """Get receipts since a timestamp."""
        with self._lock:
            return [r for r in self._receipts if r.timestamp >= since]
