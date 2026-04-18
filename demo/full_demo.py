"""
HyperRetrieval Full Demo — 3 scenarios showing complete value prop.

Demonstrates: blast radius (via live MCP) + Guard fintech patterns (direct)
+ LLM comment-code alignment (direct).

Run: LLM_API_KEY=sk-... LLM_BASE_URL=https://... python3 run_full_demo.py
"""
import os, sys, time, json, threading
import urllib.request

BASE = "http://127.0.0.1:8002"
GUARD_DIR = "/home/beast/projects/hyperretrieval/guardrails"
SEP = "─" * 70

# ─── MCP client (with proper initialization handshake) ───────────────────────

def _post(url: str, payload: dict, timeout: float = 5.0):
    data = json.dumps(payload).encode()
    full = BASE + url if url.startswith("/") else url
    req = urllib.request.Request(full, data=data,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout): pass
    except Exception: pass


def call_mcp(name: str, args: dict, timeout: float = 30.0) -> str:
    session_url = None
    result = [None]
    done = threading.Event()

    def reader():
        nonlocal session_url
        try:
            req = urllib.request.Request(f"{BASE}/sse",
                                          headers={"Accept": "text/event-stream"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                for raw in resp:
                    line = raw.decode().rstrip()
                    if line.startswith("data:") and "/messages/" in line:
                        session_url = line[5:].strip()
                        break
                for raw in resp:
                    line = raw.decode().rstrip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    try:
                        obj = json.loads(data)
                        oid = obj.get("id")
                        if oid == 1 and "result" in obj:
                            _post(session_url, {"jsonrpc": "2.0",
                                                 "method": "notifications/initialized",
                                                 "params": {}})
                            _post(session_url, {"jsonrpc": "2.0", "id": 2,
                                                 "method": "tools/call",
                                                 "params": {"name": name,
                                                            "arguments": args}})
                        elif oid == 2 and ("result" in obj or "error" in obj):
                            result[0] = data
                            done.set()
                            return
                    except json.JSONDecodeError:
                        pass
        except Exception:
            done.set()

    threading.Thread(target=reader, daemon=True).start()
    deadline = time.time() + 5
    while session_url is None and time.time() < deadline:
        time.sleep(0.01)
    if session_url is None:
        return "ERROR: MCP server not reachable at port 8002"

    _post(session_url, {
        "jsonrpc": "2.0", "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "hr-demo", "version": "1.0"}
        }
    })

    done.wait(timeout=timeout)
    raw = result[0]
    if not raw:
        return "ERROR: timeout"
    try:
        obj = json.loads(raw)
        if "error" in obj:
            return f"ERROR: {obj['error']['message']}"
        content = obj.get("result", {}).get("content", [])
        return content[0].get("text", raw) if content else raw
    except Exception:
        return raw


# ─── Guard: direct Python call (T-020 fintech patterns) ──────────────────────

def run_guard(file_path: str) -> str:
    import importlib.util
    # Use feature-branch version with T-020 fintech patterns
    branch_path = "/tmp/comment_code_checker_fintech.py"
    fallback = os.path.join(GUARD_DIR, "comment_code_checker.py")
    checker_path = branch_path if os.path.exists(branch_path) else fallback
    spec = importlib.util.spec_from_file_location("_cc_demo", checker_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    findings = (mod.check_file(file_path) or [])
    if not findings:
        return "  No issues found."
    lines = []
    for f in sorted(findings, key=lambda x: x.severity):
        sev = f.severity.upper()
        lines.append(f"  [{sev}] Line {f.line}: {f.pattern}")
        lines.append(f"         {f.message}")
    return "\n".join(lines)


# ─── Alignment: direct Python call (T-018 LLM checker) ───────────────────────

def run_alignment(file_path: str) -> str:
    if GUARD_DIR not in sys.path:
        sys.path.insert(0, GUARD_DIR)
    from llm_alignment_checker import check_llm_alignment
    source = open(file_path).read()
    findings = check_llm_alignment(source, file_path, language="python") or []
    if not findings:
        return "  All comments accurately describe their code."
    lines = []
    for f in findings:
        lines.append(f"  [{f.severity.upper()}] Line {f.line}: {f.pattern}")
        lines.append(f"         {f.message}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{'═'*70}")
print("  HyperRetrieval Pre-Commit Demo")
print(f"{'═'*70}\n")

# SCENARIO 1: safe core change
print(f"{SEP}")
print("SCENARIO 1  |  Core engine refactor  |  Expected: PASS, LOW risk")
print(SEP)
t0 = time.time()
print(call_mcp("check_my_changes", {
    "changed_files": ["serve/retrieval_engine.py", "serve/mcp_server.py"]
}))
print(f"  Latency: {time.time()-t0:.1f}s\n")

# SCENARIO 2: risky payment file — guard findings
print(f"{SEP}")
print("SCENARIO 2  |  New payment handler  |  Expected: Guard findings")
print(SEP)
print("  Step A — blast radius (MCP):")
t0 = time.time()
# Use module names for blast radius (file not in workspace index)
print(call_mcp("check_my_changes", {
    "changed_files": ["/tmp/demo_payment_bad.py"]
}))
print(f"  (blast radius: {time.time()-t0:.1f}s)\n")

print("  Step B — Guard static analysis (T-020 fintech patterns):")
t0 = time.time()
print(run_guard("/tmp/demo_payment_bad.py"))
print(f"  (guard scan: {time.time()-t0:.1f}s)\n")

# SCENARIO 3: alignment check
print(f"{SEP}")
print("SCENARIO 3  |  LLM comment-code alignment  |  Expected: MISALIGNED finding")
print(SEP)
t0 = time.time()
print(run_alignment("/tmp/demo_payment_bad.py"))
print(f"  Latency: {time.time()-t0:.1f}s\n")

print(f"{'═'*70}")
print("  Three layers. One pre-commit check.")
print("  Blast radius → Guard anti-patterns → Comment-code alignment.")
print(f"{'═'*70}\n")
