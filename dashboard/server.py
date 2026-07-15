"""Dashboard HTTP server: serves swarm.html and streams the EventBus over SSE.

Stdlib only. The dashboard is a dumb terminal: everything it knows arrives
as events on GET /events (bus history first, then live), and it cannot tell
live from replay — that is the point.
"""

from __future__ import annotations

import json
import pathlib
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DASHBOARD_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = DASHBOARD_DIR.parent
SWARM_HTML = DASHBOARD_DIR / "swarm.html"
EVAL_REPORT = REPO_ROOT / "evals" / "eval_report.html"

EVALS_PLACEHOLDER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>evals — not yet</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body{margin:0;min-height:100vh;display:grid;place-items:center;
    background:#100d14;color:#ece8f1;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
  @media (prefers-color-scheme: light){body{background:#f4f3f6;color:#211d29}}
  .card{text-align:center;padding:40px 48px;border-radius:16px;max-width:34em}
  h1{font-size:22px;letter-spacing:-.01em;margin:0 0 10px}
  p{color:#a49bad;line-height:1.6;margin:0}
  code{font-family:ui-monospace,Menlo,monospace;font-size:13px;
    background:rgba(128,128,128,.15);padding:2px 7px;border-radius:6px}
  a{color:#3ec7cf}
</style></head><body>
<div class="card">
  <div style="font-size:44px">📊</div>
  <h1>No eval report yet</h1>
  <p>Evals haven't been run for this build. Run the eval harness to generate
  <code>evals/eval_report.html</code>, then refresh this page.<br><br>
  <a href="/">← back to the swarm</a></p>
</div>
</body></html>"""


class SwarmHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    bus = None  # attached by start_dashboard


class _DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass  # keep the demo terminal clean

    # -- helpers ----------------------------------------------------------
    def _send_page(self, body: bytes, content_type: str = "text/html; charset=utf-8",
                   status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    # -- routes -----------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path == "/":
                self._route_index()
            elif path == "/events":
                self._route_events()
            elif path == "/evals":
                self._route_evals()
            else:
                self._send_page(b"not found", "text/plain; charset=utf-8", 404)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client went away; nothing to do

    def _route_index(self):
        # Read from disk on every request: hot reload while iterating on the UI.
        try:
            body = SWARM_HTML.read_bytes()
        except FileNotFoundError:
            body = b"<h1>dashboard/swarm.html is missing</h1>"
        self._send_page(body)

    def _route_evals(self):
        if EVAL_REPORT.is_file():
            self._send_page(EVAL_REPORT.read_bytes())
        else:
            self._send_page(EVALS_PLACEHOLDER.encode("utf-8"))

    def _route_events(self):
        bus = self.server.bus
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        # Subscribe BEFORE snapshotting history so nothing falls in the gap;
        # the client dedupes by seq, so any overlap is harmless.
        q = bus.subscribe()
        try:
            for event in list(bus.history):
                self._write_event(event)
            while True:
                try:
                    event = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                self._write_event(event)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # client disconnected; unsubscribe quietly below
        finally:
            bus.unsubscribe(q)

    def _write_event(self, event: dict) -> None:
        self.wfile.write(b"data: " + json.dumps(event).encode("utf-8") + b"\n\n")
        self.wfile.flush()


def start_dashboard(bus, port: int = 8787) -> SwarmHTTPServer:
    """Bind the socket, start serve_forever on a daemon thread, return the server."""
    server = SwarmHTTPServer(("127.0.0.1", port), _DashboardHandler)  # binds here
    server.bus = bus
    thread = threading.Thread(target=server.serve_forever, name="swarm-dashboard", daemon=True)
    thread.start()
    return server
