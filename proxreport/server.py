from __future__ import annotations

import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import ssl
import threading
from typing import Optional

from .auth import require_basic_auth
from .config import AppConfig
from .metrics import snapshot
from .render import render_dashboard, render_cluster_dashboard


_LOG = logging.getLogger("proxreport")


def _repo_root() -> Path:
    # proxreport/server.py -> package dir -> repo root
    return Path(__file__).resolve().parent.parent


def _static_path() -> Path:
    # Prefer repo static/ next to package, fallback to cwd/static for deployment.
    p1 = _repo_root() / "static" / "style.css"
    if p1.exists():
        return p1
    p2 = Path(os.getcwd()) / "static" / "style.css"
    return p2


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "proxreport"

    def do_GET(self) -> None:
    cfg: AppConfig = self.server.app_config  # type: ignore[attr-defined]

    if self.path == "/static/style.css":
        return self._serve_style()

    if not require_basic_auth(self, cfg.server.users_file):
        return

    # -------------------------
    # Single node dashboard
    # -------------------------
    if self.path == "/":
        snap = snapshot(cfg.mountpoints)
        body = render_dashboard(cfg, snap).encode("utf-8")

    # -------------------------
    # Cluster overview (mock)
    # -------------------------
    elif self.path == "/cluster":
        # ⚠️ Datos de ejemplo (por ahora)
        nodes = [
            {
                "name": "pve-node01",
                "cpu_pct": 34.0,
                "cpu_state": "state-green",
                "ram_pct": 62.0,
                "ram_state": "state-amber",
                "disk_pct": 51.0,
                "disk_state": "state-green",
                "est_vms": 5,
            },
            {
                "name": "pve-node02",
                "cpu_pct": 91.0,
                "cpu_state": "state-red",
                "ram_pct": 74.0,
                "ram_state": "state-amber",
                "disk_pct": 88.0,
                "disk_state": "state-amber",
                "est_vms": 1,
            },
        ]

        body = render_cluster_dashboard(nodes).encode("utf-8")

    else:
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Not found\n")
        return

    self.send_response(200)
    self.send_header("Content-Type", "text/html; charset=utf-8")
    self.send_header("Content-Length", str(len(body)))
    self.send_header("Cache-Control", "no-store")
    self.end_headers()
    self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:  # noqa: N802
        _LOG.info("%s - %s", self.address_string(), fmt % args)


class RedirectHandler(BaseHTTPRequestHandler):
    server_version = "proxreport"

    def do_GET(self) -> None:
        https_port: int = self.server.https_port  # type: ignore[attr-defined]
        host = self.headers.get("Host", "")
        host_no_port = host.split(":")[0] if host else "localhost"

        port_part = "" if https_port == 443 else f":{https_port}"
        location = f"https://{host_no_port}{port_part}{self.path}"

        self.send_response(301)
        self.send_header("Location", location)
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:  # noqa: N802
        _LOG.info("%s - %s", self.address_string(), fmt % args)


def serve(cfg: AppConfig, bind: str = "0.0.0.0") -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    https_server = ThreadingHTTPServer((bind, cfg.server.https_port), DashboardHandler)
    https_server.app_config = cfg  # type: ignore[attr-defined]

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cfg.server.certfile, keyfile=cfg.server.keyfile)
    https_server.socket = context.wrap_socket(https_server.socket, server_side=True)

    http_server = ThreadingHTTPServer((bind, cfg.server.http_port), RedirectHandler)
    http_server.https_port = cfg.server.https_port  # type: ignore[attr-defined]

    t = threading.Thread(target=http_server.serve_forever, name="http-redirect", daemon=True)
    t.start()

    _LOG.info("HTTPS listening on %s:%s", bind, cfg.server.https_port)
    _LOG.info("HTTP redirect listening on %s:%s", bind, cfg.server.http_port)

    try:
        https_server.serve_forever()
    finally:
        https_server.server_close()
        http_server.shutdown()
        http_server.server_close()
