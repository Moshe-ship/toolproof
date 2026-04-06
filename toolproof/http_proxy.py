"""HTTP reverse proxy that transparently records all tool calls.

Sits between an agent and its tool server. Every request/response pair
generates a signed receipt. The agent doesn't know it's being watched.

Usage:
    # Proxy all requests to localhost:3000, record receipts
    toolproof proxy --port 8080 --target http://localhost:3000

    # Proxy OpenAI API calls
    toolproof proxy --port 9090 --target https://api.openai.com

    # Proxy Hermes/OpenClaw tool server
    toolproof proxy --port 8081 --target http://localhost:5001

Architecture:
    Agent --> ToolProof Proxy (:8080) --> Real Tool Server (:3000)
                   |
                   v
            Receipt Store (signed JSONL)
"""

from __future__ import annotations

import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, urljoin
from typing import Any, Optional

import httpx

from toolproof.proxy import ToolProxy
from toolproof.receipt import ReceiptStore, redact_sensitive


class ProxyHandler(BaseHTTPRequestHandler):
    """HTTP request handler that proxies and records tool calls."""

    # Set by ProxyServer before serving
    target_url: str = ""
    tool_proxy: ToolProxy | None = None
    _client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self.__class__._client is None:
            self.__class__._client = httpx.Client(timeout=60.0)
        return self.__class__._client

    def _extract_tool_name(self, method: str, path: str, body: dict | None) -> str:
        """Extract a meaningful tool name from the request.

        Handles:
        - OpenAI chat completions (tool_use in response)
        - MCP tools/call JSON-RPC
        - Hermes/OpenClaw skill invocations
        - Generic REST endpoints
        """
        # MCP JSON-RPC
        if body and body.get("method") == "tools/call":
            params = body.get("params", {})
            return f"mcp:{params.get('name', 'unknown')}"

        # OpenAI-style chat completions
        if "/chat/completions" in path:
            return "llm:chat_completions"

        # Hermes skill execution
        if "/execute" in path or "/skill" in path:
            skill = body.get("skill", body.get("name", "")) if body else ""
            return f"hermes:{skill}" if skill else "hermes:execute"

        # OpenClaw
        if "/claw" in path or "/openclaw" in path:
            action = body.get("action", body.get("command", "")) if body else ""
            return f"openclaw:{action}" if action else "openclaw:call"

        # Generic REST
        segments = [s for s in path.split("/") if s and not s.startswith("v")]
        endpoint = segments[-1] if segments else path
        return f"http:{method.lower()}:{endpoint}"

    def _proxy_request(self, method: str) -> None:
        """Forward request to target, record receipt."""
        client = self._get_client()
        proxy = self.__class__.tool_proxy
        target = self.__class__.target_url

        # Build target URL — SECURITY: prevent SSRF via path override
        url = target.rstrip("/") + self.path
        parsed = urlparse(url)
        target_parsed = urlparse(target)
        if parsed.netloc != target_parsed.netloc or parsed.scheme != target_parsed.scheme:
            self.send_error(400, "Bad request")
            return

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b""

        # Parse body for tool name extraction
        body_dict = None
        if body_bytes:
            try:
                body_dict = json.loads(body_bytes)
            except (json.JSONDecodeError, ValueError):
                pass

        tool_name = self._extract_tool_name(method, self.path, body_dict)

        # Forward headers (skip hop-by-hop)
        skip_headers = {"host", "connection", "transfer-encoding", "keep-alive"}
        headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in skip_headers
        }

        # Record arguments — SECURITY: redact sensitive keys
        arguments: dict[str, Any] = {
            "method": method,
            "path": self.path,
            "url": url,
        }
        if body_dict:
            arguments["body"] = redact_sensitive(_truncate_body(body_dict))

        start = time.time()
        error_msg = None
        response_data = None
        status_code = 502

        try:
            resp = client.request(
                method=method,
                url=url,
                headers=headers,
                content=body_bytes,
            )
            status_code = resp.status_code

            # Parse response for receipt
            try:
                response_data = resp.json()
            except (json.JSONDecodeError, ValueError):
                response_data = {
                    "status_code": status_code,
                    "body_preview": resp.text[:500],
                }

            # Extract tool calls from LLM responses
            if isinstance(response_data, dict):
                tool_calls = _extract_tool_calls_from_response(response_data)
                if tool_calls:
                    response_data = {
                        "status_code": status_code,
                        "tool_calls": tool_calls,
                        "raw_keys": list(response_data.keys()),
                    }

            # Forward response to agent
            self.send_response(status_code)
            for key, val in resp.headers.items():
                if key.lower() not in {"transfer-encoding", "connection", "content-encoding", "content-length"}:
                    self.send_header(key, val)
            response_bytes = resp.content
            self.send_header("Content-Length", str(len(response_bytes)))
            self.end_headers()
            self.wfile.write(response_bytes)

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            self.send_error(502, "Proxy error: upstream unavailable")
        finally:
            duration_ms = (time.time() - start) * 1000
            if proxy:
                proxy.record(
                    tool_name=tool_name,
                    arguments=arguments,
                    response=_truncate_response(response_data),
                    error=error_msg,
                    duration_ms=duration_ms,
                )

    def do_GET(self) -> None:
        self._proxy_request("GET")

    def do_POST(self) -> None:
        self._proxy_request("POST")

    def do_PUT(self) -> None:
        self._proxy_request("PUT")

    def do_DELETE(self) -> None:
        self._proxy_request("DELETE")

    def do_PATCH(self) -> None:
        self._proxy_request("PATCH")

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight — restricted to localhost only."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, PATCH")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging — we log via receipts."""
        pass


class ProxyServer:
    """ToolProof HTTP proxy server.

    Usage:
        store = ReceiptStore()
        proxy = ToolProxy(store)
        server = ProxyServer(
            target_url="http://localhost:3000",
            tool_proxy=proxy,
            port=8080,
        )
        server.start()  # Blocks
        # or
        server.start_background()  # Returns immediately
    """

    def __init__(
        self,
        target_url: str,
        tool_proxy: ToolProxy,
        host: str = "127.0.0.1",
        port: int = 8080,
    ):
        self.target_url = target_url.rstrip("/")
        self.tool_proxy = tool_proxy
        self.host = host
        self.port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start proxy server (blocking)."""
        ProxyHandler.target_url = self.target_url
        ProxyHandler.tool_proxy = self.tool_proxy
        ProxyHandler._client = None

        self._server = HTTPServer((self.host, self.port), ProxyHandler)
        self._server.serve_forever()

    def start_background(self) -> None:
        """Start proxy server in background thread."""
        ProxyHandler.target_url = self.target_url
        ProxyHandler.tool_proxy = self.tool_proxy
        ProxyHandler._client = None

        self._server = HTTPServer((self.host, self.port), ProxyHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the proxy server."""
        if self._server:
            self._server.shutdown()
            if ProxyHandler._client:
                ProxyHandler._client.close()
                ProxyHandler._client = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


def _extract_tool_calls_from_response(data: dict) -> list[dict]:
    """Extract tool calls from OpenAI/Anthropic-style responses."""
    calls = []

    # OpenAI format
    choices = data.get("choices", [])
    for choice in choices:
        msg = choice.get("message", {})
        for tc in msg.get("tool_calls", []):
            func = tc.get("function", {})
            args = func.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"raw": args}
            calls.append({"name": func.get("name", ""), "arguments": args})

    # Anthropic format
    content = data.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls.append({
                    "name": block.get("name", ""),
                    "arguments": block.get("input", {}),
                })

    return calls


def _truncate_body(body: dict, max_size: int = 2000) -> dict:
    """Truncate request body for storage."""
    serialized = json.dumps(body, ensure_ascii=False)
    if len(serialized) <= max_size:
        return body
    # Keep structure but truncate large values
    truncated = {}
    for key, val in body.items():
        if isinstance(val, str) and len(val) > 200:
            truncated[key] = val[:200] + "..."
        elif isinstance(val, list) and len(val) > 10:
            truncated[key] = val[:10] + [f"... ({len(val)} total)"]
        else:
            truncated[key] = val
    return truncated


def _truncate_response(data: Any, max_size: int = 4000) -> Any:
    """Truncate response data for storage."""
    if data is None:
        return None
    serialized = json.dumps(data, ensure_ascii=False, default=str)
    if len(serialized) <= max_size:
        return data
    if isinstance(data, dict):
        truncated = {}
        for key, val in data.items():
            if isinstance(val, str) and len(val) > 500:
                truncated[key] = val[:500] + "..."
            elif isinstance(val, list) and len(val) > 20:
                truncated[key] = val[:20]
            else:
                truncated[key] = val
        return truncated
    return data
