"""Signed execution receipts for tool calls."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional


def _canonical(obj: Any) -> str:
    """Produce a canonical JSON string for hashing."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


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
    hash: str = ""
    hmac_sig: str = ""

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
        if expected_hash != self.hash:
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


class ReceiptStore:
    """Persistent storage for execution receipts."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or Path.home() / ".toolproof" / "receipts.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._receipts: list[Receipt] = []
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._receipts.append(Receipt.from_dict(json.loads(line)))

    def add(self, receipt: Receipt) -> None:
        self._receipts.append(receipt)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(receipt.to_dict(), ensure_ascii=False) + "\n")

    def find_by_tool(self, tool_name: str) -> list[Receipt]:
        return [r for r in self._receipts if r.tool_name == tool_name]

    def find_by_id(self, receipt_id: str) -> Optional[Receipt]:
        for r in self._receipts:
            if r.id == receipt_id:
                return r
        return None

    def find_by_hash(self, hash_val: str) -> Optional[Receipt]:
        for r in self._receipts:
            if r.hash == hash_val:
                return r
        return None

    def all(self) -> list[Receipt]:
        return list(self._receipts)

    def count(self) -> int:
        return len(self._receipts)

    def clear(self) -> None:
        self._receipts.clear()
        if self.path.exists():
            self.path.unlink()

    def session_receipts(self, since: float) -> list[Receipt]:
        """Get receipts since a timestamp."""
        return [r for r in self._receipts if r.timestamp >= since]
