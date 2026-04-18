# Ripple + Cursor Bugbot

Use Ripple's MCP tools as context for [Cursor Bugbot](https://cursor.com/changelog/3-0) — giving Bugbot access to co-change history, blast radius, and module ownership when reviewing pull requests.

Cursor Bugbot now supports MCP servers for additional context (Teams/Enterprise). Ripple provides the temporal layer Bugbot can't get from the AST: which modules co-change historically, who owns them, and what blast radius a given change carries.

## Prerequisites

1. Ripple MCP server running:
   ```bash
   cd serve && python mcp_server.py  # starts on port 8002
   ```

2. Cursor Teams or Enterprise plan (Bugbot MCP support requires Teams+)

3. A Ripple index built from your repo's git history (see QUICKSTART.md)

## Setup (Cursor Bugbot Dashboard)

1. In the Cursor dashboard, go to **Settings → Bugbot → MCP Tools**

2. Add Ripple's MCP server:
   ```
   Name:     ripple-mcp
   Type:     SSE
   URL:      http://localhost:8002/sse
   ```

3. Enable the following tools for Bugbot review context:
   - `get_blast_radius` — shows how many modules are coupled to changed files
   - `predict_missing_changes` — flags files likely missing from the PR
   - `check_my_changes` — composite PASS/WARN/FAIL verdict with risk score
   - `suggest_reviewers` — git-history-based reviewer suggestions
   - `get_why_context` — ownership, activity trend, bus factor warning

## What Bugbot gains

Without Ripple, Bugbot reviews PRs using static analysis: what the code IS.

With Ripple, Bugbot gains:

| Signal | Without Ripple | With Ripple |
|--------|---------------|-------------|
| Files likely missing from PR | ❌ | ✅ `predict_missing_changes` |
| Blast radius of changed files | ❌ | ✅ `get_blast_radius` |
| Who should review this | Partial (GitHub CODEOWNERS) | ✅ `suggest_reviewers` (git history) |
| Bus factor risk | ❌ | ✅ `get_why_context` → `bus_factor_warning` |
| Cross-service coupling | ❌ | ✅ Granger causality across repos |
| Risk score (0–100) | ❌ | ✅ `score_change_risk` |

## Example: Bugbot review with Ripple context

When a PR touches `src/payments/processor.py`, Bugbot can now call:

```
check_my_changes(["src/payments/processor.py"])
```

And receive:

```json
{
  "verdict": "WARN",
  "risk_score": 67,
  "blast_radius": 23,
  "missing_changes": ["src/payments/refund.py", "src/audit/log.py"],
  "suggested_reviewers": ["alice@example.com", "bob@example.com"],
  "bus_factor_warning": null
}
```

Bugbot surfaces this in the PR review comment, giving your team temporal intelligence that static analysis cannot provide.

## Self-hosted

Ripple is fully self-hosted. Your code, git history, and ownership data never leave your infrastructure.

---

*Built by [Amit Shukla](https://github.com/Amitshukla2308) · Research by [Carlsbert](https://carlsbert.tunnelthemvp.in/journal/)*
