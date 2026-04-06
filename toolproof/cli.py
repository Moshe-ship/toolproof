"""CLI for ToolProof."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click
from rich.console import Console

from toolproof.receipt import ReceiptStore
from toolproof.verifier import Verifier, AgentClaim
from toolproof.trust import TrustReport
from toolproof import display

console = Console()

DEFAULT_STORE_PATH = Path.home() / ".toolproof" / "receipts.jsonl"
CONFIG_PATH = Path.home() / ".toolproof" / "config.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}


def _save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
    os.chmod(str(CONFIG_PATH), 0o600)


@click.group()
@click.version_option(package_name="toolproof")
def main() -> None:
    """ToolProof - Agent tool verification.

    Agents lie about tool calls. ToolProof catches them.
    """
    pass


@main.command()
@click.option("--path", type=click.Path(), help="Receipt store path")
def status(path: str | None) -> None:
    """Show receipt store status."""
    store_path = Path(path) if path else DEFAULT_STORE_PATH
    if not store_path.exists():
        console.print("[dim]No receipts recorded yet.[/dim]")
        console.print(f"Store path: {store_path}")
        return

    store = ReceiptStore(store_path)
    console.print(f"[bold]ToolProof Status[/bold]")
    console.print(f"  Store: {store_path}")
    console.print(f"  Receipts: {store.count()}")

    if store.count() > 0:
        tools = {}
        for r in store.all():
            tools[r.tool_name] = tools.get(r.tool_name, 0) + 1
        console.print(f"  Tools: {len(tools)}")
        for name, count in sorted(tools.items(), key=lambda x: -x[1]):
            console.print(f"    {name}: {count}")


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--path", type=click.Path(), help="Receipt store path")
@click.option("--secret", envvar="TOOLPROOF_SECRET", help="HMAC secret key")
@click.option("--json-output", is_flag=True, help="Output as JSON")
def verify(input_file: str, path: str | None, secret: str | None, json_output: bool) -> None:
    """Verify agent claims against receipts.

    INPUT_FILE should be a JSON file with agent claims, or a text file
    with agent output to scan for claims.
    """
    store_path = Path(path) if path else DEFAULT_STORE_PATH
    if not store_path.exists():
        console.print("[red]No receipts found. Record tool calls first.[/red]")
        sys.exit(1)

    config = _load_config()
    secret = secret or config.get("secret")
    store = ReceiptStore(store_path)
    verifier = Verifier(store, secret=secret)

    input_path = Path(input_file)
    content = input_path.read_text(encoding="utf-8")

    # Try JSON first
    try:
        data = json.loads(content)
        if isinstance(data, list):
            claims = [AgentClaim.from_dict(item) for item in data]
        elif isinstance(data, dict):
            claims = [AgentClaim.from_dict(data)]
        else:
            console.print("[red]Invalid JSON format. Expected object or array of claims.[/red]")
            sys.exit(1)
        results = verifier.verify_claims(claims)
    except json.JSONDecodeError:
        # Fall back to text scanning
        results = verifier.verify_text(content)

    if not results:
        console.print("[dim]No tool call claims found in input.[/dim]")
        return

    report = TrustReport(results=results)

    if json_output:
        click.echo(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        display.print_report(report)

    # Exit with non-zero if tampered
    if report.tampered:
        sys.exit(2)
    if report.unverified:
        sys.exit(1)


@main.command()
@click.option("--path", type=click.Path(), help="Receipt store path")
@click.option("--json-output", is_flag=True, help="Output as JSON")
def report(path: str | None, json_output: bool) -> None:
    """Show all recorded receipts."""
    store_path = Path(path) if path else DEFAULT_STORE_PATH
    if not store_path.exists():
        console.print("[dim]No receipts recorded yet.[/dim]")
        return

    store = ReceiptStore(store_path)
    receipts = store.all()

    if json_output:
        click.echo(json.dumps([r.to_dict() for r in receipts], indent=2, ensure_ascii=False))
    else:
        display.print_receipts_summary(receipts)


@main.command()
@click.argument("receipt_id")
@click.option("--path", type=click.Path(), help="Receipt store path")
def inspect(receipt_id: str, path: str | None) -> None:
    """Inspect a specific receipt by ID or hash prefix."""
    store_path = Path(path) if path else DEFAULT_STORE_PATH
    store = ReceiptStore(store_path)

    receipt = store.find_by_id(receipt_id)
    if not receipt:
        # Try hash prefix
        for r in store.all():
            if r.hash.startswith(receipt_id) or r.id.startswith(receipt_id):
                receipt = r
                break

    if not receipt:
        console.print(f"[red]Receipt not found: {receipt_id}[/red]")
        sys.exit(1)

    display.print_receipt(receipt)


@main.command()
@click.option("--path", type=click.Path(), help="Receipt store path")
@click.confirmation_option(prompt="Clear all receipts?")
def clear(path: str | None) -> None:
    """Clear all recorded receipts."""
    store_path = Path(path) if path else DEFAULT_STORE_PATH
    store = ReceiptStore(store_path)
    count = store.count()
    store.clear()
    console.print(f"Cleared {count} receipts.")


@main.command()
@click.option("--secret", prompt="HMAC secret key (leave empty for none)",
              default="", hide_input=True)
@click.option("--store-path", prompt="Receipt store path",
              default=str(DEFAULT_STORE_PATH))
def config(secret: str, store_path: str) -> None:
    """Configure ToolProof settings."""
    cfg = _load_config()
    if secret:
        cfg["secret"] = secret
    cfg["store_path"] = store_path
    _save_config(cfg)
    console.print("[green]Configuration saved.[/green]")
    console.print(f"  Store: {store_path}")
    if secret:
        console.print(f"  Secret: {secret[:2]}...{secret[-2:]}")
