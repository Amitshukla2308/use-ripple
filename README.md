# HyperRetrieval

A self-hosted codebase intelligence platform. Point it at your source code, run a 7-stage build pipeline, and get a chat UI + MCP server that lets you (and AI agents) ask deep questions about the codebase — with answers grounded in actual source, not hallucination.

---

## What it does

- **Chat UI** (Chainlit) — Ask questions in plain English: "How does UPI Collect work?", "What calls this function?", "What breaks if I change this file?"
- **MCP server** — Exposes the same intelligence as tools directly inside Claude Code, Cursor, or Windsurf. AI agents can call `search_symbols`, `get_function_body`, `trace_callers`, etc.
- **PR analyser** — CLI tool: pipe `git diff --name-only` into it and get a blast-radius report of what your change affects.

---

## What data it works best on

- **Large, multi-service codebases** — 10k–200k symbols across 5–20 services is the sweet spot
- **Codebases with git history** — co-change analysis (which files always change together) requires commit history
- **Mixed-language repos** — works best when services have clear boundaries; handles cross-language call tracing
- **Codebases with internal docs** — markdown docs (API guides, architecture docs) are embedded alongside code

**Less useful for:**
- Single-file or tiny projects (< 500 symbols) — overhead is not worth it
- Repos with no git history or very few commits (< 100)
- Pure frontend (JS/TS) — parsers currently focus on Haskell, Rust, Python, Groovy

---

## Language support

| Language | Symbols | Bodies | Call graph | Log patterns |
|----------|---------|--------|------------|--------------|
| Haskell  | ✓       | ✓      | ✓ (approx) | ✓            |
| Rust     | ✓       | ✓      | ✓          | ✓            |
| Python   | ✓       | ✓      | ✓ (AST)    | —            |
| Groovy   | ✓       | ✓      | —          | ✓            |

---

## Folder structure

```
hyperretrieval/
├── build/                     ← 7-stage pipeline (run once to build indexes)
│   ├── 01_extract.py          ← Parse source → symbols, bodies, call graph, log patterns
│   ├── 02_build_graph.py      ← Build NetworkX graph, Louvain clustering at module level
│   ├── 03_embed.py            ← GPU-batch embed all symbols → LanceDB (vectors.lance)
│   ├── 04_summarize.py        ← LLM-summarize each cluster → human-readable descriptions
│   ├── 05_package.py          ← Copy final artifacts into workspace/artifacts/
│   ├── 06_build_cochange.py   ← Parse git history → co-change index
│   ├── 07_chunk_docs.py       ← Chunk + embed markdown docs into docs.lance
│   ├── build_cochange_gpu.py  ← GPU-accelerated co-change variant
│   ├── build_cochange_split.py← Handles split/chunked git history exports
│   ├── fix_lancedb_clusters.py← One-off repair: patch cluster_name into LanceDB
│   └── run_pipeline.sh        ← Run all 7 stages end-to-end
│
├── serve/                     ← Runtime servers (start these after the build)
│   ├── retrieval_engine.py    ← Core: loads all indexes, exposes tool functions
│   ├── embed_server.py        ← Shared GPU embedding server (port 8001) — start FIRST
│   ├── demo_server_v6.py      ← Chainlit chat UI (port 8000)
│   ├── mcp_server.py          ← MCP SSE server (port 8002) — 7 tools for AI agents
│   ├── pr_analyzer.py         ← CLI blast-radius report for changed files
│   ├── public/                ← Chainlit CSS + theme (must be in CWD at launch)
│   └── .chainlit/             ← Chainlit config (name, layout, custom CSS path)
│
├── tools/
│   └── generate_mindmap.py    ← Visualise the graph as an HTML mindmap
│
├── tests/
│   ├── test_01_artifacts.py   ← Verify build outputs exist and are non-empty
│   ├── test_02_retrieval_logic.py ← Unit tests for retrieval functions
│   ├── test_03_canary.py      ← Smoke test: does a basic query return results?
│   ├── test_04_retrieval_accuracy.py ← Benchmark: known-answer queries
│   ├── test_05_integration.py ← End-to-end server + query test
│   ├── test_06_auto_eval.py   ← LLM-as-judge retrieval quality eval
│   └── run_all.sh
│
└── config.example.yaml        ← Template workspace config (copy to your workspace)
```

```
workspaces/YOUR_ORG/           ← Org-specific data (not in git)
├── config.yaml                ← Workspace settings (paths, LLM endpoint, ports)
├── source/                    ← Your source repos (one subdirectory per service)
├── artifacts/                 ← Build outputs loaded at runtime
│   ├── graph_with_summaries.json  ← Nodes + cluster summaries (main graph file)
│   ├── vectors.lance/             ← Embeddings for all symbols
│   └── cochange_index.json        ← Co-change pairs between modules
├── output/                    ← Intermediate build outputs
│   ├── body_store.json        ← fn_id → source body text
│   ├── call_graph.json        ← fn_id → {callees, callers}
│   ├── log_patterns.json      ← fn_id → [observable log strings]
│   └── docs.lance/            ← Embedded documentation chunks
├── euler-docs/                ← Markdown docs (embedded in stage 7)
└── git_history.json           ← Git commit export for co-change analysis

models/
└── qwen3-embed-8b/            ← Qwen3-Embedding-8B model weights (~15GB)
```

---

## Setup from scratch

### Prerequisites

```bash
# Python 3.11+ (miniconda recommended)
python3 --version

# Install dependencies
pip install chainlit openai lancedb sentence-transformers networkx \
            pyarrow python-louvain mcp ijson

# CUDA-capable GPU required for stage 3 embedding (~6GB+ VRAM)
nvidia-smi
```

### Step 1 — Prepare your workspace

```bash
mkdir -p ~/projects/workspaces/YOUR_ORG/{source,artifacts,output}

# Copy your service repos into source/ (one dir per service)
cp -r /path/to/service-a ~/projects/workspaces/YOUR_ORG/source/
cp -r /path/to/service-b ~/projects/workspaces/YOUR_ORG/source/

# Copy config template
cp ~/projects/hyperretrieval/config.example.yaml \
   ~/projects/workspaces/YOUR_ORG/config.yaml
# Edit config.yaml with your LLM endpoint, API key, and port settings
```

### Step 2 — Export git history (for co-change analysis)

```bash
# Run in each service repo and concatenate:
git -C ~/projects/workspaces/YOUR_ORG/source/service-a \
    log --all --name-only --format="COMMIT|%H|%s|%ae|%ai" \
    >> ~/projects/workspaces/YOUR_ORG/git_history.json
```

### Step 3 — Download the embedding model

```bash
mkdir -p ~/projects/models
python3 -c "
from sentence_transformers import SentenceTransformer
m = SentenceTransformer('Qwen/Qwen3-Embedding-8B')
m.save('/home/YOUR_USER/projects/models/qwen3-embed-8b')
"
```

### Step 4 — Run the build pipeline

```bash
cd ~/projects/hyperretrieval

export REPO_ROOT=~/projects/workspaces/YOUR_ORG/source
export OUTPUT_DIR=~/projects/workspaces/YOUR_ORG/output
export ARTIFACT_DIR=~/projects/workspaces/YOUR_ORG/artifacts
export EMBED_MODEL=~/projects/models/qwen3-embed-8b
export KIMI_API_KEY=your_llm_api_key
export KIMI_BASE_URL=https://api.openai.com  # any OpenAI-compatible endpoint
export KIMI_MODEL=gpt-4o

# Run all 7 stages (30 min – 2 h depending on codebase size and GPU speed)
bash build/run_pipeline.sh

# Or run individual stages:
python3 build/01_extract.py        # 5–15 min for 100k symbols
python3 build/02_build_graph.py    # ~2 min
python3 build/03_embed.py          # 20–60 min (GPU-heavy)
python3 build/04_summarize.py      # ~30 min (LLM API calls, crash-safe/resumable)
python3 build/05_package.py        # ~1 min
python3 build/06_build_cochange.py # 10–30 min (streams git history, O(1) memory)
python3 build/07_chunk_docs.py     # ~5 min
```

### Step 5 — Start the servers

**Always start in this order** — only one process may load the GPU model at a time:

```bash
# 1. Embedding server — loads Qwen3 on GPU once, ~35s startup
export EMBED_MODEL=~/projects/models/qwen3-embed-8b
cd ~/projects/hyperretrieval/serve
python3 embed_server.py
# Wait for: [embed_server] Ready on 127.0.0.1:8001

# 2. Chainlit chat UI
export EMBED_SERVER_URL=http://localhost:8001
export ARTIFACT_DIR=~/projects/workspaces/YOUR_ORG/artifacts
cd ~/projects/hyperretrieval/serve
chainlit run demo_server_v6.py --port 8000
# Open http://localhost:8000

# 3. (Optional) MCP server for AI agent tools
export EMBED_SERVER_URL=http://localhost:8001
export ARTIFACT_DIR=~/projects/workspaces/YOUR_ORG/artifacts
cd ~/projects/hyperretrieval/serve
python3 mcp_server.py
# MCP SSE endpoint: http://localhost:8002/sse
```

---

## Connecting AI agents via MCP

Add to `.mcp.json` in your project root (or `~/.claude/mcp.json` globally):

```json
{
  "mcpServers": {
    "codebase": {
      "type": "sse",
      "url": "http://127.0.0.1:8002/sse"
    }
  }
}
```

Works with Claude Code, Cursor, and Windsurf.

### The 7 MCP tools

| Tool | Use when |
|------|----------|
| `search_modules` | **Start here.** You want to find which namespace contains relevant code. |
| `get_module` | List all symbols in a namespace after `search_modules` finds it. |
| `search_symbols` | You know what a function does but not its exact name. |
| `get_function_body` | Read the actual source of a function by its fully-qualified ID. |
| `trace_callers` | Who calls this function? (upstream — impact of a change) |
| `trace_callees` | What does this function call? (downstream — dependency tracing) |
| `get_blast_radius` | Full import graph + co-change impact for a changed file or module. |
| `get_context` | **Last resort.** Returns 5–18k tokens of pre-built context. Use only if targeted searches failed. Never call twice per session. |

**Optimal chain:**
```
search_modules → get_module → get_function_body → trace_callees
```

---

## PR blast-radius analysis

```bash
# Pipe changed files from git diff
git diff main...HEAD --name-only | python3 serve/pr_analyzer.py

# Explicit files
python3 serve/pr_analyzer.py --files src/Routes.hs src/Gateway.hs

# JSON output for CI pipelines
git diff main...HEAD --name-only | python3 serve/pr_analyzer.py --format json

# Security gate (exits non-zero if security-sensitive modules touched)
git diff main...HEAD --name-only | python3 serve/pr_analyzer.py --check security
```

---

## Best practices

### Build pipeline

- Run stage 3 (embed) only when no other GPU-heavy processes are active
- Never run two GPU stages simultaneously — OOM will crash WSL2 (requires `wsl --shutdown` to recover)
- Stage 4 (summarize) is crash-safe and resumable — re-run freely if interrupted
- Always run stage 5 after stage 4 — it copies `graph_with_summaries.json` to `artifacts/` where servers expect it
- Stage 6 (co-change) is O(1) memory — safe on multi-GB git history files

### Running servers

- Embed server must start before Chainlit and MCP — otherwise they load the model in-process and risk OOM
- Always set `EMBED_SERVER_URL` before starting other servers
- On WSL: daemonize with Python `subprocess.Popen(start_new_session=True)` — `setsid`/`nohup` are unreliable from `cmd //c wsl` sessions
- After WSL restart: if GPU shows "blocked by operating system", run `wsl --shutdown` from Windows PowerShell, then restart

### Querying

- Start with `search_modules`, not `search_symbols` — it is faster and gives you a namespace to explore
- Batch independent tool calls — multiple tools in one turn is more efficient than sequential single calls
- `get_context` costs 5–18k tokens — only reach for it after 3+ targeted searches have failed
- Short domain terms (`upi`, `emi`, `pan`, `cvv`, `otp`) are in an allowlist and bypass the length filter

---

## Architecture deep-dive

```
embed_server.py (:8001)
  Loads Qwen3-Embedding-8B ONCE on GPU.
  Serves POST /embed → {embeddings: [[float, ...]]}
  GET /health → {device, loaded, requests}

retrieval_engine.py  (imported by all three entry points)
  initialize(artifact_dir) loads:
    graph_with_summaries.json → NetworkX G (nodes) + MG (module graph)
    vectors.lance             → LanceDB table (all symbol embeddings)
    body_store.json           → fn_id → source body
    call_graph.json           → fn_id → {callees, callers}
    cochange_index.json       → module → [(module, weight), ...]
    log_patterns.json         → fn_id → [observable log strings]
    docs.lance                → LanceDB documentation chunks

  ↑ used by:
  demo_server_v6.py (:8000)   Chainlit chat UI
    ReAct loop: LLM calls tools → Chainlit renders steps → streams answer
    Conversation history: MAX_HISTORY=6 turns via cl.user_session

  mcp_server.py (:8002/sse)   MCP server
    Exposes AGENT_TOOLS schema over SSE transport

  pr_analyzer.py              CLI
    resolve files → blast radius → optional LLM explanation
```

**Why two graphs?**
`G` is node-level (functions, types). Import edges in source connect module *names*, not function IDs, so they are absent from `G`. `MG` is built at startup from raw import edges: 4,809 modules, 42k import edges. Used for blast-radius traversal and module navigation.

**Why stratified vector search?**
Raw nearest-neighbour search is biased toward the largest service. Stratification samples k_per_service from each service before final ranking — guarantees small services always appear in results.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `name '_encode_queries_batch' is not defined` | Function accidentally deleted | Restore it — called by `_encode_query` and `stratified_vector_search` |
| GPU "blocked by operating system" | WSL2 lost device access | `wsl --shutdown` from Windows PowerShell, restart, start embed server first |
| Chainlit shows "Assistant" not custom name | Wrong CWD at launch | Run chainlit from `serve/` directory where `.chainlit/config.toml` lives |
| CSS not loading | `public/` not in CWD | Same fix — launch from `serve/` |
| LanceDB write fails on NTFS | mmap incompatibility | Write to `/tmp/vectors.lance`, then `mv` to ext4 destination |
| `search_symbols("upi")` returns nothing | Short term filtered out | Check `_KW_ALLOWLIST` in `retrieval_engine.py` |
| Co-change builder OOM | Loading whole repo objects | Use `06_build_cochange.py` which streams at commit level |
| Background process dies on WSL session exit | PTY lifecycle | Use `subprocess.Popen(start_new_session=True)` instead of `setsid`/`nohup` |
| `vectors.lance` empty after stage 3 | Written to NTFS `/mnt/d/` | Stage 3 writes to `/tmp/` first — check `ARTIFACT_DIR` points to ext4 |
