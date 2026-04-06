---
name: toolproof-report
description: "Generate trust report — show tool call receipts, trust score, token costs, and flagged issues."
metadata: {"openclaw": {"emoji": "R", "requires": {"bins": ["toolproof"]}}}
---

# ToolProof Report

Generate a trust report for the current session.

## When to use

When you want to see:
- How many tool calls were recorded
- Trust score and grade
- Token costs per tool
- Any flagged issues

```
/toolproof-report
```

## Output

```
ToolProof Trust Report
========================================
Trust Score: 94.2% (Grade: A)
Receipts: 47 (3 errors)
Cost: $0.2847
Tokens: 125,000 in / 34,000 out

Tool Breakdown:
  Read: 18 calls ($0.0234)
  Bash: 12 calls (2 errors) ($0.0891)
  Write: 9 calls ($0.0156)
  Grep: 8 calls ($0.0089)
```

## Formats

- `summary` — Quick overview (default)
- `detailed` — Full breakdown by tool
- `json` — Machine-readable output
- `html` — Standalone HTML report (via CLI: `toolproof report --html`)
