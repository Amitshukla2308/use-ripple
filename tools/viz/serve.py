#!/usr/bin/env python3
"""Serve the viz at http://localhost:PORT. Copies viz_data.json from OUTPUT_DIR first."""
import http.server, os, pathlib, shutil, sys

PORT       = int(os.environ.get("VIZ_PORT", 8888))
OUTPUT_DIR = pathlib.Path(os.environ.get("OUTPUT_DIR", "."))
VIZ_DIR    = pathlib.Path(__file__).parent

# Copy latest data files
for fname in ("viz_data.json", "scatter_data.json"):
    src = OUTPUT_DIR / fname
    dst = VIZ_DIR    / fname
    if src.exists():
        shutil.copy2(src, dst)
        print(f"Copied {fname} from {src}")
    elif fname == "viz_data.json":
        print(f"WARNING: {src} not found — run build/09_build_viz_data.py first")

os.chdir(VIZ_DIR)

class _Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        super().do_GET()
    def log_message(self, fmt, *args):
        if "/health" not in str(args):
            super().log_message(fmt, *args)

httpd = http.server.HTTPServer(("", PORT), _Handler)
print(f"Visualization: http://localhost:{PORT}")
httpd.serve_forever()
