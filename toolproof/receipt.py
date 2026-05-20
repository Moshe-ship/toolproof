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
    r"(secret|password|passwd|token|api.?key|authorization|cookie|credential|private.?key"
    r"|access.?key.?id|session.?id|sessionid|auth$|auth.?token|bearer|jwt|refresh.?token"
    r"|client.?secret|client.?key|consumer.?key|consumer.?secret"
    r"|signing.?key|encryption.?key|ssh.?key|pgp.?key"
    r"|aws.?secret|aws.?key|gcp.?key|azure.?key|stripe.?key|webhook.?secret"
    r"|database.?url|connection.?string|dsn|db.?pass"
    r"|x.?api.?key|openai.?key|anthropic.?key|github.?token)",
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
    hash: str = ""                  # legacy-core hash (tool/args/response/error/ts)
    hmac_sig: str = ""
    evidence_hash: str = ""         # covers MTG evidence fields; empty if none populated
    # Source tracking
    source: str = ""  # "openclaw", "claude", "hermes", "proxy", "sdk"
    session_id: str = ""
    # Product/tool evidence bound separately from the legacy response hash.
    # This lets APIs expose a compact evidence array while making that evidence
    # independently tamper-evident in receipts.
    evidence: list = field(default_factory=list)
    # MTG (Morphological Type Guards) integration.
    # Populated by toolproof.mtg_bridge when consuming MTG pipeline output.
    # These fields are covered by evidence_hash (not the legacy `hash`) so
    # that 0.4.x hash compatibility is preserved AND MTG evidence is
    # tamper-evident in 0.5.0+.
    outcome: Optional[str] = None           # 'pass' | 'partial' | 'fail'
    hash_prev: Optional[str] = None         # previous receipt hash in MTG chain
    dialect_expected: Optional[str] = None  # from GuardSpec
    dialect_observed: Optional[str] = None  # from MTG Analysis
    arabic_preserved: Optional[bool] = None
    arg_integrity_score: Optional[float] = None
    mtg_violations: list = field(default_factory=list)
    # MTG reconciled-mode repair suggestions (v0.5.2+). Each entry is a
    # dict matching mtg.repair.RepairSuggestion.to_dict() with an added
    # `param` key naming which argument the repair applies to. Covered by
    # evidence_hash — tampering breaks verify_integrity().
    mtg_repairs: list = field(default_factory=list)

    def _legacy_payload(self) -> str:
        return _canonical({
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "response": self.response,
            "error": self.error,
            "timestamp": self.timestamp,
        })

    def _evidence_payload(self) -> str:
        """Canonical JSON of MTG evidence fields.

        Returns empty string if no MTG field is populated — in that case
        evidence_hash is also empty and verify_integrity() doesn't require
        one, preserving backward compatibility with pre-MTG receipts.
        """
        evidence = {
            "evidence": self.evidence,
            "outcome": self.outcome,
            "hash_prev": self.hash_prev,
            "dialect_expected": self.dialect_expected,
            "dialect_observed": self.dialect_observed,
            "arabic_preserved": self.arabic_preserved,
            "arg_integrity_score": self.arg_integrity_score,
            "mtg_violations": self.mtg_violations,
            "mtg_repairs": self.mtg_repairs,
        }
        populated = any(
            v not in (None, "", [], {}) for v in evidence.values()
        )
        if not populated:
            return ""
        return _canonical(evidence)

    def sign(self, secret: Optional[str] = None) -> None:
        """Compute legacy hash, evidence hash, and optional HMAC signature.

        The legacy hash covers tool/args/response/error/timestamp (0.4.x
        compatible). The evidence hash, when any MTG field is populated,
        covers outcome, hash_prev, dialect_expected, dialect_observed,
        arabic_preserved, arg_integrity_score, and mtg_violations. Tampering
        either region after signing will fail verify_integrity().
        """
        legacy = self._legacy_payload()
        self.hash = hashlib.sha256(legacy.encode("utf-8")).hexdigest()

        evidence = self._evidence_payload()
        self.evidence_hash = (
            hashlib.sha256(evidence.encode("utf-8")).hexdigest() if evidence else ""
        )

        if secret:
            self.hmac_sig = hmac.new(
                secret.encode("utf-8"),
                (legacy + evidence).encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

    def verify_integrity(self, secret: Optional[str] = None) -> bool:
        """Check that neither the legacy core nor the MTG evidence was tampered."""
        legacy = self._legacy_payload()
        expected_hash = hashlib.sha256(legacy.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(expected_hash, self.hash):
            return False

        evidence = self._evidence_payload()
        expected_evidence = (
            hashlib.sha256(evidence.encode("utf-8")).hexdigest() if evidence else ""
        )
        if not hmac.compare_digest(expected_evidence, self.evidence_hash or ""):
            return False

        if secret and self.hmac_sig:
            expected_hmac = hmac.new(
                secret.encode("utf-8"),
                (legacy + evidence).encode("utf-8"),
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
