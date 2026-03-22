# HyperRetrieval — CLAUDE.md

> Instructions for Claude Code. Read this before doing anything.

---

## What this repo is

HyperRetrieval is a self-hosted codebase intelligence platform. It indexes a large multi-service codebase into several data structures (graph, vector index, co-change index, body store, call graph) and exposes them via:
- A **Chainlit chat UI** (port 8000) — ReAct agent loop with tool calling
- An **MCP SSE server** (port 8002) — 8 tools for Claude Code / Cursor / Windsurf
- A **CLI pr_analyzer** — blast-radius report for changed files

The current workspace is **Juspay's payment platform** (12 services, 94,244 symbols, Haskell primary).

---

## Directory layout (understand this first)

```
~/projects/
├── hyperretrieval/          ← THIS REPO — platform code only (git)
│   ├── serve/               ← runtime servers
│   │   ├── retrieval_engine.py   ← THE core: all data loading + retrieval functions
│   │   ├── demo_server_v6.py     ← Chainlit UI (imports retrieval_engine)
│   │   ├── embed_server.py       ← GPU embedding server (port 8001)
│   │   ├── mcp_server.py         ← MCP SSE server (port 8002)
│   │   ├── pr_analyzer.py        ← CLI blast-radius tool
│   │   ├── .chainlit/            ← Chainlit config (name, layout, CSS path)
│   │   └── public/               ← Chainlit CSS + theme files
│   ├── build/               ← 7-stage build pipeline (01_extract.py … 07_chunk_docs.py)
│   ├── tools/               ← generate_mindmap.py
│   ├── tests/               ← test_01 … test_06 + run_all.sh
│   └── config.example.yaml
│
├── workspaces/juspay/       ← Juspay org data (NOT in git)
│   ├── artifacts/           ← loaded at runtime by retrieval_engine.py
│   │   ├── graph_with_summaries.json  ← 94k nodes, 45 cluster summaries (142MB)
│   │   ├── vectors.lance/             ← 94k embeddings @ 4096d
│   │   └── cochange_index.json        ← 7,363 modules, 111,005 pairs
│   ├── output/              ← intermediate build outputs
│   │   ├── body_store.json            ← 62,169 fn bodies
│   │   ├── call_graph.json            ← 60,306 call entries
│   │   ├── log_patterns.json          ← 703 functions with log patterns
│   │   └── docs.lance/                ← 523 embedded doc chunks
│   ├── source/              ← 13 Juspay service repos
│   ├── euler-docs/          ← markdown docs (embedded in stage 7)
│   ├── euler-documentation/ ← more markdown docs
│   ├── config.yaml          ← workspace config
│   └── git_history.json     ← git commit export for co-change
│
└── models/
    └── qwen3-embed-8b/      ← 15GB Qwen3 model (GPU, ~6GB VRAM at runtime)
```

---

## Starting and stopping servers

**Critical: start in this exact order. Never load the GPU model in two processes simultaneously — WSL2 will OOM and require `wsl --shutdown` to recover.**

```bash
~/start_embed.sh      # starts embed_server.py — logs: ~/embed_server.log (~35s GPU load)
~/start_chainlit.sh   # starts demo_server_v6.py — logs: ~/chainlit.log
~/start_mcp.sh        # starts mcp_server.py — logs: ~/mcp_server.log
```

**Check status:**
```bash
ps aux | grep -E "embed_server|chainlit|mcp_server" | grep -v grep
curl -s http://localhost:8001/health    # embed: should show device=cuda
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000  # chainlit: 200
```

**Kill by port:**
```bash
fuser -k 8000/tcp   # chainlit
fuser -k 8001/tcp   # embed server
fuser -k 8002/tcp   # mcp server
```

**After WSL restart** (GPU blocked): `wsl --shutdown` from Windows PowerShell, then restart WSL and start embed server first.

---

## Environment variables

Every server reads these — always set them before starting:

| Variable | Value | Purpose |
|----------|-------|---------|
| `ARTIFACT_DIR` | `/home/beast/projects/workspaces/juspay/artifacts` | Where retrieval_engine loads graph, vectors, cochange |
| `EMBED_SERVER_URL` | `http://localhost:8001` | Tells retrieval_engine to use shared GPU server instead of loading in-process |
| `EMBED_MODEL` | `/home/beast/projects/models/qwen3-embed-8b` | Used by embed_server.py and as fallback if no embed server |
| `HF_HUB_OFFLINE` | `1` | Prevent HuggingFace download attempts |
| `KIMI_API_KEY` | `sk-...` | LLM API key (Kimi or OpenAI-compatible) |
| `KIMI_BASE_URL` | `https://grid.ai.juspay.net` | LLM endpoint |
| `KIMI_MODEL` | `kimi-latest` | LLM model name |

---

## Key files — what each one does

### serve/retrieval_engine.py
The single most important file. Everything else imports from it. It:
- Defines `initialize(artifact_dir)` — loads all data stores into global state
- Defines `_DEFAULT_ARTIFACT_DIR` — reads from `ARTIFACT_DIR` env var, falls back to `serve/demo_artifact/`
- Provides `AGENT_TOOLS` (OpenAI function schemas) and `TOOL_DISPATCH` (name → callable)
- Contains all retrieval logic: stratified vector search, keyword search, module graph traversal, co-change BFS

**Do NOT remove `_encode_queries_batch`** — it is called by `_encode_query` and `stratified_vector_search`. It looks unused but is not.

Key globals loaded by `initialize()`:
```python
G              # NetworkX: 94,244 nodes, 542 symbol edges (NOT import edges)
MG             # NetworkX: 4,809 modules, 42,467 import edges — use this for blast radius
lance_tbl      # LanceDB: 94,244 code vectors @ 4096d
doc_lance_tbl  # LanceDB: 523 doc chunk vectors
body_store     # dict: fn_id → source body text (62,169 entries)
call_graph     # dict: fn_id → {callees: [], callers: []}
cochange_index # dict: module → [(module, weight), ...]
log_patterns   # dict: fn_id → [log strings]
```

### serve/demo_server_v6.py
Chainlit UI. Minimal — it delegates everything to retrieval_engine.py.
- `ARTIFACT_DIR` reads from env var, falls back to `_HERE/demo_artifact`
- `MAX_TOOL_CALLS = 12` — do not increase; LLM spins in loops at higher values
- `MAX_HISTORY = 6` — conversation turns kept in session
- System message must be FIRST in the messages array, before history
- CWD when running chainlit must be `serve/` — Chainlit looks for `.chainlit/` and `public/` relative to CWD

### serve/embed_server.py
HTTP server that loads Qwen3-Embedding-8B once and serves POST /embed.
- `EMBED_MODEL` env var sets model path
- Reads: `/health` → `{device, loaded}`, `/status` → same + request count
- Must be running before other servers set `EMBED_SERVER_URL`

### serve/mcp_server.py
MCP SSE server on port 8002. Exposes 8 tools from TOOL_DISPATCH. (AGENT_TOOLS in retrieval_engine has 12 — the extra 4 are Juspay-specific, chat-only.)
Registered in `~/projects/hyperretrieval/.mcp.json`:
```json
{"mcpServers":{"juspay-code":{"type":"sse","url":"http://127.0.0.1:8002/sse"}}}
```

### build/01_extract.py
Stage 1 — parses source → symbols, bodies, call graph, log patterns.
Env vars: `REPO_ROOT` (default: `workspaces/juspay/source`), `OUTPUT_DIR` (default: `workspaces/juspay/output`).
Supports: Haskell, Rust, Python, Groovy.

### build/06_build_cochange.py
Streams git history JSON at commit level (O(1) memory). Handles truncated JSON gracefully.
Input: `workspaces/juspay/git_history.json`
Output: `workspaces/juspay/artifacts/cochange_index.json`

---

## The 8 MCP tools (use these directly — never spawn a subagent)

**CRITICAL: Never spawn a general-purpose agent to answer codebase questions. Call MCP tools directly. A subagent costs 18× more tokens (93k vs 5k) and loses context.**

| Tool | Description | Use first when |
|------|-------------|----------------|
| `search_modules` | Find module namespaces by keyword | You need orientation — always start here |
| `get_module` | List all symbols in a module | After search_modules — see the full surface area |
| `search_symbols` | Semantic + keyword search across 94k symbols | You know what a function does, not its name |
| `get_function_body` | Read actual source of a function by ID | You have a fully-qualified ID |
| `trace_callers` | Who calls this function (upstream) | Impact analysis, entry point discovery |
| `trace_callees` | What this function calls (downstream) | Flow tracing |
| `get_blast_radius` | Import graph + co-change for changed files | PR review, change impact |
| `get_context` | Large pre-built context (5–18k tokens) | LAST RESORT only — if search_symbols + get_function_body both failed. Never call twice. |

**Optimal chain:** `search_modules → get_module → get_function_body → trace_callees`

**Function ID format:** dot notation — `Module.SubModule.functionName` (no slashes, no file extensions)

---

## WSL command patterns (running from Windows Git Bash)

```bash
# Deploy a file from Windows to WSL
cmd //c "wsl cp /mnt/d/downloads/repo/FILE ~/projects/hyperretrieval/serve/FILE"

# Complex commands with quotes — use script file, not inline
cmd //c "wsl tee /tmp/script.sh" << 'EOF'
your commands here
EOF
cmd //c "wsl bash /tmp/script.sh"

# Check if a server is running
cmd //c "wsl ps aux | grep embed_server"

# Read a log file
cmd //c "wsl tail -30 /home/beast/embed_server.log"
```

**Never do:**
- `cmd //c "wsl /home/..."` — Git Bash translates the path to `C:/Program Files/Git/home/...`
- `cmd //c "wsl <complex-command-with-single-quotes>"` — breaks heredoc
- `setsid ... &` or `nohup ... &` from `cmd //c wsl` — process dies when the session exits
- Use `cmd //c "wsl bash /home/beast/start_chainlit.sh"` directly — use `~/launch_chainlit.py` instead

**WSL daemonize pattern that works:**
```python
# ~/launch_chainlit.py — Python subprocess with start_new_session=True
import subprocess, os
p = subprocess.Popen(
    ["chainlit", "run", "demo_server_v6.py", "--port", "8000"],
    cwd="/home/beast/projects/hyperretrieval/serve",
    env={**os.environ, "ARTIFACT_DIR": "...", "EMBED_SERVER_URL": "..."},
    stdout=open("/home/beast/chainlit.log", "w"),
    stderr=subprocess.STDOUT,
    start_new_session=True,
)
```

---

## Juspay codebase facts (for answering questions)

**12 services indexed:**
| Service | Symbols | Role |
|---------|---------|------|
| euler-api-gateway | 39,806 | HTTP entry, routing, auth, gateway connectors |
| euler-api-txns | 30,673 | Transaction lifecycle, mandate, EMI, tokenization |
| UCS | 7,787 | Universal Connector Service — third-party gateway integration |
| euler-db | 5,610 | Database layer, OLTP models |
| euler-api-order | 3,652 | Order management |
| graphh | 2,377 | Graph / analytics (Groovy/Grails) |
| euler-api-pre-txn | 2,364 | Pre-transaction validation |
| euler-api-customer | 1,231 | Customer profile |
| basilisk-v3, euler-drainer, token_issuer_portal_backend, haskell-sequelize | < 400 each | Specialised |

**Payment flow direction:** `euler-api-gateway → euler-api-txns → UCS → euler-db`

**Graph internals:**
- G: 94,244 nodes, 542 edges (instance + calls only — import edges are in MG, not G)
- MG: 4,809 modules, 42,467 import edges, 8,706 cross-service
- Why no import edges in G: import edges connect module names, not symbol IDs. The graph builder checks `if src in all_node_ids` — always false for module names.

**Retrieval tuning:**
- `_KW_ALLOWLIST`: short payment terms that bypass the 4-char length filter — `upi, pix, emi, ucs, cvv, pan, otp, kyc, bnpl, nfc, qr`
- `_TEST_PATH_SEGMENTS`: adds 1.5× distance penalty to test/mock/spec files
- `_KNOWN_GATEWAYS`: 38+ gateway names — generates `PayuRoutes`, `PayuFlow` variants for keyword search
- Keyword results sorted by match count (`_kw_score`) before the cap — insertion order is meaningless

---

## Common operations

**Restart Chainlit after a code change:**
```bash
cmd //c "wsl tee /tmp/restart.sh" << 'EOF'
fuser -k 8000/tcp 2>/dev/null
sleep 2
/home/beast/miniconda3/bin/python3 /home/beast/launch_chainlit.py
EOF
cmd //c "wsl bash /tmp/restart.sh"
```

**Check what loaded:**
```bash
# /status command in the Chainlit UI, or:
curl http://localhost:8000  # HTTP 200 = up
curl http://localhost:8001/health  # {device, loaded}
```

**Run a build stage:**
```bash
cmd //c "wsl tee /tmp/run_stage.sh" << 'EOF'
export REPO_ROOT=/home/beast/projects/workspaces/juspay/source
export OUTPUT_DIR=/home/beast/projects/workspaces/juspay/output
export ARTIFACT_DIR=/home/beast/projects/workspaces/juspay/artifacts
export EMBED_MODEL=/home/beast/projects/models/qwen3-embed-8b
cd /home/beast/projects/hyperretrieval
/home/beast/miniconda3/bin/python3 build/01_extract.py
EOF
cmd //c "wsl bash /tmp/run_stage.sh"
```

**Commit and push:**
```bash
cmd //c "wsl tee /tmp/push.sh" << 'EOF'
cd /home/beast/projects/hyperretrieval
git add -A serve/ build/ tools/ tests/ CLAUDE.md README.md .gitignore
git commit -m "your message"
git push origin main
EOF
cmd //c "wsl bash /tmp/push.sh"
```

---

## Known pitfalls (do not repeat these)

1. **Two-copy bug** — demo_server_v6.py once existed in both `pipeline/` and `pipeline/demo_artifact/`. Start script ran from `demo_artifact/` → always picked up stale copy. Fix: single canonical location in `serve/`.

2. **OOM from dual GPU load** — Never start MCP or Chainlit while embed_server is not yet running. They fall back to in-process GPU load → instant OOM → WSL VM crash → `wsl --shutdown` required.

3. **`_encode_queries_batch` looks dead but is not** — Static analysis says it has no callers. It is called indirectly via `_encode_query` and `stratified_vector_search`. Deleting it breaks embedding at runtime.

4. **AGENT_TOOLS must match SYSTEM_PROMPT** — If a tool is described in the system prompt but not in AGENT_TOOLS schema, the LLM will try to call it and fail silently. Keep both in sync.

5. **System message ordering** — Messages array must be `[system, ...history, user]`. Placing system after history breaks instruction following.

6. **LanceDB on NTFS** — mmap fails on `/mnt/d/`. Always write to ext4 (`/tmp/` or `~/projects/`) then move.

7. **`search_symbols("payu")` not finding PayU** — keyword search was capped before ranking. Fix: sort by `_kw_score` before applying the cap. Do not revert this.

8. **`cmd //c "wsl <cmd-with-quotes>"` fails** — Windows CMD cannot handle nested quotes. Write to a script file via `wsl tee /tmp/script.sh` then `wsl bash /tmp/script.sh`.

9. **Split payment vs split settlement** — homonymous terms. Split payment = multi-instrument from customer. Split settlement = fund routing to sub-merchants. Disambiguate before calling tools.

10. **MCP servers in settings.json** — Does not work. MCP registration goes in `.mcp.json`, not `settings.json`.

---

## Pending tasks

1. Run `build/07_chunk_docs.py` after moving `euler-docs/` and `euler-documentation/` into the workspace (done — they are now at `workspaces/juspay/euler-docs/` and `workspaces/juspay/euler-documentation/`)
2. Test `pr_analyzer.py` on a real webhook file change
3. Package as `pyproject.toml` for generic codebase deployment
4. Rebuild pipeline stage 2 to fix import edge propagation to node-level graph (optional — MG workaround is in place and working)
