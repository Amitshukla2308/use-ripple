#!/usr/bin/env python3
"""
09_build_viz_data.py — Build compact viz_data.json for the D3 visualization.

Reads:  $ARTIFACT_DIR/graph_with_summaries.json
        $ARTIFACT_DIR/cochange_index.json
Writes: $OUTPUT_DIR/viz_data.json  (target < 3 MB)

Usage:
    ARTIFACT_DIR=/path/to/artifacts OUTPUT_DIR=/path/to/output python3 09_build_viz_data.py
"""

import json
import math
import os
import pathlib
import sys
from collections import defaultdict
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ARTIFACT_DIR = pathlib.Path(os.environ.get("ARTIFACT_DIR", "/home/beast/projects/workspaces/juspay/artifacts"))
OUTPUT_DIR   = pathlib.Path(os.environ.get("OUTPUT_DIR",   "/home/beast/projects/workspaces/juspay/output"))

GRAPH_FILE    = ARTIFACT_DIR / "graph_with_summaries.json"
COCHANGE_FILE = ARTIFACT_DIR / "cochange_index.json"
OUTPUT_FILE   = OUTPUT_DIR   / "viz_data.json"

MAX_MODULES_PER_CLUSTER = 60
MIN_SERVICE_EDGE_WEIGHT  = 3
MIN_COCHANGE_WEIGHT      = 5
MAX_CLUSTER_EDGES        = 200

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def load():
    print(f"Loading graph from {GRAPH_FILE} …", flush=True)
    with open(GRAPH_FILE) as f:
        graph = json.load(f)
    print(f"  nodes={len(graph['nodes']):,}  edges={len(graph['edges']):,}  "
          f"cluster_summaries={len(graph.get('cluster_summaries', {}))}", flush=True)

    print(f"Loading cochange from {COCHANGE_FILE} …", flush=True)
    with open(COCHANGE_FILE) as f:
        cochange = json.load(f)
    print(f"  cochange modules={len(cochange['edges']):,}", flush=True)

    return graph, cochange

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_list(raw, n):
    """Return first n items from a value that may be a list or a JSON-encoded string."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw[:n]
    if isinstance(raw, str):
        # stored as repr/json string by older pipeline versions
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed[:n]
        except json.JSONDecodeError:
            pass
        # fallback: strip brackets and split by ', '
        stripped = raw.strip("[]")
        if stripped:
            items = [s.strip().strip("'\"") for s in stripped.split("', '")]
            return items[:n]
    return []

def _lang_fractions(lang_counts: dict) -> dict:
    total = sum(lang_counts.values())
    if total == 0:
        return {}
    return {lang: round(count / total, 3) for lang, count in lang_counts.items()}

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def build(graph, cochange):
    nodes = graph["nodes"]
    edges = graph["edges"]
    cluster_summaries = graph.get("cluster_summaries", {})

    # Normalise cluster_summaries keys to int
    cs = {}
    for k, v in cluster_summaries.items():
        try:
            cs[int(k)] = v
        except (ValueError, TypeError):
            cs[k] = v

    # Only visualise clusters that have summaries (the N "named" clusters)
    valid_clusters = set(cs.keys())
    print(f"  cluster_summaries={len(valid_clusters)} (filtering graph's full cluster set to these)", flush=True)

    # -----------------------------------------------------------------------
    # Pass 1: per-node indexes
    # -----------------------------------------------------------------------
    print("Pass 1: indexing nodes …", flush=True)

    # module_id → {service, cluster, lang, symbol_count}
    module_meta: dict[str, dict] = {}
    # service → {symbol_count, module_ids, cluster_ids, lang_counts}
    service_meta: dict[str, dict] = defaultdict(lambda: {
        "symbol_count": 0,
        "module_ids": set(),
        "cluster_ids": set(),
        "lang_counts": defaultdict(int),
    })
    # cluster → {service, symbol_count, module_ids, lang_counts}  (only valid_clusters)
    cluster_meta: dict[int, dict] = defaultdict(lambda: {
        "service": None,
        "symbol_count": 0,
        "module_ids": set(),
        "lang_counts": defaultdict(int),
    })
    # module_id (dot-notation) → cluster
    module_to_cluster: dict[str, int] = {}

    for node in nodes:
        svc     = node.get("service") or "unknown"
        mod     = node.get("module")  or ""
        lang    = node.get("lang")    or "unknown"
        cluster = node.get("cluster")

        # Normalise cluster to int where possible
        if cluster is not None:
            try:
                cluster = int(cluster)
            except (ValueError, TypeError):
                pass

        # service — count ALL nodes
        sm = service_meta[svc]
        sm["symbol_count"] += 1
        if mod:
            sm["module_ids"].add(mod)
        if cluster is not None and cluster in valid_clusters:
            sm["cluster_ids"].add(cluster)
        sm["lang_counts"][lang] += 1

        # cluster — only summarised clusters
        if cluster is not None and cluster in valid_clusters:
            cm = cluster_meta[cluster]
            cm["symbol_count"] += 1
            if mod:
                cm["module_ids"].add(mod)
            cm["lang_counts"][lang] += 1
            if cm["service"] is None:
                cm["service"] = svc

        # module
        if mod:
            if mod not in module_meta:
                module_meta[mod] = {"service": svc, "cluster": cluster, "lang": lang, "symbol_count": 0}
            module_meta[mod]["symbol_count"] += 1
            if cluster is not None and cluster in valid_clusters:
                module_to_cluster[mod] = cluster

    print(f"  services={len(service_meta)}  clusters(named)={len(cluster_meta)}  "
          f"modules={len(module_meta)}", flush=True)

    # -----------------------------------------------------------------------
    # Pass 2: service edges from import edges
    # -----------------------------------------------------------------------
    print("Pass 2: building service edges …", flush=True)

    # Build module → service lookup fast
    mod_to_svc: dict[str, str] = {mod: meta["service"] for mod, meta in module_meta.items()}

    svc_edge_counts: dict[tuple, int] = defaultdict(int)
    for edge in edges:
        if edge.get("kind") != "import":
            continue
        src_mod = edge.get("from", "")
        tgt_mod = edge.get("to", "")
        # module ids may be full symbol ids; strip trailing ::symbol_name heuristically
        # just look up directly, then try parent prefix
        src_svc = mod_to_svc.get(src_mod)
        tgt_svc = mod_to_svc.get(tgt_mod)
        if src_svc is None or tgt_svc is None:
            continue
        if src_svc != tgt_svc:
            key = (src_svc, tgt_svc)
            svc_edge_counts[key] += 1

    service_edges = [
        {"source": src, "target": tgt, "weight": w}
        for (src, tgt), w in svc_edge_counts.items()
        if w >= MIN_SERVICE_EDGE_WEIGHT
    ]
    service_edges.sort(key=lambda e: -e["weight"])
    print(f"  service_edges={len(service_edges)} (weight>={MIN_SERVICE_EDGE_WEIGHT})", flush=True)

    # -----------------------------------------------------------------------
    # Pass 3: cluster edges from cochange
    # Cochange keys use service::repo::src::Haskell::Module format.
    # Graph module field uses dot-notation: Haskell.Module (no service prefix).
    # Normalise cochange keys by extracting the module path after "::src::".
    # -----------------------------------------------------------------------
    print("Pass 3: building cluster edges from cochange …", flush=True)

    def _norm_cochange_key(key: str) -> str:
        """Extract dot-notation module path from a cochange key.
        e.g. 'euler-api-gateway::common::src::Euler::API::Gateway::Config'
              → 'Euler.API.Gateway.Config'
        Falls back to replacing all '::' with '.' if 'src' not found.
        """
        parts = key.split("::")
        try:
            idx = parts.index("src")
            return ".".join(parts[idx + 1:])
        except ValueError:
            # No 'src' segment — drop first segment (service/repo name)
            return ".".join(parts[1:]) if len(parts) > 1 else key

    cc_edges = cochange.get("edges", {})

    # Build normalised lookup: dot_module → cluster
    # (module_to_cluster already uses dot-notation from graph nodes)
    cc_norm_to_cluster: dict[str, int] = {}
    for cc_key in cc_edges:
        norm = _norm_cochange_key(cc_key)
        cl = module_to_cluster.get(norm)
        if cl is not None:
            cc_norm_to_cluster[cc_key] = cl

    print(f"  cochange keys matched to clusters: {len(cc_norm_to_cluster):,} / {len(cc_edges):,}", flush=True)

    cluster_edge_counts: dict[tuple, int] = defaultdict(int)

    for mod_a, cl_a in cc_norm_to_cluster.items():
        neighbors = cc_edges.get(mod_a, [])
        for entry in neighbors:
            if not isinstance(entry, dict):
                continue
            w = entry.get("weight", 0)
            if w < MIN_COCHANGE_WEIGHT:
                continue
            mod_b = entry.get("module", "")
            cl_b = cc_norm_to_cluster.get(mod_b)
            if cl_b is None or cl_a == cl_b:
                continue
            key = (min(cl_a, cl_b), max(cl_a, cl_b))
            cluster_edge_counts[key] += w

    # Keep top MAX_CLUSTER_EDGES
    top_cluster_edges = sorted(cluster_edge_counts.items(), key=lambda x: -x[1])[:MAX_CLUSTER_EDGES]
    cluster_edges = [
        {"source": src, "target": tgt, "weight": w, "type": "cochange"}
        for (src, tgt), w in top_cluster_edges
    ]
    print(f"  cluster_edges={len(cluster_edges)}", flush=True)

    # -----------------------------------------------------------------------
    # Pass 4: modules per cluster (top 60 by symbol_count)
    # -----------------------------------------------------------------------
    print("Pass 4: building module lists per cluster …", flush=True)

    # cochange top partners per module
    mod_top_cochange: dict[str, list[str]] = {}
    for mod_a, neighbors in cc_edges.items():
        if not isinstance(neighbors, list):
            continue
        sorted_nb = sorted(
            [e for e in neighbors if isinstance(e, dict)],
            key=lambda x: -x.get("weight", 0)
        )
        mod_top_cochange[mod_a] = [e["module"] for e in sorted_nb[:5] if "module" in e]

    modules_by_cluster: dict[str, list] = {}
    for cluster_id, cm in cluster_meta.items():
        mods = sorted(
            cm["module_ids"],
            key=lambda m: -module_meta.get(m, {}).get("symbol_count", 0)
        )[:MAX_MODULES_PER_CLUSTER]

        modules_by_cluster[str(cluster_id)] = [
            {
                "id":            m,
                "label":         ".".join(m.split("::")[-2:]) if "::" in m else m,
                "service":       module_meta.get(m, {}).get("service", ""),
                "symbol_count":  module_meta.get(m, {}).get("symbol_count", 0),
                "lang":          module_meta.get(m, {}).get("lang", ""),
                "top_cochange":  mod_top_cochange.get(m, [])[:5],
            }
            for m in mods
        ]

    # -----------------------------------------------------------------------
    # Assemble output
    # -----------------------------------------------------------------------
    print("Assembling output …", flush=True)

    services_out = []
    for svc, sm in sorted(service_meta.items()):
        services_out.append({
            "id":           svc,
            "symbol_count": sm["symbol_count"],
            "module_count": len(sm["module_ids"]),
            "cluster_ids":  sorted(sm["cluster_ids"]),
            "langs":        _lang_fractions(sm["lang_counts"]),
        })

    clusters_out = []
    for cluster_id, cm in sorted(cluster_meta.items(), key=lambda x: x[0]):
        summary = cs.get(cluster_id, cs.get(str(cluster_id), {})) or {}
        contracts  = _safe_list(summary.get("contracts"),  5)
        risk_flags = _safe_list(summary.get("risk_flags"), 3)
        purpose    = summary.get("purpose", "") or ""
        if isinstance(purpose, list):
            purpose = " ".join(purpose)

        clusters_out.append({
            "id":           cluster_id,
            "label":        summary.get("name", f"Cluster {cluster_id}"),
            "purpose":      str(purpose)[:500],
            "service":      cm["service"] or "unknown",
            "symbol_count": cm["symbol_count"],
            "module_count": len(cm["module_ids"]),
            "risk_flags":   risk_flags,
            "contracts":    contracts,
        })

    meta = {
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "service_count": len(service_meta),
        "cluster_count": len(cluster_meta),
        "module_count":  len(module_meta),
        "symbol_count":  len(nodes),
    }

    out = {
        "meta":          meta,
        "services":      services_out,
        "clusters":      clusters_out,
        "service_edges": service_edges,
        "cluster_edges": cluster_edges,
        "modules":       modules_by_cluster,
    }

    return out

# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
def main():
    if not GRAPH_FILE.exists():
        print(f"ERROR: {GRAPH_FILE} not found", file=sys.stderr)
        sys.exit(1)
    if not COCHANGE_FILE.exists():
        print(f"ERROR: {COCHANGE_FILE} not found", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    graph, cochange = load()
    out = build(graph, cochange)

    print(f"Writing {OUTPUT_FILE} …", flush=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(out, f, separators=(",", ":"))

    size_mb = OUTPUT_FILE.stat().st_size / 1_048_576
    print(f"\nDone. {OUTPUT_FILE}  ({size_mb:.2f} MB)")
    print(f"  services      : {out['meta']['service_count']}")
    print(f"  clusters      : {out['meta']['cluster_count']}")
    print(f"  modules       : {out['meta']['module_count']}")
    print(f"  symbols       : {out['meta']['symbol_count']:,}")
    print(f"  service_edges : {len(out['service_edges'])}")
    print(f"  cluster_edges : {len(out['cluster_edges'])}")


if __name__ == "__main__":
    main()
