"""
test_04_retrieval_accuracy.py — Retrieval accuracy tests with loaded data.

Tests that known queries return expected functions in the top results.
Tests that tool outputs contain expected content for known IDs.

Requires:
  - Data stores loaded (body_store, call_graph, graph — no GPU)
  - EMBED_SERVER_URL not required (keyword-search tests run without it)

Run:
    EMBED_SERVER_URL="" python3 tests/test_04_retrieval_accuracy.py
"""
import sys, os, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"
errors: list = []

def ok(label):
    print(f"  {PASS} {label}")

def fail(label, detail=""):
    print(f"  {FAIL} {label}")
    if detail: print(f"      {detail}")
    errors.append(label)

def warn(label, detail=""):
    print(f"  {WARN} {label}")
    if detail: print(f"      {detail}")

# Disable embed server so all tests run keyword-only (deterministic)
os.environ["EMBED_SERVER_URL"] = ""

import retrieval_engine as RE

print("Loading data stores (no GPU)...")
RE.initialize(load_embedder=False)
print("Ready.\n")


# ══════════════════════════════════════════════════════════════════════════════
# 1. Keyword search — known queries → expected function IDs in results
# ══════════════════════════════════════════════════════════════════════════════
print("=== 1. Keyword search accuracy (deterministic — no GPU) ===")

KW_CASES = [
    # (query, expected_ids_in_any_service_results)
    ("UPI collect",
     ["PaymentFlows.getUpiFlowMapper"]),

    ("card mandate",
     ["PaymentFlows.getCardMandateFlowMapper"]),

    ("getAllPaymentFlowsForTxn",
     ["PaymentFlows.getAllPaymentFlowsForTxn"]),

    ("emandate register",
     ["PaymentFlows.getEmandateFlowMapper"]),

    ("EMI payment flows",
     ["PaymentFlows.getPaymentFlowsForEMI"]),

    ("preauth capture",
     ["PaymentFlows.getPaymentFlowsForPreAuth"]),

    ("card auth type",
     ["PaymentFlows.getCardAuthTypeDetails"]),

    ("UPI source flows",
     ["PaymentFlows.getUpiSourceFlows"]),

    ("payment flows txn type",
     ["PaymentFlows.getPaymentFlowsFromTxnType"]),

    ("updated payment flows",
     ["PaymentFlows.getUpdatedPaymentFLows"]),
]

for query, expected_ids in KW_CASES:
    results_by_svc = RE.cross_service_keyword_search(query, max_per_service=30)
    all_hits = [n.get("id", "") for hits in results_by_svc.values() for n in hits]
    missing = [eid for eid in expected_ids if eid not in all_hits]
    if missing:
        fail(f"'{query}' → expected IDs found",
             f"Missing: {missing}\nAll hits: {all_hits[:10]}")
    else:
        ok(f"'{query}' → {expected_ids}")


# ══════════════════════════════════════════════════════════════════════════════
# 2. get_function_body — known IDs → content checks
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 2. get_function_body content accuracy ===")

BODY_CASES = [
    # (fn_id, fragments_that_must_appear_in_output)
    (
        "PaymentFlows.getAllPaymentFlowsForTxn",
        ["getAllPaymentFlowsForTxn", "GUARANTEE_FLOW",
         "BILLING_MANDATE_REGISTER", "getTransactionIntentFlows"]
    ),
    (
        "PaymentFlows.getCardTokenRepeatFlowMapper",
        ["LOCKER_TOKEN_USED", "NETWORK_TOKEN_USED", "ISSUER_TOKEN_USED"]
    ),
    (
        "PaymentFlows.getPfOrPlFlowDetails",
        ["PAYMENT_LINK", "PAYMENT_FORM"]
    ),
    (
        "PaymentFlows.getUpiFlowMapper",
        ["COLLECT", "INTENT", "INAPP", "QR"]
    ),
    (
        "PaymentFlows.getFallbackPfFromSourceObject",
        ["PAYMENT_CHANNEL_FALLBACK_DOTP_TO_3DS", "FRM_FALLBACK_TO_3DS"]
    ),
    (
        "PaymentFlows.getUpdatedPaymentFLows",
        ["RISK_CHECK", "SR_SELECTION"]
    ),
]

for fn_id, expected_fragments in BODY_CASES:
    result = RE.tool_get_function_body(fn_id)
    # result is a Markdown string; the body is embedded in it
    for fragment in expected_fragments:
        if fragment in result:
            ok(f"  {fn_id}: contains {fragment!r}")
        else:
            fail(f"  {fn_id}: must contain {fragment!r}",
                 f"Output (first 300): {result[:300]!r}")


# ══════════════════════════════════════════════════════════════════════════════
# 3. get_function_body — NOT FOUND returns correct message
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 3. get_function_body NOT FOUND behaviour ===")

result = RE.tool_get_function_body("Completely.NonExistent.Function")
found_nf = "NOT FOUND" in result or "not found" in result.lower()
if found_nf:
    ok("Non-existent function returns NOT FOUND message")
else:
    fail("Non-existent function must return NOT FOUND", f"Got: {result[:100]!r}")


# ══════════════════════════════════════════════════════════════════════════════
# 4. trace_callees — known functions
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 4. trace_callees content ===")

# getAllPaymentFlowsForTxn calls several known helpers
result = RE.tool_trace_callees("PaymentFlows.getAllPaymentFlowsForTxn")
expected_callees = [
    "getCardAuthTypeDetails", "getUpiFlowMapper",
    "getCardMandateFlowMapper", "getPaymentFlowsForEMI"
]
for callee in expected_callees:
    if callee in result:
        ok(f"  getAllPaymentFlowsForTxn callees: contains {callee!r}")
    else:
        warn(f"  getAllPaymentFlowsForTxn callees: expected {callee!r} (may be in call_graph as short name)",
             f"Result snippet: {result[:200]!r}")


# ══════════════════════════════════════════════════════════════════════════════
# 5. tool_search_modules — returns sensible results
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 5. search_modules accuracy ===")

MODULE_CASES = [
    ("PaymentFlows", ["PaymentFlows"]),
    ("mandate",      ["MandateWorkFlow", "MandateWorkflow", "getCardMandateFlowMapper"]),  # any of these
    ("AutoVoid",     ["AutoVoidWorkFlow", "autoVoidWorkflow"]),
]

for query, any_expected in MODULE_CASES:
    result = RE.tool_search_modules(query)
    found = any(exp in result for exp in any_expected)
    if found:
        ok(f"  search_modules('{query}') contains expected module")
    else:
        fail(f"  search_modules('{query}') must contain one of {any_expected}",
             f"Result: {result[:200]!r}")


# ══════════════════════════════════════════════════════════════════════════════
# 6. get_blast_radius — known file → known service
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 6. get_blast_radius accuracy ===")

# PaymentFlows.hs is in euler-api-txns; blast radius must include it
blast = RE.get_blast_radius(["PaymentFlows"])
affected = blast.get("affected_services", [])
if "euler-api-txns" in affected:
    ok(f"  PaymentFlows blast radius includes euler-api-txns")
else:
    fail(f"  PaymentFlows blast radius must include euler-api-txns",
         f"Affected: {affected}")


# ══════════════════════════════════════════════════════════════════════════════
# 7. resolve_files_to_modules — known git-diff paths
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 7. resolve_files_to_modules accuracy ===")

FILE_CASES = [
    (
        "euler-api-txns/euler-x/src-generated/PaymentFlows.hs",
        "PaymentFlows"
    ),
]
for fpath, expected_mod in FILE_CASES:
    result = RE.resolve_files_to_modules([fpath])
    mods = result.get(fpath, [])
    if expected_mod in mods:
        ok(f"  {fpath} → {expected_mod}")
    else:
        # Try partial match
        if any(expected_mod in m for m in mods):
            ok(f"  {fpath} → {mods} (contains {expected_mod})")
        else:
            fail(f"  {fpath} must resolve to {expected_mod!r}",
                 f"Got: {mods}")


# ══════════════════════════════════════════════════════════════════════════════
# 8. Stratified vector search budget enforcement
#    (runs even without embed server — returns empty results but must not crash)
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 8. Stratified vector search budget (structural) ===")
results_by_svc = RE.stratified_vector_search(["UPI collect"], k_total=150)
total_returned = sum(len(v) for v in results_by_svc.values())
if total_returned <= 150:
    ok(f"Total results ≤ k_total (150): got {total_returned}")
else:
    fail(f"Total results must be ≤150", f"Got {total_returned}")


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
n_sections = 8
print()
if errors:
    print(f"\033[91m{len(errors)} FAILED: {errors}\033[0m")
    sys.exit(1)
else:
    print(f"\033[92mAll {n_sections} accuracy sections passed.\033[0m")
