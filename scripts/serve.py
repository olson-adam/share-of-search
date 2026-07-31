#!/usr/bin/env python3
"""View the dashboard, or export it as a single shareable file. No Node needed.

    python3 scripts/serve.py                             # demo data
    python3 scripts/serve.py --workspace ws/             # your data
    python3 scripts/serve.py --workspace ws/ --export report.html

The dashboard ships prebuilt in app/dist (Node is only needed if you want to
modify the app itself). `serve` runs a local stdlib web server on 127.0.0.1 —
nothing is exposed, nothing leaves the machine. `--export` bakes the snapshot
INTO the page and inlines every asset: one self-contained HTML file you can
email, attach, or drop in a shared drive — it opens anywhere, no server.
"""
from __future__ import annotations

import argparse
import http.server
import json
import re
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import os as _os
DIST = Path(_os.environ.get("SOS_DIST", ROOT / "app" / "dist"))


def load_snapshot(args) -> tuple[Path, dict]:
    path = (Path(args.workspace) / "snapshot.json" if args.workspace
            else ROOT / "examples" / "demo-workspace" / "snapshot.json")
    if not path.exists():
        sys.exit(f"error: no snapshot at {path} — run sos_calc.py first"
                 + ("" if args.workspace else " (or examples/make_demo.py for the demo)"))
    return path, json.loads(path.read_text(encoding="utf-8"))


def export(snapshot: dict, out: Path) -> None:
    html = (DIST / "index.html").read_text(encoding="utf-8")
    # inline everything vite emitted, attribute-order-agnostic; then VERIFY —
    # a "self-contained" file with external refs left behind is a silent lie
    css_n = js_n = 0
    for m in re.finditer(r'<link\b[^>]*?href="\.?/(assets/[^"]+\.css)"[^>]*>', html):
        css = (DIST / m.group(1)).read_text(encoding="utf-8")
        html = html.replace(m.group(0), f"<style>{css}</style>")
        css_n += 1
    for m in re.finditer(r'<script\b[^>]*?src="\.?/(assets/[^"]+\.js)"[^>]*></script>', html):
        js = (DIST / m.group(1)).read_text(encoding="utf-8")
        html = html.replace(m.group(0), f'<script type="module">{js}</script>')
        js_n += 1
    for m in re.finditer(r'<link\b[^>]*?href="\.?/([^"]+\.svg)"[^>]*>', html):
        try:
            import base64
            svg = (DIST / m.group(1)).read_bytes()
            uri = "data:image/svg+xml;base64," + base64.b64encode(svg).decode()
            html = html.replace(f'/{m.group(1)}', uri)
        except OSError:
            html = html.replace(m.group(0), "")
    leftover = re.search(r'(?:src|href)="\.?/(assets/[^"]+)"', html)
    if css_n == 0 or js_n == 0 or leftover:
        sys.exit("error: export could not inline the app "
                 f"(css={css_n}, js={js_n}, leftover={leftover.group(0) if leftover else None})"
                 " — the dist layout changed; please report this")
    payload = json.dumps(snapshot, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("<head>", f"<head><script>window.__SNAPSHOT__ = {payload}</script>", 1)
    out.write_text(html, encoding="utf-8")
    print(f"self-contained report → {out}  ({out.stat().st_size // 1024} kB — "
          "one file, opens anywhere, safe to share)")


def serve(snapshot_path: Path, port: int) -> None:
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(DIST), **kw)

        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.split("?")[0] == "/snapshot.json":
                body = snapshot_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"dashboard at {url} — data: {snapshot_path}. Ctrl-C to stop.", file=sys.stderr)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description="view or export the dashboard")
    ap.add_argument("--workspace", help="workspace dir (default: the fictional demo)")
    ap.add_argument("--port", type=int, default=8874)
    ap.add_argument("--export", type=Path, metavar="OUT.html",
                    help="write a single self-contained HTML instead of serving")
    args = ap.parse_args()
    if not DIST.exists():
        sys.exit("error: app/dist missing — this repo ships it prebuilt; "
                 "if you removed it: cd app && npm install && npm run build")
    snapshot_path, snapshot = load_snapshot(args)
    if args.export:
        export(snapshot, args.export)
    else:
        serve(snapshot_path, args.port)


if __name__ == "__main__":
    main()
