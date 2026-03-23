#!/usr/bin/env python3
"""Serve the viz at http://localhost:PORT. Copies viz_data.json from OUTPUT_DIR first."""
import http.server, os, pathlib, shutil, sys

PORT       = int(os.environ.get("VIZ_PORT", 8888))
OUTPUT_DIR = pathlib.Path(os.environ.get("OUTPUT_DIR", "/home/beast/projects/workspaces/juspay/output"))
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
handler = http.server.SimpleHTTPRequestHandler
httpd   = http.server.HTTPServer(("", PORT), handler)
print(f"Visualization: http://localhost:{PORT}")
httpd.serve_forever()
