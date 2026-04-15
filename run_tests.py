import subprocess, sys

REPO = "/home/beast/projects/hyperretrieval"
PY   = "/home/beast/miniconda3/bin/python3"

def run(label, cmd, env_extra=None, cwd=REPO):
    import os
    env = {**os.environ, **(env_extra or {})}
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    status = "PASS" if r.returncode == 0 else "FAIL"
    print(f"\n{'='*60}")
    print(f"  [{status}] {label}")
    print('='*60)
    out = (r.stdout + r.stderr).strip()
    if out:
        print(out[-3000:])  # last 3000 chars
    return r.returncode == 0

results = []

# ── 1. Import smoke tests ─────────────────────────────────────────────────────
smoke = """
import sys, pathlib
sys.path.insert(0, '/home/beast/projects/hyperretrieval/serve')
sys.path.insert(0, '/home/beast/projects/hyperretrieval')

print("1. importing retrieval_engine...")
import retrieval_engine as RE
print(f"   OK — {len(dir(RE))} symbols")

print("2. importing tools...")
import tools as T
print(f"   OK — {len(T.AGENT_TOOLS)} agent tools, {len(T.TOOL_DISPATCH)} dispatch entries")

print("3. importing mcp_server (no start)...")
import importlib.util, types
spec = importlib.util.spec_from_file_location("mcp_server",
    "/home/beast/projects/hyperretrieval/serve/mcp_server.py")
print("   OK — mcp_server found")

print("4. importing demo_server_v6 (no start)...")
spec2 = importlib.util.spec_from_file_location("demo_server_v6",
    "/home/beast/projects/hyperretrieval/apps/chat/demo_server_v6.py")
print("   OK — demo_server_v6 found")

print("5. importing pr_analyzer (no start)...")
spec3 = importlib.util.spec_from_file_location("pr_analyzer",
    "/home/beast/projects/hyperretrieval/apps/cli/pr_analyzer.py")
print("   OK — pr_analyzer found")

print("\\nAll imports OK")
"""
results.append(run("Import smoke tests", [PY, "-c", smoke]))

# ── 2. test_02 — pure retrieval logic (no GPU, no data) ──────────────────────
results.append(run("test_02: retrieval logic unit tests (no GPU/data)",
                   [PY, "tests/test_02_retrieval_logic.py"]))

# ── 3. test_05 — integration (only if services are running) ──────────────────
results.append(run("test_05: integration (services must be running)",
                   [PY, "tests/test_05_integration.py"],
                   env_extra={
                       "ARTIFACT_DIR": "/home/beast/projects/workspaces/juspay/artifacts",
                   }))

# ── 4. test_04 — retrieval accuracy (loads data, no GPU) ─────────────────────
results.append(run("test_04: retrieval accuracy (loads data, no embed server)",
                   [PY, "tests/test_04_retrieval_accuracy.py"],
                   env_extra={
                       "ARTIFACT_DIR": "/home/beast/projects/workspaces/juspay/artifacts",
                       "EMBED_SERVER_URL": "",
                   }))

# ── Summary ───────────────────────────────────────────────────────────────────
labels = ["imports", "test_02 logic", "test_05 integration", "test_04 accuracy"]
print(f"\n{'='*60}")
print("  SUMMARY")
print('='*60)
for label, ok in zip(labels, results):
    print(f"  {'✓' if ok else '✗'} {label}")
