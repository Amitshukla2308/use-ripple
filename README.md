# HyperRetrieval

A self-hosted codebase intelligence platform. Point it at your source code, run a 7-stage build pipeline, and get a structured knowledge graph of your entire codebase — queryable by humans and AI agents alike.

The **Chat UI** and **MCP server** are two reference implementations on top of that knowledge graph. The real value is the data layer: once your codebase is indexed, you can build any number of applications on top of it.

---

## What it does

Indexes your codebase into five complementary data structures:

| Index | What it stores | Used for |
|-------|---------------|----------|
| **Symbol graph** | Functions, types, modules + import edges | Navigation, blast-radius analysis |
| **Vector index** | Semantic embedding of every symbol | Natural-language search |
| **Body store** | Full source text per function | Code reading, LLM context |
| **Call graph** | Caller/callee relationships | Flow tracing, impact analysis |
| **Co-change index** | Files that historically change together | Risk-aware PR review |

Once indexed, the same data powers multiple entry points — all shipped in this repo:

- **Chat UI** (Chainlit) — conversational interface for engineers to explore the codebase
- **MCP server** — exposes tools directly inside AI coding assistants (Claude Code, Cursor, Windsurf)
- **PR analyser** — CLI blast-radius report for CI/CD pipelines

---

## What data it works best on

- **Large, multi-service codebases** — 10k–200k symbols across 5–20 services is the sweet spot
- **Codebases with meaningful git history** — co-change analysis requires commit history to be useful
- **Mixed-language repos** — works well when services have clear boundaries and consistent module naming
- **Codebases with internal documentation** — markdown docs are embedded alongside code and searchable together

**Less effective for:**
- Single-file or tiny projects (< 500 symbols) — the indexing overhead is not worthwhile
- Repos with little or no git history
- Codebases where the dominant language is not yet supported (see Language support below)

---

## Language support

| Language | Symbols | Bodies | Call graph | Log patterns |
|----------|---------|--------|------------|--------------|
| Haskell  | ✓       | ✓      | ✓ (approx) | ✓            |
| Rust     | ✓       | ✓      | ✓          | ✓            |
| Python   | ✓       | ✓      | ✓ (AST)    | —            |
| Groovy   | ✓       | ✓      | —          | ✓            |

Adding a new language means implementing `parse_<lang>_file()` in `build/01_extract.py` — see [Adding a language parser](#adding-a-language-parser).

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
│   └── run_pipeline.sh        ← Run all 7 stages end-to-end
│
├── serve/                     ← Runtime entry points (start after the build)
│   ├── retrieval_engine.py    ← Core library: loads all indexes, exposes tool functions
│   ├── embed_server.py        ← Shared embedding server (port 8001) — start FIRST
│   ├── demo_server_v6.py      ← Chainlit chat UI (port 8000)
│   ├── mcp_server.py          ← MCP SSE server (port 8002) — 8 tools for AI agents
│   ├── pr_analyzer.py         ← CLI blast-radius report for changed files
│   ├── public/                ← Chainlit CSS + theme
│   └── .chainlit/             ← Chainlit config (name, layout, CSS path)
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
├── config.yaml
├── source/                    ← Your source repos (one subdirectory per service)
├── artifacts/                 ← Indexes loaded at runtime
│   ├── graph_with_summaries.json
│   ├── vectors.lance/
│   └── cochange_index.json
├── output/                    ← Intermediate build outputs
│   ├── body_store.json
│   ├── call_graph.json
│   ├── log_patterns.json
│   └── docs.lance/
├── docs/                      ← Markdown documentation (embedded in stage 7)
└── git_history.json

models/
└── <embedding-model>/         ← Model weights (local provider only)
```

---

## Setup from scratch

### Prerequisites

```bash
python3 --version   # 3.11+

pip install chainlit openai lancedb sentence-transformers networkx \
            pyarrow python-louvain mcp ijson

# GPU needed only for local embedding (stage 3 + embed_server with EMBED_PROVIDER=local)
# Cloud providers (openai, voyage, cohere, etc.) require no GPU — see Embedding providers
nvidia-smi
```

### Step 1 — Prepare your workspace

```bash
mkdir -p ~/projects/workspaces/YOUR_ORG/{source,artifacts,output}

# One subdirectory per service
cp -r /path/to/service-a ~/projects/workspaces/YOUR_ORG/source/
cp -r /path/to/service-b ~/projects/workspaces/YOUR_ORG/source/

cp ~/projects/hyperretrieval/config.example.yaml \
   ~/projects/workspaces/YOUR_ORG/config.yaml
# Edit: set LLM endpoint, API keys, ports
```

### Step 2 — Export git history

```bash
# Run for each service repo, append to a single file
git -C ~/projects/workspaces/YOUR_ORG/source/service-a \
    log --all --name-only --format="COMMIT|%H|%s|%ae|%ai" \
    >> ~/projects/workspaces/YOUR_ORG/git_history.json
```

### Step 3 — Choose an embedding provider

See [Embedding providers](#embedding-providers) below. If using a cloud provider, skip the model download. If using local:

```bash
mkdir -p ~/projects/models
python3 -c "
from sentence_transformers import SentenceTransformer
m = SentenceTransformer('Qwen/Qwen3-Embedding-8B')
m.save('/path/to/models/qwen3-embed-8b')
"
```

### Step 4 — Run the build pipeline

```bash
cd ~/projects/hyperretrieval

export REPO_ROOT=~/projects/workspaces/YOUR_ORG/source
export OUTPUT_DIR=~/projects/workspaces/YOUR_ORG/output
export ARTIFACT_DIR=~/projects/workspaces/YOUR_ORG/artifacts
export EMBED_MODEL=/path/to/models/your-embed-model  # or set EMBED_PROVIDER + API key
export LLM_API_KEY=your_llm_api_key
export LLM_BASE_URL=https://your-llm-endpoint
export LLM_MODEL=your-model-name

bash build/run_pipeline.sh   # 30 min – 2 h depending on codebase size

# Or stage by stage:
python3 build/01_extract.py        # 5–15 min for 100k symbols
python3 build/02_build_graph.py    # ~2 min
python3 build/03_embed.py          # 20–60 min (GPU-heavy, or fast with cloud provider)
python3 build/04_summarize.py      # ~30 min (LLM API, crash-safe/resumable)
python3 build/05_package.py        # ~1 min
python3 build/06_build_cochange.py # 10–30 min
python3 build/07_chunk_docs.py     # ~5 min
```

### Step 5 — Start the servers

**Always start the embedding server first.** Only one process should load the embedding model at a time.

```bash
# 1. Embedding server
export EMBED_MODEL=/path/to/model   # or EMBED_PROVIDER + API key
cd ~/projects/hyperretrieval/serve
python3 embed_server.py
# Wait for: [embed_server] Ready on 127.0.0.1:8001

# 2. Chat UI
export EMBED_SERVER_URL=http://localhost:8001
export ARTIFACT_DIR=~/projects/workspaces/YOUR_ORG/artifacts
cd ~/projects/hyperretrieval/serve
chainlit run demo_server_v6.py --port 8000
# Open http://localhost:8000

# 3. MCP server (optional — for AI coding assistant integration)
export EMBED_SERVER_URL=http://localhost:8001
export ARTIFACT_DIR=~/projects/workspaces/YOUR_ORG/artifacts
python3 mcp_server.py
# SSE endpoint: http://localhost:8002/sse
```

---

## Embedding providers

`embed_server.py` provides a unified HTTP interface regardless of where embeddings come from. Switch providers with a single env var — nothing else changes.

```bash
# Local GPU
EMBED_MODEL=/path/to/model python3 serve/embed_server.py

# Cloud providers (no GPU needed)
EMBED_PROVIDER=openai  OPENAI_API_KEY=...  python3 serve/embed_server.py
EMBED_PROVIDER=cohere  COHERE_API_KEY=...  python3 serve/embed_server.py
EMBED_PROVIDER=voyage  VOYAGE_API_KEY=...  python3 serve/embed_server.py
EMBED_PROVIDER=jina    JINA_API_KEY=...    python3 serve/embed_server.py

# Fully local, no GPU (requires Ollama running)
EMBED_PROVIDER=ollama  EMBED_PROVIDER_MODEL=nomic-embed-text  python3 serve/embed_server.py
```

| Provider | Default model | Dim | GPU needed |
|----------|--------------|-----|------------|
| local | qwen3-embed-8b | 4096 | Yes (~6GB) |
| openai | see provider docs | varies | No |
| cohere | see provider docs | varies | No |
| voyage | voyage-code-3 | 1024 | No |
| jina | jina-embeddings-v3 | 1024 | No |
| ollama | nomic-embed-text | 768 | No (local CPU) |

**Tested with:** local/qwen3-embed-8b, openai/text-embedding-3-large, voyage/voyage-code-3.

**Guidance:** retrieval quality scales with embedding dimension. Use the highest-dimension model available to you, and prefer models evaluated on code or technical text retrieval. Check your provider's documentation for their recommended model for this workload.

> **Important:** embedding dimension is fixed when you run stage 3. Switching providers later requires rebuilding `vectors.lance` by re-running `build/03_embed.py`.

---

## Connecting AI agents via MCP

Add to `.mcp.json` in your project root:

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

### The 8 MCP tools

| Tool | Use when |
|------|----------|
| `search_modules` | **Start here.** Find which namespace contains relevant code. |
| `get_module` | List all symbols in a namespace. |
| `search_symbols` | Semantic search — you know what a function does, not its name. |
| `get_function_body` | Read source of a function by its fully-qualified ID. |
| `trace_callers` | Who calls this function? (upstream impact) |
| `trace_callees` | What does this function call? (downstream dependencies) |
| `get_blast_radius` | Import graph + co-change impact for changed files or modules. |
| `get_context` | **Last resort.** Pre-built context block (large). Use only if targeted searches failed. |

**Optimal chain:** `search_modules → get_module → get_function_body → trace_callees`

---

## PR blast-radius analysis

```bash
git diff main...HEAD --name-only | python3 serve/pr_analyzer.py
python3 serve/pr_analyzer.py --files src/Routes.hs src/Gateway.hs
git diff main...HEAD --name-only | python3 serve/pr_analyzer.py --format json
git diff main...HEAD --name-only | python3 serve/pr_analyzer.py --check security
```

---

## Applications you can build

The Chat UI and MCP server are two reference implementations. The retrieval engine is a general-purpose data layer — any application that benefits from understanding a codebase can be built on top of it.

### What large engineering organisations have used similar platforms for

**Developer tooling**
- Automated onboarding guides — generate a "tour" of any service for new engineers
- Codebase-aware code review bots — flag changes that touch historically fragile modules
- On-call runbooks — auto-generated from log patterns and call graphs, linked to actual code
- IDE plugins — inline answers to "what does this function do?" without leaving the editor

**Engineering operations**
- Incident response assistants — given an error log, trace back to the responsible module and its owner
- Dependency audits — identify which services depend on a library before upgrading it
- Security scanning agents — find every location where sensitive data (credentials, PAN, tokens) is handled
- Technical debt dashboards — surface modules with high co-change churn, low test coverage, or complex call graphs

**AI agent infrastructure**
- Coding agents that understand your internal APIs without fine-tuning
- Test generation agents — read a function body and generate unit tests grounded in actual behaviour
- Migration assistants — trace all call sites before deprecating an API
- Documentation generators — auto-draft docstrings and API guides from source + commit history

**CI/CD integration**
- Pre-merge blast-radius checks — block risky changes automatically
- Change-linked release notes — describe what changed and what it affects
- Cross-service impact summaries for release managers

The pattern in all cases is the same: **retrieve relevant context from the index, pass it to an LLM, act on the answer.**

---

## Building a ReAct agent

`retrieval_engine.py` is the data layer. You can write any agent that uses it — the Chat UI and MCP server are just two examples. Here is the minimal pattern:

### How ReAct works

ReAct (Reason + Act) is a loop where an LLM:
1. Reads the question and any prior tool results
2. Decides which tool to call (or stops if it has enough information)
3. The tool runs and the result is appended to the conversation
4. Repeat until the LLM produces a final answer

```
User question
     ↓
[LLM] → tool_call: search_modules("payment gateway")
     ↓
[Tool runs] → returns module list
     ↓
[LLM] → tool_call: get_function_body("Gateway.processPayment")
     ↓
[Tool runs] → returns source code
     ↓
[LLM] → no more tool calls → final answer streamed to user
```

### Minimal agent loop

```python
import retrieval_engine as RE
from openai import OpenAI

RE.initialize("/path/to/workspaces/YOUR_ORG/artifacts")
client = OpenAI(api_key="...", base_url="...")

def run_agent(question: str) -> str:
    messages = [
        {"role": "system", "content": "You are a codebase expert. Use tools to answer questions."},
        {"role": "user",   "content": question},
    ]

    for _ in range(12):   # max tool calls
        resp = client.chat.completions.create(
            model="your-model",
            messages=messages,
            tools=RE.AGENT_TOOLS,
            tool_choice="auto",
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:
            return msg.content   # LLM finished reasoning

        # Append assistant turn + execute each tool
        messages.append({"role": "assistant", "content": msg.content,
                         "tool_calls": [...]})   # serialise tool_calls
        for tc in msg.tool_calls:
            import json
            args   = json.loads(tc.function.arguments)
            result = RE.TOOL_DISPATCH[tc.function.name](args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    return "Investigation limit reached."
```

The real implementations in `demo_server_v6.py` (Chainlit) and `mcp_server.py` follow this exact pattern — the only difference is how tool steps are rendered and how the final answer is delivered.

### Choosing what to expose

`AGENT_TOOLS` in `retrieval_engine.py` is the full list of tools the LLM can call. `TOOL_DISPATCH` maps tool names to functions. Your agent can use all of them or a subset depending on the use case:

| Use case | Recommended tools |
|----------|------------------|
| Answering architecture questions | search_modules, get_module, get_function_body, trace_callees |
| Impact analysis / PR review | get_blast_radius, trace_callers, search_symbols |
| Incident investigation | search_symbols, get_function_body, get_log_patterns |
| Security audit | search_symbols, get_function_body, trace_callers |
| Documentation generation | get_module, get_function_body, get_type_definition |

---

## Adding tools

Every tool in the system has three parts. Add all three to expose a new capability.

### 1. The function in `retrieval_engine.py`

```python
def tool_find_tests(fn_id: str) -> str:
    """Find test files that reference a given function ID."""
    if not G or fn_id not in G.nodes:
        return f"Function '{fn_id}' not found."

    # Your retrieval logic here — search the graph, body_store, call_graph, etc.
    results = [
        nid for nid, d in G.nodes(data=True)
        if "test" in d.get("file", "").lower()
        and fn_id.split(".")[-1] in body_store.get(nid, "")
    ]
    return "\n".join(results[:20]) or "No test references found."
```

### 2. The schema in `AGENT_TOOLS`

`AGENT_TOOLS` is a list of OpenAI function-calling schemas. Add an entry so the LLM knows the tool exists and how to call it:

```python
{
    "type": "function",
    "function": {
        "name": "find_tests",
        "description": "Find test functions that reference a given function ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "fn_id": {
                    "type": "string",
                    "description": "Fully-qualified function ID, e.g. Module.SubModule.functionName"
                }
            },
            "required": ["fn_id"]
        }
    }
}
```

### 3. The dispatch entry in `TOOL_DISPATCH`

```python
TOOL_DISPATCH: dict = {
    # ... existing tools ...
    "find_tests": lambda a: tool_find_tests(a.get("fn_id", "")),
}
```

### 4. Expose via MCP (optional)

To make the tool available in AI coding assistants, add it to `mcp_server.py`:

```python
@mcp.tool()
def find_tests(fn_id: str) -> str:
    """Find test functions that reference a given function ID."""
    RE.ensure_initialized()
    return RE.tool_find_tests(fn_id)
```

That is the complete change. The tool is now available in the Chat UI, MCP server, and any custom agent that uses `TOOL_DISPATCH`.

### Adding a language parser

To add support for a new language, implement the parser function in `build/01_extract.py` following the same contract as the existing parsers:

```python
def parse_javascript_file(path: pathlib.Path, service: str) \
        -> tuple[list, list, dict, dict, dict]:
    """Returns: (symbols, edges, body_store, call_store, log_store)"""
    symbols, edges = [], []
    body_store, call_store, log_store = {}, {}, {}

    # Each symbol must have: id, name, module, kind, type, file, lang, service
    # Each edge must have: from, to, kind, lang
    # body_store: fn_id → source text
    # call_store: fn_id → {"callees": [name, ...], "callers": []}
    # log_store:  fn_id → [log string, ...]

    return symbols, edges, body_store, call_store, log_store
```

Then add the file glob and parser call inside the service loop in `main()`.

---

## Best practices

### Build pipeline

- Run stage 3 (embed) with no other embedding workloads active — it is the most memory-intensive stage
- Stage 4 (summarize) checkpoints after every cluster — safe to interrupt and resume
- Always run stage 5 after stage 4 — it copies the final graph to `artifacts/` where servers load it from
- Stage 6 (co-change) streams git history at commit level — O(1) memory, safe on arbitrarily large history files
- Validate your git history export before running stage 6: check the last few bytes for truncation

### Running servers

- Start the embedding server before all others — if other servers start first they attempt in-process model loading
- Set `EMBED_SERVER_URL` in every server process that uses embeddings
- Run long-lived server processes with proper session isolation (`start_new_session=True` in Python subprocess, or a process manager like systemd/supervisor in production)
- In production, put servers behind a reverse proxy (nginx, Caddy) — do not expose ports directly

### Querying and retrieval

- Start exploration with `search_modules` — it returns namespaces, which are then browsable with `get_module`. This is faster and more precise than open-ended `search_symbols`.
- Short domain-specific terms (acronyms, payment codes, protocol names) may be filtered by length. Add them to `_KW_ALLOWLIST` in `retrieval_engine.py`.
- Batch independent tool calls in a single LLM turn — sequential single-call round-trips are slower and use more tokens
- `get_context` is a large fallback — only invoke it if targeted searches have genuinely failed
- If search results are consistently wrong for a particular term, check whether it is being split or normalised unexpectedly before the keyword search

### Workspace hygiene

- Keep platform code (`hyperretrieval/`) and org data (`workspaces/YOUR_ORG/`) in separate git repos — the data is not part of the product
- Rebuild the vector index (`03_embed.py`) whenever you change the embedding provider or model
- Re-run the full pipeline periodically as the codebase evolves — the co-change index especially benefits from fresh commit history
- Store API keys in environment variables or a secrets manager, never in `config.yaml`

---

## Architecture deep-dive

```
embed_server.py (:8001)
  One process loads the embedding model (local GPU or cloud API).
  Serves POST /embed → {embeddings: [[float, ...]]}
  GET /health → {provider, model, dim, device, loaded}
  All other processes connect via EMBED_SERVER_URL — zero model duplication.

retrieval_engine.py  (imported by every entry point)
  initialize(artifact_dir) loads all indexes into memory:
    graph_with_summaries.json → NetworkX symbol graph G + module graph MG
    vectors.lance             → LanceDB vector table
    body_store.json           → fn_id → source body
    call_graph.json           → fn_id → {callees, callers}
    cochange_index.json       → module → [(module, weight), ...]
    log_patterns.json         → fn_id → [observable log strings]
    docs.lance                → LanceDB documentation chunks

  Exposes:
    AGENT_TOOLS     — OpenAI function-calling schemas for the LLM
    TOOL_DISPATCH   — name → callable, used by every agent implementation

Entry points (all import retrieval_engine, none duplicate logic):

  demo_server_v6.py (:8000)    Chainlit chat UI
    ReAct loop renders tool calls as expandable steps.
    Streams the final answer token by token.

  mcp_server.py (:8002/sse)    MCP server
    Wraps TOOL_DISPATCH as MCP tools over SSE transport.
    Compatible with any MCP client.

  pr_analyzer.py               CLI
    resolve files → blast radius → optional LLM explanation.
    Exits non-zero for CI gates.

  your_app.py                  Anything you build
    Import retrieval_engine, call initialize(), use TOOL_DISPATCH.
```

**Why two graphs (G and MG)?**
Import edges connect module *names*, not function IDs. G is a symbol-level graph — it holds function nodes and call/instance edges. MG is a module-level graph built at startup from raw import edges. Blast-radius traversal and module search use MG; function body lookup and call tracing use G and the body/call stores.

**Why stratified vector search?**
Without stratification, nearest-neighbour search returns results biased toward the largest service (most symbols). Stratification caps results per service before final ranking, ensuring all services get representation regardless of size.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `name '_encode_queries_batch' is not defined` | Function deleted by mistake | Restore it — it is called by `_encode_query` and `stratified_vector_search` |
| Embed server reports `device=cpu` when GPU is available | GPU driver not visible to the process | Check `nvidia-smi` and CUDA driver installation; on WSL2 run `wsl --shutdown` and restart |
| Chainlit shows default name/theme instead of custom | Wrong working directory at launch | Run chainlit from `serve/` where `.chainlit/config.toml` and `public/` live |
| LanceDB write fails silently | Writing to a filesystem that does not support mmap | Write to a native Linux ext4 path; on WSL2 avoid `/mnt/` paths |
| Semantic search misses obvious results | Short terms filtered by length | Add short domain terms to `_KW_ALLOWLIST` in `retrieval_engine.py` |
| Co-change builder runs out of memory | Loading full repository objects into memory | Use `06_build_cochange.py` which streams at commit level, not repo level |
| Server process exits when terminal closes | Process attached to a PTY | Use a process manager, `nohup`, or `subprocess.Popen(start_new_session=True)` |
| vectors.lance is empty after stage 3 | Stage 3 wrote to a temp path and was not copied | Check `ARTIFACT_DIR` env var; ensure stage 5 ran after stage 3 |
| MCP tools not showing in Claude Code | Wrong transport or URL | Use `type: sse` in `.mcp.json`; confirm port is correct; check server log |
