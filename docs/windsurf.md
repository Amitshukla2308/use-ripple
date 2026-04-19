# Adding HyperRetrieval to Windsurf

*One-page integration guide. 2026-04-18. Carlsbert.*

## Why

Windsurf's Cascade agent is the fastest way to write code in an IDE today. But Cascade — like every IDE agent — starts from zero context on every session. It reads your open files. It doesn't know that `payments/idempotency.py` has broken three times in the last six months every time someone touches `payments/refund.py`. It doesn't know that `core/auth.py` is the system's highest-criticality module and has a guardrail document that three senior engineers agreed on. It doesn't know what blast radius looks like before a change is made.

HyperRetrieval gives Cascade that memory. It indexes your git history into temporal signals — co-change, criticality, blast radius, change prediction — and exposes them through 17 MCP tools Cascade can call in every session. You don't change how you use Windsurf. You add one config block and Cascade gets smarter about your specific codebase.

## What HyperRetrieval gives Cascade

**Before opening a PR:**
- `check_my_changes` — blast-radius + co-change prediction + criticality scoring + Guard static checks in one call. PASS/WARN/FAIL. Cascade self-checks before it asks you to review.
- `get_blast_radius` — which files historically move when the files Cascade just edited move. Kills "why didn't you also update X?"

**While writing code:**
- `search_modules` / `search_symbols` — semantic search over your actual codebase, grounded in git history, not generic pre-training. Cascade stops hallucinating internal API names.
- `get_function_body` / `get_module` — retrieve exact implementation before rewriting it. Zero drift.

**For high-risk changes:**
- `check_criticality` + `get_guardrails` — for any module Cascade is about to touch, criticality score (0–1) plus auto-generated guardrail document: what invariant must stay true, who should review. Cascade can attach this to the PR automatically.
- `predict_missing_changes` — given Cascade's edits, surface the other files that likely need updating. Reduces maintainer-rejected PRs by catching incomplete changes before commit.

Benchmarks from the reference deployment: blast radius recall@10 0.11 → 0.47 (+322%) on 563 real commits; Guard runs at 2.4 ms/file; 17 MCP tools covering retrieval, graph traversal, PR review, and guardrails.

## Setup (3 steps)

### 1. Start the HyperRetrieval MCP server

```bash
git clone https://github.com/Amitshukla2308/Index-the-code
cd Index-the-code
pip install -e .
# Index your codebase (one-time, ~5-10 min for 50K-file repos)
python serve/index.py --repo /path/to/your/repo
# Start MCP server
python serve/mcp_server.py --port 8002
```

### 2. Add HyperRetrieval to Windsurf's MCP config

Open Windsurf Settings → Extensions → MCP Servers, or edit `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "hyperretrieval": {
      "serverUrl": "http://localhost:8002/mcp",
      "description": "Temporal code intelligence — co-change, criticality, blast radius, guardrails"
    }
  }
}
```

Restart Windsurf. Cascade now has access to all 17 HyperRetrieval tools.

### 3. Tell Cascade when to use it (optional but recommended)

Add to your workspace `.windsurfrules` file:

```
Before modifying any module, call check_criticality. 
If criticality > 0.7, call get_guardrails and include the output in your change summary.
After completing edits, call check_my_changes. If WARN or FAIL, address findings before asking for review.
```

## Honest limits

- HyperRetrieval requires an indexed git history (≥ 6 months of commits for meaningful signal). Works best on codebases with 10K+ commits.
- The MCP server runs on your infrastructure. It does not send your code anywhere.
- `check_my_changes` currently supports Python, Rust, JavaScript/TypeScript, Go, Java, Haskell. Comment-code alignment (Guard Layer 3) requires devstral-small or compatible local LLM on the same machine.
- First-time indexing takes 5–10 minutes for a 50K-file repo. Subsequent updates are incremental.

## The ask

If you're an engineering leader at a fintech or regulated-industry company using Windsurf for AI-assisted development, we want to talk. We're particularly interested in teams where: AI coding tools are in production, code review cycles are slow, or compliance requires traceability of AI-generated code.

Contact: [ripple.tunnelthemvp.in](https://ripple.tunnelthemvp.in) or ping @amitshukla2308 on GitHub.

---

*HyperRetrieval is self-hosted, open-source core, Apache 2.0. Enterprise support available.*
