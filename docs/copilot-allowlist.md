# Adding ripple-mcp to Your GitHub Copilot Org Allowlist

GitHub Copilot's April 2026 update added org-level MCP governance: admins can allowlist specific MCP servers so developers can use them without individual approval. This guide walks through adding ripple-mcp to your org's allowlist.

---

## Why this matters

By default, Copilot blocks unapproved MCP servers in Agent Mode. Your developers may have ripple-mcp running locally but Copilot won't load its tools until an admin allowlists it. Allowlisting takes 5 minutes and unlocks all 15 ripple-mcp tools for your entire org.

---

## Prerequisites

- GitHub org with Copilot Business or Enterprise
- ripple-mcp running locally (see [setup guide](../README.md#full-setup))
- GitHub org admin or owner role

---

## Step 1 — Start ripple-mcp

On each developer machine, ripple-mcp must be running before Copilot can use it:

```bash
# Start the MCP server (runs at localhost:8002)
ARTIFACT_DIR=~/projects/workspaces/YOUR_ORG/artifacts python3 serve/mcp_server.py
```

ripple-mcp is self-hosted: it runs on the developer's machine, indexes stay local, and **no code leaves the network**. Copilot connects to `http://127.0.0.1:8002/sse` — a localhost call, not an external endpoint.

---

## Step 2 — Add the allowlist entry

1. Go to `github.com/organizations/YOUR-ORG/settings/copilot/mcp`
2. Click **Add MCP server**
3. Fill in:
   - **Name**: `ripple-mcp`
   - **URL**: `http://127.0.0.1:8002/sse`
   - **Type**: SSE
   - **Description**: "Temporal code intelligence — blast radius, co-change, Guard"
4. Click **Save**

The URL `127.0.0.1:8002` is a loopback address — GitHub's servers never see it. Each developer connects Copilot to their own local instance.

---

## Step 3 — Add `.vscode/mcp.json` to your repo

Commit this file to your repository root so every developer gets ripple-mcp automatically when they open the repo in VS Code:

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

With the org allowlist active, VS Code will load this without prompting each developer.

---

## Step 4 — Verify tools are visible

In VS Code with Copilot Chat open, switch to **Agent Mode** (the robot icon). Type `@ripple` — you should see the 15 ripple-mcp tools listed:

```
check_my_changes    get_blast_radius    get_why_context
predict_missing_changes    score_change_risk    suggest_reviewers
check_criticality   get_guardrails      list_critical_modules
fast_search         search_symbols      search_modules
get_function_body   trace_callers       trace_callees
```

If tools don't appear, verify the MCP server is running: `curl http://127.0.0.1:8002/health`

---

## Data residency and compliance

| Concern | Answer |
|---|---|
| Does code leave our network? | No. ripple-mcp runs on each developer's machine. All calls are localhost. |
| Does Copilot send our index to GitHub? | No. Copilot calls ripple-mcp locally; only the tool response (a text summary) goes to Copilot. |
| FedRAMP compatibility | ripple-mcp is self-hosted. No data residency requirement because no data leaves your environment. |
| EU AI Act traceability | Guard + Provenance tools log findings locally. Export-ready for audit. |

---

## Enterprise deployment (team-wide)

For teams where not every developer runs ripple-mcp locally, you can run a shared instance:

```bash
# On a team server
ARTIFACT_DIR=/shared/artifacts python3 serve/mcp_server.py --host 0.0.0.0 --port 8002
```

Then update `.vscode/mcp.json` to point at the server:

```json
{
  "mcpServers": {
    "ripple": {
      "type": "sse",
      "url": "http://ripple.internal:8002/sse"
    }
  }
}
```

Add `RIPPLE_API_TOKEN` for bearer token auth (see [RFC-009](../rfcs/009_mcp_oauth21_enterprise_auth.md)).

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Tools don't appear in Agent Mode | Verify MCP server is running: `curl http://127.0.0.1:8002/health` |
| `Connection refused` | Start ripple-mcp first: `python3 serve/mcp_server.py` |
| Tools appear but return errors | Check `ARTIFACT_DIR` env var points to a built index |
| Org allowlist shows "blocked" | Confirm your GitHub role is org admin or owner |

---

*ripple-mcp is open source (Apache 2.0). Source: [github.com/Amitshukla2308/use-ripple](https://github.com/Amitshukla2308/use-ripple)*
