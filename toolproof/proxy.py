"""Core proxy that intercepts tool calls and generates receipts."""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from toolproof.receipt import Receipt, ReceiptStore


class ToolProxy:
    """Proxy wrapper around tool functions that generates execution receipts.

    Usage:
        store = ReceiptStore()
        proxy = ToolProxy(store, secret="my-key")

        # Wrap a function
        safe_search = proxy.wrap(search_database)
        result = safe_search(query="users")

        # Or record manually
        receipt = proxy.record("search_database", {"query": "users"}, actual_result)
    """

    def __init__(self, store: ReceiptStore, secret: Optional[str] = None):
        self.store = store
        self.secret = secret

    def wrap(self, func: Callable, tool_name: Optional[str] = None) -> Callable:
        """Wrap a tool function to automatically generate receipts.

        Args:
            func: The tool function to wrap.
            tool_name: Override name (defaults to func.__name__).

        Returns:
            Wrapped function that records receipts.
        """
        name = tool_name or getattr(func, "__name__", str(func))

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            error = None
            result = None

            try:
                result = func(*args, **kwargs)
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                raise
            finally:
                duration_ms = (time.time() - start) * 1000
                # Convert positional args to dict for recording
                arguments = kwargs.copy()
                if args:
                    import inspect
                    try:
                        sig = inspect.signature(func)
                        params = list(sig.parameters.keys())
                        for i, arg in enumerate(args):
                            if i < len(params):
                                arguments[params[i]] = arg
                    except (ValueError, TypeError):
                        arguments["_positional"] = list(args)

                receipt = Receipt(
                    tool_name=name,
                    arguments=arguments,
                    response=result,
                    error=error,
                    duration_ms=duration_ms,
                )
                receipt.sign(self.secret)
                self.store.add(receipt)

            return result

        wrapper.__name__ = name
        wrapper.__wrapped__ = func
        return wrapper

    def record(
        self,
        tool_name: str,
        arguments: dict,
        response: Any,
        error: Optional[str] = None,
        duration_ms: float = 0.0,
    ) -> Receipt:
        """Manually record a tool execution receipt.

        Use this when you can't wrap the function directly (e.g., HTTP interceptor).
        """
        receipt = Receipt(
            tool_name=tool_name,
            arguments=arguments,
            response=response,
            error=error,
            duration_ms=duration_ms,
        )
        receipt.sign(self.secret)
        self.store.add(receipt)
        return receipt

    def wrap_dict(self, tools: dict[str, Callable]) -> dict[str, Callable]:
        """Wrap a dictionary of tool functions.

        Args:
            tools: {"tool_name": function, ...}

        Returns:
            Same dict with all functions wrapped.
        """
        return {name: self.wrap(func, name) for name, func in tools.items()}
