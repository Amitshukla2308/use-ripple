"""
Demo server — Chainlit UI with graph traversal + vector search + LLM reasoning.
Runs on MacBook Air M4 (or any machine with the demo_artifact folder).

Usage:
  pip install -r requirements_demo.txt
  chainlit run demo_server.py --port 8000
"""
import json, os, pathlib, sys
import chainlit as cl

# ── Config ───────────────────────────────────────────────────────────────────

ARTIFACT_DIR  = pathlib.Path(__file__).parent
MODEL_PATH    = str(ARTIFACT_DIR / "model.gguf")
GRAPH_PATH    = str(ARTIFACT_DIR / "graph_with_summaries.json")
LANCE_PATH    = str(ARTIFACT_DIR / "vectors.lance")
EMBED_MODEL   = "nomic-ai/nomic-embed-code"

# LM Studio fallback (for build machine demo)
LM_STUDIO_URL   = os.environ.get("LM_STUDIO_URL", "http://172.18.0.1:1234/v1")
USE_LM_STUDIO   = os.environ.get("USE_LM_STUDIO", "0") == "1"

# ── Globals (loaded once at startup) ─────────────────────────────────────────

llm       = None
embedder  = None
G         = None
lance_tbl = None
cluster_summaries = {}


def load_all():
    global llm, embedder, G, lance_tbl, cluster_summaries
    import networkx as nx
    import lancedb
    from sentence_transformers import SentenceTransformer

    print("Loading graph...")
    graph_data = json.load(open(GRAPH_PATH))
    G = nx.node_link_graph(graph_data["networkx"])
    cluster_summaries = graph_data.get("cluster_summaries", {})
    print(f"  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print(f"  Clusters with summaries: {len(cluster_summaries)}")

    print("Loading vector index...")
    db = lancedb.connect(LANCE_PATH)
    lance_tbl = db.open_table("chunks")
    print(f"  Vectors loaded from {LANCE_PATH}")

    print("Loading embedder (CPU)...")
    embedder = SentenceTransformer(EMBED_MODEL, device="cpu")

    if USE_LM_STUDIO:
        print(f"Using LM Studio at {LM_STUDIO_URL}")
        from openai import OpenAI
        llm = OpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")
    elif pathlib.Path(MODEL_PATH).exists():
        print(f"Loading GGUF model: {MODEL_PATH}")
        from llama_cpp import Llama
        llm = Llama(
            model_path=MODEL_PATH,
            n_ctx=4096,
            n_gpu_layers=-1,   # all layers on Metal / CUDA
            verbose=False,
        )
        print("  Model loaded.")
    else:
        print(f"[warn] No model found at {MODEL_PATH} and USE_LM_STUDIO=0")
        print("  Set USE_LM_STUDIO=1 or place model.gguf in demo_artifact/")

    print("\n✓ Ready — open http://localhost:8000\n")


# ── Retrieval ─────────────────────────────────────────────────────────────────

def vector_search(query: str, k: int = 10) -> list[dict]:
    qvec = embedder.encode([query], normalize_embeddings=True)[0].tolist()
    return lance_tbl.search(qvec).limit(k).to_list()


def graph_expand(seed_ids: list[str], depth: int = 2) -> list[dict]:
    import networkx as nx
    context = []
    visited = set()
    for nid in seed_ids:
        if nid not in G:
            continue
        try:
            sub = nx.ego_graph(G, nid, radius=depth, undirected=True)
            for node_id, attrs in sub.nodes(data=True):
                if node_id not in visited:
                    visited.add(node_id)
                    context.append(attrs)
        except Exception:
            pass
    return context[:20]


def get_cluster_context(seed_ids: list[str]) -> list[dict]:
    """Return the cluster summaries for the clusters containing seed nodes."""
    seen_clusters = set()
    results = []
    for nid in seed_ids:
        if nid in G:
            cid = str(G.nodes[nid].get("cluster", -1))
            if cid != "-1" and cid not in seen_clusters and cid in cluster_summaries:
                seen_clusters.add(cid)
                results.append({"cluster_id": cid, **cluster_summaries[cid]})
    return results


# ── Prompt builder ────────────────────────────────────────────────────────────

def build_prompt(query: str, hits: list, graph_ctx: list, cluster_ctx: list) -> str:
    vec_lines = "\n".join(
        f"  [{h.get('lang','?')}/{h.get('kind','?')}] {h.get('name','?')} "
        f"({h.get('service','?')}) — {h.get('summary','')[:100]}"
        for h in hits[:8]
    )
    graph_lines = "\n".join(
        f"  {n.get('name','?')} [{n.get('kind','?')}] in {n.get('service','?')}"
        + (f": {n.get('cluster_purpose','')[:80]}" if n.get('cluster_purpose') else "")
        for n in graph_ctx[:12] if n.get("kind") != "phantom"
    )
    cluster_lines = "\n".join(
        f"  Cluster '{c.get('name','?')}': {c.get('purpose','')[:120]}"
        + (f"\n    Ghost deps: {', '.join(c.get('ghost_deps',[]))}" if c.get('ghost_deps') else "")
        + (f"\n    Risk flags: {', '.join(c.get('risk_flags',[]))}" if c.get('risk_flags') else "")
        for c in cluster_ctx
    )

    return f"""You are an expert on this specific payment processing codebase (Haskell + Rust microservices).
Think step by step. Show your reasoning chain before giving your final answer.
Be specific — name actual functions, modules, and services when you can.

## Relevant code symbols (vector search):
{vec_lines or '  (none found)'}

## Connected neighbours (graph traversal):
{graph_lines or '  (none found)'}

## Subsystem context (cluster summaries):
{cluster_lines or '  (none found)'}

## Question:
{query}

## Reasoning:"""


# ── LLM call ─────────────────────────────────────────────────────────────────

def stream_llm(prompt: str):
    if llm is None:
        yield "(No model loaded — set USE_LM_STUDIO=1 or add model.gguf)"
        return

    if USE_LM_STUDIO:
        from openai import OpenAI
        models = llm.models.list()
        model  = models.data[0].id if models.data else "default"
        for chunk in llm.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1024,
            stream=True,
        ):
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    else:
        for chunk in llm(prompt, max_tokens=1024, stream=True, temperature=0.2):
            token = chunk["choices"][0]["text"]
            if token:
                yield token


# ── Chainlit handlers ─────────────────────────────────────────────────────────

@cl.on_chat_start
async def on_start():
    await cl.Message(
        content=(
            "**Codebase Mind Map** — ready.\n\n"
            "Try asking:\n"
            "- *What does the transaction processing flow do end-to-end?*\n"
            "- *If the UserSession type changes, what breaks?*\n"
            "- *Are there any services that seem to do the same thing?*\n"
            "- *What external systems does the gateway depend on?*"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    query = message.content

    # Step 1: Vector search
    async with cl.Step(name="Searching semantic index") as step:
        hits = vector_search(query, k=10)
        step.output = (
            f"Found {len(hits)} relevant symbols:\n" +
            "\n".join(f"  • {h.get('name','?')} ({h.get('service','?')})" for h in hits[:5])
        )

    # Step 2: Graph expansion
    async with cl.Step(name="Traversing dependency graph") as step:
        seed_ids   = [h["id"] for h in hits]
        graph_ctx  = graph_expand(seed_ids, depth=2)
        cluster_ctx = get_cluster_context(seed_ids)
        step.output = (
            f"Graph walk: {len(graph_ctx)} connected nodes across "
            f"{len(set(n.get('service','?') for n in graph_ctx))} services\n"
            f"Subsystems: {', '.join(c.get('name','?') for c in cluster_ctx)}"
        )

    # Step 3: LLM reasoning (streamed)
    prompt = build_prompt(query, hits, graph_ctx, cluster_ctx)
    msg    = cl.Message(content="")

    async with cl.Step(name="Reasoning"):
        pass

    for token in stream_llm(prompt):
        await msg.stream_token(token)

    await msg.send()


# ── Entry point ───────────────────────────────────────────────────────────────

load_all()
