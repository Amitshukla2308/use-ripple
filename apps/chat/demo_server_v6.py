"""
HyperRetrieval — Agentic codebase intelligence (Chainlit UI)

Clean ReAct architecture:
  - Single system prompt (no routing, no persona selection)
  - LLM starts with the user query and decides what to look up
  - Tool calls rendered as Chainlit steps
  - Final answer streamed when LLM stops calling tools

No pre-retrieval, no fast_route, no context pre-loading.
"""
import asyncio, json, os, pathlib, sys, time, threading, uuid
import chainlit as cl

_REPO = pathlib.Path(__file__).parent.parent.parent   # apps/chat → apps → repo root
sys.path.insert(0, str(_REPO))                        # for tools.py
sys.path.insert(0, str(_REPO / "serve"))              # for retrieval_engine.py
import retrieval_engine as RE
import tools as T

# ── Config ────────────────────────────────────────────────────────────────────
_HERE          = pathlib.Path(__file__).resolve().parent
ARTIFACT_DIR   = pathlib.Path(os.environ.get(
    "ARTIFACT_DIR",
    str(_HERE / "demo_artifact" if (_HERE / "demo_artifact").exists() else _HERE)
))
LLM_API_KEY    = os.environ.get("LLM_API_KEY",  "")
LLM_BASE_URL   = os.environ.get("LLM_BASE_URL", "")
LLM_MODEL      = os.environ.get("LLM_MODEL",    "reasoning-large-model")
MAX_HISTORY    = 6
MAX_TOOL_CALLS = 50   # hard ceiling — LLM self-terminates; this is runaway protection only
MAX_SAME_CALL  = 2    # break if identical (tool, args) repeats this many times
RETRIEVAL_LOG  = pathlib.Path(os.environ.get("OUTPUT_DIR", "/tmp")) / "retrieval_log.jsonl"

llm_client       = None
async_llm_client = None
_load_all_done   = False
_load_lock       = threading.Lock()


# ════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT  — tells the LLM who it is, what it can do, and how to think
# ════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """\
You are a Senior Juspay Platform Engineer — one of the few people who knows this entire \
payment platform codebase deeply. You do not guess. You read actual source code and reason \
from facts. You own this codebase. When asked about any flow, module, or function, you \
investigate until you have read the actual implementation, then give a precise, confident answer.

## Your Codebase

114,534 indexed symbols across 12 microservices (Haskell primary, some Rust/JS/Python/Groovy):

| Service | Symbols | Role |
|---|---|---|
| euler-api-gateway | 39,806 | HTTP entry point, routing, auth, rate-limiting, all payment gateway connectors |
| euler-api-txns | 30,673 | Transaction lifecycle: authorize, capture, refund, mandate, EMI, tokenization, 3DS |
| UCS | 7,787 | Universal Connector Service — pluggable third-party payment gateway integration |
| euler-db | 5,610 | OLTP database layer — all persistent models and DB operations |
| euler-api-order | 3,652 | Order creation, session management, payment method selection |
| graphh | 2,377 | Graph analytics, reporting pipeline |
| euler-api-pre-txn | 2,364 | Pre-transaction: eligibility checks, routing rules, payment method validation |
| euler-api-customer | 1,231 | Customer profiles, saved cards, wallet |
| basilisk-v3 | 335 | Fraud and risk scoring |
| euler-drainer | 233 | Async job processing, webhook dispatch |
| token_issuer_portal_backend | 121 | Card tokenization issuer portal |
| haskell-sequelize | 55 | ORM layer for Haskell DB models |

**Primary flow:** euler-api-gateway → euler-api-txns → UCS → euler-db

**Module naming:** Dot-notation without service prefix. \
Examples: `Euler.API.Gateway.Handlers.UPI`, `PaymentFlows.Authorize`, `Types.Transaction`

**Domain glossary:** UPI (Unified Payments Interface), PIX (Brazilian instant payment), \
EMI (Equated Monthly Instalment), mandate (recurring payment authorization), \
UCS (Universal Connector Service), CVV (card verification value), PAN (card number), \
OTP (one-time password), KYC (know your customer), BNPL (buy-now-pay-later), \
NFC (contactless payment), QR (QR-code payment), 3DS (3D Secure authentication). \
IMPORTANT: split payment ≠ split settlement — always disambiguate before investigating.

## How the index works (internal guidance — do not repeat this to users)

Use this to interpret tool results correctly. Never mention indexing, embeddings, BM25, \
Leiden, or pipeline details in your answers — answer as a senior engineer, not a system describer.

- **search_symbols** fuses two signals: semantic vector similarity and BM25 keyword matching. \
When results are thin on a semantic query, also try the exact identifier name — BM25 will \
rank exact matches highly even if the embedding distance is mediocre.

- **trace_callers / trace_callees** only covers in-process function calls within a service. \
Cross-service communication happens over HTTP and is NOT in the call graph. If tracing a flow \
that crosses service boundaries, use search_modules on the downstream service to pick up the \
thread — do not assume trace_callees will cross service lines.

- **Clusters** are Leiden communities: groups of modules that are both structurally coupled \
(import each other) and semantically similar. A cluster boundary means the two sides are \
loosely coupled. When a user asks why certain modules are grouped together, the answer is \
coupling and similarity — not manual categorisation.

- **Co-change data** (used by get_blast_radius) comes from git commit history, not static \
analysis. It reflects what has historically changed together, which often reveals runtime \
coupling that the import graph misses — especially across services.

- **Symbol coverage** is at function/type level, not file level. If a search returns no \
results for a broad concept, narrow to a specific function name or try get_module on a \
likely namespace rather than assuming the code doesn't exist.

## Tools

**search_modules(query)** — START HERE for every new topic. Returns module namespaces. \
Use functional domain language. If first results are sparse, try 2–3 alternate phrasings. \
Good queries: "UPI collect flow", "mandate debit registration", "3DS authentication", "gateway routing"

**get_module(module_name)** — List all symbols in a module namespace. Call this after \
search_modules to see the full surface area before choosing what to read. Never skip this. \
Good inputs: "Euler.API.Gateway.Gateway.UPI", "PaymentFlows", "Types.Transaction"

**search_symbols(query)** — RRF-fused semantic + BM25 search across 114k symbols. \
Use when you know what a function does but not its name. Rephrase and retry if results thin. \
Good queries: "card tokenization initiation", "emandate debit execution", "refund status update"

**get_function_body(fn_id)** — Read actual source code by fully-qualified ID. \
This is your primary tool for confirming implementation. \
ALWAYS batch multiple independent reads in a single turn (3–5 calls at once). \
Good inputs: "PaymentFlows.getAllPaymentFlowsForTxn", "Euler.API.Gateway.Handlers.UPI.collectRequest"

**trace_callers(fn_id)** — Who calls this function (upstream). Use to find entry points \
or assess who is affected by a change.

**trace_callees(fn_id)** — What this function calls (downstream). Use to trace a flow \
forward step by step until you reach the actual implementation.

**get_blast_radius(files_or_modules)** — Import graph + co-change history. \
Use for change impact analysis before proposing any modification.

**get_context(query)** — LAST RESORT ONLY. Builds a full cross-service context block and \
returns part 1 of 3. Only call after search_symbols + get_function_body have failed on 3+ \
different query phrasings. Part 1 alone covers roughly a third of the full context — read it \
and assess before fetching more. It costs ~10x the tokens of a targeted search, so the bar \
for using it is: "I have searched multiple ways, read several function bodies, and still \
cannot locate the implementation."

**get_context_continue(token, part)** — Fetch part 2 or 3 of a previous get_context result. \
Use the token returned by get_context. Only call if part 1 was genuinely insufficient — \
stop as soon as you have found what you need.

## Investigation Protocol

**1. Orient — search_modules**
Every investigation starts here. Use functional language: "UPI collect", "mandate registration", \
"payment routing". If sparse, rephrase (try 2–3 variants). Never skip this step.

**2. Survey — get_module**
Once you have a module, call get_module to see all symbols. This prevents missing key \
functions in the same namespace.

**3. Read — get_function_body (in parallel)**
Read actual code — not summaries. Batch all independent reads in one turn (3–5 calls). \
If a function delegates to others you need, call trace_callees and read those next.

**4. Trace — trace_callers / trace_callees**
Follow the flow in both directions until you can describe the complete path end-to-end.

**4b. Field / column queries — mandatory deeper protocol**
When the query asks about a field, column, or data attribute (e.g. "where is accountInfo used?", \
"which flows read txnCardInfo.paymentMethod?", "where is settled_by stored?"):

- **Step A — Find the type**: Use `get_type_definition` or `search_symbols` for the field name \
to find the record/type that owns it.
- **Step B — Search the field name directly**: Call `search_symbols` with just the bare field \
name (e.g. "accountInfo", "settled_by") — this finds ALL functions that reference it, not just \
the owning module.
- **Step C — Cross-service sweep**: Explicitly search for the field in EVERY service. Fields \
on shared types (customer accounts, transactions, orders) are consumed across multiple services. \
Do NOT stop at the primary owning service. Run `search_modules` + `search_symbols` in each \
service that could plausibly consume this data.
- **Step D — Trace callers of readers**: Once you find functions that READ the field, call \
`trace_callers` on them to find the full upstream call chain — which API, which flow, which \
trigger. A field usage question is not answered until you can name the API endpoint and flow \
for each usage site.
- **Step E — Distinguish read vs write**: Explicitly separate: (1) where is the field WRITTEN \
(creation, update, sync), (2) where is it READ for business logic, (3) where is it exposed in \
API responses. The answer must cover all three.

A field-usage answer that only covers the primary CRUD service is incomplete. \
You must trace downstream consumers across ALL services before synthesizing.

**5. Synthesize**
Answer only from code you have actually read. Reference exact function names and module paths. \
Never extrapolate beyond what the source code shows.

## Convergence Rules

- **Match depth to task type**: For synthesis tasks (write a document, explain a concept, \
create a presentation, summarise a topic) stop after 10–12 tool calls and synthesize. \
You have enough material. For deep debugging or tracing an unknown flow, go deeper.
- **Never answer from search summaries or module names alone** — read at least 2–3 function \
bodies before synthesizing any answer
- **Parallel reads**: Send all independent get_function_body calls in a single turn — \
never read functions one by one when they can be batched
- **Rephrase before giving up**: If a query returns thin results, try 2 alternate phrasings \
before concluding the code doesn't exist
- **Chase the flow**: If a function delegates to another, read that next. Follow until you \
reach the actual implementation, not just a dispatcher or type signature
- **Cross-service**: When a flow crosses services, call search_modules in each service — \
gateway and txns often share a concept under different module names
- **Never repeat a failed query verbatim** — rephrase it or switch tools
- **Every code block must start with a `-- From` comment**: The first line of every \
code block must be `-- From FullyQualified.Function.Id` (or `// From` for JS/Groovy). \
This is required for source grounding — every code block is automatically replaced with \
the exact source from the index. Do NOT retype code from memory; the system overwrites \
your version with the real source anyway, so the comment is what matters.
- **ALL identifiers must be in backticks — no exceptions**: Every function name, constant, \
type, field, or module path you mention — whether in a code block or plain prose — MUST be \
wrapped in backticks. This applies to `ALL_CAPS_CONSTANTS`, `CamelCaseTypes`, \
`dot.notation.paths`, and `fieldNames`. Writing an identifier outside backticks is not allowed.
- **Zero tolerance for invented identifiers**: Every identifier you put in backticks MUST \
appear verbatim in a tool result from this session. Do NOT guess names based on patterns \
(seeing `MAX_X_COUNT` does not mean `MAX_Y_COUNT` exists). Do NOT cite a constant because \
it "should exist" — fetch it first or omit it. If you haven't retrieved the exact name write: \
*"a configuration constant (exact name not retrieved)"*. \
Every identifier in your response — in prose AND in code — is automatically fact-checked \
against the full codebase index. Fabricated identifiers are flagged to the user. \
Being caught inventing names is worse than admitting you don't have the data.

## Between Tool Rounds

Before each new batch of tool calls, emit one sentence:
- What you found in the last round
- What you are looking for next

Example: *"Found the UPI collect handler in euler-api-gateway. Now reading the collect \
function body and tracing its callees into euler-api-txns."*

## Investigation Examples

**How does a UPI collect payment work end-to-end?**
Start by searching modules for "UPI collect" to find the gateway namespace. Call get_module on \
the result to see all symbols, then read the collect request handler body. While reading, \
trace its callees to follow the flow into euler-api-txns. Read the txns-side handler next. \
By the end you should be able to describe the complete path: gateway receives → validates → \
dispatches → txns processes → UCS calls bank → db persists.

**Where is the refund flow implemented?**
Search modules for "refund" — expect hits in both gateway and txns. Get the module listing \
for the top result to identify the core handler. Read the handler body and trace its callees \
into the db layer. Answer with the full function path and data flow, not just the module name.

## Response Format

Structure every final answer in two parts, separated by a horizontal rule:

**Part 1 — TL;DR** (3–5 sentences)
Lead with what the answer is. Name the key functions and the flow in plain English. \
A reader skimming this should understand the answer without reading further.

---

**Part 2 — Detail**
Walk through the full investigation in plain English first, then support it with code where useful. \
For every function, type, or data structure you reference, explain in one or two sentences what it \
does in business terms — not just its name or fields. A non-technical product manager reading this \
should be able to follow the narrative even if they skip the code blocks.

Structure the detail as a narrative flow, not a list of code dumps. Example of what NOT to do:
  ❌ Show a Haskell record with field names and comments, no explanation.
Example of what to do:
  ✓ "When a transaction is eligible for retry, the system creates an InternalRetryWorkflowTxn \
record that tracks the retry attempt number, links back to the original transaction, and carries \
flags for special retry paths like OnUs (same-bank) retries. The parentTxnDetail field preserves \
the full original transaction so the retry can replay it without re-fetching from the database."

If you include a code block, always follow it with a plain-English explanation of what it means \
and why it matters in the context of the question.

Close the detail section with a `> **Explore further:**` block containing 2–3 concrete \
follow-up questions referencing actual function names or module paths you discovered.

## MANDATORY: Humor Line
BEFORE every set of tool calls, the absolute first line of your message MUST be a [FUN:] tag.
No exceptions. Format: [FUN: one line here]
Rules: specific to what you are about to look up, funny to a developer, max one sentence, no quotes inside.
Bad: [FUN: Let me search for information.]
Good: [FUN: 14 callers. Nothing screams legacy like a function everyone uses but nobody owns.]
Good: [FUN: euler-api-gateway will definitely know. And by know I mean delegate to three other services.]
Good: [FUN: The co-change index shows these two modules changed together 47 times. Basically roommates.]
Good: [FUN: Entering the Haskell module. If I'm not back in 10 types, avenge me.]
"""


# ════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ════════════════════════════════════════════════════════════════════════════

def load_all():
    global llm_client, async_llm_client, _load_all_done
    if _load_all_done:
        return
    with _load_lock:
        if _load_all_done:   # re-check inside lock — second thread may have finished
            return
        from openai import OpenAI, AsyncOpenAI
        RE.initialize(ARTIFACT_DIR)
        llm_client       = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
        async_llm_client = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
        _load_all_done   = True


# ════════════════════════════════════════════════════════════════════════════
# TOOL STEP RENDERING
# ════════════════════════════════════════════════════════════════════════════

_TOOL_LABELS = {
    "get_function_body":  ("📖", "Reading"),
    "trace_callers":      ("⬆",  "Callers of"),
    "trace_callees":      ("⬇",  "Calls from"),
    "search_symbols":     ("🔍", "Searching"),
    "search_modules":     ("📦", "Modules"),
    "get_module":         ("📂", "Module"),
    "get_blast_radius":   ("💥", "Blast radius"),
    "get_log_patterns":   ("📋", "Log patterns"),
    "get_context":        ("📚", "Context"),
}

def _step_name(fn_name: str, args: dict) -> str:
    icon, verb = _TOOL_LABELS.get(fn_name, ("⚙", fn_name))
    subject = (args.get("fn_id") or args.get("query") or
               args.get("module_name") or args.get("files_or_modules") or "")
    parts = [p for p in str(subject).replace("/", ".").split(".")
             if p and p not in ("hs", "py", "rs", "js", "ts")]
    short = parts[-1] if parts else str(subject)
    return f"{icon} {verb} · {short}" if short else f"{icon} {verb}"


import re as _re, random as _random

_THINK_FALLBACKS = [
    "☕ Hold on, interrogating 94,000 functions…",
    "🦀 Lost in the type signatures. Send chai.",
    "🌀 Somewhere in 40k import edges. Do not panic.",
    "🏦 Asking euler-api-gateway. It will delegate. It always delegates.",
    "📦 Opening a Haskell module. Helmet recommended.",
    "🎲 Rolling for initiative against the call graph.",
    "🕵️ The co-change index is giving me the side-eye.",
    "🔁 Not looping. Definitely not looping.",
    "🧱 Six microservices walked into a bar. None of them owned the bug.",
    "💸 Following the money. There are many hops. Many.",
]

def _think_msg(content: str | None) -> str:
    """Extract [FUN: ...] from LLM content; fall back to a short generic."""
    if content:
        m = _re.search(r'\[FUN:\s*(.+?)\]', content, _re.DOTALL)
        if m:
            return m.group(1).strip()[:160]
    return _random.choice(_THINK_FALLBACKS)


def _log_step(session_id: str, query: str, call_n: int, entry: dict) -> None:
    """Flush a single tool-call entry to the log immediately after execution."""
    try:
        with open(RETRIEVAL_LOG, "a") as lf:
            lf.write(json.dumps({
                "ts": time.time(), "session_id": session_id,
                "query": query, "call_n": call_n, "type": "step",
                **entry,
            }) + "\n")
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════
# CHAINLIT HANDLERS
# ════════════════════════════════════════════════════════════════════════════

@cl.set_chat_profiles
async def set_chat_profiles():
    return [
        cl.ChatProfile(
            name="HyperRetrieval",
            markdown_description="Codebase intelligence — ask anything about your codebase.",
            starters=[
                cl.Starter(label="Card payment flow end-to-end",
                           message="Walk me through the complete card payment flow from order creation to gateway response."),
                cl.Starter(label="How does UPI Collect work?",
                           message="Explain the UPI Collect flow — which services are involved and what happens at each step?"),
                cl.Starter(label="Gateways across services",
                           message="What is the difference between gateways written in api-txns, api-gateway and UCS?"),
                cl.Starter(label="What does UCS do?",
                           message="What is UCS and how does it relate to euler-api-gateway? When is each used?"),
                cl.Starter(label="Payment stuck in PENDING",
                           message="What are the failure scenarios that can leave a payment permanently stuck in PENDING state?"),
                cl.Starter(label="Where is card data handled?",
                           message="Where is cardholder data (PAN, CVV) handled in the codebase? List every location where it is stored, logged, or transmitted."),
            ],
        ),
    ]


@cl.on_chat_start
async def on_start():
    cl.user_session.set("history", [])
    cl.user_session.set("session_id", uuid.uuid4().hex)
    # Kick off loading in the background but send NO message — welcome screen
    # (centered input + starter cards) must stay visible until the user acts.
    # Sending any message here immediately destroys the welcome layout.
    if not _load_all_done:
        asyncio.create_task(asyncio.to_thread(load_all))


# ════════════════════════════════════════════════════════════════════════════
# AGENT LOOP — extracted so action callbacks can resume it
# ════════════════════════════════════════════════════════════════════════════

def _build_research_brief(tool_log: list) -> str:
    """
    Compact summary of everything retrieved this session.
    Injected as the last message before synthesis so Kimi has exact identifiers
    and code snippets in its immediate context — prevents transcription errors.
    Capped at ~8k chars to stay token-efficient.
    """
    bodies, searches = [], []
    for entry in tool_log:
        if entry.get("status") != "useful":
            continue
        tool = entry.get("tool", "")
        args = entry.get("args", {})
        if tool == "get_function_body":
            fn_id  = args.get("fn_id", "")
            actual = RE.body_store.get(fn_id, "") if fn_id and hasattr(RE, "body_store") else ""
            snippet = "\n".join(l for l in actual.splitlines() if l.strip())[:500] if actual else entry.get("preview", "")[:300]
            bodies.append(f"**{fn_id}**\n```\n{snippet}\n```")
        elif tool in ("search_modules", "search_symbols", "get_module",
                      "trace_callers", "trace_callees", "get_type_definition"):
            key = args.get("query") or args.get("module_name") or args.get("fn_id") or ""
            searches.append(f"- `{tool}({key})` → {entry.get('preview', '')[:200]}")

    sections = []
    if bodies:
        sections.append("### Function / Type Bodies (copy identifiers and field names VERBATIM)\n\n" + "\n\n".join(bodies))
    if searches:
        sections.append("### Search & Module Results\n\n" + "\n".join(searches))

    brief = "\n\n---\n\n".join(sections)
    # Hard cap — trim from the middle to keep newest entries intact
    if len(brief) > 8000:
        brief = brief[:3500] + "\n\n… [trimmed] …\n\n" + brief[-4000:]
    return brief


async def _stream_final_answer(messages: list, query: str, tool_log: list,
                               converged: bool = True, t_query: float = None) -> None:
    """Stream the LLM's final answer, update session history, log to disk."""
    history = cl.user_session.get("history", [])

    t_start      = time.time()          # synthesis start (for t/s)
    t_ttft_base  = t_query or t_start  # TTFT base: query submission if available
    t_first_tok  = None
    in_tokens    = 0
    out_tokens   = 0

    stream = await async_llm_client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=65536,
        stream=True,
        stream_options={"include_usage": True},
    )
    response_msg = cl.Message(content="")
    await response_msg.send()
    full_response = ""
    async for chunk in stream:
        # Final usage chunk (stream_options=include_usage)
        if hasattr(chunk, "usage") and chunk.usage:
            in_tokens  = chunk.usage.prompt_tokens or 0
            out_tokens = chunk.usage.completion_tokens or 0
        if not chunk.choices:
            continue
        token = chunk.choices[0].delta.content
        if token:
            if t_first_tok is None:
                t_first_tok = time.time()
            full_response += token
            await response_msg.stream_token(token)
    # Strip any [FUN: ...] that leaked into the final answer
    import re as _re2
    if '[FUN:' in full_response:
        full_response = _re2.sub(r'\[FUN:[^\]]*\]\s*', '', full_response).strip()

    # ── Ground code blocks: replace LLM-reconstructed code with exact source ──
    # Kimi sometimes mis-transcribes variable names when writing from memory.
    # Any code block containing "-- From X.Y.Z" or "From X.Y.Z" gets its
    # content swapped with the actual body_store entry — deterministic, zero tokens.
    _grounded: list[str] = []

    def _replace_with_actual(m: "_re2.Match") -> str:
        lang, block = m.group(1) or "", m.group(2)
        fn_m = _re2.search(
            r'(?:--\s*From|From|{-\s*From)\s+([\w][\w.]+[\w])', block)
        if not fn_m:
            return m.group(0)
        fn_id  = fn_m.group(1)
        actual = (RE.body_store.get(fn_id) if hasattr(RE, "body_store") else None)
        if not actual:
            return m.group(0)
        _grounded.append(fn_id)
        return f"```{lang}\n{actual}\n```"

    full_response = _re2.sub(
        r'```(\w*)\n(.*?)```', _replace_with_actual, full_response, flags=_re2.DOTALL)

    response_msg.content = full_response
    await response_msg.update()

    if _grounded:
        await cl.Message(
            content=f"✅ **{len(_grounded)} code block(s) grounded** — replaced with exact source: "
                    + ", ".join(f"`{f}`" for f in _grounded),
            author="fact-check",
        ).send()

    # ── Post-response reference verification ─────────────────────────────────
    # Extract from: backtick spans, code blocks, AND plain text
    _code_spans  = _re2.findall(r'`([^`\n]{4,80})`', full_response)
    _code_blocks = _re2.findall(r'```[^\n]*\n(.*?)```', full_response, _re2.DOTALL)
    # Strip code blocks + backtick spans from plain text before scanning
    _plain_text  = _re2.sub(r'```.*?```', ' ', full_response, flags=_re2.DOTALL)
    _plain_text  = _re2.sub(r'`[^`]+`', ' ', _plain_text)

    _candidates: set[str] = set()
    for span in _code_spans:
        s = span.strip('`() ')
        if '.' in s and '/' not in s and ' ' not in s:
            _candidates.add(s)
        if _re2.match(r'^[A-Z][A-Z0-9_]{4,}$', s):
            _candidates.add(s)
    for blk in _code_blocks:
        for tok in _re2.findall(r'[A-Z][A-Z0-9_]{5,}', blk):
            _candidates.add(tok)
    # Plain text: ALL_CAPS_CONSTANTS and Dot.Notation.Paths
    for tok in _re2.findall(r'\b[A-Z][A-Z0-9_]{5,}\b', _plain_text):
        _candidates.add(tok)
    for tok in _re2.findall(r'\b[A-Z][A-Za-z0-9]+(?:\.[A-Z][A-Za-z0-9]+){2,}\b', _plain_text):
        _candidates.add(tok)

    # Build a fast lookup: graph nodes + body_store keys + body_store content
    # Content search: ALL_CAPS tokens are string literals in source; search body values
    _graph_nodes   = set(RE.G.nodes()) if hasattr(RE, 'G') and RE.G else set()
    _body_keys     = set(RE.body_store.keys()) if hasattr(RE, 'body_store') else set()
    # session retrieved content (tool previews from this conversation)
    _session_text  = " ".join(e.get("preview", "") for e in tool_log)

    def _exists(c: str) -> bool:
        if c in _graph_nodes or c in _body_keys:
            return True
        if any(c in n for n in _graph_nodes):          # partial node match
            return True
        if c in _session_text:                          # appeared in retrieved content
            return True
        # search body_store values (string literals inside source code)
        return any(c in v for v in RE.body_store.values()) if hasattr(RE, 'body_store') else False

    _unverified = sorted(c for c in _candidates if not _exists(c))

    if _unverified:
        await cl.Message(
            content=(
                "⚠️ **Unverified references** — cited but not found anywhere in the "
                "indexed codebase (not a node, not in any function body). "
                "These may be hallucinated:\n"
                + "\n".join(f"- `{u}`" for u in _unverified)
            ),
            author="fact-check",
        ).send()

    t_end    = time.time()
    ttft_s   = (t_first_tok - t_ttft_base) if t_first_tok else None
    gen_s    = (t_end - t_first_tok)   if t_first_tok else (t_end - t_start)
    # Fall back to rough char-based estimate if API didn't return usage
    if out_tokens == 0:
        out_tokens = max(1, len(full_response) // 4)
        in_tokens  = 0  # unknown
    tps = out_tokens / gen_s if gen_s > 0 else 0

    statuses     = [t["status"] for t in tool_log]
    tools_used   = len([t for t in tool_log if t.get("status") != "blocked_early"])
    tools_failed = statuses.count("error")

    ttft_str  = (f"{ttft_s*1000:.0f}ms" if ttft_s < 1 else f"{ttft_s:.1f}s") if ttft_s is not None else "—"
    tps_str   = f"{tps:.1f}"
    tok_str   = f"{in_tokens:,}+{out_tokens:,}" if in_tokens else f"~{out_tokens:,} out"

    await cl.Message(
        content=(
            f"`tok {tok_str}` · "
            f"`{tps_str} t/s` · "
            f"`TTFT {ttft_str}` · "
            f"`{tools_used} tools` · "
            f"`{tools_failed} failed`"
        ),
        author="perf",
    ).send()

    history.append((query, full_response[:8000]))
    cl.user_session.set("history", history[-MAX_HISTORY:])

    session_id = cl.user_session.get("session_id", "unknown")

    # ── Save response to disk (detached — runs after UI is already updated) ──
    def _save_response() -> None:
        try:
            out_dir = pathlib.Path(os.environ.get("OUTPUT_DIR", "/tmp")) / "responses"
            out_dir.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts":          t_end,
                "query":       query,
                "response":    full_response,
                "converged":   converged,
                "tools_used":  tools_used,
                "tools_failed": tools_failed,
                "in_tokens":   in_tokens,
                "out_tokens":  out_tokens,
                "grounded":    _grounded,
                "unverified":  _unverified,
            }
            path = out_dir / f"{session_id}.jsonl"
            with open(path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    asyncio.create_task(asyncio.to_thread(_save_response))

    try:
        with open(RETRIEVAL_LOG, "a") as lf:
            lf.write(json.dumps({
                "type":         "conversation",
                "ts":           t_end,
                "session_id":   session_id,
                "query":        query,
                "converged":    converged,
                "total_calls":  len(tool_log),
                "useful":       statuses.count("useful"),
                "empty":        statuses.count("empty"),
                "errors":       statuses.count("error"),
                "in_tokens":    in_tokens,
                "out_tokens":   out_tokens,
                "ttft_ms":      round(ttft_s * 1000) if ttft_s else None,
                "tps":          round(tps, 1),
                "tool_calls":   tool_log,
            }) + "\n")
    except Exception:
        pass


def _classify_result(result: str) -> str:
    """Classify a tool result as useful / empty / error."""
    if not result or not result.strip():
        return "empty"
    low = result.strip().lower()
    if low.startswith("error") or low.startswith("unknown tool") or "not found" in low[:80]:
        return "error"
    # Empty-result patterns from tools
    empty_signals = ("no results", "0 results", "no symbols", "no matches",
                     "no callers", "no callees", "no entries", "not in graph")
    if any(s in low[:120] for s in empty_signals):
        return "empty"
    return "useful"


async def _react_loop(messages: list, query: str, tool_log: list, t_query: float = None) -> bool:
    """
    Run one batch of the ReAct loop (up to MAX_TOOL_CALLS tool calls).
    - Returns True  → LLM finished naturally; final answer streamed.
    - Returns False → ceiling hit; state saved to session, action buttons shown.
    Caller should return immediately on False.
    """
    seen_calls: dict = {}
    tool_calls_count  = 0
    consecutive_empty = 0   # consecutive tool calls returning empty/error
    EMPTY_STREAK_LIMIT = 4  # inject pivot hint after this many consecutive empties
    CTX_MIN_PRIOR_CALLS = 5 # minimum tool calls before get_context is appropriate

    while True:
        _think = cl.Message(content=_random.choice(_THINK_FALLBACKS), author=" ")
        await _think.send()
        resp = await asyncio.to_thread(
            llm_client.chat.completions.create,
            model=LLM_MODEL,
            messages=messages,
            tools=T.AGENT_TOOLS,
            tool_choice="auto",
            temperature=0.15,
            max_tokens=16000,
        )
        assistant_msg = resp.choices[0].message

        # Update the transient message with the LLM's own first reasoning line
        _think.content = _think_msg(assistant_msg.content)
        await _think.update()

        # LLM finished — no more tool calls
        if not assistant_msg.tool_calls:
            await _think.remove()
            break

        # Show between-round reasoning (strip [FUN] line to avoid duplication)
        _reasoning = _re.sub(r'\[FUN:[^\]]*\]\s*', '',
                             assistant_msg.content or "").strip()
        if _reasoning:
            async with cl.Step(name="💭 Reasoning", type="run",
                               show_input=False) as thought:
                thought.output = _reasoning

        messages.append({
            "role": "assistant",
            "content": assistant_msg.content,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in assistant_msg.tool_calls
            ],
        })

        tool_results  = []
        loop_detected = False
        for tc in assistant_msg.tool_calls:
            fn_name  = tc.function.name
            args_raw = tc.function.arguments
            try:
                args = json.loads(args_raw)
            except Exception:
                args = {}

            call_key = (fn_name, args_raw)
            seen_calls[call_key] = seen_calls.get(call_key, 0) + 1
            if seen_calls[call_key] >= MAX_SAME_CALL:
                loop_detected = True

            # ── get_context early-use guard ──────────────────────────────────
            if fn_name == "get_context" and tool_calls_count < CTX_MIN_PRIOR_CALLS:
                tool_results.append({"role": "tool", "tool_call_id": tc.id,
                    "content": (f"[GUIDANCE] get_context was called after only "
                                f"{tool_calls_count} tool calls. This is too early — "
                                "try search_modules, get_module, and search_symbols with "
                                "at least 3 different phrasings first. "
                                "get_context is a last resort after targeted searches fail.")})
                tool_log.append({"tool": fn_name, "args": args,
                                 "status": "blocked_early", "preview": "", "len": 0})
                continue

            tool_calls_count += 1
            async with cl.Step(name=_step_name(fn_name, args), type="tool",
                               show_input=False) as step:
                dispatcher = T.TOOL_DISPATCH.get(fn_name)
                try:
                    result = await asyncio.to_thread(dispatcher, args) if dispatcher \
                             else f"Unknown tool: {fn_name}"
                except Exception as exc:
                    result = f"Tool error ({fn_name}): {exc}"
                step.output = result  # full response in dropdown

            status = _classify_result(result)
            entry = {
                "tool":    fn_name,
                "args":    args,
                "status":  status,
                "result":  result,       # full result logged
                "preview": result[:200] if result else "",
                "len":     len(result) if result else 0,
            }
            tool_log.append(entry)
            _log_step(cl.user_session.get("session_id", "?"), query,
                      tool_calls_count, entry)
            tool_results.append({"role": "tool", "tool_call_id": tc.id, "content": result})

            # ── Empty streak tracking ─────────────────────────────────────────
            if status == "useful":
                consecutive_empty = 0
            else:
                consecutive_empty += 1

        await _think.remove()
        messages.extend(tool_results)

        # ── Empty streak: inject pivot hint ──────────────────────────────────
        if consecutive_empty >= EMPTY_STREAK_LIMIT:
            messages.append({"role": "user", "content": (
                f"[SYSTEM] Your last {consecutive_empty} tool calls returned no results. "
                "Your current search approach is not converging. Try a different strategy:\n"
                "1. Use get_module on a likely namespace instead of searching by keyword\n"
                "2. Try the exact identifier name as a search_symbols query (BM25 ranks exact matches highly)\n"
                "3. Search in a different service — the code may live upstream or downstream\n"
                "4. If genuinely stuck after trying the above, use get_context as a last resort\n"
                "Do not repeat the same query phrasings that have already failed."
            )})
            consecutive_empty = 0  # reset after injecting hint

        # ── Ceiling: save state, show action buttons, yield control to UI ──
        if tool_calls_count >= MAX_TOOL_CALLS:
            cl.user_session.set("_paused", {
                "messages": messages,
                "query":    query,
                "tool_log": tool_log,
                "t_query":  t_query,
            })
            await cl.Message(
                content=(
                    f"⚠️ **{tool_calls_count} tool calls used.** "
                    "The agent can keep investigating or synthesize what it has found so far."
                ),
                actions=[
                    cl.Action(name="cl_extend",    label="🔍 Keep investigating",
                              payload={"action": "extend"}),
                    cl.Action(name="cl_synthesize", label="✓ Synthesize now",
                              payload={"action": "synthesize"}),
                ],
            ).send()
            return False  # paused — caller must return

        # ── Loop detected: inject stop instruction and break ──
        if loop_detected:
            messages.append({
                "role": "user",
                "content": "You have called the same tool with the same arguments more than once. "
                           "You have enough context — synthesize your answer now.",
            })
            break

    await _stream_final_answer(messages, query, tool_log, t_query=t_query)
    return True


@cl.action_callback("cl_extend")
async def on_extend(action: cl.Action):
    """User chose to keep investigating — resume the loop with saved state."""
    state = cl.user_session.get("_paused")
    if not state:
        await cl.Message(content="No paused investigation found.").send()
        return
    cl.user_session.set("_paused", None)
    messages = state["messages"]
    # Without this the LLM sees the last batch of tool results and immediately synthesizes.
    # Explicitly tell it to keep going.
    messages.append({
        "role": "user",
        "content": (
            "Continue your investigation. You have not yet synthesized — keep calling tools "
            "to deepen your understanding. Only stop when you have read the key function "
            "bodies and can answer with confidence."
        ),
    })
    try:
        await _react_loop(messages, state["query"], state["tool_log"], t_query=state.get("t_query"))
    except Exception as e:
        import traceback
        await cl.Message(
            content=f"**Error:** {e}\n```\n{traceback.format_exc()[:1000]}\n```"
        ).send()


@cl.action_callback("cl_synthesize")
async def on_synthesize(action: cl.Action):
    """User chose to synthesize — inject stop instruction and stream final answer."""
    state = cl.user_session.get("_paused")
    if not state:
        await cl.Message(content="No paused investigation found.").send()
        return
    cl.user_session.set("_paused", None)
    messages = state["messages"]
    messages.append({
        "role": "user",
        "content": "You have used many tool calls. Synthesize your findings into a complete answer now.",
    })
    try:
        await _stream_final_answer(messages, state["query"], state["tool_log"], converged=False, t_query=state.get("t_query"))
    except Exception as e:
        import traceback
        await cl.Message(
            content=f"**Error:** {e}\n```\n{traceback.format_exc()[:1000]}\n```"
        ).send()


# ════════════════════════════════════════════════════════════════════════════
# CHAINLIT MESSAGE HANDLER
# ════════════════════════════════════════════════════════════════════════════

@cl.on_message
async def on_message(message: cl.Message):
    query = message.content.strip()

    # If indexes are still loading (first-ever connection), wait here.
    if not _load_all_done:
        loading_msg = cl.Message(content="⏳ Loading indexes, please wait…")
        await loading_msg.send()
        await asyncio.to_thread(load_all)
        loading_msg.content = "✓ Ready — processing your query…"
        await loading_msg.update()

    # /status command
    if query.lower().startswith("/status"):
        lines = [
            "**HyperRetrieval Status**",
            f"- Graph: {RE.G.number_of_nodes():,} nodes, {RE.G.number_of_edges():,} edges",
            f"- Vectors: {RE.lance_tbl.count_rows():,} @ 4096d",
            f"- Module graph: {RE.MG.number_of_nodes():,} modules, {RE.MG.number_of_edges():,} edges",
            f"- Co-change: {len(RE.cochange_index):,} modules indexed",
            f"- Body store: {len(RE.body_store):,} bodies",
            f"- Call graph: {len(RE.call_graph):,} entries",
            f"- Log patterns: {len(RE.log_patterns):,} functions",
            f"- Doc chunks: {len(RE.doc_chunks):,}",
            f"- LLM: {LLM_MODEL}",
        ]
        await cl.Message(content="\n".join(lines)).send()
        return

    history = cl.user_session.get("history", [])
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for past_q, past_a in history[-MAX_HISTORY:]:
        messages.append({"role": "user",      "content": past_q})
        messages.append({"role": "assistant", "content": past_a})
    messages.append({"role": "user", "content": query})

    try:
        await _react_loop(messages, query, [], t_query=time.time())
    except Exception as e:
        import traceback
        await cl.Message(
            content=f"**Error:** {e}\n```\n{traceback.format_exc()[:1000]}\n```"
        ).send()
