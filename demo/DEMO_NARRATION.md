# HyperRetrieval Demo: Pre-Commit Intelligence

**5-minute walkthrough for engineers and VPs of Engineering.**

## What you're seeing

A developer is about to merge a payment service change. Before they commit, HyperRetrieval runs three automated checks — things that would normally only be caught in code review, or worse, in production.

## Run it yourself

```bash
git clone https://github.com/Amitshukla2308/MindmapAgent
cd MindmapAgent/demo

# Point at your running HyperRetrieval MCP server
# (default: port 8002, set LLM_API_KEY for alignment check)
LLM_API_KEY=<your-key> LLM_BASE_URL=<llm-base> python3 full_demo.py
```

---

## Scenario 1 — Safe refactor: PASS

```
check_my_changes(["serve/retrieval_engine.py", "serve/mcp_server.py"])

## Guardian Check: PASS
Risk Score: 22/100 (LOW)
Blast Radius: 20 | Coverage Gap: 0 | Reviewer Risk: 50

Changed modules: 4 | Affected services: 2 | PR completeness: 100%
Your changes look complete. Safe to commit.
```

**What this means:** Changing the core retrieval engine touches 4 modules across 2 services, but no co-change neighbors are missing and the blast radius is contained. The engineer can commit with confidence.

---

## Scenario 2 — New payment handler: WARN

```
check_my_changes(["/path/to/payment_handler.py"])

## Guardian Check: WARN
Risk Score: 10/100 (LOW)
Guard: 1 warning — error-swallowed

### Guard Findings (3 total, 1 CRITICAL)
🔴 CRITICAL  Line 24: missing-idempotency-key
             Payment API call without idempotency key.
             Retries may cause duplicate charges.
🟡 WARNING   Line  8: float-for-money
             Monetary variable uses float. Use Decimal or integer cents.
🟡 WARNING   Line 39: error-swallowed
             Exception caught and silently ignored.
```

**What this means:** The code looks innocent but contains three payment-specific anti-patterns that have caused real-world incidents:
- Missing idempotency key → duplicate charges under network retries
- Float arithmetic on money → rounding errors that compound over millions of transactions
- Silent exception swallowing → failed payments that look successful

These patterns are invisible to general linters (mypy, ruff). HyperRetrieval's fintech Guard catches them because it understands payment domain semantics.

---

## Scenario 3 — Comment-code alignment: MISALIGNED

```
check_alignment("/path/to/payment_handler.py")

[CRITICAL] Line 15: llm-comment-alignment
           Comment-code misaligned: disabled
           Comment says "validates limits (max 10000)"
           Code: return True

[CRITICAL] Line 21: llm-comment-alignment
           Comment-code misaligned
           Comment says "retries until success"
           Code: single HTTP call, no retry loop
```

**What this means:** Two functions have comments that describe behavior the code doesn't implement:
1. `validate_payment_amount` — documented as enforcing a $10,000 limit, but always returns `True`. The validation was disabled "temporarily" and the comment was never updated.
2. `charge_card` — documented as retrying until success, but makes one HTTP call and returns.

An LLM assistant reading these comments would confidently write callers that assume these contracts hold. HyperRetrieval catches the lie before it propagates.

---

## The combined verdict

| Layer | What it checks | Catches |
|---|---|---|
| Blast radius | Import graph + co-change history | Which services you're really touching |
| Guard patterns | AST + regex on payment semantics | Float money, missing idempotency, unbounded retry |
| LLM alignment | Comment vs code via LLM | Misleading docs, disabled validations, stale comments |

**All three run in < 30 seconds, before a single line is pushed.**

---

## For VPs of Engineering

The cost of the bugs above:
- Missing idempotency key: one network hiccup → duplicate charge → angry customer → dispute → chargeback fee + reputation damage
- Float money: tiny rounding errors per transaction × millions of transactions = real money missing from reconciliation
- Disabled validation with honest comment: next engineer reads "validates limits" and trusts it; security boundary quietly gone

HyperRetrieval surfaces these in the pre-commit hook. Not in the post-mortem.
