"""Built-in interceptors for common tool patterns."""

from __future__ import annotations

import json
import subprocess
import time
from typing import Any, Optional

import httpx

from toolproof.proxy import ToolProxy
from toolproof.receipt import Receipt, ReceiptStore


class HTTPInterceptor:
    """Intercept HTTP tool calls and generate receipts.

    Wraps httpx client to record all requests as tool executions.
    """

    def __init__(self, proxy: ToolProxy, base_url: Optional[str] = None):
        self.proxy = proxy
        self.base_url = base_url
        self._client = httpx.Client(base_url=base_url)

    def request(
        self,
        method: str,
        url: str,
        tool_name: Optional[str] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request and record a receipt."""
        name = tool_name or f"http_{method.lower()}_{url.split('/')[-1]}"
        arguments = {
            "method": method,
            "url": url,
        }
        if "json" in kwargs:
            arguments["body"] = kwargs["json"]
        if "params" in kwargs:
            arguments["params"] = kwargs["params"]

        start = time.time()
        error = None
        response_data = None

        try:
            resp = self._client.request(method, url, **kwargs)
            try:
                response_data = resp.json()
            except (json.JSONDecodeError, ValueError):
                response_data = {"status_code": resp.status_code, "text": resp.text[:500]}
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            raise
        finally:
            duration_ms = (time.time() - start) * 1000
            self.proxy.record(
                tool_name=name,
                arguments=arguments,
                response=response_data,
                error=error,
                duration_ms=duration_ms,
            )

        return resp

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HTTPInterceptor:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class SubprocessInterceptor:
    """Intercept subprocess/shell tool calls and generate receipts."""

    def __init__(self, proxy: ToolProxy):
        self.proxy = proxy

    def run(
        self,
        command: list[str] | str,
        tool_name: Optional[str] = None,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess:
        """Run a subprocess and record a receipt."""
        if isinstance(command, list):
            name = tool_name or f"subprocess_{command[0]}"
            arguments = {"command": command}
        else:
            name = tool_name or f"shell_{command.split()[0]}"
            arguments = {"command": command}

        start = time.time()
        error = None
        response_data = None

        kwargs.setdefault("capture_output", True)
        kwargs.setdefault("text", True)

        try:
            result = subprocess.run(command, **kwargs)
            response_data = {
                "returncode": result.returncode,
                "stdout": result.stdout[:2000] if result.stdout else "",
                "stderr": result.stderr[:2000] if result.stderr else "",
            }
            if result.returncode != 0:
                error = f"exit code {result.returncode}"
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            raise
        finally:
            duration_ms = (time.time() - start) * 1000
            self.proxy.record(
                tool_name=name,
                arguments=arguments,
                response=response_data,
                error=error,
                duration_ms=duration_ms,
            )

        return result


class MCPInterceptor:
    """Intercept MCP (Model Context Protocol) tool calls.

    Reads MCP JSON-RPC messages and generates receipts for tool calls.
    """

    def __init__(self, proxy: ToolProxy):
        self.proxy = proxy

    def intercept_request(self, message: dict) -> Optional[Receipt]:
        """Record an MCP tool call request.

        Call this with the JSON-RPC request message. The receipt is created
        but response is None until intercept_response is called.
        """
        if message.get("method") != "tools/call":
            return None

        params = message.get("params", {})
        tool_name = params.get("name", "unknown_mcp_tool")
        arguments = params.get("arguments", {})

        receipt = self.proxy.record(
            tool_name=tool_name,
            arguments=arguments,
            response=None,
            duration_ms=0.0,
        )
        return receipt

    def intercept_response(self, request_id: str, response: dict, receipt: Receipt) -> None:
        """Update a receipt with the MCP tool response.

        Note: This creates a NEW receipt with the response since receipts
        are append-only.
        """
        result = response.get("result", {})
        content = result.get("content", [])

        response_data = None
        if content:
            if len(content) == 1 and content[0].get("type") == "text":
                response_data = content[0].get("text")
            else:
                response_data = content

        self.proxy.record(
            tool_name=receipt.tool_name,
            arguments=receipt.arguments,
            response=response_data,
            duration_ms=0.0,
        )
