# toolproof

**Agent tool verification**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-green.svg)](https://python.org)

> Agents lie about tool calls. ToolProof catches them.

## Why

AI agents claim they searched a database, read a file, or called an API. 91.1% of the time under adversarial conditions, they hallucinate the results. They report data that was never returned. They reference tool calls that never happened.

No tool on the market detects this.

ToolProof records every tool execution with a signed receipt, then cross-references what the agent claims against what actually happened.

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

## Commands

| Command | What it does |
|---|---|
| `toolproof status` | Show receipt store status |
| `toolproof verify <file>` | Verify agent claims against receipts |
| `toolproof report` | Show all recorded receipts |
| `toolproof report --html` | Generate HTML trust report |
| `toolproof inspect <id>` | Inspect a specific receipt |
| `toolproof proxy --target <url>` | Start HTTP proxy that records tool calls |
| `toolproof wrap -- <command>` | Run command with automatic recording |
| `toolproof import-claude` | Import from Claude Code sessions |
| `toolproof import-hermes` | Import from Hermes agent logs |
| `toolproof import-openclaw` | Import from OpenClaw skill logs |
| `toolproof import-all` | Import from all sources |
| `toolproof watch` | Live monitoring dashboard |
| `toolproof ci` | One-shot CI trust check |
| `toolproof config` | Configure settings |
| `toolproof clear` | Clear all receipts |
| `toolproof github-action` | Print GitHub Action template |

## How It Works

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

## HTTP Proxy

The proxy sits between your agent and its tools. It forwards every request, records a signed receipt, and the agent never knows it's being watched.

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

- Receipts are cryptographically signed (SHA-256 + optional HMAC)
- Config stored at `~/.toolproof/config.json` with `0600` permissions
- Secret keys are never printed in full
- Proxy does not modify request or response content
- All receipt data is stored locally

## Community

Built with input from the [Saudi AI Community](https://x.com/i/communities/2032184341682643429).

## License

MIT -- Musa the Carpenter
