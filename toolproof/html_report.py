"""Generate standalone HTML trust reports.

Usage:
    toolproof report --html > trust-report.html
    toolproof report --html --output report.html
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from typing import Any

from toolproof.receipt import Receipt, ReceiptStore
from toolproof.trust import TrustReport, TrustScore
from toolproof.verifier import Verdict, VerificationResult


def _esc(value: Any) -> str:
    """Escape HTML to prevent XSS."""
    return html.escape(str(value))


def generate_html_report(
    store: ReceiptStore,
    report: TrustReport | None = None,
    title: str = "ToolProof Trust Report",
) -> str:
    """Generate a standalone HTML report.

    If report is provided, includes verification results.
    Always includes receipt summary.
    """
    receipts = store.all()
    score = report.trust_score if report else None
    results = report.results if report else []

    # Group receipts by tool
    by_tool: dict[str, list[Receipt]] = {}
    for r in receipts:
        by_tool.setdefault(r.tool_name, []).append(r)

    # Build tool stats
    tool_stats = []
    for tool_name, tool_receipts in sorted(by_tool.items(), key=lambda x: -len(x[1])):
        errors = sum(1 for r in tool_receipts if r.error)
        avg_duration = sum(r.duration_ms for r in tool_receipts) / len(tool_receipts)
        tool_stats.append({
            "name": tool_name,
            "count": len(tool_receipts),
            "errors": errors,
            "avg_duration_ms": round(avg_duration, 1),
        })

    # Build verification rows
    verification_rows = ""
    for r in results:
        color = {"verified": "#22c55e", "unverified": "#eab308", "tampered": "#ef4444"}[r.verdict.value]
        verification_rows += f"""
        <tr>
            <td>{_esc(r.claim_tool)}</td>
            <td><span style="color:{color};font-weight:bold">{_esc(r.verdict.value.upper())}</span></td>
            <td style="color:#666">{_esc(r.details)}</td>
        </tr>"""

    # Build tool rows
    tool_rows = ""
    for ts in tool_stats:
        error_badge = f'<span style="color:#ef4444">{ts["errors"]} errors</span>' if ts["errors"] else ""
        tool_rows += f"""
        <tr>
            <td><code>{_esc(ts["name"])}</code></td>
            <td>{ts["count"]}</td>
            <td>{ts["avg_duration_ms"]}ms</td>
            <td>{error_badge}</td>
        </tr>"""

    # Trust score section
    score_section = ""
    if score:
        grade_color = {
            "A": "#22c55e", "B": "#3b82f6", "C": "#eab308", "D": "#ef4444", "F": "#ef4444",
        }.get(score.grade, "#666")
        risk_color = {
            "LOW": "#22c55e", "MEDIUM": "#eab308", "HIGH": "#ef4444",
        }.get(score.risk_level, "#666")

        score_section = f"""
        <div class="score-card">
            <div class="score-main">
                <div class="score-number">{score.score_percent:.1f}%</div>
                <div class="score-grade" style="color:{grade_color}">{score.grade}</div>
            </div>
            <div class="score-details">
                <div class="score-item">
                    <span class="label">Verified</span>
                    <span class="value" style="color:#22c55e">{score.verified}</span>
                </div>
                <div class="score-item">
                    <span class="label">Unverified</span>
                    <span class="value" style="color:#eab308">{score.unverified}</span>
                </div>
                <div class="score-item">
                    <span class="label">Tampered</span>
                    <span class="value" style="color:#ef4444">{score.tampered}</span>
                </div>
                <div class="score-item">
                    <span class="label">Risk</span>
                    <span class="value" style="color:{risk_color}">{score.risk_level}</span>
                </div>
            </div>
        </div>"""

    verification_section = ""
    if results:
        verification_section = f"""
        <h2>Verification Results</h2>
        <table>
            <thead><tr><th>Tool</th><th>Verdict</th><th>Details</th></tr></thead>
            <tbody>{verification_rows}</tbody>
        </table>"""

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title)}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, system-ui, sans-serif; background: #0a0a0a; color: #e5e5e5; padding: 2rem; max-width: 900px; margin: 0 auto; }}
h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
h2 {{ font-size: 1.1rem; margin: 2rem 0 1rem; color: #a3a3a3; }}
.subtitle {{ color: #666; font-size: 0.85rem; margin-bottom: 2rem; }}
.score-card {{ background: #141414; border: 1px solid #262626; border-radius: 8px; padding: 1.5rem; margin: 1.5rem 0; }}
.score-main {{ display: flex; align-items: baseline; gap: 1rem; margin-bottom: 1rem; }}
.score-number {{ font-size: 3rem; font-weight: 700; letter-spacing: -0.02em; }}
.score-grade {{ font-size: 2rem; font-weight: 700; }}
.score-details {{ display: flex; gap: 2rem; }}
.score-item {{ display: flex; flex-direction: column; }}
.score-item .label {{ font-size: 0.75rem; color: #666; text-transform: uppercase; letter-spacing: 0.05em; }}
.score-item .value {{ font-size: 1.25rem; font-weight: 600; }}
table {{ width: 100%; border-collapse: collapse; background: #141414; border: 1px solid #262626; border-radius: 8px; overflow: hidden; }}
th {{ text-align: left; padding: 0.75rem 1rem; background: #1a1a1a; color: #a3a3a3; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 500; }}
td {{ padding: 0.75rem 1rem; border-top: 1px solid #1f1f1f; font-size: 0.9rem; }}
code {{ background: #1a1a1a; padding: 0.15rem 0.4rem; border-radius: 3px; font-size: 0.85rem; }}
.footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #1f1f1f; color: #404040; font-size: 0.75rem; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="subtitle">Generated {now} &middot; {len(receipts)} receipts &middot; {len(by_tool)} tools</div>

{score_section}

{verification_section}

<h2>Tool Execution Summary</h2>
<table>
    <thead><tr><th>Tool</th><th>Calls</th><th>Avg Duration</th><th>Errors</th></tr></thead>
    <tbody>{tool_rows}</tbody>
</table>

<div class="footer">
    ToolProof &middot; Agents lie about tool calls. ToolProof catches them. &middot; toolproof.dev
</div>
</body>
</html>"""
