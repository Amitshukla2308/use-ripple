"""
engine.py — HyperCode QueryEngine.

ReAct loop powered by Kimi (or any OpenAI-compatible LLM) with:
  - Full Ripple tool suite (retrieval + coding tools)
  - Token budget tracking with auto-compaction at context limits
  - Post-turn memory extraction trigger
  - Permission callbacks for destructive tool calls

Ported from codetoolcli's QueryEngine — adapted for Ripple's stack.
"""
import json
import os
import pathlib
import sys
import time
import re as _re
from typing import Callable, Optional

# ── Repo path bootstrap ───────────────────────────────────────────────────────
_CLI_DIR = pathlib.Path(__file__).parent
_REPO    = _CLI_DIR.parent.parent
_SERVE   = _REPO / "serve"
# _CLI_DIR must be at sys.path[0] so `import tools` resolves to apps/cli/tools/ package
# (not root tools.py which has no build_tool_registry).
for _p in (str(_SERVE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_cli_str = str(_CLI_DIR)
if _cli_str in sys.path:
    sys.path.remove(_cli_str)
sys.path.insert(0, _cli_str)

# ── LLM config ────────────────────────────────────────────────────────────────
LLM_API_KEY  = os.environ.get("LLM_API_KEY",  "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_MODEL    = os.environ.get("LLM_MODEL",    "kimi-latest")

# ── Tool limits ───────────────────────────────────────────────────────────────
DEFAULT_MAX_TOOL_CALLS = int(os.environ.get("HRCODE_MAX_TOOL_CALLS", "40"))
MAX_SAME_CALL          = 2   # loop detection threshold
CTX_MIN_PRIOR_CALLS    = 3   # get_context early-use guard

# ── Token budget (codetoolcli's token_budget pattern) ────────────────────────
TOKEN_WARN_THRESHOLD    = int(os.environ.get("HRCODE_TOKEN_WARN",    "80000"))
TOKEN_COMPACT_THRESHOLD = int(os.environ.get("HRCODE_TOKEN_COMPACT", "110000"))
TOKEN_COMPACT_KEEP_MSGS = int(os.environ.get("HRCODE_COMPACT_KEEP",  "8"))  # recent msgs to preserve

# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
You are HyperCode — a senior software engineer AI embedded in the Ripple platform.

You act on code directly. You read files, write them, run tests, trace call graphs, \
search 94 k indexed symbols, commit changes, and explain what you find. \
You do not describe what you would do — you do it.

## Core principles

1. **Read before writing** — always read_file before edit_file so old_string is exact.
2. **Minimal footprint** — make only the requested changes; no unsolicited refactors.
3. **Ground every claim** — cite actual file paths and function IDs, never invent them.
4. **Batch independent tools** — call multiple tools in one response when they do not \
depend on each other; never chain single tool calls you could parallelise.
5. **Verify with tests** — run tests after non-trivial code changes.

## Tool strategy

| Goal | Primary tools |
|------|--------------|
| Find where something lives | `search_modules` → `get_module` |
| Understand a function | `get_function_body` → `trace_callees` |
| Find and read a file | `glob_files` → `read_file` |
| Make a targeted change | `read_file` → `edit_file` |
| Create a new file | `write_file` |
| Build / test / git | `run_bash` |
| Search content | `grep_files` |
| Cross-service impact | `get_blast_radius` |
| Delegate bounded sub-problem | `run_agent` |

## Between tool rounds

Before each new batch of tool calls, emit one sentence:
- What you found in the last round
- What you are looking for next

Format: [STATUS: <one concise sentence — no quotes>]

## Code output format

- File paths in backticks.
- Code in fenced blocks with language tags (```python, ```bash, …).
- For multi-file changes, list every changed file at the end.
- No preamble, no trailing summary.
"""


def _strip_status(text: str) -> str:
    return _re.sub(r'\[STATUS:[^\]]*\]\s*', '', text or "").strip()


def _classify_result(result: str) -> str:
    if not result or not result.strip():
        return "empty"
    low = result.strip().lower()
    if low.startswith("error") or "not found" in low[:80] or low.startswith("unknown tool"):
        return "error"
    empty_signals = (
        "no results", "0 results", "no symbols", "no matches",
        "no callers", "no callees", "no files found", "no output",
    )
    if any(s in low[:120] for s in empty_signals):
        return "empty"
    return "useful"


# ── Rich terminal helpers ─────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.markdown import Markdown
    _RICH = True
except ImportError:
    _RICH = False


def _console():
    return Console() if _RICH else None


def _print_tool_call(fn_name: str, args: dict, status: str, verbose: bool) -> None:
    _ICONS = {
        "get_function_body": "📖", "trace_callers": "⬆ ", "trace_callees": "⬇ ",
        "search_symbols":    "🔍", "search_modules": "📦", "get_module":    "📂",
        "get_blast_radius":  "💥", "get_context":    "📚", "run_bash":      "⚡",
        "read_file":         "📄", "write_file":     "✏️ ", "edit_file":     "✏️ ",
        "glob_files":        "🔎", "grep_files":     "🔎", "run_agent":     "🤖",
    }
    icon    = _ICONS.get(fn_name, "⚙ ")
    subject = str(
        args.get("fn_id") or args.get("query") or args.get("file_path")
        or args.get("command", "")[:40] or args.get("module_name") or ""
    )[:60]
    badge = {"useful": "✓", "empty": "∅", "error": "✗"}.get(status, "?")
    line  = f"  {icon} {fn_name}({subject})  {badge}"
    if _RICH:
        color = {"useful": "green", "empty": "yellow", "error": "red"}.get(status, "white")
        Console(highlight=False).print(line, style=color)
    else:
        print(line)


# ════════════════════════════════════════════════════════════════════════════
# TOKEN BUDGET + AUTO-COMPACTION
# ════════════════════════════════════════════════════════════════════════════

def _compact_messages(
    messages: list[dict],
    client,
    model: str,
    keep_recent: int = TOKEN_COMPACT_KEEP_MSGS,
) -> list[dict]:
    """
    Compact the message list to free context:
      1. Keep messages[0] (system prompt)
      2. Summarise messages[1 : -keep_recent] with a single LLM call
      3. Return [system, summary_block] + messages[-keep_recent:]

    Mirrors codetoolcli's reactive_compact / session_memory_compact pattern.
    """
    if len(messages) <= keep_recent + 2:
        return messages  # nothing to compact

    system_msg  = messages[0]
    to_compress = messages[1 : -keep_recent]
    keep_msgs   = messages[-keep_recent:]

    # Build a readable transcript of what to compress
    transcript_parts: list[str] = []
    for m in to_compress:
        role    = m.get("role", "")
        content = m.get("content") or ""
        if role == "tool":
            # Summarise tool results to reduce noise
            transcript_parts.append(f"[tool result: {str(content)[:300]}]")
        elif role in ("user", "assistant") and content:
            transcript_parts.append(f"{role.capitalize()}: {str(content)[:600]}")

    if not transcript_parts:
        return messages

    summary_prompt = (
        "Summarise the following conversation segment concisely. "
        "Preserve: key decisions, findings, files edited, errors encountered, "
        "and the user's goal. Be factual, no commentary.\n\n"
        + "\n".join(transcript_parts)
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a concise summarisation assistant."},
                {"role": "user",   "content": summary_prompt},
            ],
            temperature=0.1,
            max_tokens=1500,
        )
        summary_text = resp.choices[0].message.content or "(summary unavailable)"
    except Exception:
        summary_text = "(compaction summary failed — continuing with truncated history)"

    compacted_block = {
        "role":    "user",
        "content": f"[COMPACTED CONTEXT]\n{summary_text}\n[END COMPACTED CONTEXT]",
    }

    return [system_msg, compacted_block] + keep_msgs


# ════════════════════════════════════════════════════════════════════════════
# QUERY ENGINE
# ════════════════════════════════════════════════════════════════════════════

class QueryEngine:
    """
    HyperCode's core ReAct loop.

    Parameters
    ----------
    max_tool_calls     : hard ceiling on tool calls per query
    extra_system       : additional text appended to the system prompt
    verbose            : print tool call details
    streaming          : stream final answer token by token
    include_retrieval  : include Ripple codebase tools
    session            : Session object for memory extraction (optional)
    """

    def __init__(
        self,
        max_tool_calls:    int  = DEFAULT_MAX_TOOL_CALLS,
        extra_system:      str  = "",
        verbose:           bool = True,
        streaming:         bool = True,
        include_retrieval: bool = True,
        session=None,
    ):
        self.max_tool_calls    = max_tool_calls
        self.extra_system      = extra_system
        self.verbose           = verbose
        self.streaming         = streaming
        self.include_retrieval = include_retrieval
        self.session           = session  # apps.cli.session.Session

        self._client                = None
        self._tools_schemas: list   = []
        self._dispatch:      dict   = {}
        self._budget_warned:  bool  = False   # inject budget warning only once per query

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")
        self._client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL or None)

    def _ensure_tools(self) -> None:
        if self._tools_schemas:
            return
        from tools import build_tool_registry  # type: ignore
        self._tools_schemas, self._dispatch = build_tool_registry(
            include_retrieval=self.include_retrieval
        )

    def _system_prompt(self, memory_ctx: str = "") -> str:
        parts = [_SYSTEM_PROMPT]
        if memory_ctx:
            parts.append(memory_ctx)
        if self.extra_system:
            parts.append(f"\n{self.extra_system}")
        return "\n".join(parts)

    # ── Budget helpers ────────────────────────────────────────────────────────

    def _check_budget(
        self,
        messages: list[dict],
        total_tokens: int,
    ) -> tuple[list[dict], bool]:
        """
        Returns (possibly compacted messages, should_warn).
        Triggers auto-compaction when total_tokens > TOKEN_COMPACT_THRESHOLD.
        """
        should_warn = (
            total_tokens >= TOKEN_WARN_THRESHOLD
            and not self._budget_warned
        )

        if total_tokens >= TOKEN_COMPACT_THRESHOLD:
            if self.verbose:
                msg = f"[token budget] {total_tokens:,} tokens — auto-compacting context"
                if _RICH:
                    Console(highlight=False).print(msg, style="yellow")
                else:
                    print(msg, file=sys.stderr)
            messages = _compact_messages(messages, self._client, LLM_MODEL)
            self._budget_warned = False   # reset after compact so warning fires again

        return messages, should_warn

    # ── Public API ────────────────────────────────────────────────────────────

    def query(
        self,
        user_input:       str,
        history_messages: list[dict] = None,
        memory_ctx:       str = "",
    ) -> str:
        """Run full ReAct loop. Returns final answer string."""
        self._ensure_client()
        self._ensure_tools()
        self._budget_warned = False

        messages: list[dict] = [
            {"role": "system", "content": self._system_prompt(memory_ctx)},
        ]
        if history_messages:
            messages.extend(history_messages)
        messages.append({"role": "user", "content": user_input})

        tool_log:         list[dict] = []
        seen_calls:       dict       = {}
        tool_calls_count             = 0
        consecutive_empty            = 0
        total_tokens                 = 0

        while True:
            # ── Budget check ──────────────────────────────────────────────────
            messages, should_warn = self._check_budget(messages, total_tokens)
            if should_warn:
                self._budget_warned = True
                messages.append({"role": "user", "content": (
                    f"[SYSTEM] Token budget: {total_tokens:,} / {TOKEN_COMPACT_THRESHOLD:,} used. "
                    "Be more concise in tool calls. Avoid redundant searches."
                )})

            # ── LLM call ──────────────────────────────────────────────────────
            resp = self._client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                tools=self._tools_schemas,
                tool_choice="auto",
                temperature=0.15,
                max_tokens=16000,
            )
            usage = getattr(resp, "usage", None)
            if usage:
                total_tokens += (getattr(usage, "prompt_tokens", 0) or 0)
                total_tokens += (getattr(usage, "completion_tokens", 0) or 0)

            assistant_msg = resp.choices[0].message

            if not assistant_msg.tool_calls:
                final_text = _strip_status(assistant_msg.content or "")
                self._output(final_text)
                self._after_turn(messages, total_tokens)
                return final_text

            reasoning = _strip_status(assistant_msg.content or "")
            if reasoning and self.verbose:
                if _RICH:
                    Console(highlight=False).print(f"\n[dim]{reasoning}[/dim]")
                else:
                    print(f"\n{reasoning}", file=sys.stderr)

            messages.append({
                "role":       "assistant",
                "content":    assistant_msg.content,
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name,
                                  "arguments": tc.function.arguments}}
                    for tc in assistant_msg.tool_calls
                ],
            })

            # ── Dispatch tool calls ───────────────────────────────────────────
            tool_results: list[dict] = []
            loop_detected            = False

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

                if fn_name == "get_context" and tool_calls_count < CTX_MIN_PRIOR_CALLS:
                    result = (
                        f"[GUIDANCE] get_context called after only {tool_calls_count} "
                        "tool calls. Try search_modules + search_symbols with 2–3 "
                        "different phrasings first. get_context is a last resort."
                    )
                    tool_results.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                    continue

                tool_calls_count += 1
                dispatcher = self._dispatch.get(fn_name)
                t0 = time.monotonic()
                try:
                    result = dispatcher(args) if dispatcher else f"Unknown tool: {fn_name}"
                except Exception as exc:
                    result = f"Tool error ({fn_name}): {exc}"
                elapsed = time.monotonic() - t0

                status = _classify_result(result)
                if self.verbose:
                    _print_tool_call(fn_name, args, status, self.verbose)

                tool_log.append({
                    "tool": fn_name, "args": args, "status": status,
                    "preview": (result or "")[:200], "len": len(result or ""),
                    "ms": round(elapsed * 1000),
                })
                if self.session:
                    self.session.tool_log.append(tool_log[-1])

                tool_results.append({"role": "tool", "tool_call_id": tc.id, "content": result})

                consecutive_empty = 0 if status == "useful" else consecutive_empty + 1

            messages.extend(tool_results)

            if consecutive_empty >= 4:
                messages.append({"role": "user", "content": (
                    f"[SYSTEM] Your last {consecutive_empty} tool calls returned no results. "
                    "Try a different approach: use get_module on a likely namespace, "
                    "use the exact identifier as a search_symbols query, "
                    "or search in a different service."
                )})
                consecutive_empty = 0

            if tool_calls_count >= self.max_tool_calls:
                messages.append({"role": "user", "content": (
                    f"You have used {tool_calls_count} tool calls — synthesize now."
                )})
                final_resp = self._client.chat.completions.create(
                    model=LLM_MODEL, messages=messages, temperature=0.2, max_tokens=8000,
                )
                final_text = _strip_status(final_resp.choices[0].message.content or "")
                self._output(final_text)
                self._after_turn(messages, total_tokens)
                return final_text

            if loop_detected:
                messages.append({"role": "user", "content": (
                    "You called the same tool with the same arguments twice. "
                    "You have enough context — synthesize your answer now."
                )})
                break  # force exit — don't let LLM ignore the hint

    def query_streaming(
        self,
        user_input:       str,
        history_messages: list[dict] = None,
        memory_ctx:       str = "",
        on_token:         Callable   = None,
    ) -> tuple[str, int, int]:
        """
        Like query() but streams the final answer token by token.
        Returns (full_response, in_tokens, out_tokens).
        """
        self._ensure_client()
        self._ensure_tools()
        self._budget_warned = False

        messages: list[dict] = [
            {"role": "system", "content": self._system_prompt(memory_ctx)},
        ]
        if history_messages:
            messages.extend(history_messages)
        messages.append({"role": "user", "content": user_input})

        tool_log:         list[dict] = []
        seen_calls:       dict       = {}
        tool_calls_count             = 0
        consecutive_empty            = 0
        in_tokens                    = 0
        out_tokens                   = 0
        total_tokens                 = 0

        while True:
            messages, should_warn = self._check_budget(messages, total_tokens)
            if should_warn:
                self._budget_warned = True
                messages.append({"role": "user", "content": (
                    f"[SYSTEM] Token budget warning: {total_tokens:,} tokens used. "
                    "Prioritise concise tool calls."
                )})

            resp = self._client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                tools=self._tools_schemas,
                tool_choice="auto",
                temperature=0.15,
                max_tokens=16000,
            )
            usage = getattr(resp, "usage", None)
            if usage:
                pt = getattr(usage, "prompt_tokens",    0) or 0
                ct = getattr(usage, "completion_tokens", 0) or 0
                in_tokens    += pt
                out_tokens   += ct
                total_tokens += pt + ct

            assistant_msg = resp.choices[0].message

            if not assistant_msg.tool_calls:
                # Stream the final answer
                stream_msgs = list(messages)
                if assistant_msg.content:
                    stream_msgs.append({"role": "assistant", "content": assistant_msg.content})
                stream = self._client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=stream_msgs,
                    temperature=0.2,
                    max_tokens=65536,
                    stream=True,
                    stream_options={"include_usage": True},
                )
                full_response = ""
                for chunk in stream:
                    if hasattr(chunk, "usage") and chunk.usage:
                        in_tokens  += chunk.usage.prompt_tokens    or 0
                        out_tokens += chunk.usage.completion_tokens or 0
                    if not chunk.choices:
                        continue
                    token = chunk.choices[0].delta.content
                    if token:
                        full_response += token
                        if on_token:
                            on_token(token)
                        elif self.streaming:
                            print(token, end="", flush=True)
                if self.streaming:
                    print()
                full_response = _strip_status(full_response)
                self._after_turn(messages, total_tokens)
                return full_response, in_tokens, out_tokens

            reasoning = _strip_status(assistant_msg.content or "")
            if reasoning and self.verbose:
                print(f"\n{reasoning}", file=sys.stderr)

            messages.append({
                "role":       "assistant",
                "content":    assistant_msg.content,
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name,
                                  "arguments": tc.function.arguments}}
                    for tc in assistant_msg.tool_calls
                ],
            })

            tool_results: list[dict] = []
            loop_detected            = False

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

                if fn_name == "get_context" and tool_calls_count < CTX_MIN_PRIOR_CALLS:
                    result = (
                        f"[GUIDANCE] get_context called too early ({tool_calls_count} prior calls). "
                        "Try search_modules and search_symbols first."
                    )
                    tool_results.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                    continue

                tool_calls_count += 1
                dispatcher = self._dispatch.get(fn_name)
                t0 = time.monotonic()
                try:
                    result = dispatcher(args) if dispatcher else f"Unknown tool: {fn_name}"
                except Exception as exc:
                    result = f"Tool error ({fn_name}): {exc}"
                elapsed = time.monotonic() - t0

                status = _classify_result(result)
                if self.verbose:
                    _print_tool_call(fn_name, args, status, self.verbose)

                tool_log.append({
                    "tool": fn_name, "args": args, "status": status,
                    "preview": (result or "")[:200], "len": len(result or ""),
                    "ms": round(elapsed * 1000),
                })
                if self.session:
                    self.session.tool_log.append(tool_log[-1])

                tool_results.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                consecutive_empty = 0 if status == "useful" else consecutive_empty + 1

            messages.extend(tool_results)

            if consecutive_empty >= 4:
                messages.append({"role": "user", "content": (
                    f"[SYSTEM] {consecutive_empty} consecutive empty results. "
                    "Try a different query, different service, or use get_module."
                )})
                consecutive_empty = 0

            if tool_calls_count >= self.max_tool_calls:
                messages.append({"role": "user", "content": (
                    f"[SYSTEM] {tool_calls_count} tool calls used. Synthesize now."
                )})
                stream = self._client.chat.completions.create(
                    model=LLM_MODEL, messages=messages,
                    temperature=0.2, max_tokens=8000, stream=True,
                    stream_options={"include_usage": True},
                )
                full_response = ""
                for chunk in stream:
                    if hasattr(chunk, "usage") and chunk.usage:
                        in_tokens  += chunk.usage.prompt_tokens    or 0
                        out_tokens += chunk.usage.completion_tokens or 0
                    if not chunk.choices:
                        continue
                    token = chunk.choices[0].delta.content
                    if token:
                        full_response += token
                        if on_token:
                            on_token(token)
                        elif self.streaming:
                            print(token, end="", flush=True)
                if self.streaming:
                    print()
                self._after_turn(messages, total_tokens)
                return _strip_status(full_response), in_tokens, out_tokens

            if loop_detected:
                messages.append({"role": "user", "content": (
                    "Repeated tool call detected. Synthesize now."
                )})
                break  # force exit — don't let LLM ignore the hint

    # ── Post-turn hooks ───────────────────────────────────────────────────────

    def _after_turn(self, messages: list[dict], total_tokens: int) -> None:
        """
        Called after every completed turn. Fires background memory extraction
        if thresholds are met (mirrors codetoolcli's post-sampling hook).
        """
        if self.session is None:
            return
        self.session.maybe_extract_memories(
            messages    = messages,
            llm_api_key = LLM_API_KEY,
            llm_base_url= LLM_BASE_URL,
            llm_model   = LLM_MODEL,
        )

    # ── Terminal output ───────────────────────────────────────────────────────

    def _output(self, text: str) -> None:
        if not text:
            return
        if _RICH and self.streaming:
            Console().print(Markdown(text))
        else:
            print(text)
