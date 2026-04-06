"""Watch mode and CI threshold enforcement.

Usage:
    # Watch receipts in real-time, alert on issues
    toolproof watch

    # CI mode: fail if trust drops below threshold
    toolproof watch --min-trust 0.8 --timeout 60

    # Watch with specific store
    toolproof watch --path /tmp/test-receipts.jsonl
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from toolproof.receipt import ReceiptStore
from toolproof.trust import TrustScore


console = Console()


class ReceiptWatcher:
    """Watch receipt store for changes and report in real-time."""

    def __init__(
        self,
        store: ReceiptStore,
        min_trust: float = 0.0,
        alert_on_error: bool = True,
    ):
        self.store = store
        self.min_trust = min_trust
        self.alert_on_error = alert_on_error
        self._last_count = 0
        self._tool_counts: dict[str, int] = {}
        self._error_counts: dict[str, int] = {}
        self._total_errors = 0

    def check(self) -> dict:
        """Check current state. Returns status dict."""
        receipts = self.store.all()
        current_count = len(receipts)
        new_receipts = receipts[self._last_count:]
        self._last_count = current_count

        # Update counts
        for r in new_receipts:
            self._tool_counts[r.tool_name] = self._tool_counts.get(r.tool_name, 0) + 1
            if r.error:
                self._error_counts[r.tool_name] = self._error_counts.get(r.tool_name, 0) + 1
                self._total_errors += 1

        # Calculate trust (simple: non-error / total)
        total = len(receipts)
        errors = sum(1 for r in receipts if r.error)
        clean = total - errors
        trust = clean / total if total > 0 else 1.0

        return {
            "total": total,
            "new": len(new_receipts),
            "tools": len(self._tool_counts),
            "errors": self._total_errors,
            "trust": trust,
            "below_threshold": trust < self.min_trust if self.min_trust > 0 else False,
        }

    def build_table(self, status: dict) -> Table:
        """Build a rich table for live display."""
        table = Table(title="ToolProof Watch", show_lines=False)
        table.add_column("Metric", style="dim")
        table.add_column("Value", justify="right")

        trust_pct = status["trust"] * 100
        trust_color = "green" if trust_pct >= 90 else "yellow" if trust_pct >= 70 else "red"

        table.add_row("Receipts", str(status["total"]))
        table.add_row("Tools", str(status["tools"]))
        table.add_row("Errors", Text(str(status["errors"]), style="red" if status["errors"] else "green"))
        table.add_row("Trust", Text(f"{trust_pct:.1f}%", style=trust_color))

        if self.min_trust > 0:
            threshold_str = f"{self.min_trust * 100:.0f}%"
            if status["below_threshold"]:
                table.add_row("Threshold", Text(f"BELOW {threshold_str}", style="red bold"))
            else:
                table.add_row("Threshold", Text(f"OK (>={threshold_str})", style="green"))

        # Top tools
        if self._tool_counts:
            table.add_row("", "")
            table.add_row(Text("Top Tools", style="bold"), "")
            for name, count in sorted(self._tool_counts.items(), key=lambda x: -x[1])[:8]:
                err = self._error_counts.get(name, 0)
                suffix = f" ({err} err)" if err else ""
                table.add_row(f"  {name}", f"{count}{suffix}")

        return table


def watch_live(
    store: ReceiptStore,
    min_trust: float = 0.0,
    interval: float = 2.0,
    timeout: float = 0.0,
) -> int:
    """Watch receipt store with live updating display.

    Args:
        store: Receipt store to watch.
        min_trust: Minimum trust threshold (0-1). Exit 1 if below.
        interval: Check interval in seconds.
        timeout: Stop after this many seconds (0 = run forever).

    Returns:
        Exit code (0 = ok, 1 = below threshold, 2 = error).
    """
    watcher = ReceiptWatcher(store, min_trust=min_trust)
    start_time = time.time()

    try:
        with Live(console=console, refresh_per_second=1) as live:
            while True:
                # Reload store to pick up new receipts
                store._receipts.clear()
                store._load()

                status = watcher.check()
                table = watcher.build_table(status)
                live.update(table)

                # CI mode: check threshold
                if min_trust > 0 and status["total"] > 0 and status["below_threshold"]:
                    console.print(f"\n[red bold]Trust {status['trust']:.1%} below threshold {min_trust:.1%}[/red bold]")
                    return 1

                # Timeout
                if timeout > 0 and (time.time() - start_time) >= timeout:
                    if min_trust > 0 and status["total"] == 0:
                        console.print("\n[yellow]Timeout with no receipts.[/yellow]")
                        return 0
                    return 0

                time.sleep(interval)

    except KeyboardInterrupt:
        console.print("\n[dim]Watch stopped.[/dim]")
        return 0


def ci_check(
    store: ReceiptStore,
    min_trust: float = 0.8,
    min_receipts: int = 1,
    json_output: bool = False,
) -> int:
    """One-shot CI check. Returns exit code.

    Args:
        store: Receipt store to check.
        min_trust: Minimum trust score (0-1).
        min_receipts: Minimum number of receipts required.
        json_output: Output results as JSON.

    Returns:
        0 if passing, 1 if failing.
    """
    receipts = store.all()
    total = len(receipts)
    errors = sum(1 for r in receipts if r.error)
    clean = total - errors
    trust = clean / total if total > 0 else 1.0

    result = {
        "total_receipts": total,
        "errors": errors,
        "trust_score": round(trust, 4),
        "min_trust": min_trust,
        "min_receipts": min_receipts,
        "pass": trust >= min_trust and total >= min_receipts,
    }

    if json_output:
        print(json.dumps(result, indent=2))
    else:
        if result["pass"]:
            console.print(f"[green]PASS[/green] Trust: {trust:.1%} ({total} receipts, {errors} errors)")
        else:
            reasons = []
            if trust < min_trust:
                reasons.append(f"trust {trust:.1%} < {min_trust:.1%}")
            if total < min_receipts:
                reasons.append(f"receipts {total} < {min_receipts}")
            console.print(f"[red]FAIL[/red] {', '.join(reasons)}")

    return 0 if result["pass"] else 1


# GitHub Action YAML template
GITHUB_ACTION_YAML = """# .github/workflows/toolproof.yml
name: ToolProof Trust Check

on:
  push:
    branches: [main]
  pull_request:

jobs:
  trust-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install ToolProof
        run: pip install toolproof

      - name: Run agent tests
        run: |
          # Your agent test command here
          python test_agent.py

      - name: Verify tool calls
        run: |
          toolproof ci --min-trust 0.8 --min-receipts 5
"""
