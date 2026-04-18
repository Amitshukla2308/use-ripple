# Ripple + JetBrains IDEs

Use Ripple's MCP tools inside IntelliJ IDEA, PyCharm, GoLand, WebStorm, or any JetBrains IDE with AI Assistant enabled.

JetBrains AI Assistant added MCP server support in 2025.1+. Ripple provides the temporal layer the built-in code analysis can't — co-change history, blast radius from real commits, module ownership, and Granger causal direction.

## Prerequisites

1. JetBrains IDE 2025.1+ with AI Assistant plugin enabled
2. Ripple MCP server running:
   ```bash
   ARTIFACT_DIR=~/projects/workspaces/YOUR_ORG/artifacts python3 serve/mcp_server.py
   # starts on port 8002
   ```
3. A Ripple index built from your repo's git history (see README)

## Setup

### Option A — Project-level (recommended)

Create `.mcp.json` at your project root:

```json
{
  "mcpServers": {
    "ripple": {
      "type": "sse",
      "url": "http://127.0.0.1:8002/sse"
    }
  }
}
```

JetBrains AI Assistant auto-discovers `.mcp.json` files in the project root.

### Option B — IDE-level (all projects)

1. Open **Settings → Tools → AI Assistant → MCP Servers**
2. Click **+** → **SSE**
3. Fill in:
   - **Name**: `ripple`
   - **URL**: `http://127.0.0.1:8002/sse`
4. Click **OK** → **Apply**

Ripple's 15 tools are now available in all JetBrains AI chat sessions.

## Using Ripple in AI Assistant chat

Once connected, AI Assistant can call Ripple tools automatically when answering questions about your codebase. You can also invoke tools explicitly:

```
What files are likely missing from my PR that touches PaymentProcessor?
→ AI calls: predict_missing_changes(["src/payments/processor.py"])

Who should review changes to the auth module?
→ AI calls: suggest_reviewers(["src/auth/middleware.py"])

What's the risk score for my current changeset?
→ AI calls: check_my_changes(["src/payments/processor.py", "src/auth/session.py"])
```

## Key tools for JetBrains workflows

| Tool | JetBrains use case |
|------|--------------------|
| `check_my_changes` | Pre-commit PASS/WARN/FAIL verdict with blast radius + missing files |
| `get_blast_radius` | "What else do I need to update?" when editing a module |
| `suggest_reviewers` | Who to assign on Code Review tool window |
| `get_why_context` | Why does this code exist? Ownership, activity trend, causal direction |
| `fast_search` | Zero-GPU BM25 symbol search, ~40ms — faster than IDE indexing for large monorepos |
| `predict_missing_changes` | Catch incomplete refactors before push |

## Verification

Open AI Assistant chat and type:

```
list the top 5 most critical modules in this codebase
```

If Ripple is connected, you'll see it call `list_critical_modules` and return a ranked list with criticality scores. If it returns a generic answer without tool calls, check that the MCP server is running (`curl http://localhost:8002/sse`) and the `.mcp.json` is in the project root.

## Self-hosted

Ripple runs entirely on your infrastructure. Your code, git history, and ownership data never leave your machines — which matters for teams with strict data residency requirements.

---

*Built by [Amit Shukla](https://github.com/Amitshukla2308) · Research by [Carlsbert](https://carlsbert.tunnelthemvp.in/journal/) — an autonomous Claude agent*
