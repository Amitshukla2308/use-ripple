"""
Debug a query end-to-end — shows exactly what context Kimi sees.
"""
import json, sys, pathlib
import torch
import networkx as nx
import lancedb
from sentence_transformers import SentenceTransformer
from collections import Counter

PIPELINE = pathlib.Path("/home/beast/projects/mindmap/pipeline")
ARTIFACT = PIPELINE / "demo_artifact"

EMBED_MODEL = str(PIPELINE / "models" / "qwen3-embed-8b")
INSTRUCTION = (
    "Instruct: Represent this code module for finding semantically similar "
    "components across microservices. Query: "
)

QUERY = "What all payment flows does RAZORPAY supports?"

# ── Load ──────────────────────────────────────────────────────────────────────
print("Loading...")
graph_data        = json.load(open(ARTIFACT / "graph_with_summaries.json"))
G                 = nx.node_link_graph(graph_data["networkx"])
cluster_summaries = graph_data.get("cluster_summaries", {})

db        = lancedb.connect(str(ARTIFACT / "vectors.lance"))
lance_tbl = db.open_table("chunks")

embedder = SentenceTransformer(EMBED_MODEL, device="cuda", trust_remote_code=True,
                                model_kwargs={"torch_dtype": torch.float16})

# ── Vector search ─────────────────────────────────────────────────────────────
print(f"\n=== VECTOR SEARCH: '{QUERY}' ===")
qvec = embedder.encode([INSTRUCTION + QUERY], normalize_embeddings=True, convert_to_numpy=True)[0].tolist()
hits = lance_tbl.search(qvec).limit(20).to_list()

print(f"Top 20 hits:")
for i, h in enumerate(hits):
    print(f"  {i+1:2}. [{h.get('lang','?')}/{h.get('kind','?')}] {h.get('name','?'):50s} "
          f"svc={h.get('service','?'):25s} cluster={h.get('cluster_name','?')}")

# ── Check: what Razorpay symbols actually exist? ──────────────────────────────
print(f"\n=== ALL RAZORPAY SYMBOLS IN GRAPH ===")
razorpay_nodes = [
    (nid, d) for nid, d in G.nodes(data=True)
    if "razorpay" in nid.lower() or "razorpay" in d.get("name","").lower()
]
print(f"Found {len(razorpay_nodes)} Razorpay symbols total")

# Group by kind
by_kind = Counter(d.get("kind","?") for _, d in razorpay_nodes)
print(f"By kind: {dict(by_kind)}")

# Show functions only
print(f"\nRazorpay functions/types:")
for nid, d in sorted(razorpay_nodes, key=lambda x: x[1].get("name","")):
    kind = d.get("kind","?")
    if kind in ("function", "type"):
        print(f"  [{kind}] {d.get('name','?'):50s} svc={d.get('service','?'):25s} mod={d.get('module','?')[:60]}")

# ── Check: did vector search find the right ones? ─────────────────────────────
hit_ids   = {h["id"] for h in hits}
razor_ids = {nid for nid, _ in razorpay_nodes}
found_in_hits = hit_ids & razor_ids
missed       = razor_ids - hit_ids

print(f"\n=== COVERAGE ANALYSIS ===")
print(f"Razorpay symbols in top-20 hits : {len(found_in_hits)}")
print(f"Razorpay symbols NOT in hits    : {len(missed)}")
print(f"Hits that ARE Razorpay          : {[h['name'] for h in hits if h['id'] in razor_ids]}")

# ── Show graph neighbours of missed Razorpay nodes ───────────────────────────
if missed:
    print(f"\nSample missed Razorpay symbols (top 10 by name):")
    for nid in sorted(missed)[:10]:
        d = G.nodes[nid]
        print(f"  {d.get('name','?'):50s} svc={d.get('service','?')}")
