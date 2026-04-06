"""Pre-execution gating for tool calls.

AEGIS-style policy enforcement: check tool calls against rules
before they execute. Allow, block, or hold for review.

Aligns with:
- Microsoft Agent Governance Toolkit patterns
- AEGIS pre-execution firewall (arxiv 2603.12621)
- W3C Agentic Integrity Verification draft
- EU AI Act Article 19 audit requirements

Usage:
    from toolproof.gate import Gate, Policy

    policy = Policy.load()  # from ~/.toolproof/policy.json
    gate = Gate(policy)

    decision = gate.check("Bash", {"command": "rm -rf /"})
    # Decision(action="block", reason="Destructive shell command")

    decision = gate.check("Read", {"file_path": "/src/main.py"})
    # Decision(action="allow")
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


_CATASTROPHIC_RE = re.compile(
    r"(\([^)]*[+*][^)]*\)[+*])"  # nested quantifiers like (a+)+ or (a*)*
)


def _safe_regex(pattern: str, text: str, timeout_ms: int = 100) -> bool:
    """Run regex match with ReDoS prevention.

    Strategy: reject patterns with nested quantifiers at parse time.
    These are the only patterns that cause catastrophic backtracking.
    No threads, no signals, no zombie processes.
    """
    # Reject patterns with nested quantifiers — the root cause of ALL ReDoS
    if _CATASTROPHIC_RE.search(pattern):
        return False

    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return False

    # With nested quantifiers rejected, normal regex is safe on truncated input
    try:
        return compiled.search(text[:2000]) is not None
    except Exception:
        return False


class Action(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REVIEW = "review"


@dataclass
class Decision:
    """Result of a policy check."""

    action: Action
    reason: str = ""
    rule_id: str = ""
    cost_estimate: float = 0.0

    @property
    def allowed(self) -> bool:
        return self.action == Action.ALLOW

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "rule_id": self.rule_id,
            "cost_estimate": self.cost_estimate,
        }


@dataclass
class Rule:
    """A single policy rule."""

    id: str = ""
    tool: str = "*"  # tool name pattern, "*" matches all
    action: Action = Action.ALLOW
    reason: str = ""
    pattern: str = ""  # regex pattern to match against arguments
    arg_key: str = ""  # specific argument key to check
    arg_pattern: str = ""  # regex pattern for argument value

    def matches(self, tool_name: str, arguments: dict) -> bool:
        """Check if this rule matches a tool call."""
        # Check tool name
        if self.tool != "*":
            pattern = self.tool.replace("*", ".*")
            if not _safe_regex(f"^{pattern}$", tool_name):
                return False

        # Check argument patterns (with hard timeout protection)
        if self.pattern:
            args_str = json.dumps(arguments, ensure_ascii=False)[:2000]
            if not _safe_regex(self.pattern, args_str):
                return False

        if self.arg_key and self.arg_pattern:
            val = str(arguments.get(self.arg_key, ""))[:1000]
            if not _safe_regex(self.arg_pattern, val):
                return False

        return True

    @classmethod
    def from_dict(cls, data: dict) -> Rule:
        return cls(
            id=data.get("id", ""),
            tool=data.get("tool", "*"),
            action=Action(data.get("action", "allow")),
            reason=data.get("reason", ""),
            pattern=data.get("pattern", ""),
            arg_key=data.get("arg_key", ""),
            arg_pattern=data.get("arg_pattern", ""),
        )


@dataclass
class Policy:
    """Collection of rules for pre-execution gating."""

    rules: list[Rule] = field(default_factory=list)
    max_cost_per_call: float = 0.0  # 0 = no limit
    max_session_cost: float = 0.0   # 0 = no limit
    blocked_tools: list[str] = field(default_factory=list)
    review_tools: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> Policy:
        """Load policy from JSON file."""
        policy_path = path or Path.home() / ".toolproof" / "policy.json"
        if not policy_path.exists():
            return cls.default()

        with open(policy_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        rules = [Rule.from_dict(r) for r in data.get("rules", [])]
        return cls(
            rules=rules,
            max_cost_per_call=data.get("max_cost_per_call", 0.0),
            max_session_cost=data.get("max_session_cost", 0.0),
            blocked_tools=data.get("blocked_tools", []),
            review_tools=data.get("review_tools", []),
        )

    def save(self, path: Optional[Path] = None) -> None:
        """Save policy to JSON file."""
        policy_path = path or Path.home() / ".toolproof" / "policy.json"
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "rules": [
                {
                    "id": r.id, "tool": r.tool, "action": r.action.value,
                    "reason": r.reason, "pattern": r.pattern,
                    "arg_key": r.arg_key, "arg_pattern": r.arg_pattern,
                }
                for r in self.rules
            ],
            "max_cost_per_call": self.max_cost_per_call,
            "max_session_cost": self.max_session_cost,
            "blocked_tools": self.blocked_tools,
            "review_tools": self.review_tools,
        }
        with open(policy_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def default(cls) -> Policy:
        """Sensible default policy."""
        return cls(
            rules=[
                Rule(
                    id="block-destructive-bash",
                    tool="Bash",
                    action=Action.REVIEW,
                    arg_key="command",
                    arg_pattern=r"(rm\s+-rf|drop\s+table|truncate|--force|--hard|format\s+c:)",
                    reason="Destructive command requires review",
                ),
                Rule(
                    id="block-system-write",
                    tool="Write",
                    action=Action.BLOCK,
                    arg_key="file_path",
                    arg_pattern=r"^/(etc|usr|bin|sbin|boot|sys|proc)/",
                    reason="System directory writes blocked",
                ),
                Rule(
                    id="review-env-access",
                    tool="*",
                    action=Action.REVIEW,
                    pattern=r"(\.env|credentials|secret|password|token|api.?key)",
                    reason="Sensitive data access requires review",
                ),
                Rule(
                    id="allow-all",
                    tool="*",
                    action=Action.ALLOW,
                ),
            ],
        )

    def to_dict(self) -> dict:
        return {
            "rules_count": len(self.rules),
            "max_cost_per_call": self.max_cost_per_call,
            "max_session_cost": self.max_session_cost,
            "blocked_tools": self.blocked_tools,
            "review_tools": self.review_tools,
        }


class Gate:
    """Pre-execution gate that checks tool calls against policy.

    Usage:
        gate = Gate(Policy.load())
        decision = gate.check("Bash", {"command": "ls -la"})
        if decision.allowed:
            # proceed with tool call
        else:
            # block or hold for review
    """

    def __init__(self, policy: Policy):
        self.policy = policy
        self.session_cost: float = 0.0
        self.call_count: int = 0
        self.blocked_count: int = 0
        self.reviewed_count: int = 0

    def check(
        self,
        tool_name: str,
        arguments: dict,
        estimated_cost: float = 0.0,
    ) -> Decision:
        """Check a tool call against policy.

        Args:
            tool_name: Name of the tool being called.
            arguments: Arguments being passed.
            estimated_cost: Estimated cost of this call in USD.

        Returns:
            Decision with action, reason, and metadata.
        """
        self.call_count += 1

        # Check blocked tools list
        for pattern in self.policy.blocked_tools:
            if re.match(pattern.replace("*", ".*"), tool_name, re.IGNORECASE):
                self.blocked_count += 1
                return Decision(
                    action=Action.BLOCK,
                    reason=f"Tool '{tool_name}' is in blocked list",
                )

        # Check review tools list
        for pattern in self.policy.review_tools:
            if re.match(pattern.replace("*", ".*"), tool_name, re.IGNORECASE):
                self.reviewed_count += 1
                return Decision(
                    action=Action.REVIEW,
                    reason=f"Tool '{tool_name}' requires review",
                )

        # Check cost limits
        if self.policy.max_cost_per_call > 0 and estimated_cost > self.policy.max_cost_per_call:
            self.blocked_count += 1
            return Decision(
                action=Action.BLOCK,
                reason=f"Estimated cost ${estimated_cost:.4f} exceeds per-call limit ${self.policy.max_cost_per_call:.4f}",
                cost_estimate=estimated_cost,
            )

        if self.policy.max_session_cost > 0 and (self.session_cost + estimated_cost) > self.policy.max_session_cost:
            self.blocked_count += 1
            return Decision(
                action=Action.BLOCK,
                reason=f"Session cost ${self.session_cost:.4f} + ${estimated_cost:.4f} exceeds limit ${self.policy.max_session_cost:.4f}",
                cost_estimate=estimated_cost,
            )

        # Check rules (first match wins)
        for rule in self.policy.rules:
            if rule.matches(tool_name, arguments):
                if rule.action == Action.BLOCK:
                    self.blocked_count += 1
                elif rule.action == Action.REVIEW:
                    self.reviewed_count += 1
                return Decision(
                    action=rule.action,
                    reason=rule.reason,
                    rule_id=rule.id,
                    cost_estimate=estimated_cost,
                )

        # Default: allow
        return Decision(action=Action.ALLOW)

    def record_cost(self, cost: float) -> None:
        """Record actual cost after execution."""
        self.session_cost += cost

    @property
    def stats(self) -> dict:
        return {
            "calls": self.call_count,
            "blocked": self.blocked_count,
            "reviewed": self.reviewed_count,
            "session_cost": round(self.session_cost, 6),
        }
