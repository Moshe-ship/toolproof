"""Rich terminal output for ToolProof."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from toolproof.trust import TrustReport, TrustScore
from toolproof.verifier import Verdict, VerificationResult
from toolproof.receipt import Receipt

console = Console()


VERDICT_COLORS = {
    Verdict.VERIFIED: "green",
    Verdict.UNVERIFIED: "yellow",
    Verdict.TAMPERED: "red",
}

GRADE_COLORS = {
    "A": "green",
    "B": "blue",
    "C": "yellow",
    "D": "red",
    "F": "red bold",
}

RISK_COLORS = {
    "LOW": "green",
    "MEDIUM": "yellow",
    "HIGH": "red bold",
}


def print_trust_score(score: TrustScore) -> None:
    """Print a trust score summary."""
    grade_color = GRADE_COLORS.get(score.grade, "white")
    risk_color = RISK_COLORS.get(score.risk_level, "white")

    panel_content = Text()
    panel_content.append(f"Score: {score.score_percent:.1f}%  ", style="bold")
    panel_content.append(f"Grade: ", style="dim")
    panel_content.append(f"{score.grade}", style=grade_color)
    panel_content.append(f"  Risk: ", style="dim")
    panel_content.append(f"{score.risk_level}", style=risk_color)

    console.print(Panel(panel_content, title="Trust Score", border_style="bold"))


def print_verification_table(results: list[VerificationResult]) -> None:
    """Print verification results as a table."""
    table = Table(title="Verification Results", show_lines=True)
    table.add_column("Tool", style="cyan")
    table.add_column("Verdict", justify="center")
    table.add_column("Details", style="dim")

    for r in results:
        color = VERDICT_COLORS[r.verdict]
        verdict_text = Text(r.verdict.value.upper(), style=color)
        table.add_row(r.claim_tool, verdict_text, r.details)

    console.print(table)


def print_report(report: TrustReport) -> None:
    """Print a full trust report."""
    score = report.trust_score

    console.print()
    print_trust_score(score)
    console.print()

    # Summary counts
    console.print(f"  [green]{score.verified}[/green] verified  "
                  f"[yellow]{score.unverified}[/yellow] unverified  "
                  f"[red]{score.tampered}[/red] tampered  "
                  f"[dim]{score.total} total[/dim]")
    console.print()

    if report.results:
        print_verification_table(report.results)

    if report.tampered:
        console.print()
        console.print("[red bold]Tampered claims detected:[/red bold]")
        for r in report.tampered:
            console.print(f"  [red]x[/red] {r.claim_tool}: {r.details}")

    if report.unverified:
        console.print()
        console.print("[yellow]Unverified claims (possible hallucinations):[/yellow]")
        for r in report.unverified:
            console.print(f"  [yellow]?[/yellow] {r.claim_tool}: {r.details}")


def print_receipt(receipt: Receipt) -> None:
    """Print a single receipt."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Field", style="dim")
    table.add_column("Value")

    table.add_row("ID", receipt.id)
    table.add_row("Tool", receipt.tool_name)
    table.add_row("Arguments", str(receipt.arguments))
    table.add_row("Response", str(receipt.response)[:200])
    if receipt.error:
        table.add_row("Error", f"[red]{receipt.error}[/red]")
    table.add_row("Duration", f"{receipt.duration_ms:.1f}ms")
    table.add_row("Hash", receipt.hash[:16] + "...")
    if receipt.hmac_sig:
        table.add_row("HMAC", receipt.hmac_sig[:16] + "...")

    console.print(Panel(table, title=f"Receipt: {receipt.tool_name}", border_style="dim"))


def print_receipts_summary(receipts: list[Receipt]) -> None:
    """Print summary of all receipts."""
    table = Table(title=f"{len(receipts)} Receipts")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Tool", style="cyan")
    table.add_column("Args", max_width=40)
    table.add_column("Duration", justify="right")
    table.add_column("Error", style="red")
    table.add_column("Hash", style="dim", max_width=12)

    for i, r in enumerate(receipts, 1):
        args_str = str(r.arguments)[:40]
        error_str = r.error[:20] if r.error else ""
        table.add_row(
            str(i),
            r.tool_name,
            args_str,
            f"{r.duration_ms:.0f}ms",
            error_str,
            r.hash[:12],
        )

    console.print(table)
