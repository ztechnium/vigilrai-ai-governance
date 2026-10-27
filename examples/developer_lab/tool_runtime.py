"""Local MCP endpoint. RAI posts here only when a tool action is allowed.

Run:
  python examples/developer_lab/tool_runtime.py
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from actions import ToolError, apply_action

HOST = "0.0.0.0"
PORT = 8765


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/health":
            self._send(200, {"ok": True, "service": "developer-lab-mcp"})
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/invoke":
            self._send(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid_json"})
            return
        tool_key = body.get("tool_key")
        parameters = body.get("parameters") or {}
        if not tool_key:
            self._send(400, {"error": "tool_key is required"})
            return
        try:
            result = apply_action(str(tool_key), parameters)
        except ToolError as exc:
            self._send(exc.status_code, {"ok": False, "error": exc.message})
            return
        self._send(200, {"ok": True, "tool_key": tool_key, "result": result})

    def log_message(self, fmt: str, *args) -> None:
        print(f"[tool-runtime] {self.address_string()} {fmt % args}")

    def _send(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Developer lab MCP listening on http://{HOST}:{PORT}/invoke")
    server.serve_forever()


if __name__ == "__main__":
    main()
