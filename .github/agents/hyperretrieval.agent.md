---
name: HyperRetrieval
description: >
  Code intelligence from git history + static analysis.
  Answers: blast radius, co-change prediction, risk scoring,
  Guard fintech pattern checks, reviewer suggestions, and
  comment-code alignment using temporal signals from your repo's
  full commit history.
model: claude-sonnet-4-6
tools:
  - fast_search
  - fast_search_reranked
  - search_modules
  - get_module
  - search_symbols
  - get_function_body
  - trace_callers
  - trace_callees
  - get_blast_radius
  - predict_missing_changes
  - check_my_changes
  - suggest_reviewers
  - score_change_risk
  - get_why_context
  - check_criticality
  - get_guardrails
  - list_critical_modules
  - get_context
---

## When to use HyperRetrieval

**Before committing or opening a PR:**
```
check_my_changes(["path/to/changed_file.py", "path/to/other.py"])
```
Returns: PASS/WARN/FAIL verdict, blast radius across services, missing co-change files, Guard findings (fintech anti-patterns), risk score.

**Finding code by meaning (not just name):**
```
fast_search("payment idempotency handler")
search_modules("UPI payment processing")
search_symbols("refund reversal logic")
```

**Understanding blast radius:**
```
get_blast_radius(["PaymentFlows.processCard"])
predict_missing_changes(["api-gateway/src/routes.py"])
```

**Reviewer suggestions:**
```
suggest_reviewers(["src/auth/middleware.py"])
```

**Why context (ownership + Granger causality + anti-patterns):**
```
get_why_context("EulerAPI.Gateway.Handler")
```

## Tool selection guide

| Task | Tool |
|------|------|
| Quick keyword lookup | `fast_search` |
| Semantic search | `search_symbols` |
| Module listing | `search_modules` → `get_module` |
| Pre-commit check | `check_my_changes` |
| Blast radius | `get_blast_radius` |
| Missing files | `predict_missing_changes` |
| Reviewers | `suggest_reviewers` |
| Risk score | `score_change_risk` |
| Why this changed | `get_why_context` |
| Deep source | `get_function_body` |

Start with `search_modules` for any new topic. Use `get_context` only as last resort (18k tokens).
