#!/usr/bin/env python3
"""
09b_build_scatter_data.py — Build 2D UMAP scatter data for the visualization.

Reads:  $ARTIFACT_DIR/vectors.lance       (114k symbol embeddings, 4096-dim)
        $ARTIFACT_DIR/graph_with_summaries.json  (node metadata)
Writes: $OUTPUT_DIR/scatter_data.json     (< 5 MB)

Pipeline: lancedb read → PCA 4096→50 → UMAP 50→2 → normalize → JSON

Usage:
    ARTIFACT_DIR=/path/to/artifacts OUTPUT_DIR=/path/to/output python3 09b_build_scatter_data.py

Runtime: ~5–15 min on CPU (PCA fast, UMAP ~10 min for 114k points).
Install: pip install umap-learn scikit-learn lancedb
"""

import json
import os
import pathlib
import sys
import time
from collections import defaultdict

import numpy as np

ARTIFACT_DIR = pathlib.Path(os.environ.get("ARTIFACT_DIR", "/home/beast/projects/workspaces/juspay/artifacts"))
OUTPUT_DIR   = pathlib.Path(os.environ.get("OUTPUT_DIR",   "/home/beast/projects/workspaces/juspay/output"))

LANCE_PATH  = ARTIFACT_DIR / "vectors.lance"
GRAPH_FILE  = ARTIFACT_DIR / "graph_with_summaries.json"
OUTPUT_FILE = OUTPUT_DIR   / "scatter_data.json"

PCA_DIMS  = 50     # intermediate PCA target before UMAP
MAX_NAMES = 2      # how many trailing dot-segments to keep for labels

# ---------------------------------------------------------------------------
# Load vectors from LanceDB
# ---------------------------------------------------------------------------
def load_vectors():
    print(f"Loading vectors from {LANCE_PATH} …", flush=True)
    try:
        import lancedb
        db  = lancedb.connect(str(LANCE_PATH))
        tbl = db.open_table("chunks")
        t0  = time.time()
        # Use PyArrow (no pandas dependency)
        arrow_tbl = tbl.to_arrow()
        print(f"  lancedb read: {arrow_tbl.num_rows:,} rows in {time.time()-t0:.1f}s", flush=True)
        ids     = arrow_tbl.column("id").to_pylist()
        vectors = np.stack(arrow_tbl.column("vector").to_pylist()).astype(np.float32)
    except Exception as e:
        print(f"lancedb failed ({e}), trying lance directly …", flush=True)
        try:
            import lance
            ds      = lance.dataset(str(LANCE_PATH))
            t0      = time.time()
            tbl     = ds.to_table(columns=["id", "vector"])
            ids     = tbl["id"].to_pylist()
            vectors = np.array(tbl["vector"].to_pylist(), dtype=np.float32)
            print(f"  lance read: {len(ids):,} rows in {time.time()-t0:.1f}s", flush=True)
        except Exception as e2:
            print(f"ERROR: cannot read vectors.lance — {e2}", file=sys.stderr)
            print("Install: pip install lancedb  OR  pip install lance", file=sys.stderr)
            sys.exit(1)

    print(f"  shape: {vectors.shape}", flush=True)
    return ids, vectors


# ---------------------------------------------------------------------------
# Load graph metadata: id → {service, cluster}
# ---------------------------------------------------------------------------
def load_graph_meta():
    print(f"Loading graph metadata from {GRAPH_FILE} …", flush=True)
    with open(GRAPH_FILE) as f:
        graph = json.load(f)

    meta      = {}   # id → {service, cluster, name}
    cs_labels = {}   # cluster_id (int) → label

    for n in graph.get("nodes", []):
        nid     = n.get("id") or ""
        svc     = n.get("service") or "unknown"
        cluster = n.get("cluster")
        try:
            cluster = int(cluster) if cluster is not None else -1
        except (ValueError, TypeError):
            cluster = -1
        parts  = nid.split(".")
        label  = ".".join(parts[-MAX_NAMES:]) if len(parts) >= MAX_NAMES else nid
        meta[nid] = {"service": svc, "cluster": cluster, "label": label}

    for k, v in graph.get("cluster_summaries", {}).items():
        try:
            cid = int(k)
        except (ValueError, TypeError):
            continue
        cs_labels[cid] = (v or {}).get("name", f"Cluster {k}") if isinstance(v, dict) else f"Cluster {k}"

    print(f"  nodes={len(meta):,}  cluster_labels={len(cs_labels)}", flush=True)
    return meta, cs_labels


# ---------------------------------------------------------------------------
# Dimensionality reduction: PCA → UMAP
# ---------------------------------------------------------------------------
def reduce(vectors):
    from sklearn.decomposition import PCA
    import umap

    # --- PCA ---
    n_pca = min(PCA_DIMS, vectors.shape[1], vectors.shape[0] - 1)
    print(f"PCA {vectors.shape[1]}→{n_pca} dims on {vectors.shape[0]:,} vectors …", flush=True)
    t0 = time.time()
    pca = PCA(n_components=n_pca, random_state=42)
    reduced = pca.fit_transform(vectors)
    explained = pca.explained_variance_ratio_.sum()
    print(f"  PCA done in {time.time()-t0:.1f}s  (explained variance: {explained:.1%})", flush=True)

    # --- UMAP ---
    print(f"UMAP {n_pca}→2 on {reduced.shape[0]:,} points (this takes a while) …", flush=True)
    t0 = time.time()
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=30,
        min_dist=0.1,
        metric="cosine",
        random_state=42,
        low_memory=False,
        verbose=True,
    )
    coords = reducer.fit_transform(reduced).astype(np.float32)
    print(f"  UMAP done in {time.time()-t0:.1f}s", flush=True)

    return coords


# ---------------------------------------------------------------------------
# Normalize to [0, 1]
# ---------------------------------------------------------------------------
def normalize(coords):
    mn = coords.min(axis=0)
    mx = coords.max(axis=0)
    rng = mx - mn
    rng[rng == 0] = 1.0
    return (coords - mn) / rng


# ---------------------------------------------------------------------------
# Assemble output JSON
# ---------------------------------------------------------------------------
def assemble(ids, coords, meta, cs_labels):
    # Build lookup tables
    all_services  = sorted({(meta.get(i) or {}).get("service", "unknown") for i in ids})
    all_clusters  = sorted({(meta.get(i) or {}).get("cluster", -1)        for i in ids})

    svc_idx = {s: i for i, s in enumerate(all_services)}
    cls_idx = {c: i for i, c in enumerate(all_clusters)}

    cluster_labels = [cs_labels.get(c, f"Cluster {c}") for c in all_clusters]

    x_arr   = []
    y_arr   = []
    svc_arr = []
    cls_arr = []
    names   = []

    for i, nid in enumerate(ids):
        m = meta.get(nid) or {}
        x_arr.append(round(float(coords[i, 0]), 4))
        y_arr.append(round(float(coords[i, 1]), 4))
        svc_arr.append(svc_idx.get(m.get("service", "unknown"), 0))
        cls_arr.append(cls_idx.get(m.get("cluster", -1), 0))
        names.append(m.get("label", nid.split(".")[-1]))

    return {
        "n":              len(ids),
        "services":       all_services,
        "cluster_ids":    all_clusters,
        "cluster_labels": cluster_labels,
        "x":              x_arr,
        "y":              y_arr,
        "svc":            svc_arr,
        "cls":            cls_arr,
        "names":          names,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    for p in (LANCE_PATH, GRAPH_FILE):
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    ids, vectors    = load_vectors()
    meta, cs_labels = load_graph_meta()

    # Align: only keep ids that have both a vector and graph metadata
    # (ids are the authoritative list from the vector store)
    print(f"Aligning {len(ids):,} vector ids with graph metadata …", flush=True)
    mask = [i for i, nid in enumerate(ids) if nid in meta]
    if len(mask) < len(ids):
        print(f"  {len(ids)-len(mask):,} ids not in graph — keeping all {len(ids):,} anyway", flush=True)

    coords = reduce(vectors)
    coords = normalize(coords)

    out = assemble(ids, coords, meta, cs_labels)

    print(f"Writing {OUTPUT_FILE} …", flush=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(out, f, separators=(",", ":"))

    mb = OUTPUT_FILE.stat().st_size / 1_048_576
    print(f"\nDone. {OUTPUT_FILE}  ({mb:.2f} MB)")
    print(f"  points   : {out['n']:,}")
    print(f"  services : {len(out['services'])}")
    print(f"  clusters : {len(out['cluster_labels'])}")


if __name__ == "__main__":
    main()
