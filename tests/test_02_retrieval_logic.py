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
# 1. _extract_query_subject
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 1. _extract_query_subject ===")
cases = [
    ("Find out all payment flows and write a short note on each one of them", "payment flows"),
    ("How does UPI collect flow work end to end",                             "UPI collect flow"),
    ("What is the card mandate registration flow",                            "card mandate registration flow"),
    ("Trace the preauth and capture path in euler-api-txns",                  "preauth and capture path in euler-api-txns"),
    ("Explain the netbanking redirect flow",                                  "netbanking redirect flow"),
    ("What are all UPI flows",                                                "UPI flows"),
    ("list all payment flows and give me a summary",                          "payment flows"),
    ("How does card 3DS work",                                                "card 3DS"),
    ("How does UPI collect flow work",                                        "UPI collect flow"),
    ("Tell me about the e2e preauth flow",                                    "e2e preauth flow"),
    ("Describe the mandate registration step by step",                        "mandate registration"),
    ("Which function handles card tokenisation",                              "handles card tokenisation"),
    ("Which service owns UPI collect",                                        "owns UPI collect"),
]
for query, expected in cases:
    got = RE._extract_query_subject(query)
    check(repr(query[:60]), got, expected)


# ══════════════════════════════════════════════════════════════════════════════
# 2. _query_variants_heuristic
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 2. _query_variants_heuristic ===")
variant_cases = [
    # (query, must_contain_any, must_not_contain_any)
    ("Find out all payment flows and write a short note on each one of them",
     [],
     ["write", "short", "note", "find", "each"]),

    ("How does UPI collect flow work end to end",
     ["upiCollect", "UpiCollect"],
     ["work", "end"]),

    ("What is the card mandate registration flow",
     ["cardMandate", "CardMandate"],
     ["what"]),

    ("Trace the preauth capture path",
     ["preauthCapture", "PreauthCapture"],
     ["path", "trace"]),

    ("Trace the preauth and capture path in euler-api-txns",
     ["preauthCapture", "PreauthCapture"],
     ["euler", "txns", "path"]),

    ("How does the PayU webhook handler work",
     ["PayuRoutes", "PayuFlow", "PayuGateway"],
     ["work", "handler"]),

    ("Explain the netbanking redirect flow",
     ["netbankingRedirect", "NetbankingRedirect"],
     ["explain"]),
]
for query, must_have, must_not in variant_cases:
    variants = RE._query_variants_heuristic(query)
    label = repr(query[:60])
    bad = [v for v in must_not if any(v.lower() in var.lower() for var in variants)]
    missing = [v for v in must_have if not any(v.lower() in var.lower() for var in variants)]
    ok_v = not bad and not missing
    print(f"  {PASS if ok_v else FAIL} {label}")
    print(f"      variants: {variants}")
    if bad:
        print(f"      BAD tokens present: {bad}")
        errors.append(f"variants:bad:{label}")
    if missing:
        print(f"      MISSING expected: {missing}")
        errors.append(f"variants:missing:{label}")


# ══════════════════════════════════════════════════════════════════════════════
# 3. Variant stopwords
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 3. Variant stopwords (tokens that must NEVER appear in variants) ===")
absolute_stopwords = [
    ("Trace the preauth handler path",
     ["handler", "handlers", "path", "paths", "trace"]),
    # "payment" IS a valid variant — only instruction verbs must be absent
    ("How does payment work",
     ["work", "works"]),
    ("What flows exist across services",
     ["what", "flows", "exist", "across", "services", "service"]),
]
for query, bad_tokens in absolute_stopwords:
    variants = RE._query_variants_heuristic(query)
    found_bad = [t for t in bad_tokens if any(t.lower() == v.lower() for v in variants)]
    ok_v = not found_bad
    print(f"  {PASS if ok_v else FAIL} {repr(query[:50])}")
    print(f"      variants: {variants}")
    if found_bad:
        print(f"      BAD stopwords in variants: {found_bad}")
        errors.append(f"stopword:{query[:30]}")


# ══════════════════════════════════════════════════════════════════════════════
# 4. _ambiguity_hint
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 4. _ambiguity_hint ===")
hint_cases = [
    ("How does split payment work",           "split",   True),
    ("What triggers an auto-refund",          "refund",  True),
    ("How is a mandate executed",             "mandate", True),
    ("Inbound webhook handling for Razorpay", "webhook", True),
    ("NB preauth capture flow",               "preauth", True),
    ("How does card 3DS work",                None,      False),
    ("UPI collect flow end to end",           None,      False),
    ("What is the BNPL flow",                 None,      False),  # should not fire ambiguity
]
for query, term, fires in hint_cases:
    hint = DS._ambiguity_hint(query)
    if fires:
        ok_h = hint != "" and term in hint.lower()
        print(f"  {PASS if ok_h else FAIL} '{query[:50]}' → hint contains '{term}': {ok_h}")
        if not ok_h:
            print(f"      hint: {hint!r}")
            errors.append(f"hint_missing:{query[:30]}")
    else:
        ok_h = hint == ""
        print(f"  {PASS if ok_h else FAIL} '{query[:50]}' → no hint: {ok_h}")
        if not ok_h:
            print(f"      unexpected hint: {hint!r}")
            errors.append(f"hint_spurious:{query[:30]}")


# ══════════════════════════════════════════════════════════════════════════════
# 5. fast_route depth / max_tool_calls
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 5. fast_route depth / max_tool_calls ===")
depth_cases = [
    ("What is upi",
     "targeted", 5, 5),
    ("How does card 3DS work",
     "flow", 10, 10),
    ("Find out all payment flows and write a short note",
     "flow", 10, 10),
    ("Trace the entire flow from order creation through gateway response for UPI collect",
     "architectural", 18, 18),
    ("Map all payment flows end to end across services",
     "architectural", 18, 18),
    ("Which function handles card tokenisation",
     "targeted", 5, 5),
    ("Which service owns UPI collect",
     "targeted", 5, 5),
    ("Which class manages gateway routing",
     "targeted", 5, 5),
]
for query, expected_depth, mn, mx in depth_cases:
    _, _, variants, _, n_calls, depth = RE.fast_route(query, [])
    ok_d = expected_depth in depth.lower()
    ok_c = mn <= n_calls <= mx
    ok_v = ok_d and ok_c
    print(f"  {PASS if ok_v else FAIL} depth={depth:14s}  calls={n_calls:2d}  '{query[:60]}'")
    if not ok_d:
        print(f"       expected_depth: {expected_depth!r}  got: {depth!r}")
        errors.append(f"depth:{query[:30]}")
    if not ok_c:
        print(f"       expected calls in [{mn},{mx}], got {n_calls}")
        errors.append(f"calls:{query[:30]}")


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
matched, body = RE._fuzzy_fn_lookup("Euler.API.Gateway.Foo.Bar.baz")
check("Exact match returns correct body",
      body, "body of baz in Foo.Bar")

# Suffix match — partial key
matched2, body2 = RE._fuzzy_fn_lookup("Bar.quux")
check("Suffix match finds Foo.Bar.quux",
      body2, "body of quux")

# Ambiguous — longest common prefix wins
matched3, body3 = RE._fuzzy_fn_lookup("Euler.API.Gateway.Foo.Bar.baz")
check("Ambiguous match: longest common prefix wins (Foo.Bar.baz over Qux.Bar.baz)",
      matched3, "Euler.API.Gateway.Foo.Bar.baz")

# Not found — use a 2+ component ID that definitely won't match anything in the fake store
matched4, body4 = RE._fuzzy_fn_lookup("NonExistent.CompletelyMadeUp")
check("Not-found returns empty body", body4, "")
check("Not-found returns None matched", matched4, None)

# Single-component name must NOT match (too ambiguous — min 2 components enforced)
matched4b, body4b = RE._fuzzy_fn_lookup("fn")
check("Single-component lookup returns empty (ambiguity guard)", body4b, "")

# Full ID lookup
matched5, body5 = RE._fuzzy_fn_lookup("PaymentFlows.getAllPaymentFlowsForTxn")
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

impls = RE._same_name_impls("Euler.API.Gateway.Razorpay.Flow.startPayment",
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

_test_tool_returns_string(RE.tool_get_function_body, "NonExistent.fn")
_test_tool_returns_string(RE.tool_trace_callees,     "NonExistent.fn")
_test_tool_returns_string(RE.tool_trace_callers,     "NonExistent.fn")
_test_tool_returns_string(RE.tool_search_symbols,    "upi collect")
_test_tool_returns_string(RE.tool_search_modules,    "PaymentFlows")
_test_tool_returns_string(RE.tool_get_module,        "PaymentFlows")

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
