# Codebase Mind Map Project

## Current System State (as of 2026-03-21)

### What exists

- `pipeline/demo_server_v6.py` — v6 (AI Dev Specialist). Deployed and running on localhost:8000 via Chainlit.
- `pipeline/retrieval_engine.py` — all data loading, retrieval, and tool functions. Imported by all entry points.
- `pipeline/mcp_server.py` — MCP HTTP/SSE server on port 8002. 7 tools exposed to Claude Code / Cursor / Windsurf.
- `pipeline/embed_server.py` — shared GPU embedding server on port 8001. Loads Qwen3-Embedding-8B once.
- `pipeline/pr_analyzer.py` — CLI blast-radius tool for CI/CD integration.
- `pipeline/demo_artifact/graph_with_summaries.json` — 142MB. **94,244 nodes**, 45 cluster summaries.
- `pipeline/demo_artifact/vectors.lance` — 94,244 vectors @ 4096d (Qwen3-Embedding-8B).
- `pipeline/demo_artifact/cochange_index.json` — **7,363 modules, 111,005 pairs** (partial — euler-api-gateway only).
- `pipeline/git_history_export.json` — 1.1GB git history. TRUNCATED — ends mid-JSON at ~15,000 commits (euler-api-gateway only).
- `.mcp.json` — registers juspay-code MCP server with Claude Code via SSE: `{"mcpServers":{"juspay-code":{"type":"sse","url":"http://127.0.0.1:8002/sse"}}}`

### Services in graph (12 total)

euler-api-gateway (39,806), euler-api-txns (30,673), UCS (7,787), euler-db (5,610), euler-api-order (3,652),
graphh (2,377), euler-api-pre-txn (2,364), euler-api-customer (1,231), basilisk-v3 (335), euler-drainer (233),
token_issuer_portal_backend (121), haskell-sequelize (55)

---

## Architecture

```
embed_server.py (port 8001) ← GPU model loaded once, shared via HTTP
         ↑ EMBED_SERVER_URL env var
retrieval_engine.py ← all data + retrieval functions
    ↑                      ↑                     ↑
demo_server_v6.py    mcp_server.py         pr_analyzer.py
(Chainlit :8000)     (MCP SSE :8002)       (CLI / CI)
```

**Critical constraint:** Qwen3-Embedding-8B = ~6GB VRAM. Never load it in more than one process simultaneously. embed_server.py is the only process that loads the GPU model. All others set `EMBED_SERVER_URL=http://localhost:8001`.

### Graph internals
- Node-level graph G: 94,244 nodes, 542 symbol edges (instance-type only — import edges connect MODULE names, not node IDs, so they're absent here)
- Module-level graph MG: **4,809 modules, 42,467 import edges, 8,706 cross-service** — built at startup from raw edges
- Body store: 62,169 entries
- Call graph: 60,306 entries
- Doc chunks: 523 (LanceDB)
- Log patterns: 703 entries

---

## MCP Server — 7 Tools

| Tool | Description |
|------|-------------|
| `search_symbols` | Semantic + keyword search for functions/types. Returns full IDs. |
| `search_modules` | Search module namespaces by keyword. Returns `get_module`-callable paths. Use FIRST for orientation. |
| `get_module` | List all symbols in a module namespace in one call. |
| `get_function_body` | Source of a function by fully-qualified ID. |
| `trace_callers` | Who calls this function (callers stored as full IDs in call graph). |
| `trace_callees` | What this function calls (short names qualified via module prefix or name→id index). |
| `get_blast_radius` | Import graph + co-change history for changed files/modules. |
| `get_context` | LAST RESORT — 5k-18k tokens. Full cross-service context. Rules: must call search_symbols first; never call twice per turn. |

**Optimal query path:** `search_modules("X")` → `get_module("X.Y")` → `get_function_body("X.Y.fn")` → `trace_callees`
**Token budget:** A well-scoped question needs ~5k tokens over 4-6 MCP calls. Never spawn agents for MCP queries — it costs 18× more (93k vs 5k tokens) and loses context.

### Retrieval improvements (current in retrieval_engine.py)
- `_KW_ALLOWLIST`: short payment terms bypassing length filter: upi, pix, emi, ucs, cvv, pan, otp, kyc, bnpl, nfc, qr
- `_TEST_PATH_SEGMENTS`: noise path penalty (1.5× distance): test, spec, harness, scenario, mock, connector-integration
- `_KNOWN_GATEWAYS`: frozenset of 38+ gateway names — generates targeted query variants (PayuRoutes, PayuFlow) instead of camelCase noise
- Keyword search sorted by match count (`_kw_score`) before cap — high-match nodes appear first
- `MAX_TOOL_CALLS = 12` (was 50 — LLM was spinning in long loops when initial context was wrong)
- `trace_callers`: direct full-ID lookup in G.nodes (callers stored as full qualified IDs)
- `trace_callees`: qualifies short callee names via `<target_module>.<callee>` or name→id index; labels unresolved as `(unresolved — local var or stdlib)`

---

## What the v6 Server Does

1. 6 expert personas via Kimi tool calling: Domain Expert, New Engineer Guide, Reliability Engineer, Security Auditor, Bar Raiser, Observability Engineer
2. Stratified vector search — k_total=150, k_per_service=12 (ensures all 12 services covered)
3. Cross-service keyword search — exhaustive per-service, sorted by match count, allowlist for short terms
4. Module-level import graph (MG) — 4,809 modules, 42,467 edges, 8,706 cross-service
5. Co-change traversal — BFS on cochange_index (7,363 modules, 111,005 pairs)
6. Type signatures — shown in evidence per symbol (:: type)
7. Ghost deps — external dependencies shown per service
8. Entry points — HTTP handlers/route defs surfaced
9. Mermaid diagrams — injected into domain_expert and observability frameworks
10. Conversation history — MAX_HISTORY=6 turns maintained via cl.user_session
11. /status command — shows live system state
12. Hot-reload — background thread checks for cochange_index.json every 30s
13. Embed server integration — `EMBED_SERVER_URL=http://localhost:8001` for shared GPU access

---

## Mistakes Made & RCA

1. **Empty cluster_name in LanceDB**
   RCA: LanceDB was built from pre-stage-4 graph (no cluster names). Fix: Rebuilt LanceDB after stage 4.
   Lesson: When re-running a stage, always identify downstream artifacts that need rebuilding.

2. **Empty cluster_name in NetworkX G**
   RCA: node_link_graph only includes attributes present at serialization time.
   Fix: `nx.set_node_attributes(G, cluster_attrs)` patches after loading.
   Lesson: Always patch post-serialization graph attributes at load time.

3. **"upi" filtered out by keyword search**
   RCA: len("upi") < 4 dropped by min-length filter. Fix: `_KW_ALLOWLIST`.
   Lesson: Domain-specific terms need explicit allowlists.

4. **Graph has only 542 edges**
   RCA: Import edges connect MODULE NAMES, not NODE IDs. Graph builder's `if src in all_node_ids` always fails for module names.
   Fix: Built separate MODULE-LEVEL graph (MG) at startup.
   Lesson: Module-level vs symbol-level graphs are fundamentally different. Always verify edge counts.

5. **Co-change builder OOM (v1)**
   RCA: `ijson.items(f, 'repositories.item')` loaded entire repo objects into memory.
   Fix: Stream at commit level using `ijson.parse()` events.
   Lesson: Stream at the LEAF collection level, not the container level.

6. **Co-change builder slow on NTFS**
   RCA: NTFS via WSL2 ~100MB/s vs ext4 ~500MB/s.
   Fix: Copy to `/home/beast/projects/mindmap/pipeline/git_history_export.json` (ext4).
   Lesson: Large file operations in WSL must use ext4 paths.

7. **Builder process dying**
   RCA: Processes attached to pseudo-terminals — SIGHUP killed on terminal close.
   Fix: `setsid ... > /tmp/log.log 2>&1 &` with `PYTHONUNBUFFERED=1`.
   Lesson: Long-running WSL processes MUST use setsid. Verify with ps aux — `?` in TTY = daemonized.

8. **Git history file truncated**
   RCA: Export script interrupted. Only euler-api-gateway (~15k commits), 4 other repos missing.
   Fix: Builder v2 wraps parser in try/except for IncompleteJSONError, writes partial results.
   Lesson: Always validate large files before pipeline stages. `tail -c 200 file.json`.

9. **/status slash command**
   RCA: `@cl.on_chat_message` doesn't exist in Chainlit — only `@cl.on_message`.
   Fix: Handle /status as first check inside `@cl.on_message`.
   Lesson: Verify Chainlit API against docs.

10. **WSL path translation in Git Bash**
    RCA: Git Bash translates `/home/beast/...` to `C:/Program Files/Git/home/beast/...`.
    Fix: `cmd //c "wsl ..."` or `//home/...` (double-slash).
    Lesson: In Windows Claude Code (Git Bash), always use `cmd //c "wsl <cmd>"`.

11. **PayU not found by retrieval (keyword search order bug)**
    RCA: `cross_service_keyword_search` returned first-20 by NetworkX insertion order, not relevance. PayU nodes never appeared in top-20.
    Fix: Added `_kw_score` (match count), sort by `-_kw_score` before cap.
    Lesson: Never cap results before ranking — insertion order is meaningless.

12. **Wrong gateway→service mapping**
    RCA: Added `_GATEWAY_SERVICE` dict mapping PayU → UCS. PayU is NOT in UCS for Juspay.
    Fix: Use `_KNOWN_GATEWAYS` frozenset with no service assumption.
    Lesson: Don't hardcode service assignments for gateways without confirmation.

13. **Spawning agent for MCP queries**
    RCA: Used general-purpose Agent tool for codebase exploration despite having MCP tools directly available in session.
    Cost: 93k tokens / 68 tool calls vs ~5k tokens / 5-6 direct MCP calls (18× waste).
    Fix: Call MCP tools directly in the main session.
    Lesson: NEVER spawn a subagent for juspay-code MCP queries. Use the tools directly.

14. **Split payment vs split settlement conflated**
    RCA: Agent searched "split" and found `SplitSettlement` (vendor disbursement) before `SplitPayment` (multi-instrument). Mixed both flows in one answer.
    Fix: Clarify before searching — split payment = multiple instruments from customer; split settlement = fund routing to sub-merchants after collection.
    Lesson: Homonymous terms in payment domain require disambiguation BEFORE tool calls.

15. **`cmd //c "wsl <cmd-with-quotes>"` fails for complex commands**
    RCA: Windows CMD cannot handle nested quotes reliably. Commands with double quotes inside `cmd //c "wsl ..."` fail with unexpected EOF.
    Fix: Write commands to a script file via `wsl tee /tmp/script.sh` (heredoc from Git Bash), then `wsl /tmp/script.sh`. Or use Python launcher (`/tmp/launch_mcp.py`) for processes needing env vars.
    Lesson: Complex WSL commands must go through a script file, not inline.

16. **`settings.json` rejects `mcpServers` field**
    RCA: Claude Code `settings.json` schema does not accept `mcpServers`. Only recognized keys are theme, model, permissions, hooks, etc.
    Fix: Use `.mcp.json` in the project root (or `~/.claude/mcp.json` for global).
    Lesson: MCP server registration goes in `.mcp.json`, NOT `settings.json`.

---

## What To Do (Confirmed Working)

- **Deploy changes to WSL:** `cmd //c "wsl cp /mnt/d/downloads/repo/FILE /home/beast/projects/mindmap/pipeline/FILE"`
- **Restart Chainlit:** `cmd //c "wsl fuser 8000/tcp"` → get PID → `cmd //c "wsl kill PID"` → `cmd //c "wsl /tmp/start_chainlit.sh"`
- **Start MCP server:** `cmd //c "wsl /home/beast/miniconda3/bin/python3 /tmp/launch_mcp.py"` (Python launcher sets EMBED_SERVER_URL, uses setsid)
- **Write WSL scripts:** Use `cmd //c "wsl tee /tmp/script.sh" << 'EOF' ... EOF` (heredoc in Git Bash) — then `cmd //c "wsl bash /tmp/script.sh"`
- **Run long processes:** Script must use `setsid ... > /tmp/log.log 2>&1 &` with `PYTHONUNBUFFERED=1`
- **Check WSL process:** `cmd //c "wsl ps aux | grep PATTERN"` — `?` in TTY = daemonized properly
- **Python in WSL:** Always `/home/beast/miniconda3/bin/python3` (Python 3.13), not system python3 (3.12)
- **MCP launcher script:** `/tmp/launch_mcp.py` — Python subprocess.Popen with `EMBED_SERVER_URL` + `start_new_session=True`

## What NOT To Do

- **Never** `wsl -e /home/...` or `wsl.exe -- /home/...` — Git Bash path translation.
- **Never** use `cmd //c "wsl <complex-cmd-with-quotes>"` — use a script file instead.
- **Never** load full repo objects with `ijson.items(f, 'repositories.item')` — OOM.
- **Never** assume graph edges are preserved — always verify `G.number_of_edges()` after loading.
- **Never** read from `/mnt/d/` for large files — copy to ext4 first.
- **Never** start long WSL processes without setsid — they die with the terminal.
- **Never** claim a file is complete without checking the last bytes for truncation.
- **Never** run two co-change builders simultaneously — output file corruption.
- **Never** use `--break-system-packages pip` — use `/home/beast/miniconda3/bin/pip`.
- **Never** spawn a general-purpose Agent to answer juspay-code questions — call MCP tools directly.
- **Never** add `mcpServers` to `settings.json` — use `.mcp.json`.
- **Never** load data in a second process while Chainlit is running — WSL2 VM OOM (reboot required).

---

## Pending Tasks (in priority order)

1. Regenerate git_history_export.json from all 5 repos (only ~15k of ~100k commits available, euler-api-gateway only)
2. Copy euler-docs markdown to `/home/beast/projects/mindmap/euler-docs` for internal doc embedding
3. Test pr_analyzer.py on a real webhook file change
4. Package as installable Python package (pyproject.toml) for generic codebase use
5. Rebuild pipeline stage 2 to fix import edge propagation to node-level graph (optional — MG workaround is in place)

---

## Key Architecture Decisions

- **Why MG vs G for imports:** Import edges connect module names, not symbol IDs. Building MG separately avoids re-running the entire pipeline.
- **Why stratified vector search:** Raw vector search is biased toward euler-api-txns (most symbols). Stratification guarantees all 12 services get representation.
- **Why 2-call LLM architecture:** Router call selects persona (cheap, ~300 tokens). Answer call uses full context (expensive, ~32k tokens). Separating them lets Kimi read all evidence before committing to a reasoning mode.
- **Why embed_server.py:** Qwen3-Embedding-8B = ~6GB VRAM. Two processes loading it = OOM. Shared HTTP server = one load, zero conflict.
- **Why MCP HTTP/SSE (not stdio):** Chainlit server holds the data in memory. MCP SSE transport lets the MCP server connect to the Chainlit process's embedder via `EMBED_SERVER_URL`. stdio would need its own independent load.
- **Why MAX_TOOL_CALLS=12 (not 50):** LLM was spinning in 50-call loops when initial retrieval returned wrong context. 12 forces earlier synthesis.
