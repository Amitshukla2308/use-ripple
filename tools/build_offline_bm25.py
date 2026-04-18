#!/usr/bin/env python3
"""Build an offline BM25 index that exactly matches production corpus composition.

Root cause of T-014b inconclusiveness: the offline validation script used
  text = name + module + summary + keywords  (whitespace tokenizer)
while production uses
  text = name + module + type[:100] + cluster_name  (non-alphanumeric split)

The module field contains dot-notation like 'Euler.Product.Refund.Handler'
which the production tokenizer splits into ['euler','product','refund','handler'].
High-frequency domain terms ('refund', 'mandate') appear in thousands of module
names, making n_positive~3600 in production vs ~148 in the wrong offline corpus.

Usage:
  python3 tools/build_offline_bm25.py [--graph PATH] [--verify] [--save PATH]

Output:
  Prints n_positive for a set of canary queries.
  Optionally saves (bm25_ids, bm25_corpus) as a pickle for reuse in benchmarks.
"""
import json, re, sys, pathlib, argparse

ARTIFACT_DIR = pathlib.Path("/home/beast/projects/workspaces/juspay/artifacts")
DEFAULT_GRAPH = ARTIFACT_DIR / "graph_with_summaries.json"

CANARY_QUERIES = [
    "refund",           # production n_pos=3626 (high-freq, false-skip case)
    "mandate",          # production n_pos=2884 (high-freq, false-skip case)
    "chargeback",       # production n_pos≈medium
    "reconciliation",   # production n_pos≈medium
    "upi payment",      # multi-word, should always rerank
    "payment gateway",  # multi-word
]
PRODUCTION_NPOS = {
    "refund": 3626,
    "mandate": 2884,
}


def _tokenize(text: str) -> list[str]:
    """Exact replica of production _tokenize_for_bm25."""
    return [t for t in re.split(r'[^a-zA-Z0-9]+', text.lower()) if len(t) >= 2]


def build_from_graph(graph_path: pathlib.Path):
    print(f"Loading graph: {graph_path} ...", flush=True)
    with open(graph_path) as f:
        raw = json.load(f)

    # graph_with_summaries.json is {"nodes": {...}, "edges": [...]} or a list
    if isinstance(raw, dict) and "nodes" in raw:
        nodes_src = raw["nodes"]
        if isinstance(nodes_src, dict):
            nodes = list(nodes_src.values())
        else:
            nodes = nodes_src
    elif isinstance(raw, list):
        nodes = raw
    else:
        nodes = list(raw.values())

    print(f"  {len(nodes):,} nodes total", flush=True)

    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        print("pip install rank-bm25"); sys.exit(1)

    corpus, ids, svcs = [], [], []
    skipped_phantom = 0
    for n in nodes:
        if isinstance(n, dict) and n.get("kind") == "phantom":
            skipped_phantom += 1
            continue
        # EXACT MATCH of production _build_bm25_index text formula
        text = " ".join([
            (n.get("name", "") if isinstance(n, dict) else ""),
            (n.get("module", "") if isinstance(n, dict) else ""),
            (n.get("type", "") or "")[:100],
            (n.get("cluster_name", "") if isinstance(n, dict) else ""),
        ])
        tokens = _tokenize(text)
        if not tokens:
            continue
        corpus.append(tokens)
        ids.append(n.get("id", n.get("name", "?")) if isinstance(n, dict) else "?")
        svcs.append(n.get("service", "unknown") if isinstance(n, dict) else "unknown")

    print(f"  {len(corpus):,} indexed docs ({skipped_phantom} phantom skipped)", flush=True)
    bm25 = BM25Okapi(corpus)
    return bm25, ids, svcs, corpus


def analyze_query(bm25, query: str, n_docs: int):
    tokens = _tokenize(query)
    if not tokens:
        return {"query": query, "n_positive": 0, "spread": 0.0, "max_score": 0.0}
    scores = bm25.get_scores(tokens)
    pos = sorted([s for s in scores if s > 0], reverse=True)
    n_pos = len(pos)
    if not pos:
        return {"query": query, "n_positive": 0, "spread": 0.0, "max_score": 0.0}
    max_s = pos[0]
    med_s = pos[len(pos) // 2]
    spread = (max_s - med_s) / max_s if max_s > 0 else 0.0
    return {"query": query, "n_positive": n_pos, "spread": round(spread, 3), "max_score": round(max_s, 4)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--graph", default=str(DEFAULT_GRAPH), help="Path to graph_with_summaries.json")
    ap.add_argument("--verify", action="store_true", help="Compare n_positive against known production values")
    ap.add_argument("--save", default="", help="Save corpus+ids as pickle to this path for benchmark reuse")
    args = ap.parse_args()

    bm25, ids, svcs, corpus = build_from_graph(pathlib.Path(args.graph))
    n_docs = len(corpus)

    print(f"\n{'Query':<25} {'n_pos':>7} {'spread':>7} {'max_score':>10}  {'prod_n_pos':>10}  {'delta%':>7}")
    print("-" * 75)

    all_ok = True
    for q in CANARY_QUERIES:
        r = analyze_query(bm25, q, n_docs)
        prod = PRODUCTION_NPOS.get(q, "?")
        if isinstance(prod, int):
            delta = f"{100*(r['n_positive']-prod)/prod:+.1f}%"
            if abs(r['n_positive'] - prod) / prod > 0.30:
                delta += " ⚠"
                all_ok = False
        else:
            delta = "—"
        print(f"  {q:<23} {r['n_positive']:>7,} {r['spread']:>7.3f} {r['max_score']:>10.4f}  {str(prod):>10}  {delta:>7}")

    print()
    if args.verify:
        if all_ok:
            print("✓ CORPUS MATCH — offline n_pos within 30% of production for all canary queries")
        else:
            print("✗ CORPUS MISMATCH — n_pos diverges >30% from production; check graph path or node fields")

    if args.save:
        import pickle
        with open(args.save, "wb") as f:
            pickle.dump({"ids": ids, "svcs": svcs, "corpus": corpus}, f)
        print(f"Saved corpus to {args.save} ({pathlib.Path(args.save).stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
