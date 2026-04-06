"""CLI for ToolProof."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console

from toolproof.receipt import ReceiptStore
from toolproof.verifier import Verifier, AgentClaim
from toolproof.trust import TrustReport
from toolproof.proxy import ToolProxy
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


def _get_store(path: str | None) -> ReceiptStore:
    store_path = Path(path) if path else DEFAULT_STORE_PATH
    return ReceiptStore(store_path)


def _get_secret(secret: str | None) -> str | None:
    if secret:
        return secret
    return _load_config().get("secret")


@click.group()
@click.version_option(package_name="toolproof")
def main() -> None:
    """ToolProof - Agent tool verification.

    Agents lie about tool calls. ToolProof catches them.
    """
    pass


# =========================================================================
# Core commands
# =========================================================================

@main.command()
@click.option("--path", type=click.Path(), help="Receipt store path")
def status(path: str | None) -> None:
    """Show receipt store status."""
    store = _get_store(path)
    if store.count() == 0:
        console.print("[dim]No receipts recorded yet.[/dim]")
        console.print(f"Store path: {store.path}")
        return

    console.print(f"[bold]ToolProof Status[/bold]")
    console.print(f"  Store: {store.path}")
    console.print(f"  Receipts: {store.count()}")

    tools: dict[str, int] = {}
    errors = 0
    for r in store.all():
        tools[r.tool_name] = tools.get(r.tool_name, 0) + 1
        if r.error:
            errors += 1

    console.print(f"  Tools: {len(tools)}")
    console.print(f"  Errors: {errors}")
    console.print()
    for name, count in sorted(tools.items(), key=lambda x: -x[1]):
        console.print(f"    {name}: {count}")


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--path", type=click.Path(), help="Receipt store path")
@click.option("--secret", envvar="TOOLPROOF_SECRET", help="HMAC secret key")
@click.option("--json-output", is_flag=True, help="Output as JSON")
def verify(input_file: str, path: str | None, secret: str | None, json_output: bool) -> None:
    """Verify agent claims against receipts.

    INPUT_FILE: JSON file with claims, or text file with agent output.
    """
    store = _get_store(path)
    if store.count() == 0:
        console.print("[red]No receipts found. Record tool calls first.[/red]")
        sys.exit(1)

    secret = _get_secret(secret)
    verifier = Verifier(store, secret=secret)

    content = Path(input_file).read_text(encoding="utf-8")

    try:
        data = json.loads(content)
        if isinstance(data, list):
            claims = [AgentClaim.from_dict(item) for item in data]
        elif isinstance(data, dict):
            claims = [AgentClaim.from_dict(data)]
        else:
            console.print("[red]Invalid JSON format.[/red]")
            sys.exit(1)
        results = verifier.verify_claims(claims)
    except json.JSONDecodeError:
        results = verifier.verify_text(content)

    if not results:
        console.print("[dim]No tool call claims found in input.[/dim]")
        return

    report = TrustReport(results=results)

    if json_output:
        click.echo(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        display.print_report(report)

    if report.tampered:
        sys.exit(2)
    if report.unverified:
        sys.exit(1)


@main.command()
@click.option("--path", type=click.Path(), help="Receipt store path")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--html", is_flag=True, help="Output as HTML report")
@click.option("--output", "-o", type=click.Path(), help="Write to file instead of stdout")
def report(path: str | None, json_output: bool, html: bool, output: str | None) -> None:
    """Show all recorded receipts."""
    store = _get_store(path)
    if store.count() == 0:
        console.print("[dim]No receipts recorded yet.[/dim]")
        return

    if html:
        from toolproof.html_report import generate_html_report
        html_content = generate_html_report(store)
        if output:
            Path(output).write_text(html_content, encoding="utf-8")
            console.print(f"[green]Report written to {output}[/green]")
        else:
            click.echo(html_content)
        return

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
    store = _get_store(path)
    receipt = store.find_by_id(receipt_id)
    if not receipt:
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
    store = _get_store(path)
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


# =========================================================================
# Proxy commands
# =========================================================================

@main.command("proxy")
@click.option("--port", "-p", default=8080, help="Proxy listen port")
@click.option("--target", "-t", required=True, help="Target URL to proxy to")
@click.option("--host", default="127.0.0.1", help="Proxy listen host")
@click.option("--path", type=click.Path(), help="Receipt store path")
@click.option("--secret", envvar="TOOLPROOF_SECRET", help="HMAC secret key")
def proxy_cmd(port: int, target: str, host: str, path: str | None, secret: str | None) -> None:
    """Start HTTP proxy that records tool calls.

    Sits between agent and tool server. Every request generates a signed receipt.

    Examples:

        toolproof proxy --target http://localhost:3000

        toolproof proxy --port 9090 --target https://api.openai.com

        toolproof proxy --target http://localhost:5001  # Hermes
    """
    from toolproof.http_proxy import ProxyServer

    store = _get_store(path)
    tp = ToolProxy(store, secret=_get_secret(secret))
    server = ProxyServer(target_url=target, tool_proxy=tp, host=host, port=port)

    console.print(f"[bold]ToolProof Proxy[/bold]")
    console.print(f"  Listening: http://{host}:{port}")
    console.print(f"  Target:    {target}")
    console.print(f"  Store:     {store.path}")
    console.print(f"  [dim]Press Ctrl+C to stop[/dim]")
    console.print()

    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
        console.print(f"\n[dim]Stopped. {store.count()} receipts recorded.[/dim]")


@main.command("wrap")
@click.argument("command", nargs=-1, required=True)
@click.option("--port", "-p", default=0, help="Proxy port (0 = auto)")
@click.option("--target", "-t", help="Target URL (auto-detected from common env vars)")
@click.option("--path", type=click.Path(), help="Receipt store path")
@click.option("--secret", envvar="TOOLPROOF_SECRET", help="HMAC secret key")
def wrap_cmd(command: tuple[str, ...], port: int, target: str | None, path: str | None, secret: str | None) -> None:
    """Run a command with automatic tool call recording.

    Starts a proxy, sets environment variables, runs your command,
    then reports receipts.

    Examples:

        toolproof wrap -- python agent.py

        toolproof wrap --target http://localhost:3000 -- node bot.js
    """
    import socket
    from toolproof.http_proxy import ProxyServer

    store = _get_store(path)
    tp = ToolProxy(store, secret=_get_secret(secret))

    # Auto-detect target from env
    if not target:
        for env_var in ["OPENAI_BASE_URL", "ANTHROPIC_BASE_URL", "LLM_BASE_URL"]:
            target = os.environ.get(env_var)
            if target:
                break
        if not target:
            target = "https://api.openai.com"

    # Auto-pick port
    if port == 0:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

    server = ProxyServer(target_url=target, tool_proxy=tp, host="127.0.0.1", port=port)
    server.start_background()

    proxy_url = f"http://127.0.0.1:{port}"
    console.print(f"[dim]Proxy: {proxy_url} -> {target}[/dim]")
    console.print(f"[dim]Running: {' '.join(command)}[/dim]")
    console.print()

    # Set env vars so the child process uses our proxy
    env = os.environ.copy()
    env["OPENAI_BASE_URL"] = f"{proxy_url}/v1"
    env["ANTHROPIC_BASE_URL"] = proxy_url
    env["HTTP_PROXY"] = proxy_url
    env["TOOLPROOF_ACTIVE"] = "1"
    env["TOOLPROOF_STORE"] = str(store.path)

    try:
        result = subprocess.run(list(command), env=env)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()

    console.print()
    console.print(f"[bold]ToolProof Results[/bold]")
    console.print(f"  Receipts recorded: {store.count()}")

    if store.count() > 0:
        display.print_receipts_summary(store.all())

    sys.exit(result.returncode if "result" in dir() else 1)


# =========================================================================
# Import commands
# =========================================================================

@main.command("import-claude")
@click.option("--session", help="Specific session ID")
@click.option("--limit", default=5, help="Number of recent sessions to import")
@click.option("--path", type=click.Path(), help="Receipt store path")
@click.option("--secret", envvar="TOOLPROOF_SECRET", help="HMAC secret key")
def import_claude(session: str | None, limit: int, path: str | None, secret: str | None) -> None:
    """Import tool calls from Claude Code sessions."""
    from toolproof.claude_reader import find_claude_sessions, import_claude_session

    store = _get_store(path)
    secret = _get_secret(secret)

    if session:
        # Find specific session
        claude_dir = Path.home() / ".claude" / "projects"
        matches = list(claude_dir.rglob(f"{session}*.jsonl"))
        if not matches:
            console.print(f"[red]Session not found: {session}[/red]")
            sys.exit(1)
        sessions = matches[:1]
    else:
        sessions = find_claude_sessions(limit=limit)

    if not sessions:
        console.print("[dim]No Claude Code sessions found.[/dim]")
        return

    total = 0
    for sess_path in sessions:
        receipts = import_claude_session(sess_path, store, secret)
        total += len(receipts)
        console.print(f"  [green]+{len(receipts)}[/green] from {sess_path.stem[:12]}...")

    console.print(f"\n[bold]{total} receipts imported from {len(sessions)} sessions.[/bold]")


@main.command("import-hermes")
@click.option("--profile", help="Hermes profile name")
@click.option("--path", type=click.Path(), help="Receipt store path")
@click.option("--secret", envvar="TOOLPROOF_SECRET", help="HMAC secret key")
def import_hermes(profile: str | None, path: str | None, secret: str | None) -> None:
    """Import tool calls from Hermes agent logs."""
    from toolproof.claude_reader import import_hermes_logs

    store = _get_store(path)
    receipts = import_hermes_logs(profile=profile, store=store, secret=_get_secret(secret))

    if not receipts:
        console.print("[dim]No Hermes logs found.[/dim]")
        return

    console.print(f"[bold]{len(receipts)} receipts imported from Hermes.[/bold]")


@main.command("import-openclaw")
@click.option("--path", type=click.Path(), help="Receipt store path")
@click.option("--secret", envvar="TOOLPROOF_SECRET", help="HMAC secret key")
def import_openclaw_cmd(path: str | None, secret: str | None) -> None:
    """Import tool calls from OpenClaw skill execution logs."""
    from toolproof.claude_reader import import_openclaw_logs

    store = _get_store(path)
    receipts = import_openclaw_logs(store=store, secret=_get_secret(secret))

    if not receipts:
        console.print("[dim]No OpenClaw logs found.[/dim]")
        return

    console.print(f"[bold]{len(receipts)} receipts imported from OpenClaw.[/bold]")


@main.command("import-all")
@click.option("--path", type=click.Path(), help="Receipt store path")
@click.option("--secret", envvar="TOOLPROOF_SECRET", help="HMAC secret key")
def import_all_cmd(path: str | None, secret: str | None) -> None:
    """Import from all available sources (Claude Code, Hermes, OpenClaw)."""
    from toolproof.claude_reader import import_all

    store = _get_store(path)
    counts = import_all(store, secret=_get_secret(secret))

    total = sum(counts.values())
    if total == 0:
        console.print("[dim]No logs found from any source.[/dim]")
        return

    console.print(f"[bold]{total} receipts imported:[/bold]")
    for source, count in counts.items():
        if count > 0:
            console.print(f"  {source}: {count}")


# =========================================================================
# Watch / CI commands
# =========================================================================

@main.command("watch")
@click.option("--path", type=click.Path(), help="Receipt store path")
@click.option("--min-trust", type=float, default=0.0, help="Minimum trust threshold (0-1)")
@click.option("--interval", type=float, default=2.0, help="Check interval in seconds")
@click.option("--timeout", type=float, default=0.0, help="Stop after N seconds (0=forever)")
def watch_cmd(path: str | None, min_trust: float, interval: float, timeout: float) -> None:
    """Watch receipt store in real-time.

    Shows live updating dashboard of tool calls and trust score.

    Examples:

        toolproof watch

        toolproof watch --min-trust 0.8 --timeout 60
    """
    from toolproof.watch import watch_live

    store = _get_store(path)
    exit_code = watch_live(store, min_trust=min_trust, interval=interval, timeout=timeout)
    sys.exit(exit_code)


@main.command("ci")
@click.option("--path", type=click.Path(), help="Receipt store path")
@click.option("--min-trust", type=float, default=0.8, help="Minimum trust score (0-1)")
@click.option("--min-receipts", type=int, default=1, help="Minimum receipts required")
@click.option("--json-output", is_flag=True, help="Output as JSON")
def ci_cmd(path: str | None, min_trust: float, min_receipts: int, json_output: bool) -> None:
    """One-shot CI trust check.

    Exits 0 if passing, 1 if failing. Use in CI pipelines.

    Examples:

        toolproof ci --min-trust 0.8

        toolproof ci --min-trust 0.9 --min-receipts 10 --json-output
    """
    from toolproof.watch import ci_check

    store = _get_store(path)
    exit_code = ci_check(store, min_trust=min_trust, min_receipts=min_receipts, json_output=json_output)
    sys.exit(exit_code)


@main.command("github-action")
def github_action() -> None:
    """Print a GitHub Action YAML template for CI integration."""
    from toolproof.watch import GITHUB_ACTION_YAML
    click.echo(GITHUB_ACTION_YAML)
