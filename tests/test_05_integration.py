"""
test_05_integration.py — Integration tests for running services.

Tests embed server health, MCP tool responses, and end-to-end call chains.
Requires running services: embed_server (:8001), mcp_server (:8002).

Run:
    python3 tests/test_05_integration.py
"""
import sys, json, pathlib, urllib.request, urllib.error
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "serve"))

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"
errors: list = []
skipped: list = []

def ok(label):
    print(f"  {PASS} {label}")

def fail(label, detail=""):
    print(f"  {FAIL} {label}")
    if detail: print(f"      {detail}")
    errors.append(label)

def warn(label, detail=""):
    print(f"  {WARN} {label}")
    if detail: print(f"      {detail}")

def skip(label, reason=""):
    print(f"  ── SKIP: {label} ({reason})")
    skipped.append(label)

def _get(url: str, timeout: int = 5) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return None

def _post(url: str, data: dict, timeout: int = 10) -> dict | None:
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 1. Embed server health
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 1. Embed server (:8001) ===")

health = _get("http://localhost:8001/health")
if health is None:
    skip("Embed server reachable", "server not running on :8001")
    EMBED_AVAILABLE = False
else:
    EMBED_AVAILABLE = True
    ok("Embed server reachable")

    # 1a: Status must be ok
    status = health.get("status", "")
    if status == "ok":
        ok(f"Status = 'ok'")
    else:
        fail(f"Status must be 'ok'", f"Got: {status!r}")

    # 1b: Model must be loaded
    loaded = health.get("loaded", False)
    if loaded:
        ok("Model loaded")
    else:
        fail("Model must be loaded", f"health: {health}")

    # 1c: Dimension must be 4096
    dim = health.get("dim", 0)
    if dim == 4096:
        ok(f"Embedding dimension = 4096")
    elif dim == 0:
        warn("'dim' not in health response — checking via /embed")
    else:
        fail(f"Embedding dimension must be 4096", f"Got: {dim}")

    # 1d: POST /embed — basic embedding
    resp = _post("http://localhost:8001/embed",
                 {"texts": ["test query about UPI payment flow"], "instruction": ""})
    if resp is None:
        fail("/embed endpoint reachable")
    else:
        ok("/embed endpoint responds")
        embeddings = resp.get("embeddings", [])
        if len(embeddings) == 1:
            ok(f"/embed returns 1 vector for 1 input")
        else:
            fail(f"/embed must return 1 vector for 1 input", f"Got {len(embeddings)}")

        if embeddings:
            vec = embeddings[0]
            actual_dim = len(vec)
            if actual_dim == 4096:
                ok(f"Vector dimension = 4096")
            else:
                fail(f"Vector dimension must be 4096", f"Got: {actual_dim}")

    # 1e: Determinism — same input must produce same output
    resp1 = _post("http://localhost:8001/embed",
                  {"texts": ["card mandate registration"], "instruction": ""})
    resp2 = _post("http://localhost:8001/embed",
                  {"texts": ["card mandate registration"], "instruction": ""})
    if resp1 and resp2:
        v1 = resp1.get("embeddings", [[]])[0]
        v2 = resp2.get("embeddings", [[]])[0]
        if v1 == v2:
            ok("Embedding is deterministic (same input → same output)")
        else:
            # Check if they're close (float precision may differ)
            if v1 and v2:
                max_diff = max(abs(a - b) for a, b in zip(v1[:10], v2[:10]))
                if max_diff < 1e-4:
                    ok(f"Embedding is deterministic (max diff: {max_diff:.2e})")
                else:
                    fail(f"Embedding is not deterministic", f"Max diff in first 10 dims: {max_diff}")

    # 1f: Different inputs must produce different outputs
    resp_upi = _post("http://localhost:8001/embed",
                     {"texts": ["UPI collect payment flow"], "instruction": ""})
    resp_card = _post("http://localhost:8001/embed",
                      {"texts": ["card 3DS authentication"], "instruction": ""})
    if resp_upi and resp_card:
        v_upi  = resp_upi.get("embeddings", [[]])[0]
        v_card = resp_card.get("embeddings", [[]])[0]
        if v_upi and v_card and v_upi != v_card:
            ok("Different inputs produce different embeddings")
        else:
            fail("Different inputs must produce different embeddings")


# ══════════════════════════════════════════════════════════════════════════════
# 2. MCP server health
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 2. MCP server (:8002) ===")

# Try to hit the SSE endpoint
try:
    with urllib.request.urlopen("http://localhost:8002/sse", timeout=3) as r:
        MCP_AVAILABLE = True
        ok("MCP SSE endpoint reachable (:8002/sse)")
except urllib.error.HTTPError as e:
    if e.code in (200, 405):
        MCP_AVAILABLE = True
        ok("MCP SSE endpoint reachable")
    else:
        MCP_AVAILABLE = False
        skip("MCP server reachable", f"HTTP {e.code}")
except Exception as e:
    MCP_AVAILABLE = False
    skip("MCP server reachable", str(e))


# ══════════════════════════════════════════════════════════════════════════════
# 3. MCP tools via direct import (bypasses transport, tests logic with live data)
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 3. MCP tool functions with live data ===")

try:
    import mcp_server as MCP
    import os, retrieval_engine as RE

    # Initialize data (if not already loaded)
    if RE.G is None:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "")
        RE.initialize(artifact_dir=artifact_dir or None, load_embedder=False)

    # 3a: search_symbols returns a non-empty string for known term
    result = MCP.search_symbols("getAllPaymentFlowsForTxn")
    if result and "getAllPaymentFlowsForTxn" in result:
        ok("search_symbols('getAllPaymentFlowsForTxn') finds target")
    else:
        fail("search_symbols must find getAllPaymentFlowsForTxn",
             f"Result: {result[:200]!r}")

    # 3b: get_function_body returns correct content
    result = MCP.get_function_body("PaymentFlows.getAllPaymentFlowsForTxn")
    if "isOTMFlow" in result and "isGuranteeFlow" in result:
        ok("get_function_body: contains function body content")
    else:
        fail("get_function_body must contain function body content",
             f"Result: {result[:300]!r}")

    # 3c: trace_callees returns string (not None/error)
    result = MCP.trace_callees("PaymentFlows.getAllPaymentFlowsForTxn")
    if isinstance(result, str) and len(result) > 10:
        ok("trace_callees returns non-empty string")
    else:
        fail("trace_callees must return non-empty string", f"Got: {result!r}")

    # 3d: trace_callers handles non-existent function gracefully
    result = MCP.trace_callers("NonExistent.Function")
    if isinstance(result, str):
        ok("trace_callers handles unknown ID gracefully")
    else:
        fail("trace_callers must return string for unknown ID")

    # 3e: search_modules returns module names
    result = MCP.search_modules("PaymentFlows")
    if "PaymentFlows" in result:
        ok("search_modules('PaymentFlows') finds PaymentFlows module")
    else:
        fail("search_modules must find PaymentFlows", f"Result: {result[:200]!r}")

    # 3f: get_module returns symbol list
    result = MCP.get_module("PaymentFlows")
    if "getAllPaymentFlowsForTxn" in result:
        ok("get_module('PaymentFlows') lists getAllPaymentFlowsForTxn")
    else:
        fail("get_module('PaymentFlows') must list getAllPaymentFlowsForTxn",
             f"Result: {result[:200]!r}")

    # 3g: get_blast_radius returns structured output
    result = MCP.get_blast_radius(["euler-api-txns/euler-x/src-generated/PaymentFlows.hs"])
    if isinstance(result, str) and "euler-api-txns" in result:
        ok("get_blast_radius resolves PaymentFlows.hs to euler-api-txns")
    else:
        fail("get_blast_radius must mention euler-api-txns", f"Result: {result[:300]!r}")

    # 3h: All 7 tool functions callable and return strings
    all_tools = [
        (MCP.search_symbols,    ("upi",)),
        (MCP.search_modules,    ("mandate",)),
        (MCP.get_module,        ("PaymentFlows",)),
        (MCP.get_function_body, ("PaymentFlows.getUpiFlowMapper",)),
        (MCP.trace_callers,     ("PaymentFlows.getUpiFlowMapper",)),
        (MCP.trace_callees,     ("PaymentFlows.getUpiFlowMapper",)),
        (MCP.get_blast_radius,  (["PaymentFlows"],)),
    ]
    for fn, args in all_tools:
        try:
            r = fn(*args)
            if isinstance(r, str):
                ok(f"  {fn.__name__} returns string")
            else:
                fail(f"  {fn.__name__} must return string", f"Got {type(r).__name__}")
        except Exception as e:
            fail(f"  {fn.__name__} must not raise", str(e))

except ImportError as e:
    skip("MCP tool import tests", f"mcp_server not importable: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 4. Chainlit /status command format
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 4. Chainlit server basics (:8000) ===")

chainlit_health = _get("http://localhost:8000/healthz", timeout=3)
if chainlit_health is None:
    skip("Chainlit server reachable", "server not running on :8000")
else:
    ok("Chainlit server reachable (:8000)")


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
print()
if skipped:
    print(f"  {len(skipped)} test(s) skipped (services not running): {skipped}")
if errors:
    print(f"\033[91m{len(errors)} FAILED: {errors}\033[0m")
    sys.exit(1)
else:
    print(f"\033[92mAll integration tests passed ({len(skipped)} skipped).\033[0m")
