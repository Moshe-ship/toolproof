---
name: toolproof-verify
description: "Auto-record signed execution receipts for every tool call. Catches hallucinated tool results before they reach the user."
events: ["tool:execute:after", "tool:result:after"]
priority: 95
---

# ToolProof Verification Hook

Records every tool execution as a cryptographically signed receipt. Cross-references agent claims against actual execution in real-time.

## What it does

On every `tool:execute:after` event:

1. Captures the tool name, arguments, and response
2. Records execution duration
3. Extracts token usage from response headers (if available)
4. Generates a SHA-256 signed receipt
5. Optionally signs with HMAC if `TOOLPROOF_SECRET` is set
6. Appends to `~/.toolproof/receipts.jsonl`

On every `tool:result:after` event:

1. Matches the result to its pending receipt
2. Updates the receipt with actual response data
3. Flags discrepancies between claimed and actual output
4. If response was hallucinated (no matching execution), marks as UNVERIFIED

## Configuration

Set these environment variables:

| Variable | Description | Default |
|---|---|---|
| `TOOLPROOF_SECRET` | HMAC signing key | (none, SHA-256 only) |
| `TOOLPROOF_STORE` | Receipt store path | `~/.toolproof/receipts.jsonl` |
| `TOOLPROOF_GATE` | Enable pre-execution gating | `false` |
| `TOOLPROOF_COST` | Track token costs | `true` |
| `TOOLPROOF_ALERT_THRESHOLD` | Trust score alert threshold | `0.7` |

## Context variables set

- `toolproof.lastReceipt` — ID of the most recent receipt
- `toolproof.sessionTrust` — Running trust score for this session (0-1)
- `toolproof.totalReceipts` — Count of receipts in this session
- `toolproof.totalCost` — Running cost in USD for this session
- `toolproof.flagged` — Number of unverified/tampered claims this session

## Pre-execution gating

When `TOOLPROOF_GATE=true`, the hook checks tool calls against a policy before execution:

- **allow** — Tool call proceeds normally
- **block** — Tool call is denied, agent receives error
- **review** — Tool call held for human approval (sets `toolproof.pendingReview`)

Policy is defined in `~/.toolproof/policy.json`:

```json
{
  "rules": [
    {"tool": "Bash", "action": "review", "reason": "Shell commands require review"},
    {"tool": "Write", "pattern": "/etc/*", "action": "block", "reason": "System files protected"},
    {"tool": "*", "action": "allow"}
  ],
  "max_cost_per_call": 0.50,
  "max_session_cost": 10.00
}
```

## Integration with OpenClaw

This hook works alongside any OpenClaw plugin or skill:

- Compatible with mkhlab (Arabic skills)
- Compatible with tool-guard plugin
- Does not modify tool inputs or outputs — observe only (unless gating is enabled)
- Receipt format matches W3C Agentic Integrity Verification draft

## Receipt format

```json
{
  "id": "uuid",
  "timestamp": 1712400000.0,
  "tool_name": "Read",
  "arguments": {"file_path": "/src/main.py"},
  "response": "import os\n...",
  "error": null,
  "duration_ms": 42.3,
  "tokens_in": 1250,
  "tokens_out": 340,
  "cost_usd": 0.0047,
  "hash": "sha256...",
  "hmac_sig": "hmac-sha256...",
  "source": "openclaw",
  "session_id": "abc123"
}
```
