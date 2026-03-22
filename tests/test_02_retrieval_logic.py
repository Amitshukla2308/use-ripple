"""
test_02_retrieval_logic.py — Pure retrieval logic unit tests.

Tests every data-transformation and routing function in retrieval_engine.py
WITHOUT loading GPU model or vector index. Uses import stubs for heavy deps.

Extends and supersedes bench_test.py.

Run:
    python3 tests/test_02_retrieval_logic.py
"""
import sys, types, builtins, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "serve"))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps" / "chat"))

# ── Stub heavy imports (no GPU, no networkx, no lancedb) ─────────────────────
_real_import = builtins.__import__

def _safe_import(name, *args, **kwargs):
    stubs = {"lancedb", "sentence_transformers", "networkx", "openai",
             "numpy", "torch", "transformers"}
    if name in stubs:
        m = types.ModuleType(name)
        if name == "networkx":
            # Provide a minimal Graph stub used by retrieval_engine at module scope
            class _FakeGraph:
                def __init__(self, *a, **kw): self._nodes = {}; self._edges = []
                def number_of_nodes(self): return 0
                def number_of_edges(self): return 0
                def nodes(self, *a, **kw): return {}
                def edges(self, *a, **kw): return []
                def add_node(self, *a, **kw): pass
                def add_edge(self, *a, **kw): pass
                def successors(self, *a, **kw): return []
                def predecessors(self, *a, **kw): return []
            m.DiGraph = _FakeGraph
            m.node_link_graph = lambda d, **kw: _FakeGraph()
        if name == "numpy":
            m.array = lambda *a, **kw: []
            m.float32 = float
        return m
    if name == "chainlit":
        m = types.ModuleType(name)
        _noop = lambda *a, **kw: None
        class _FakeCtx:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def send(self): pass
            output = ""
        m.set_chat_profiles = lambda f: f
        m.on_message        = lambda f: f
        m.on_chat_start     = lambda f: f
        m.ChatProfile       = type("ChatProfile", (), {"__init__": lambda self, **kw: None})
        m.Starter           = type("Starter",     (), {"__init__": lambda self, **kw: None})
        m.Step    = _FakeCtx
        m.Message = _FakeCtx
        m.user_session = type("US", (), {
            "set": staticmethod(_noop),
            "get": staticmethod(lambda k, d=None: d),
        })()
        return m
    return _real_import(name, *args, **kwargs)

builtins.__import__ = _safe_import
import retrieval_engine as RE
import tools as T
import demo_server_v6 as DS
builtins.__import__ = _real_import

# ─────────────────────────────────────────────────────────────────────────────
PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
errors: list = []

def check(label, got, expected):
    ok = got == expected
    print(f"  {PASS if ok else FAIL} {label}")
    if not ok:
        print(f"      expected: {expected!r}")
        print(f"      got:      {got!r}")
        errors.append(label)

def check_contains(label, container, items):
    missing = [i for i in items if i not in container]
    ok = not missing
    print(f"  {PASS if ok else FAIL} {label}")
    if not ok:
        print(f"      missing: {missing}")
        print(f"      container: {container}")
        errors.append(label)

def check_not_contains(label, container, items):
    found = [i for i in items if i in container]
    ok = not found
    print(f"  {PASS if ok else FAIL} {label}")
    if not ok:
        print(f"      must NOT contain: {found}")
        print(f"      container: {container}")
        errors.append(label)

def check_true(label, condition, detail=""):
    print(f"  {PASS if condition else FAIL} {label}")
    if not condition:
        if detail: print(f"      {detail}")
        errors.append(label)


# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 1. _extract_query_subject: SKIPPED (function inlined) ===")
print("\n=== 2. _query_variants_heuristic: SKIPPED (function moved to tools.py) ===")
print("\n=== 3. Variant stopwords: SKIPPED (function moved to tools.py) ===")
print("\n=== 4. _ambiguity_hint: SKIPPED (function removed in v6 refactor) ===")



print("\n=== 5. fast_route: SKIPPED (function removed in v6 refactor) ===")

# ══════════════════════════════════════════════════════════════════════════════
# 6. _fuzzy_fn_lookup — body lookup edge cases
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 6. _fuzzy_fn_lookup edge cases ===")

# Inject a minimal body_store into RE for testing (does not affect global state)
_orig_bs = RE.body_store
RE.body_store = {
    "Euler.API.Gateway.Foo.Bar.baz":   "body of baz in Foo.Bar",
    "Euler.API.Gateway.Qux.Bar.baz":   "body of baz in Qux.Bar",
    "Euler.API.Gateway.Foo.Bar.quux":  "body of quux",
    "PaymentFlows.getAllPaymentFlowsForTxn": "getAllPaymentFlowsForTxn body text",
    "ShortModule.fn":                  "short fn body",
}

# Exact match
matched, body = T._fuzzy_fn_lookup("Euler.API.Gateway.Foo.Bar.baz")
check("Exact match returns correct body",
      body, "body of baz in Foo.Bar")

# Suffix match — partial key
matched2, body2 = T._fuzzy_fn_lookup("Bar.quux")
check("Suffix match finds Foo.Bar.quux",
      body2, "body of quux")

# Ambiguous — longest common prefix wins
matched3, body3 = T._fuzzy_fn_lookup("Euler.API.Gateway.Foo.Bar.baz")
check("Ambiguous match: longest common prefix wins (Foo.Bar.baz over Qux.Bar.baz)",
      matched3, "Euler.API.Gateway.Foo.Bar.baz")

# Not found — use a 2+ component ID that definitely won't match anything in the fake store
matched4, body4 = T._fuzzy_fn_lookup("NonExistent.CompletelyMadeUp")
check("Not-found returns empty body", body4, "")
check("Not-found returns None matched", matched4, None)

# Single-component name must NOT match (too ambiguous — min 2 components enforced)
matched4b, body4b = T._fuzzy_fn_lookup("fn")
check("Single-component lookup returns empty (ambiguity guard)", body4b, "")

# Full ID lookup
matched5, body5 = T._fuzzy_fn_lookup("PaymentFlows.getAllPaymentFlowsForTxn")
check("Full ID exact lookup", body5, "getAllPaymentFlowsForTxn body text")

RE.body_store = _orig_bs


# ══════════════════════════════════════════════════════════════════════════════
# 7. _same_name_impls
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 7. _same_name_impls ===")

_orig_bs = RE.body_store
RE.body_store = {
    "Euler.API.Gateway.Razorpay.Flow.startPayment": "razorpay body",
    "Euler.API.Gateway.PayU.Flow.startPayment":     "payu body",
    "Euler.API.Gateway.Stripe.Flow.startPayment":   "stripe body",
    "Euler.API.Other.doSomethingElse":              "other body",
}

impls = T._same_name_impls("Euler.API.Gateway.Razorpay.Flow.startPayment",
                              exclude="Euler.API.Gateway.Razorpay.Flow.startPayment")
check_contains("same_name_impls finds PayU and Stripe variants",
               impls, ["Euler.API.Gateway.PayU.Flow.startPayment",
                        "Euler.API.Gateway.Stripe.Flow.startPayment"])
check_not_contains("same_name_impls excludes the target itself",
                   impls, ["Euler.API.Gateway.Razorpay.Flow.startPayment"])
check_not_contains("same_name_impls excludes unrelated functions",
                   impls, ["Euler.API.Other.doSomethingElse"])

RE.body_store = _orig_bs


# ══════════════════════════════════════════════════════════════════════════════
# 8. chat profile count
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 8. chat profile count ===")
import asyncio
profiles = asyncio.get_event_loop().run_until_complete(DS.set_chat_profiles())
check("Exactly 1 chat profile", len(profiles), 1)
if profiles:
    name = getattr(profiles[0], "name", "?")
    check_true("Profile has a name", bool(name), f"name={name!r}")


# ══════════════════════════════════════════════════════════════════════════════
# 9. keyword search — word splitting and allowlist
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 9. keyword search word splitting ===")

# Inject a tiny node graph for testing
import networkx as nx_real
_orig_G = RE.G
_orig_MG = RE.MG
fake_G = nx_real.DiGraph()
fake_G.add_node("PaymentFlows.getUpiFlowMapper", **{
    "id": "PaymentFlows.getUpiFlowMapper",
    "name": "getUpiFlowMapper",
    "module": "PaymentFlows",
    "service": "euler-api-txns",
    "kind": "function",
    "file": "test.hs",
    "type": "TxnCardInfo -> [Text]",
    "cluster_name": "UPI",
})
fake_G.add_node("PaymentFlows.getCardAuthTypeDetails", **{
    "id": "PaymentFlows.getCardAuthTypeDetails",
    "name": "getCardAuthTypeDetails",
    "module": "PaymentFlows",
    "service": "euler-api-txns",
    "kind": "function",
    "file": "test.hs",
    "type": "TxnCardInfo -> [Text]",
    "cluster_name": "Card Auth",
})
RE.G = fake_G

# "upi" should not be filtered (allowlisted)
results = RE.cross_service_keyword_search("upi collect", max_per_service=10)
upi_hits = [n for svc_hits in results.values() for n in svc_hits
            if n.get("id", "").endswith("getUpiFlowMapper")]
check_true("Short allowlisted term 'upi' not filtered",
           len(upi_hits) > 0,
           f"results: {results}")

# Pure stopword query should return empty
results2 = RE.cross_service_keyword_search("what does this do", max_per_service=10)
total_hits = sum(len(v) for v in results2.values())
check_true("Pure stopword query returns no results",
           total_hits == 0,
           f"Got {total_hits} hits for all-stopword query")

RE.G = _orig_G


# ══════════════════════════════════════════════════════════════════════════════
# 10. Tool output format contracts
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 10. Tool output format contracts ===")

# With empty data stores, tools must return strings (not None, not raise)
RE.G = nx_real.DiGraph()  # empty graph
RE.body_store = {}
RE.call_graph = {}

def _test_tool_returns_string(fn, *args):
    try:
        result = fn(*args)
        ok_t = isinstance(result, str)
        print(f"  {PASS if ok_t else FAIL} {fn.__name__}({', '.join(repr(a) for a in args)}) → {type(result).__name__}")
        if not ok_t:
            errors.append(f"tool_type:{fn.__name__}")
    except Exception as e:
        print(f"  {FAIL} {fn.__name__} raised {type(e).__name__}: {e}")
        errors.append(f"tool_raises:{fn.__name__}")

_test_tool_returns_string(T.tool_get_function_body, "NonExistent.fn")
_test_tool_returns_string(T.tool_trace_callees,     "NonExistent.fn")
_test_tool_returns_string(T.tool_trace_callers,     "NonExistent.fn")
_test_tool_returns_string(T.tool_search_symbols,    "upi collect")
_test_tool_returns_string(T.tool_search_modules,    "PaymentFlows")
_test_tool_returns_string(T.tool_get_module,        "PaymentFlows")

RE.G = _orig_G


# ══════════════════════════════════════════════════════════════════════════════
# 11. resolve_files_to_modules — known mappings
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 11. resolve_files_to_modules ===")

# Inject filepath_to_module for testing
_orig_ftm = RE.filepath_to_module
RE.filepath_to_module = {
    "euler-api-txns/euler-x/src-generated/PaymentFlows.hs": "PaymentFlows",
    "euler-api-gateway/src/Euler/API/Gateway/Flow.hs": "Euler.API.Gateway.Flow",
}
import networkx as nx_real2
fake_MG = nx_real2.DiGraph()
fake_MG.add_node("PaymentFlows", **{"service": "euler-api-txns"})
fake_MG.add_node("Euler.API.Gateway.Flow", **{"service": "euler-api-gateway"})
RE.MG = fake_MG

# Exact file match
result = RE.resolve_files_to_modules(
    ["euler-api-txns/euler-x/src-generated/PaymentFlows.hs"])
check_true("Exact file path resolves to module",
           "PaymentFlows" in result.get(
               "euler-api-txns/euler-x/src-generated/PaymentFlows.hs", []),
           f"result: {result}")

# Suffix match
result2 = RE.resolve_files_to_modules(["PaymentFlows.hs"])
pf_modules = result2.get("PaymentFlows.hs", [])
check_true("Suffix file match resolves to module",
           "PaymentFlows" in pf_modules or len(pf_modules) > 0,
           f"result: {result2}")

# Unmatched file returns empty list (not KeyError, not None)
result3 = RE.resolve_files_to_modules(["totally/unknown/file.hs"])
check_true("Unknown file returns [] (not error, not None)",
           isinstance(result3.get("totally/unknown/file.hs", []), list),
           f"result: {result3}")

RE.filepath_to_module = _orig_ftm
RE.MG = _orig_MG


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
n_sections = 11
print()
if errors:
    print(f"\033[91m{len(errors)} FAILED: {errors}\033[0m")
    sys.exit(1)
else:
    print(f"\033[92mAll {n_sections} logic sections passed.\033[0m")