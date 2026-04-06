# toolproof

**Agent tool verification**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-green.svg)](https://python.org)

> Agents lie about tool calls. ToolProof catches them.

## Why

AI agents claim they searched a database, read a file, or called an API. 91.1% of the time under adversarial conditions, they hallucinate the results. They report data that was never returned. They reference tool calls that never happened.

No tool on the market detects this.

ToolProof sits between the agent and its tools. It records every tool execution with a signed receipt, then cross-references what the agent claims against what actually happened. The output is a trust score.

## Install

```bash
pip install toolproof
```

## Quick Start

### As a library

```python
from toolproof import ToolProxy, ReceiptStore, Verifier, AgentClaim, TrustReport

# 1. Set up the proxy
store = ReceiptStore()
proxy = ToolProxy(store, secret="your-secret-key")

# 2. Wrap your tools
def search_database(query: str) -> list:
    return db.execute(query)

safe_search = proxy.wrap(search_database)

# 3. Agent uses the wrapped tool (receipts generated automatically)
results = safe_search(query="SELECT * FROM users")

# 4. Later: verify what the agent claims
verifier = Verifier(store, secret="your-secret-key")
claim = AgentClaim(
    tool_name="search_database",
    arguments={"query": "SELECT * FROM users"},
    response=[{"id": 1, "name": "Alice"}],
)
result = verifier.verify_claim(claim)
print(result.verdict)  # VERIFIED, UNVERIFIED, or TAMPERED
```

### From the CLI

```bash
# Check receipt store status
toolproof status

# Verify agent claims against receipts
toolproof verify agent_output.json

# View all recorded receipts
toolproof report

# Inspect a specific receipt
toolproof inspect abc123

# Configure secret key
toolproof config
```

## How It Works

```
Agent --> ToolProof Proxy --> Actual Tool
             |                    |
             |  signed receipt    |
             |<-------------------|
             |
             v
        Receipt Store (JSONL)

Later:
Agent claims "I called X with Y and got Z"
             |
             v
        Verifier cross-references claims against receipts
             |
             v
        Trust Score: VERIFIED / UNVERIFIED / TAMPERED
```

### Execution Receipt

Every tool call produces a signed receipt:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": 1712400000.0,
  "tool_name": "search_database",
  "arguments": {"query": "SELECT * FROM users"},
  "response": [{"id": 1, "name": "Alice"}],
  "duration_ms": 142.3,
  "hash": "a1b2c3d4...",
  "hmac_sig": "e5f6g7h8..."
}
```

### Verdicts

| Verdict | Meaning |
|---|---|
| **VERIFIED** | Claim matches a receipt exactly |
| **UNVERIFIED** | No matching receipt found (possible hallucination) |
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

## Interceptors

Built-in interceptors for common patterns:

### HTTP

```python
from toolproof.interceptors import HTTPInterceptor

http = HTTPInterceptor(proxy, base_url="https://api.example.com")
response = http.get("/users", params={"role": "admin"})
# Receipt generated automatically
```

### Subprocess

```python
from toolproof.interceptors import SubprocessInterceptor

shell = SubprocessInterceptor(proxy)
result = shell.run(["grep", "-r", "TODO", "src/"])
# Receipt generated automatically
```

### MCP (Model Context Protocol)

```python
from toolproof.interceptors import MCPInterceptor

mcp = MCPInterceptor(proxy)
receipt = mcp.intercept_request(jsonrpc_request)
mcp.intercept_response(request_id, jsonrpc_response, receipt)
```

## Verify Agent Text Output

ToolProof can scan agent text output for tool call claims:

```python
agent_output = """
I searched the database for admin users and found 3 results.
Then I deleted user ID 99 from the system.
"""

results = verifier.verify_text(agent_output)
for r in results:
    print(f"{r.claim_tool}: {r.verdict.value}")
```

## CI / Automation

```bash
# JSON output for pipelines
toolproof verify output.json --json-output

# Exit codes: 0=all verified, 1=unverified found, 2=tampered found
toolproof verify output.json && echo "trusted" || echo "suspicious"
```

## Security

- Receipts are signed with SHA-256 by default
- Optional HMAC-SHA256 with a secret key for tamper-proof receipts
- Config stored at `~/.toolproof/config.json` with `0600` permissions
- Secret keys are never printed in full

## Community

Built with input from the [Saudi AI Community](https://x.com/i/communities/2032184341682643429).

## License

MIT -- Musa the Carpenter
