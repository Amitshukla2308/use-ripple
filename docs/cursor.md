---
title: "Adding HyperRetrieval to Cursor 3"
slug: adding-hyperretrieval-to-cursor
date: 2026-04-18
description: "Give Cursor 3's agent-first architecture temporal code intelligence — co-change, criticality, blast radius, and guardrails — via a single MCP config block."
tags: [hyperretrieval, cursor, mcp, integration]
---

# Adding HyperRetrieval to Cursor 3

*One-page integration guide. Updated 2026-04-18 for Cursor 3. Carlsbert.*

## Why

Cursor 3 ships with agent-first architecture — parallel agents, multi-model execution, SSH remotes. The IDE is now backup infrastructure. But regardless of how capable the agent is, it still starts every session from zero context about your codebase. It writes plausible code. Plausible code in high-criticality sections fails in production in ways that are hard to trace back to the AI author.

The distinction matters at scale. When Cursor edits a module in a 50-repo payment platform, it has no idea that the function it just changed is a criticality-0.9 blast-radius node, that three other modules historically co-change within the same commit window, or that a guardrail document says "never modify the lock acquisition order in this file without a migration test." It writes plausible code. Plausible code in high-criticality sections fails in production in ways that are hard to trace back to the AI author.

HyperRetrieval is the missing memory layer. It indexes your git history — 100K+ commits, cross-repo co-change, ownership, blast radius, organizational guardrails — and exposes them as 15 MCP tools that Cursor Agent can call in the same turn it writes code. Fully self-hosted. Your code and history never leave your machines.

## What HyperRetrieval gives Cursor

Four capabilities unavailable to static analysis or generic RAG:

- **`check_my_changes`** — one call before opening a PR: blast-radius assessment + co-change prediction + criticality scoring + Guard static checks → PASS/WARN/FAIL verdict. Cursor self-reviews before it proposes a commit.
- **`get_blast_radius` + `predict_missing_changes`** — given the files just edited, show what historically co-changes with them and what else probably needs updating. Kills "I edited X but forgot Y always changes with it."
- **`check_criticality` + `get_guardrails`** — for any module Cursor is about to touch, get a 0–1 criticality score and an auto-generated guardrail document: *what invariant must stay true*, *who owns this*, *what tests must pass*. Cursor reads the rules before writing the code.
- **`search_modules` / `search_symbols` / `get_function_body`** — semantic and keyword search grounded in your actual codebase, not a pre-training prior. Cursor finds the real internal API rather than hallucinating a plausible one.

Evidence: blast radius v2 recall@10 improved 0.11 → 0.47 (+322%) on 563 real commits. Guard runs at 2.4 ms/file. fast_search_reranked precision@10=0.900, p95=84ms. 17 MCP tools total.

## Setup (3 steps)

### 1. Start the HyperRetrieval MCP server

```bash
git clone https://github.com/Amitshukla2308/Index-the-code
cd Index-the-code
pip install -e .

# Index your codebase (run once, ~5 min for 50K files)
python build/01_extract.py --repos /path/to/your/repos
python build/02_graph.py
python build/03_embed.py

# Start the MCP server (ripple-mcp CLI available after pip install)
python serve/mcp_server.py  # stdio mode by default
```

### 2. Wire Cursor to HyperRetrieval

Create `.cursor/mcp.json` in your project root (or `~/.cursor/mcp.json` for global):

```json
{
  "mcpServers": {
    "hyperretrieval": {
      "command": "python",
      "args": ["/path/to/Index-the-code/serve/mcp_server.py"],
      "env": {
        "HR_DATA_DIR": "/path/to/your/hr_data"
      }
    }
  }
}
```

Restart Cursor. The 17 HR tools appear in Cursor's Agent tool palette. In Cursor 3, agents automatically discover and invoke MCP tools — verify by opening an agent session and typing `list available tools`.

### 3. Add rules to `.cursor/rules` (Cursor 3)

Create `.cursor/rules` in your project root:

```
Before modifying any module, call check_criticality.
If criticality > 0.7, call get_guardrails and reference its invariants in your change summary.
After completing edits, call check_my_changes. Address any WARN or FAIL findings before committing.
When searching for existing implementations, call search_symbols first — never assume something doesn't exist.
```

Cursor 3 agents read `.cursor/rules` automatically. Every agent in every session now has temporal intelligence about your codebase.

## Honest limits

- **Index freshness**: HR indexes at build time. Rebuild weekly (or on merge to main) for fast-moving repos. A stale index misses recent hot files.
- **Language coverage**: Python, JavaScript/TypeScript, Rust, Haskell well-supported. Other languages get partial symbol extraction.
- **Self-hosted only**: No cloud option yet. Requires a machine with 8–16GB RAM and ~10GB disk for a 50-repo org.
- **MCP tool calls add ~200ms per turn**: negligible for code review turns, perceptible for rapid back-and-forth chat. Use `HR_CRITICALITY_BOOST=0` to disable the reranking pass for speed.

## Next steps

- **Try it on your own repo first**: `python build/01_extract.py --repos .` takes 30 seconds on a single repo. Run `check_my_changes` on your last commit and see what fires.
- **Questions / issues**: [github.com/Amitshukla2308/Index-the-code](https://github.com/Amitshukla2308/Index-the-code)
- **OpenHands users**: same MCP config, different agent runtime. See `openhands_integration.md` in this directory.

---

*HyperRetrieval is open-source. Self-hosted. Your history stays yours.*
*Integration guide by Carlsbert — a Claude agent. AI-generated content.*
