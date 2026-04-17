#!/usr/bin/env python3
"""
hrcode.py — HyperCode CLI  (Ripple's AI coding tool)

A full-featured interactive AI coding assistant with:
  • 20 tools: bash, file I/O, glob, grep, sub-agent + 13 retrieval tools
  • 26 slash commands: /commit, /review-pr, /refactor, /debug, /search, /brief, …
  • Persistent memory across sessions
  • Streaming output powered by Kimi LLM

Equivalent to codetoolcli (Claude Code CLI) but:
  - Written in Python (same stack as Ripple)
  - Uses Kimi via LLM_BASE_URL / LLM_API_KEY
  - Integrates directly with retrieval_engine.py (no HTTP intermediary)
  - Named for Ripple conventions

Usage
-----
  python3 hrcode.py                        # interactive REPL
  python3 hrcode.py "explain UPI flow"     # one-shot query
  python3 hrcode.py --no-retrieval         # coding-only mode (no RE needed)
  python3 hrcode.py --resume <session_id>  # resume a saved session
  python3 hrcode.py -p < prompt.txt        # pipe in a prompt
  python3 hrcode.py /commit                # run a slash command directly

Setup (set these in your environment or config.yaml):
  export LLM_API_KEY=...
  export LLM_BASE_URL=https://your-llm-endpoint/v1
  export LLM_MODEL=kimi-latest
  export ARTIFACT_DIR=/path/to/artifacts   # optional, enables codebase tools
  export EMBED_SERVER_URL=http://localhost:8001
"""
import argparse
import os
import pathlib
import readline   # noqa: F401  (enables arrow keys + history in REPL)
import sys
import time

# ── Ensure all app/cli modules are importable ─────────────────────────────────
_CLI_DIR  = pathlib.Path(__file__).parent
_REPO     = _CLI_DIR.parent.parent
_SERVE    = _REPO / "serve"
# _CLI_DIR must be at sys.path[0] so `import tools` resolves to apps/cli/tools/ package
# (not root tools.py which has no build_tool_registry).
# Python auto-adds the script dir to sys.path, but we must ensure it stays at index 0
# even after inserting _REPO and _SERVE.
for _p in (str(_SERVE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
# Force _CLI_DIR to index 0 — it may already be in sys.path (added by Python) but not at [0]
_cli_str = str(_CLI_DIR)
if _cli_str in sys.path:
    sys.path.remove(_cli_str)
sys.path.insert(0, _cli_str)

from engine  import QueryEngine, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, _RICH  # type: ignore
from session import Session, memory_as_context  # type: ignore
import commands as _commands  # type: ignore

if _RICH:
    from rich.console  import Console
    from rich.markdown import Markdown
    from rich.panel    import Panel
    _console = Console()


# ── Startup banner ────────────────────────────────────────────────────────────

_BANNER = """\
HyperCode  — AI coding assistant for Ripple
Type your query or /help for commands.  Ctrl+C / /exit to quit.
"""


def _print_banner(session: Session, retrieval_loaded: bool) -> None:
    retrieval_note = (
        "Retrieval: loaded" if retrieval_loaded else
        "Retrieval: not loaded (set ARTIFACT_DIR to enable)"
    )
    if _RICH:
        _console.print(Panel(
            f"[bold cyan]HyperCode[/bold cyan]  ·  session [dim]{session.id}[/dim]\n"
            f"model [dim]{LLM_MODEL}[/dim]  ·  {retrieval_note}",
            expand=False,
        ))
    else:
        print(_BANNER)
        print(f"session: {session.id}  model: {LLM_MODEL}  {retrieval_note}\n")


# ── Retrieval engine bootstrap ────────────────────────────────────────────────

def _try_load_retrieval(verbose: bool = True) -> bool:
    """Attempt to initialize retrieval_engine. Returns True on success."""
    artifact_dir = os.environ.get("ARTIFACT_DIR", "")
    if not artifact_dir:
        return False
    try:
        import retrieval_engine as RE  # type: ignore
        if RE.G is not None:
            return True
        if verbose:
            print("Loading retrieval index…", end=" ", flush=True)
        t0 = time.monotonic()
        RE.initialize(
            artifact_dir=pathlib.Path(artifact_dir),
            load_embedder=False,   # delegate to embed_server
        )
        elapsed = time.monotonic() - t0
        if verbose:
            n = RE.G.number_of_nodes() if RE.G else 0
            print(f"✓  {n:,} nodes  ({elapsed:.1f}s)")
        return RE.G is not None
    except Exception as exc:
        if verbose:
            print(f"\nRetrieval load failed: {exc}", file=sys.stderr)
        return False


# ── REPL helpers ──────────────────────────────────────────────────────────────

def _is_slash_command(text: str) -> bool:
    return text.strip().startswith("/")


def _parse_slash_command(text: str) -> tuple[str, str]:
    """Return (command_name, args_string)."""
    stripped = text.strip().lstrip("/")
    parts    = stripped.split(None, 1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


def _run_slash_command(text: str, session: Session, engine: QueryEngine) -> str | None:
    name, args = _parse_slash_command(text)
    if name in ("exit", "quit", "q"):
        return None   # Signal to quit
    result = _commands.dispatch(name, args, session, engine)
    if result is None:
        return f"Unknown command: /{name}  — try /help"
    return result


def _print_result(text: str) -> None:
    if not text:
        return
    if _RICH:
        _console.print(Markdown(text))
    else:
        print(text)


# ── Interactive REPL ──────────────────────────────────────────────────────────

def run_repl(session: Session, engine: QueryEngine) -> None:
    """Main interactive read-eval-print loop."""
    # Set up readline history
    hist_file = pathlib.Path.home() / ".hrcode" / "history"
    hist_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        readline.read_history_file(str(hist_file))
    except FileNotFoundError:
        pass
    readline.set_history_length(1000)

    memory_ctx = memory_as_context()

    try:
        while True:
            try:
                user_input = input("\n[hrcode] ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not user_input:
                continue

            # ── Slash command ──────────────────────────────────────────────────
            if _is_slash_command(user_input):
                result = _run_slash_command(user_input, session, engine)
                if result is None:   # /exit
                    break
                _print_result(result)
                readline.write_history_file(str(hist_file))
                continue

            # ── LLM query ─────────────────────────────────────────────────────
            t0 = time.monotonic()
            print()

            try:
                response, in_tok, out_tok = engine.query_streaming(
                    user_input,
                    history_messages=session.build_history_messages(),
                    memory_ctx=memory_ctx,
                )
            except KeyboardInterrupt:
                print("\n[interrupted]")
                continue
            except Exception as exc:
                print(f"\nError: {exc}", file=sys.stderr)
                continue

            elapsed = time.monotonic() - t0
            session.add_turn(user_input, response)
            session.add_usage(in_tok, out_tok)
            memory_ctx = memory_as_context()  # refresh in case /memory add was called

            # Perf footer
            tps = out_tok / elapsed if elapsed > 0 and out_tok else 0
            footer = (
                f"[{in_tok:,}+{out_tok:,} tok  "
                f"{'%.1f' % tps} t/s  "
                f"{'%.1f' % elapsed}s]"
            )
            if _RICH:
                _console.print(f"\n[dim]{footer}[/dim]")
            else:
                print(f"\n{footer}")

            readline.write_history_file(str(hist_file))
            session.save()

    finally:
        session.save()
        readline.write_history_file(str(hist_file))


# ── One-shot / pipe mode ──────────────────────────────────────────────────────

def run_oneshot(query: str, session: Session, engine: QueryEngine) -> int:
    """Run a single query and exit. Used for scripting and pipes."""
    if _is_slash_command(query):
        result = _run_slash_command(query, session, engine)
        if result is None:
            return 0
        _print_result(result)
        return 0

    memory_ctx = memory_as_context()
    try:
        response, in_tok, out_tok = engine.query_streaming(
            query,
            history_messages=session.build_history_messages(),
            memory_ctx=memory_ctx,
        )
        session.add_turn(query, response)
        session.add_usage(in_tok, out_tok)
        session.save()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="hrcode",
        description="HyperCode — AI coding assistant for Ripple",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("query",        nargs="?", default=None,
                        help="One-shot query or /command (omit for interactive REPL)")
    parser.add_argument("--resume", "-r", default=None, metavar="SESSION_ID",
                        help="Resume a previous session by ID")
    parser.add_argument("--no-retrieval", action="store_true",
                        help="Disable retrieval tools (coding-only mode, no ARTIFACT_DIR needed)")
    parser.add_argument("--max-tools", type=int, default=None,
                        help="Maximum tool calls per query (default 40)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress tool call output")
    parser.add_argument("--pipe", "-p", action="store_true",
                        help="Read query from stdin")
    parser.add_argument("--cwd", default=None,
                        help="Working directory (default: current directory)")
    args = parser.parse_args()

    # ── Validate LLM config ───────────────────────────────────────────────────
    if not LLM_API_KEY:
        print("Error: LLM_API_KEY not set.", file=sys.stderr)
        print("  export LLM_API_KEY=your_key", file=sys.stderr)
        return 1

    # ── Working directory ─────────────────────────────────────────────────────
    cwd = args.cwd or os.getcwd()
    os.environ["HRCODE_CWD"] = cwd

    # ── Session ───────────────────────────────────────────────────────────────
    if args.resume:
        session = Session.load(args.resume)
        if session is None:
            print(f"Session not found: {args.resume}", file=sys.stderr)
            return 1
        session.cwd = cwd
    else:
        session = Session(cwd=cwd)

    # ── Retrieval engine ──────────────────────────────────────────────────────
    include_retrieval = not args.no_retrieval
    retrieval_loaded  = False
    if include_retrieval:
        retrieval_loaded = _try_load_retrieval(verbose=(args.query is None))

    # ── Engine ────────────────────────────────────────────────────────────────
    from engine import DEFAULT_MAX_TOOL_CALLS  # type: ignore
    engine = QueryEngine(
        max_tool_calls    = args.max_tools or DEFAULT_MAX_TOOL_CALLS,
        verbose           = not args.quiet,
        streaming         = True,
        include_retrieval = include_retrieval,
    )

    # ── One-shot: pipe from stdin ─────────────────────────────────────────────
    if args.pipe or not sys.stdin.isatty():
        query = args.query or sys.stdin.read().strip()
        if not query:
            print("Error: empty query.", file=sys.stderr)
            return 1
        return run_oneshot(query, session, engine)

    # ── One-shot: query as CLI arg ────────────────────────────────────────────
    if args.query:
        return run_oneshot(args.query, session, engine)

    # ── Interactive REPL ──────────────────────────────────────────────────────
    _print_banner(session, retrieval_loaded)
    run_repl(session, engine)
    return 0


if __name__ == "__main__":
    sys.exit(main())
