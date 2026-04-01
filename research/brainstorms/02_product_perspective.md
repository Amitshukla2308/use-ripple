# HyperRetrieval: Brutally Honest Product Teardown

**Author:** Senior PM, 3 months daily usage
**Date:** 2026-03-31
**Deployment:** 94,244 symbols, 12 Haskell microservices, Chainlit chat UI + `hrcode` CLI

---

## 1. First 5 Minutes: The New Engineer Experience

**What actually happens:** You hit the Chainlit URL, get a login screen with username/password. No SSO, no Google login -- just a raw password form. First-time users are auto-registered, which is nice, but there is zero indication of this. An engineer who types a wrong password on their "first login" has now created an account with that wrong password.

**The onboarding flow is good but front-loaded.** The welcome message shows a table of example queries ("Trace a payment flow", "Understand a module", etc.) and then presents six starter buttons. This is the right idea. But:

- **No system status indicator.** The data takes ~35 seconds to load (embed server GPU warmup). If a new user types a question before `load_all()` finishes, what happens? They get a cryptic failure or empty results. There is no loading bar, no "warming up" toast, nothing.
- **No documentation link.** No "How this works" page. No explanation that this is a ReAct agent that calls tools against an index. Engineers do not know what the system can and cannot do.
- **No codebase overview.** 94k symbols across 12 services, but nowhere does the UI say "here are the 12 services, here is how big each one is, here is what each one does." The starters assume you already know what euler-api-txns and UCS are.
- **The starters are domain-specific.** "How does UPI Collect work?" is useless to an engineer who works on settlement. There is no personalization, no role-based starter sets.
- **File upload is disabled** (`spontaneous_file_upload.enabled = false`). An engineer cannot paste a stack trace or upload a log file. This is a fundamental gap for an investigation tool.

**What is missing:**
- A 30-second animated walkthrough showing the ReAct loop in action
- A "What services are indexed?" sidebar panel
- An indication of freshness ("Index last updated: 2 hours ago")
- SSO integration (every enterprise expects this)

---

## 2. The Query Gap: Questions Engineers Want to Ask But Cannot

### Questions the system handles well:
- "How does function X work?" (search_symbols + get_function_body)
- "Who calls X?" (trace_callers)
- "What would break if I change file Y?" (get_blast_radius)

### Questions the system cannot answer:

| Question | Why it fails | What would fix it |
|----------|-------------|-------------------|
| "What changed in the last sprint?" | No git history integration in the query path. `git_history.json` exists but is only used for co-change index building, not real-time queries. | Add a `get_recent_changes(service, days)` tool that queries git log. |
| "Who owns this module?" | No ownership data. No CODEOWNERS parsing. No team mapping. | Ingest CODEOWNERS files. Add `get_owner(module)` tool. |
| "Is this function safe to delete?" | Blast radius shows import-level impact, but cannot tell you about runtime reflection, config-driven dispatch, or template references. | Add dead code analysis. Cross-reference with runtime call logs if available. |
| "Show me all the places we handle timeouts" | Semantic search finds some, but "timeout" is a pattern (try/catch with specific exception types, config values), not a symbol name. | Add pattern-based search: grep over source with semantic ranking. The `grep_files` tool exists in the CLI but is not surfaced prominently. |
| "What is the API contract for this endpoint?" | No OpenAPI/Swagger ingestion. The system indexes Haskell AST but does not extract HTTP route definitions as first-class objects. | Parse route definitions. Build an endpoint registry. |
| "How does this compare to how it worked 6 months ago?" | No historical index. One snapshot in time. | Maintain versioned indexes or diff against git history. |
| "What are the known bugs in this area?" | No Jira/issue tracker integration. | Add a `search_issues(query)` tool backed by Jira API. |
| "Show me the data model for orders" | Types are indexed as symbols, but there is no ERD or relationship view. You have to manually call `get_function_body` on each type. | Add a `get_data_model(entity)` tool that collects all related types and their field relationships. |

The fundamental gap: **HyperRetrieval knows code structure but not code history, code ownership, or code intent.** It is a spatial map without a temporal dimension.

---

## 3. The Response Problem: 15 Tool Calls and 90 Seconds of Silence

### What the log data tells us

From the retrieval log, a typical deep investigation query (like the auto-refund split payment example) triggers 4+ tool calls, each taking 1-4 seconds, with the full conversation easily exceeding 60 seconds wall time. The first token time (TTFT) for even simple queries is ~8 seconds (logged as `ttft_ms: 7976`).

### The waiting experience

**Chainlit shows tool calls as collapsible "Steps"** -- this is the right UX pattern. The engineer can see `search_modules("auto refund")` completing, then `get_module("Product.OLTP.Services.AutoRefundService")`, and so on. Chain-of-thought display is set to `cot = "full"`, so reasoning is visible.

**But the problems are real:**

1. **No progress indicator.** There is no "Step 3 of ~8" estimate. The engineer does not know if they are 20% done or 90% done. They see steps appearing but have no mental model of when the answer will arrive.

2. **No early signal of answer quality.** After 60 seconds of tool calls, the final answer might be "I could not find enough information about this." The engineer just wasted a minute. The system should surface confidence early: "I found 3 relevant modules, assembling answer..." vs "I'm struggling to find relevant code for this query."

3. **Tab-away problem.** Engineers tab away after ~15 seconds. No browser notification when the answer is ready. No sound. No desktop notification API integration. The answer sits unseen.

4. **The 50-call ceiling is too high.** `MAX_TOOL_CALLS = 50` means a runaway loop can burn 3+ minutes. The CLAUDE.md says 12 is the real target. The gap between 12 (documented) and 50 (code) suggests the ceiling was raised to handle edge cases, but it also means worst-case latency is unbearable.

5. **Token economics are invisible.** The log shows `in_tokens: 3658, out_tokens: 255` for simple queries but the deep queries accumulate massive context. Engineers have no idea they are consuming expensive LLM tokens. This matters when leadership asks "why is our API bill $X?"

### What engineers actually do:

- **Simple questions (< 15s):** They wait. Acceptable.
- **Medium questions (15-45s):** They start reading the tool call steps. This is actually valuable -- they learn the codebase structure by watching the agent navigate. But most do not realize this.
- **Long questions (45s+):** They tab away. They may forget they asked. They may ask the same question again in a new tab.

### Fixes:

- **Streaming partial answers.** After 3 tool calls, stream a preliminary "Here is what I have found so far..." paragraph, then continue investigating.
- **Browser notifications.** `Notification.requestPermission()` on first visit. Fire when answer is ready.
- **Estimated time remaining.** Track historical query-to-answer times by query type. Show "Usually takes 30-60 seconds for this type of question."
- **Cancel button.** Let the user abort a long-running investigation and get whatever partial results exist.

---

## 4. The 10x Features: What Would Make Engineers Come Back Daily

### 4a. VS Code Extension -- "Answer about the file you are editing"

**Impact: HIGH. This is where engineers live.**

Right now, to ask about a function, you: open browser, navigate to HR, type the question, wait, read the answer, then go back to VS Code. That is 4 context switches.

A VS Code extension that adds a sidebar panel: select a function, right-click "Explain this", "Who calls this?", "What breaks if I change this?" -- the answer appears in a panel next to your code. Zero context switches.

The MCP server already exists on port 8002. A VS Code extension just needs to be a thin client. The hard part is not building it -- it is making it fast enough that engineers prefer it over Cmd+clicking through the code themselves.

**Concrete implementation:** A CodeLens provider that adds "Callers (7) | Callees (3) | Blast Radius" above each function definition. Clicking any of these opens a panel with the results. No LLM needed for these -- they are direct index lookups, sub-second.

### 4b. PR Review Assistant -- "Auto-analyze every PR for blast radius"

**Impact: VERY HIGH. This is the first feature that delivers value without the engineer asking.**

Today: engineer opens a PR, manually checks which files changed, mentally traces dependencies. With HR: a GitHub Action runs `pr_analyzer.py` (which already exists in `serve/`), posts a comment on the PR showing blast radius, co-change history, and cross-service impact.

**The key insight:** This is the only feature that can be **push-based** rather than pull-based. Every other feature requires the engineer to decide to use HR. This one runs automatically.

What the PR comment should show:
- Files changed and their blast radius (import graph + co-change)
- Cross-service boundaries crossed (e.g., "This PR touches euler-api-txns but co-change history shows euler-api-gateway usually changes with these modules")
- Functions with high caller counts that were modified (high-risk changes)
- New functions that have no callers yet (dead code alert)
- A confidence score: "This is a low-risk change" vs "This change has wide impact across 3 services"

### 4c. Incident Responder -- "Paste an error, get root cause analysis"

**Impact: HIGH during incidents, but incidents are rare.**

The flow: paste a stack trace or error message. HR extracts function names and module paths from the trace, runs `trace_callers` and `trace_callees` on each frame, cross-references with blast radius data, and presents a root cause hypothesis.

**The problem:** File upload is disabled in the current config. You cannot paste a multi-line stack trace easily in a chat input. And Haskell stack traces are notoriously unhelpful (lazy evaluation, no line numbers in many cases).

**What would actually help for incidents:**
- Parse the error message for function/module names (HR already does semantic search)
- Show the call chain leading to the failure point
- Show recent co-changes ("this module was last changed 2 days ago, along with these other modules")
- Link to the relevant PR that last modified the failing code

### 4d. Onboarding Generator -- "Auto-create onboarding docs for new team members"

**Impact: MEDIUM. High value but low frequency (new hires are infrequent).**

Given a service name, generate:
- Architecture overview (module graph visualization -- the `generate_mindmap.py` tool already exists)
- Key entry points and their flows
- Data model summary
- Common patterns and conventions used in the codebase
- "Start here" reading list of the 10 most important modules

This is a batch job, not a real-time query. Run it once, produce a markdown doc, put it in Confluence. Update it monthly.

**Priority ranking:** PR Review > VS Code Extension > Incident Responder > Onboarding Generator

---

## 5. What Copilot/Cursor Do Better (Honest Assessment)

### Where they win:

| Capability | Copilot/Cursor | HyperRetrieval |
|-----------|---------------|----------------|
| **Inline code completion** | Instant, in-editor, zero friction | Does not exist. HR is a question-answering tool, not a completion engine. |
| **Edit suggestions** | "Fix this", "Refactor this" with one click | Cannot write or edit code. Read-only by design (write tools explicitly removed from chat). |
| **Speed** | Sub-second for completions | 8+ seconds minimum (TTFT), 30-90s for deep queries. |
| **Context window** | Cursor indexes the open project automatically | HR requires a separate build pipeline (`01_extract.py` through `07_chunk_docs.py`). Index staleness is a real issue. |
| **IDE integration** | Native. Zero setup for the user. | Separate browser tab. Or MCP config that most engineers will not set up. |
| **Multi-file edits** | Cursor Composer edits across files | Not applicable -- HR does not edit files. |

### Where HR wins:

| Capability | HyperRetrieval | Copilot/Cursor |
|-----------|---------------|----------------|
| **Cross-service understanding** | Indexes 12 services as one graph. Traces calls across service boundaries. | Each is limited to the open workspace. Cannot trace a function from euler-api-gateway into euler-api-txns. |
| **Call graph accuracy** | AST-extracted, not heuristic. Shows real callers/callees. | Relies on LLM guessing from context window. Hallucinates callers regularly. |
| **Blast radius** | Import graph + co-change history. Quantified impact. | "What files might be affected?" -- vague, incomplete, no co-change data. |
| **Codebase-wide search** | 94k symbols searchable by semantics and keywords. Finds things across all 12 services. | Limited to open files + whatever fits in context. |
| **Institutional knowledge** | Answers "why does this code exist?" by tracing the full dependency chain | Cannot explain legacy decisions without explicit comments. |

### The honest conclusion:

**Copilot/Cursor win on writing code. HR wins on understanding code.** They are complementary, not competitive. The mistake would be trying to make HR do code completion. The opportunity is making HR the knowledge layer that feeds into Copilot/Cursor via MCP.

The real competitor is not Copilot -- it is **an engineer who has been at the company for 3 years and knows the codebase by heart.** HR needs to get a new hire to that level of understanding in weeks, not years.

---

## 6. The Trust Problem

### Why engineers do not trust AI code answers:

1. **Hallucination trauma.** Every engineer has seen ChatGPT confidently describe a function that does not exist. Once burned, twice shy.
2. **No source attribution.** If the answer says "processPayment calls validateCard," the engineer wants to see the actual line of code. Not a summary -- the code.
3. **Stale index.** If the codebase changed yesterday but the index was built last week, every answer is potentially wrong. Engineers know this.
4. **Black box reasoning.** "The AI said so" is not an acceptable justification in a code review.

### How HR is already better than generic AI (but does not advertise it):

- **Every answer is grounded in tool calls.** The CoT display shows exactly which functions were looked up. This is a trust differentiator -- but it is buried in collapsible Steps that most users do not expand.
- **Function bodies are real code.** `get_function_body` returns actual source, not LLM-generated approximations.
- **Search results show module paths and symbol IDs.** These are verifiable -- the engineer can go look at the file.

### What would build trust:

1. **Clickable source links.** Every function name in the answer should be a hyperlink to the actual source file (GitHub URL or VS Code deeplink). Not "see AutoRefundService.hs" -- a direct link to line 47.

2. **Confidence indicators.** "I found this function and read its source code [HIGH CONFIDENCE]" vs "I inferred this from module names but did not read the implementation [LOW CONFIDENCE]."

3. **"Verify this" button.** One click opens the relevant source files in a new tab so the engineer can spot-check.

4. **Freshness badge.** "Index built from commit `abc1234` (2 hours ago)" on every answer. If the index is > 24 hours old, show a warning.

5. **Diff against source.** If the engineer has the repo cloned, let them run `hrcode verify` to check that the indexed version matches their local checkout.

6. **Wrong answer reporting.** A thumbs-down button that logs the query, the answer, and the actual correct answer. Use this to build a regression test suite. Chainlit has a feedback table (`feedbacks`) but it only captures value/comment -- no structured "what was wrong" data.

7. **Show the negative results too.** "I searched for X but found nothing" is more trustworthy than silently skipping failed searches. The logs show `"status": "empty"` entries but these are not surfaced to the user.

---

## 7. Metrics That Matter

### Adoption metrics (are people using it?):

| Metric | How to measure | Target |
|--------|---------------|--------|
| **Daily Active Users (DAU)** | Unique `user_id` per day in `retrieval_log.jsonl` | 50%+ of engineering team |
| **Queries per user per day** | Count of conversation-type log entries per user | > 3 (indicates habitual use) |
| **Retention (Week 1 to Week 4)** | % of users who queried in week 1 and still query in week 4 | > 60% |
| **Session depth** | Average queries per session | > 2 (indicates follow-up questions, not drive-by) |
| **Feature distribution** | % of queries that use CLI vs Chat vs MCP-in-IDE | Track to see which surface is winning |

### Quality metrics (is it helping?):

| Metric | How to measure | Target |
|--------|---------------|--------|
| **Answer convergence rate** | % of queries where `converged: true` in logs | > 90% |
| **Tool call efficiency** | Average `useful` / `total_calls` ratio | > 70% |
| **Empty result rate** | % of tool calls with `status: "empty"` | < 15% |
| **Feedback score** | Average rating from thumbs up/down | > 4.0/5.0 |
| **Time to first useful token** | `ttft_ms` from logs | < 5 seconds |

### Impact metrics (is it making the team faster?):

| Metric | How to measure | Baseline needed |
|--------|---------------|-----------------|
| **Time to understanding** | Survey: "How long did it take you to understand [X concept]?" Compare HR users vs non-users. | Requires control group. |
| **Onboarding velocity** | Days until first meaningful PR for new hires who use HR vs those who do not. | Track by cohort. |
| **PR review turnaround** | Time from PR opened to first substantive review comment. Does HR integration reduce it? | Measure before/after PR analyzer deployment. |
| **Oncall MTTR** | Mean time to resolve for incidents where HR was used vs not. | Tag incidents in PagerDuty/Jira. |
| **Code review quality** | Number of post-merge bugs in PRs reviewed with HR blast radius vs without. | Requires 3+ months of data. |
| **Repeat question rate** | Same question asked by different engineers in a month. If HR had an FAQ, these would be self-serve. | Mine query logs for semantic duplicates. |

### The metric I would start with:

**"Did the engineer's next action succeed?"** After using HR, did they:
- Submit a PR that passed CI on first try?
- Resolve an incident faster than the team average?
- Ask a follow-up question (engaged) or never come back (disappointed)?

This requires instrumenting the workflow beyond HR itself, but it is the only metric that proves value to leadership.

---

## 8. The Killer Feature I Would Ship Tomorrow

### PR Blast Radius Bot

**One sentence:** A GitHub Action that automatically posts a structured comment on every PR showing cross-service impact, co-change warnings, and high-risk function modifications.

**Why this doubles DAU overnight:**

1. **Zero adoption friction.** Engineers do not need to sign up, open a browser, or change their workflow. The bot comes to them.
2. **Visible to the entire team.** Every PR reviewer sees the comment. Curiosity drives them to the chat UI. "Oh, that blast radius tool is interesting -- what else can it do?"
3. **Immediate, concrete value.** "This PR modifies `shouldAutoRefundTransaction` which has 14 callers across 3 services" is information that would take 20 minutes to gather manually. The bot delivers it in seconds.
4. **Creates trust through repetition.** After seeing accurate blast radius comments on 50 PRs, engineers start trusting the underlying system. Trust transfers from the bot to the chat UI.
5. **Generates content for the chat.** Engineers see the bot comment and think "I want to know more about that dependency." They open the chat UI and ask a follow-up. The bot is a lead-gen machine for the chat product.

**What the PR comment looks like:**

```markdown
## Blast Radius Analysis

### Files Changed: 3 | Services Affected: 2 | Risk: MEDIUM

#### Direct Impact
- `Product.OLTP.Services.AutoRefundService.shouldAutoRefundTransaction`
  - **14 callers** across euler-api-txns, euler-api-gateway
  - Last modified: 12 days ago (PR #847)

#### Co-Change Warning
- Historically, changes to `AutoRefundService` co-occur with changes to
  `RefundScheduler` (87% of the time). This PR does not include `RefundScheduler`.
  Consider reviewing if this is intentional.

#### Cross-Service Boundaries
- This change in euler-api-txns may affect euler-api-gateway via:
  `Types.Communication.OLTP.Refund` (shared type)

---
Powered by HyperRetrieval | [Ask a follow-up question](https://hr.internal.juspay.net)
```

**Implementation effort:** LOW. `pr_analyzer.py` already exists. The co-change index has 111,005 module pairs. The import graph has 42,467 edges. Wire it into a GitHub Action, format the output as markdown, post via GitHub API. Two-week sprint, maximum.

**This is the feature that turns HyperRetrieval from "a tool some people use" into "infrastructure the team depends on."**

---

## Summary: What I Would Do in the Next 90 Days

| Week | Action | Expected Outcome |
|------|--------|-----------------|
| 1-2 | Ship PR Blast Radius Bot (GitHub Action) | Every PR gets automated impact analysis |
| 3-4 | Add browser notifications + progress indicators to chat | Reduce tab-away abandonment by 50% |
| 5-6 | Add clickable source links (GitHub URLs) to every function reference | Trust score improvement |
| 7-8 | Build VS Code CodeLens extension (callers/callees/blast radius) | Engineers use HR without leaving IDE |
| 9-10 | Add `get_recent_changes` and `get_owner` tools | Close the two biggest query gaps |
| 11-12 | Add index freshness indicator + staleness warnings | Eliminate "is this current?" doubt |

The product is solid at its core. The index quality is real. The ReAct loop works. The starters and onboarding are thoughtful. But it is trapped in a browser tab that engineers have to remember to visit. The path to indispensability runs through automation (PR bot), integration (VS Code), and trust (source links, freshness, confidence scores).

Stop waiting for engineers to come to you. Go to where they already are.
