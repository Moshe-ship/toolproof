"""Tests for pre-execution gating."""

import tempfile
from pathlib import Path

from toolproof.gate import Gate, Policy, Rule, Action, Decision


def test_default_policy_allows_safe_commands():
    gate = Gate(Policy.default())
    decision = gate.check("Read", {"file_path": "/src/main.py"})
    assert decision.allowed


def test_default_policy_reviews_destructive_bash():
    gate = Gate(Policy.default())
    decision = gate.check("Bash", {"command": "rm -rf /tmp/stuff"})
    assert decision.action == Action.REVIEW
    assert "Destructive" in decision.reason


def test_default_policy_blocks_system_writes():
    gate = Gate(Policy.default())
    decision = gate.check("Write", {"file_path": "/etc/passwd"})
    assert decision.action == Action.BLOCK
    assert "System" in decision.reason


def test_default_policy_reviews_secret_access():
    gate = Gate(Policy.default())
    decision = gate.check("Read", {"file_path": "/app/.env"})
    assert decision.action == Action.REVIEW
    assert "Sensitive" in decision.reason


def test_blocked_tools_list():
    policy = Policy(blocked_tools=["DangerousTool", "Evil*"])
    gate = Gate(policy)

    assert gate.check("DangerousTool", {}).action == Action.BLOCK
    assert gate.check("EvilScript", {}).action == Action.BLOCK
    assert gate.check("SafeTool", {}).allowed


def test_review_tools_list():
    policy = Policy(review_tools=["Bash", "Write"])
    gate = Gate(policy)

    assert gate.check("Bash", {}).action == Action.REVIEW
    assert gate.check("Write", {}).action == Action.REVIEW
    assert gate.check("Read", {}).allowed


def test_cost_per_call_limit():
    policy = Policy(max_cost_per_call=0.10)
    gate = Gate(policy)

    assert gate.check("BigQuery", {}, estimated_cost=0.05).allowed
    assert gate.check("BigQuery", {}, estimated_cost=0.50).action == Action.BLOCK


def test_session_cost_limit():
    policy = Policy(max_session_cost=1.00)
    gate = Gate(policy)

    gate.record_cost(0.80)
    assert gate.check("Tool", {}, estimated_cost=0.15).allowed
    gate.record_cost(0.15)
    assert gate.check("Tool", {}, estimated_cost=0.10).action == Action.BLOCK


def test_custom_rule():
    policy = Policy(rules=[
        Rule(
            id="block-drop",
            tool="Bash",
            action=Action.BLOCK,
            arg_key="command",
            arg_pattern=r"DROP TABLE",
            reason="No dropping tables",
        ),
        Rule(id="allow-all", tool="*", action=Action.ALLOW),
    ])
    gate = Gate(policy)

    assert gate.check("Bash", {"command": "DROP TABLE users"}).action == Action.BLOCK
    assert gate.check("Bash", {"command": "ls -la"}).allowed


def test_policy_save_and_load():
    policy = Policy.default()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "policy.json"
        policy.save(path)
        loaded = Policy.load(path)
        assert len(loaded.rules) == len(policy.rules)
        assert loaded.rules[0].id == policy.rules[0].id


def test_gate_stats():
    policy = Policy(blocked_tools=["Bad"])
    gate = Gate(policy)

    gate.check("Good", {})
    gate.check("Bad", {})
    gate.check("Good", {})

    stats = gate.stats
    assert stats["calls"] == 3
    assert stats["blocked"] == 1


def test_first_matching_rule_wins():
    policy = Policy(rules=[
        Rule(id="block-specific", tool="Bash", action=Action.BLOCK, arg_key="command", arg_pattern="danger"),
        Rule(id="allow-bash", tool="Bash", action=Action.ALLOW),
    ])
    gate = Gate(policy)

    assert gate.check("Bash", {"command": "danger zone"}).action == Action.BLOCK
    assert gate.check("Bash", {"command": "ls"}).allowed
