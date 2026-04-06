---
name: toolproof-audit
description: "Verify tool call claims — check if a tool was actually called with specific arguments. Returns VERIFIED/UNVERIFIED/TAMPERED."
metadata: {"openclaw": {"emoji": "S", "requires": {"bins": ["toolproof"]}}}
---

# ToolProof Audit

Verify whether a tool call actually happened.

## When to use

When you want to confirm that a tool was actually executed (not hallucinated):

```
/toolproof-audit search_database {"query": "users"}
```

## What it does

1. Checks the receipt store at `~/.toolproof/receipts.jsonl`
2. Finds receipts matching the tool name and arguments
3. Verifies cryptographic signatures
4. Returns verdict: **VERIFIED**, **UNVERIFIED**, or **TAMPERED**

## CLI usage

```bash
# Verify a specific claim
toolproof verify claims.json

# Check all recent tool calls
toolproof status
```

## Verdicts

- **VERIFIED** — Receipt matches. The tool was called with these arguments.
- **UNVERIFIED** — No matching receipt found. Possible hallucination.
- **TAMPERED** — Receipt exists but arguments or response differ. Definite hallucination.
