"""
bench_cochange_impact.py — Measure co-change integration impact on search.

Compares unified_search results with and without co-change expansion.
Runs in keyword-only mode (no GPU required).

Run:
    ARTIFACT_DIR=/path/to/artifacts python3 tests/bench_cochange_impact.py
"""
import sys, os, pathlib, json, time
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "serve"))

os.environ["EMBED_SERVER_URL"] = ""  # keyword-only mode

import retrieval_engine as RE

print("Loading data stores (no GPU)...")
RE.initialize(load_embedder=False)
print()

# ══════════════════════════════════════════════════════════════════════════════
# Test queries — chosen to exercise co-change (modules that change together)
# ══════════════════════════════════════════════════════════════════════════════
QUERIES = [
    "payment flow mapper",
    "gateway routes",
    "transaction sync",
    "refund processing",
    "mandate creation",
    "order status update",
    "customer authentication",
    "settlement flow",
    "UPI collect",
    "card tokenization",
]


def extract_modules(results: dict) -> list:
    """Extract unique modules from search results, preserving rank order."""
    seen = set()
    modules = []
    for svc in sorted(results.keys()):
        for node in results[svc]:
            mod = node.get("module", "")
            if mod and mod not in seen:
                seen.add(mod)
                modules.append(mod)
    return modules


def run_search(query, with_cochange=True):
    """Run unified_search, optionally disabling co-change."""
    saved = dict(RE.cochange_index) if not with_cochange else None
    if not with_cochange:
        RE.cochange_index.clear()
    try:
        results = RE.unified_search([query])
    finally:
        if saved is not None:
            RE.cochange_index.update(saved)
    return results


# ══════════════════════════════════════════════════════════════════════════════
# Run benchmark
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("BENCHMARK: Co-change Impact on Unified Search")
print("=" * 70)

total_new_modules = 0
total_new_nodes = 0
total_queries = 0
query_details = []

for query in QUERIES:
    t0 = time.time()
    results_with = run_search(query, with_cochange=True)
    t_with = time.time() - t0

    t0 = time.time()
    results_without = run_search(query, with_cochange=False)
    t_without = time.time() - t0

    mods_with = extract_modules(results_with)
    mods_without = extract_modules(results_without)
    new_modules = [m for m in mods_with if m not in set(mods_without)]

    nodes_with = sum(len(v) for v in results_with.values())
    nodes_without = sum(len(v) for v in results_without.values())
    new_nodes = nodes_with - nodes_without

    svcs_with = set(results_with.keys())
    svcs_without = set(results_without.keys())
    new_svcs = svcs_with - svcs_without

    total_new_modules += len(new_modules)
    total_new_nodes += max(0, new_nodes)
    total_queries += 1

    detail = {
        "query": query,
        "modules_with": len(mods_with),
        "modules_without": len(mods_without),
        "new_modules": len(new_modules),
        "new_module_names": new_modules[:5],
        "nodes_with": nodes_with,
        "nodes_without": nodes_without,
        "services_with": len(svcs_with),
        "services_without": len(svcs_without),
        "new_services": list(new_svcs),
        "time_with": t_with,
        "time_without": t_without,
    }
    query_details.append(detail)

    status = f"+{len(new_modules)} modules" if new_modules else "no change"
    svc_status = f" +{len(new_svcs)} svcs" if new_svcs else ""
    print(f"  [{status}{svc_status}] {query}")
    if new_modules:
        for m in new_modules[:3]:
            print(f"         → {m}")

print()
print("-" * 70)
print(f"SUMMARY ({total_queries} queries)")
print(f"  New modules surfaced by co-change: {total_new_modules}")
print(f"  Average new modules per query:     {total_new_modules / total_queries:.1f}")
print(f"  Queries where co-change helped:    {sum(1 for d in query_details if d['new_modules'] > 0)}/{total_queries}")

avg_time_with = sum(d["time_with"] for d in query_details) / total_queries
avg_time_without = sum(d["time_without"] for d in query_details) / total_queries
overhead_ms = (avg_time_with - avg_time_without) * 1000
print(f"  Avg latency with co-change:        {avg_time_with*1000:.0f}ms")
print(f"  Avg latency without:               {avg_time_without*1000:.0f}ms")
print(f"  Co-change overhead:                 {overhead_ms:.0f}ms")
print("-" * 70)

# Also test blast_radius directly
print()
print("BLAST RADIUS VERIFICATION")
test_modules = ["Euler.API.Gateway.Gateway.Common", "Euler.API.Txns.Flow",
                "PaymentFlows"]
for mod in test_modules:
    br = RE.get_blast_radius([mod])
    n_import = len(br["import_neighbors"])
    n_cochange = len(br["cochange_neighbors"])
    n_svcs = len(br["affected_services"])
    print(f"  {mod}: {n_import} import + {n_cochange} co-change neighbors, {n_svcs} services")

# Save results
out_path = pathlib.Path(__file__).parent / "generated"
out_path.mkdir(parents=True, exist_ok=True)
with open(out_path / "cochange_bench_results.json", "w") as f:
    json.dump({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_queries": total_queries,
        "total_new_modules": total_new_modules,
        "avg_new_modules_per_query": total_new_modules / total_queries,
        "queries_helped": sum(1 for d in query_details if d["new_modules"] > 0),
        "avg_latency_with_ms": avg_time_with * 1000,
        "avg_latency_without_ms": avg_time_without * 1000,
        "overhead_ms": overhead_ms,
        "details": query_details,
    }, f, indent=2)
print(f"\nResults saved to {out_path / 'cochange_bench_results.json'}")
