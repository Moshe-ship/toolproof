"""Tests for HTTP proxy server."""

import json
import tempfile
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import httpx

from toolproof.proxy import ToolProxy
from toolproof.receipt import ReceiptStore
from toolproof.http_proxy import ProxyServer, _extract_tool_calls_from_response


class MockToolHandler(BaseHTTPRequestHandler):
    """Simple mock tool server."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"result": "hello", "path": self.path}).encode())

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        resp = {"received": True, "path": self.path}
        try:
            resp["body"] = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            pass
        self.wfile.write(json.dumps(resp).encode())

    def log_message(self, format, *args):
        pass


def test_proxy_records_get_request():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ReceiptStore(Path(tmpdir) / "test.jsonl")
        proxy = ToolProxy(store)

        # Start mock target
        target = HTTPServer(("127.0.0.1", 0), MockToolHandler)
        target_port = target.server_address[1]
        target_thread = threading.Thread(target=target.serve_forever, daemon=True)
        target_thread.start()

        # Start proxy
        server = ProxyServer(
            target_url=f"http://127.0.0.1:{target_port}",
            tool_proxy=proxy,
            port=0,
        )
        # Get actual port
        from toolproof.http_proxy import ProxyHandler, HTTPServer as StdHTTPServer
        ProxyHandler.target_url = f"http://127.0.0.1:{target_port}"
        ProxyHandler.tool_proxy = proxy
        ProxyHandler._client = None
        test_server = StdHTTPServer(("127.0.0.1", 0), ProxyHandler)
        proxy_port = test_server.server_address[1]
        proxy_thread = threading.Thread(target=test_server.serve_forever, daemon=True)
        proxy_thread.start()

        try:
            # Make request through proxy
            resp = httpx.get(f"http://127.0.0.1:{proxy_port}/api/search?q=test")
            assert resp.status_code == 200
            data = resp.json()
            assert data["result"] == "hello"

            # Check receipt was recorded
            assert store.count() == 1
            receipt = store.all()[0]
            assert "search" in receipt.tool_name
            assert receipt.arguments["method"] == "GET"
        finally:
            test_server.shutdown()
            target.shutdown()


def test_proxy_records_post_request():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ReceiptStore(Path(tmpdir) / "test.jsonl")
        proxy = ToolProxy(store)

        target = HTTPServer(("127.0.0.1", 0), MockToolHandler)
        target_port = target.server_address[1]
        target_thread = threading.Thread(target=target.serve_forever, daemon=True)
        target_thread.start()

        from toolproof.http_proxy import ProxyHandler, HTTPServer as StdHTTPServer
        ProxyHandler.target_url = f"http://127.0.0.1:{target_port}"
        ProxyHandler.tool_proxy = proxy
        ProxyHandler._client = None
        test_server = StdHTTPServer(("127.0.0.1", 0), ProxyHandler)
        proxy_port = test_server.server_address[1]
        proxy_thread = threading.Thread(target=test_server.serve_forever, daemon=True)
        proxy_thread.start()

        try:
            resp = httpx.post(
                f"http://127.0.0.1:{proxy_port}/api/execute",
                json={"action": "search", "query": "test"},
            )
            assert resp.status_code == 200

            assert store.count() == 1
            receipt = store.all()[0]
            assert receipt.arguments["method"] == "POST"
            assert receipt.arguments["body"]["action"] == "search"
        finally:
            test_server.shutdown()
            target.shutdown()


def test_extract_openai_tool_calls():
    response = {
        "choices": [{
            "message": {
                "tool_calls": [{
                    "function": {
                        "name": "search_db",
                        "arguments": '{"query": "users"}',
                    }
                }]
            }
        }]
    }
    calls = _extract_tool_calls_from_response(response)
    assert len(calls) == 1
    assert calls[0]["name"] == "search_db"
    assert calls[0]["arguments"]["query"] == "users"


def test_extract_anthropic_tool_calls():
    response = {
        "content": [
            {"type": "text", "text": "I will search..."},
            {"type": "tool_use", "name": "search", "input": {"q": "test"}},
        ]
    }
    calls = _extract_tool_calls_from_response(response)
    assert len(calls) == 1
    assert calls[0]["name"] == "search"
    assert calls[0]["arguments"]["q"] == "test"
