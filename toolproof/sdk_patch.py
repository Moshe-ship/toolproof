"""Monkey-patch OpenAI and Anthropic SDKs to auto-record tool calls.

Zero-config interception. Import and call patch — every tool_use
response gets a receipt automatically.

Usage:
    import toolproof
    toolproof.patch_openai()  # Patches globally

    # Now every OpenAI call with tools generates receipts
    client = openai.OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[...],
        tools=[...],
    )
    # Receipt already recorded for any tool_calls in the response

    # Check trust later
    store = toolproof.ReceiptStore()
    print(f"Recorded {store.count()} receipts")
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from toolproof.proxy import ToolProxy
from toolproof.receipt import ReceiptStore


_patched_openai = False
_patched_anthropic = False
_store: ReceiptStore | None = None
_proxy: ToolProxy | None = None


def _get_store_and_proxy(
    store: ReceiptStore | None = None,
    secret: str | None = None,
) -> tuple[ReceiptStore, ToolProxy]:
    """Get or create global store and proxy."""
    global _store, _proxy
    if store:
        _store = store
        _proxy = ToolProxy(_store, secret=secret)
    elif _store is None:
        _store = ReceiptStore()
        _proxy = ToolProxy(_store, secret=secret)
    assert _proxy is not None
    return _store, _proxy


def patch_openai(
    store: ReceiptStore | None = None,
    secret: str | None = None,
) -> None:
    """Patch the OpenAI SDK to record tool call receipts.

    After calling this, every chat.completions.create() call that
    returns tool_calls will generate receipts automatically.

    Args:
        store: Custom receipt store. Defaults to ~/.toolproof/receipts.jsonl
        secret: HMAC secret for signing receipts.
    """
    global _patched_openai
    if _patched_openai:
        return

    try:
        import openai
        from openai.resources.chat import completions as chat_mod
    except ImportError:
        raise ImportError("openai package not installed. Run: pip install openai")

    s, proxy = _get_store_and_proxy(store, secret)

    original_create = chat_mod.Completions.create

    def patched_create(self: Any, *args: Any, **kwargs: Any) -> Any:
        start = time.time()
        error_msg = None
        result = None

        try:
            result = original_create(self, *args, **kwargs)
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            raise
        finally:
            duration_ms = (time.time() - start) * 1000

            # Record the LLM call itself
            model = kwargs.get("model", "unknown")
            messages = kwargs.get("messages", [])
            tools = kwargs.get("tools", [])
            tool_names = [t.get("function", {}).get("name", "") for t in tools if isinstance(t, dict)]

            proxy.record(
                tool_name=f"openai:{model}",
                arguments={
                    "model": model,
                    "message_count": len(messages),
                    "tools": tool_names,
                },
                response=_extract_openai_response(result) if result else None,
                error=error_msg,
                duration_ms=duration_ms,
            )

            # Record individual tool calls from the response
            if result:
                _record_openai_tool_calls(result, proxy, duration_ms)

        return result

    chat_mod.Completions.create = patched_create
    _patched_openai = True


def _extract_openai_response(result: Any) -> dict:
    """Extract key info from OpenAI response."""
    try:
        choice = result.choices[0] if result.choices else None
        if choice is None:
            return {"finish_reason": "unknown"}
        return {
            "finish_reason": choice.finish_reason,
            "tool_calls_count": len(choice.message.tool_calls or []),
            "has_content": bool(choice.message.content),
        }
    except (AttributeError, IndexError):
        return {"raw": str(result)[:200]}


def _record_openai_tool_calls(result: Any, proxy: ToolProxy, parent_duration: float) -> None:
    """Record individual tool calls from OpenAI response."""
    try:
        for choice in result.choices:
            for tc in (choice.message.tool_calls or []):
                func_name = tc.function.name
                args_str = tc.function.arguments
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except json.JSONDecodeError:
                    args = {"raw": args_str}

                proxy.record(
                    tool_name=f"tool:{func_name}",
                    arguments=args,
                    response=None,  # Response comes from tool execution, not LLM
                    duration_ms=0,
                )
    except (AttributeError, TypeError):
        pass


def patch_anthropic(
    store: ReceiptStore | None = None,
    secret: str | None = None,
) -> None:
    """Patch the Anthropic SDK to record tool use receipts.

    After calling this, every messages.create() call that returns
    tool_use blocks will generate receipts automatically.

    Args:
        store: Custom receipt store. Defaults to ~/.toolproof/receipts.jsonl
        secret: HMAC secret for signing receipts.
    """
    global _patched_anthropic
    if _patched_anthropic:
        return

    try:
        import anthropic
        from anthropic.resources import messages as msg_mod
    except ImportError:
        raise ImportError("anthropic package not installed. Run: pip install anthropic")

    s, proxy = _get_store_and_proxy(store, secret)

    original_create = msg_mod.Messages.create

    def patched_create(self: Any, *args: Any, **kwargs: Any) -> Any:
        start = time.time()
        error_msg = None
        result = None

        try:
            result = original_create(self, *args, **kwargs)
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            raise
        finally:
            duration_ms = (time.time() - start) * 1000

            model = kwargs.get("model", "unknown")
            messages = kwargs.get("messages", [])
            tools = kwargs.get("tools", [])
            tool_names = [t.get("name", "") for t in tools if isinstance(t, dict)]

            proxy.record(
                tool_name=f"anthropic:{model}",
                arguments={
                    "model": model,
                    "message_count": len(messages),
                    "tools": tool_names,
                },
                response=_extract_anthropic_response(result) if result else None,
                error=error_msg,
                duration_ms=duration_ms,
            )

            # Record individual tool uses
            if result:
                _record_anthropic_tool_uses(result, proxy)

        return result

    msg_mod.Messages.create = patched_create
    _patched_anthropic = True


def _extract_anthropic_response(result: Any) -> dict:
    """Extract key info from Anthropic response."""
    try:
        content = result.content or []
        tool_uses = [b for b in content if hasattr(b, "type") and b.type == "tool_use"]
        text_blocks = [b for b in content if hasattr(b, "type") and b.type == "text"]
        return {
            "stop_reason": result.stop_reason,
            "tool_use_count": len(tool_uses),
            "text_blocks": len(text_blocks),
        }
    except (AttributeError, TypeError):
        return {"raw": str(result)[:200]}


def _record_anthropic_tool_uses(result: Any, proxy: ToolProxy) -> None:
    """Record individual tool_use blocks from Anthropic response."""
    try:
        for block in (result.content or []):
            if hasattr(block, "type") and block.type == "tool_use":
                proxy.record(
                    tool_name=f"tool:{block.name}",
                    arguments=block.input if isinstance(block.input, dict) else {},
                    response=None,
                    duration_ms=0,
                )
    except (AttributeError, TypeError):
        pass


def patch_all(
    store: ReceiptStore | None = None,
    secret: str | None = None,
) -> None:
    """Patch all available SDKs."""
    errors = []
    try:
        patch_openai(store, secret)
    except ImportError:
        errors.append("openai not installed")

    try:
        patch_anthropic(store, secret)
    except ImportError:
        errors.append("anthropic not installed")

    if len(errors) == 2:
        raise ImportError(f"No SDK available to patch: {', '.join(errors)}")


def unpatch_all() -> None:
    """Remove all patches (best-effort, mainly for testing)."""
    global _patched_openai, _patched_anthropic
    _patched_openai = False
    _patched_anthropic = False
