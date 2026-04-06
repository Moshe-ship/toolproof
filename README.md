# ToolProof v0.4.0

**Agent tool verification. Pre-execution gating. Eval-driven optimization.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-green.svg)](https://python.org)
[![Tests: 71 passing](https://img.shields.io/badge/tests-71%20passing-green.svg)]()
[![OpenClaw Plugin](https://img.shields.io/badge/OpenClaw-native%20plugin-orange.svg)]()

> Agents lie about tool calls. ToolProof catches them before and after execution.

[Landing Page](https://moshe-ship.github.io/toolproof/)

---

## The Problem

AI agents claim they searched a database, read a file, or called an API. Under adversarial conditions, 91.1% of the time they hallucinate the results. They report data that was never returned. They reference tool calls that never happened. They execute destructive commands without authorization.

No tool on the market detects this.

ToolProof does two things:

1. **Pre-execution gating** -- AEGIS-style policy enforcement that blocks dangerous tool calls before they run.
2. **Post-execution verification** -- signed receipts that prove what actually happened, cross-referenced against what the agent claims.

## Install

```bash
pip install toolproof
```

## Quick Start

### Zero-config: wrap any command

```bash
# Run your agent through ToolProof. All tool calls recorded automatically.
toolproof wrap -- python my_agent.py

# Proxy mode: sit between agent and tool server
toolproof proxy --target http://localhost:3000

# Import from Claude Code sessions
toolproof import-claude

# Import from Hermes agent
toolproof import-hermes --profile nashir

# Import from OpenClaw
toolproof import-openclaw

# Import from everything
toolproof import-all
```

### SDK auto-patch (one line)

```python
import toolproof
toolproof.patch_openai()   # Patches globally, zero config
toolproof.patch_anthropic() # Same for Anthropic

# Now every API call with tools generates signed receipts
import openai
client = openai.OpenAI()
resp = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Search the database"}],
    tools=[...],
)
# Receipts already recorded at ~/.toolproof/receipts.jsonl
```

### Manual wrapping

```python
from toolproof import ToolProxy, ReceiptStore, Verifier, AgentClaim

store = ReceiptStore()
proxy = ToolProxy(store, secret="your-key")

# Wrap your tools
safe_search = proxy.wrap(search_database)
result = safe_search(query="SELECT * FROM users")

# Verify claims
verifier = Verifier(store, secret="your-key")
claim = AgentClaim(tool_name="search_database", arguments={"query": "SELECT * FROM users"})
result = verifier.verify_claim(claim)
print(result.verdict)  # VERIFIED, UNVERIFIED, or TAMPERED
```

### Pre-execution gating

```python
from toolproof.gate import Gate, Policy

policy = Policy.load()  # from ~/.toolproof/policy.json
gate = Gate(policy)

decision = gate.check("Bash", {"command": "rm -rf /"})
# Decision(action="block", reason="Destructive shell command")

decision = gate.check("Read", {"file_path": "/src/main.py"})
# Decision(action="allow")
```

Block, allow, or hold tool calls for human review. Policy-driven. No code changes in your agent.

---

## Commands

17 CLI commands.

| Command | What it does |
|---|---|
| `toolproof analyze` | Run trust analytics on receipt history |
| `toolproof ci` | One-shot CI trust check |
| `toolproof clear` | Clear all receipts |
| `toolproof config` | Configure settings |
| `toolproof feedback` | Generate actionable feedback for agent frameworks |
| `toolproof github-action` | Print GitHub Action template |
| `toolproof import-all` | Import from all sources |
| `toolproof import-claude` | Import from Claude Code sessions |
| `toolproof import-hermes` | Import from Hermes agent logs |
| `toolproof import-openclaw` | Import from OpenClaw skill logs |
| `toolproof inspect <id>` | Inspect a specific receipt |
| `toolproof proxy --target <url>` | Start HTTP proxy that records tool calls |
| `toolproof report` | Show all recorded receipts |
| `toolproof status` | Show receipt store status |
| `toolproof verify <file>` | Verify agent claims against receipts |
| `toolproof watch` | Live monitoring dashboard |
| `toolproof wrap -- <command>` | Run command with automatic recording |

---

## Architecture

### 18 Python Modules

```
toolproof/
  __init__.py          # Package entry, SDK patch exports
  __main__.py          # python -m toolproof
  analytics.py         # Trust analytics, pattern detection, cost hotspots
  claude_reader.py     # Claude Code session log parser
  cli.py               # Click CLI, 17 commands
  display.py           # Rich terminal output
  feedback.py          # Actionable feedback generator for agent frameworks
  gate.py              # Pre-execution gating (AEGIS-style policy enforcement)
  html_report.py       # Standalone dark-theme HTML trust reports
  http_proxy.py        # HTTP proxy, protocol auto-detection
  interceptors.py      # Tool call interception layer
  proxy.py             # Function-level tool wrapping
  receipt.py           # Signed execution receipts, JSONL store
  safepath.py          # Path validation, traversal prevention
  sdk_patch.py         # OpenAI/Anthropic SDK monkey-patching
  trust.py             # Trust scoring, grading, risk assessment
  verifier.py          # Claim verification engine
  watch.py             # Live monitoring dashboard
```

### Recording

```
Agent --> ToolProof Proxy --> Actual Tool
             |                    |
             |  signed receipt    |
             |<-------------------|
             v
        Receipt Store (signed JSONL)
```

ToolProof intercepts tool calls through one of these methods:

1. **HTTP proxy** -- sits between agent and tool server, records everything
2. **SDK patch** -- monkey-patches OpenAI/Anthropic SDKs to auto-record
3. **Function wrapper** -- wraps individual functions
4. **Log import** -- reads existing logs from Claude Code, Hermes, OpenClaw

### Pre-Execution Gating

```
Agent wants to call tool X with args Y
             |
             v
        Gate checks against policy
             |
        allow / block / hold
             |
             v
        Tool executes (or doesn't)
```

AEGIS-style policy enforcement. Define rules in `~/.toolproof/policy.json`. Block destructive commands, restrict file access, require human approval for sensitive operations. Aligned with Microsoft Agent Governance Toolkit patterns and W3C Agentic Integrity Verification draft.

### Verification

```
Agent claims "I called X with Y and got Z"
             |
             v
        Verifier cross-references against receipts
             |
             v
        Trust Score: VERIFIED / UNVERIFIED / TAMPERED
```

### Eval-Driven Optimization Loop

```
Run agent --> Record receipts --> Analyze patterns --> Generate feedback --> Improve agent
    ^                                                                          |
    |__________________________________________________________________________|
```

The analytics module finds which tools get hallucinated most, which models produce the lowest trust scores, and where token costs concentrate. The feedback module turns those findings into actionable config changes for Hermes profiles, OpenClaw config, and system prompts.

This is eval-driven development applied to tool calling. Measure. Find patterns. Improve systematically. Close the loop.

### Verdicts

| Verdict | Meaning |
|---|---|
| **VERIFIED** | Claim matches a receipt |
| **UNVERIFIED** | No matching receipt (possible hallucination) |
| **TAMPERED** | Receipt exists but claim doesn't match (definite hallucination) |

### Trust Score

```
trust_score = verified / (verified + unverified + tampered)
```

| Grade | Score | Risk |
|---|---|---|
| A | 95%+ | LOW |
| B | 85-94% | LOW |
| C | 70-84% | MEDIUM |
| D | 50-69% | MEDIUM |
| F | <50% | HIGH |

### Token Cost Tracking

Every receipt records execution duration. Analytics aggregates cost by tool, model, session, and time window. Find expensive calls. Find broken caching. Find the 20% of tool calls eating 80% of your budget.

---

## HTTP Proxy

The proxy sits between your agent and its tools. It forwards every request, records a signed receipt, and the agent never knows it is being watched.

```bash
# Proxy to a local tool server
toolproof proxy --port 8080 --target http://localhost:3000

# Proxy OpenAI API calls
toolproof proxy --port 9090 --target https://api.openai.com

# Proxy Hermes tool server
toolproof proxy --target http://localhost:5001

# Proxy OpenClaw
toolproof proxy --target http://localhost:8000
```

The proxy auto-detects and parses:
- OpenAI chat completions (tool_calls)
- Anthropic messages (tool_use blocks)
- MCP JSON-RPC (tools/call)
- Hermes skill executions
- OpenClaw commands
- Generic REST endpoints

## Wrap Command

Run any agent command with automatic interception:

```bash
# Wrap sets up a proxy and forwards env vars automatically
toolproof wrap -- python agent.py
toolproof wrap -- node bot.js
toolproof wrap --target http://localhost:5001 -- hermes run --profile nashir
```

The child process gets `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`, and `HTTP_PROXY` pointed at the ToolProof proxy.

## Import from Agent Platforms

### Claude Code

```bash
# Import recent sessions
toolproof import-claude

# Import specific session
toolproof import-claude --session abc123

# Import more sessions
toolproof import-claude --limit 20
```

Reads `~/.claude/projects/` JSONL files. Extracts every tool_use/tool_result pair as a signed receipt.

### Hermes

```bash
# Import all profiles
toolproof import-hermes

# Import specific profile
toolproof import-hermes --profile nashir
toolproof import-hermes --profile mkhlab
```

### OpenClaw

```bash
toolproof import-openclaw
```

### All at once

```bash
toolproof import-all
```

## Analytics and Feedback

```bash
# Run analytics on your receipt history
toolproof analyze

# Generate actionable feedback for your agent framework
toolproof feedback
```

Analytics finds:
- Which tools get hallucinated most
- Which models produce the lowest trust
- Cost hotspots (broken caching, expensive repeated calls)
- Failure patterns by time of day, session, source

Feedback generates specific config changes for:
- Hermes profiles (skill weights, model selection)
- OpenClaw config (tool permissions, routing)
- System prompts (add verification instructions)
- Generic JSON for any framework

## HTML Reports

```bash
# Print to stdout
toolproof report --html > trust-report.html

# Write to file
toolproof report --html --output report.html
```

Generates a standalone dark-theme HTML page with:
- Trust score card (grade, risk level)
- Verification results table
- Tool execution summary
- Duration and error stats

## CI Integration

### One-shot check

```bash
# Pass if trust >= 80% and at least 1 receipt
toolproof ci --min-trust 0.8

# Strict: 90% trust, minimum 10 receipts
toolproof ci --min-trust 0.9 --min-receipts 10

# JSON for scripts
toolproof ci --json-output
```

Exit codes: 0 = pass, 1 = fail.

### Live watch

```bash
# Watch in real-time
toolproof watch

# Watch with threshold (exits 1 if trust drops below)
toolproof watch --min-trust 0.8 --timeout 60
```

### GitHub Action

```bash
# Print the template
toolproof github-action
```

```yaml
- name: Verify tool calls
  run: toolproof ci --min-trust 0.8 --min-receipts 5
```

## OpenClaw Native Plugin

ToolProof ships as a native OpenClaw plugin. ClawHub publishable.

```
openclaw/
  clawhub.json       # ClawHub package manifest
  extensions/        # OpenClaw extension points
  hooks/             # Pre/post execution hooks
  skills/            # ToolProof skills for OpenClaw agents
```

Install into OpenClaw and every skill execution gets a signed receipt. Pre-execution gating applies to OpenClaw commands. Feedback writes directly to OpenClaw config.

## Execution Receipt Format

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": 1712400000.0,
  "tool_name": "search_database",
  "arguments": {"query": "SELECT * FROM users"},
  "response": [{"id": 1, "name": "Alice"}],
  "error": null,
  "duration_ms": 142.3,
  "hash": "a1b2c3d4e5f6...",
  "hmac_sig": "9a8b7c6d5e4f..."
}
```

Receipts are signed with SHA-256. Optional HMAC-SHA256 with a secret key for tamper-proof verification.

## Security

Security hardened through 2 rounds of adversarial pen-testing. All bypasses found and fixed.

- Receipts are cryptographically signed (SHA-256 + optional HMAC)
- Pre-execution gating blocks dangerous tool calls before they run
- Path traversal prevention on all file operations
- Config stored at `~/.toolproof/config.json` with `0600` permissions
- Secret keys are never printed in full
- Proxy does not modify request or response content
- All receipt data is stored locally
- No external telemetry, no phone-home

---

## Built With

This project stands on the shoulders of specific people and projects:

- **[@anthropic](https://anthropic.com) / Claude Code** -- where the problem was first discovered. Watching Claude claim it ran tools that never executed is what started this.
- **[@OpenAI](https://openai.com)** -- the `tool_use` format standard that every agent framework now follows. ToolProof parses it natively.
- **[@steipete](https://github.com/steipete) (Peter Steinberger) / [@OpenClaw](https://github.com/nicholasgasior/openclaw)** -- native plugin platform. ToolProof ships as a first-class OpenClaw plugin with ClawHub publishing.
- **[@karpathy](https://github.com/karpathy) (Andrej Karpathy)** -- eval-driven development philosophy. The analytics and feedback loop in ToolProof is directly inspired by his approach: measure everything, find patterns, improve systematically. No vibes.
- **[@LangChainAI](https://github.com/langchain-ai)** -- tool scoping patterns that informed how ToolProof intercepts and classifies tool calls.
- **[Microsoft Agent Governance Toolkit](https://github.com/microsoft/agent-governance-toolkit)** -- patterns for policy-driven agent control that shaped the gating module.
- **[AEGIS Research](https://arxiv.org/abs/2603.12621)** -- pre-execution firewall concept. ToolProof's gating is an implementation of this idea.
- **[W3C Agentic Integrity Verification](https://www.w3.org/groups/)** -- draft specification for agent transparency and verifiability that ToolProof aligns with.
- **[Saudi AI Community](https://x.com/i/communities/2032184341682643429)** -- testing, feedback, and the push to ship it.

## Community

Built with input from the [Saudi AI Community](https://x.com/i/communities/2032184341682643429).

## License

MIT -- Musa the Carpenter
