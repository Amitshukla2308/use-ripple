"""
code_commands.py — Coding-assistance slash commands.

Ported from codetoolcli: search, find, brief, refactor, optimize, test, debug.
All use the engine's ReAct loop with appropriate system context.
"""
from __future__ import annotations
import os
import subprocess
import sys


# ── /search ───────────────────────────────────────────────────────────────────

def cmd_search(args: str, session, engine) -> str:
    """Search the indexed codebase for a concept or identifier."""
    if not args:
        return "Usage: /search <query>"
    prompt = (
        f"Search the codebase for: {args}\n\n"
        "Use search_modules, search_symbols, and get_module to find relevant code. "
        "Summarise what you find: module paths, key functions, which service owns it."
    )
    return engine.query(prompt)


# ── /find ─────────────────────────────────────────────────────────────────────

def cmd_find(args: str, session, engine) -> str:
    """
    Find files matching a pattern.
    /find *.py              → glob pattern
    /find TODO              → search file contents
    """
    if not args:
        return "Usage: /find <glob-pattern or text>"
    from tools.file_tools import glob_files, grep_files  # type: ignore
    # If it looks like a glob pattern, use glob; otherwise grep
    if any(c in args for c in ("*", "?", "[")):
        return glob_files(args, session.cwd)
    else:
        return grep_files(args, session.cwd)


# ── /brief ────────────────────────────────────────────────────────────────────

def cmd_brief(args: str, session, engine) -> str:
    """
    Generate a codebase summary using retrieval tools.
    Optionally focus on a specific service or topic.
    """
    topic = args.strip() or "the entire codebase"
    prompt = (
        f"Give a structured overview of {topic}.\n\n"
        "Cover:\n"
        "1. High-level architecture and service responsibilities\n"
        "2. Key entry points and primary flows\n"
        "3. Important modules and their purposes\n"
        "4. Cross-service dependencies\n\n"
        "Use search_modules, get_module, and search_symbols to ground your answer in actual code."
    )
    return engine.query(prompt)


# ── /refactor ─────────────────────────────────────────────────────────────────

def cmd_refactor(args: str, session, engine) -> str:
    """
    Refactor code based on a description.
    /refactor extract payment validation from checkout.py into a separate module
    """
    if not args:
        return "Usage: /refactor <description of what to change>"
    prompt = (
        f"Refactor task: {args}\n\n"
        "Steps:\n"
        "1. Find the relevant files (glob_files, grep_files)\n"
        "2. Read the code (read_file)\n"
        "3. Plan the changes\n"
        "4. Apply them (edit_file or write_file)\n"
        "5. Verify nothing is broken (run_bash for tests if available)\n\n"
        "Minimal footprint: only change what is needed. "
        "No unsolicited cleanups beyond the stated goal."
    )
    return engine.query(prompt)


# ── /optimize ─────────────────────────────────────────────────────────────────

def cmd_optimize(args: str, session, engine) -> str:
    """
    Analyse and optimize code for performance or clarity.
    /optimize serve/retrieval_engine.py  → optimize a file
    /optimize search latency             → broader optimization goal
    """
    if not args:
        return "Usage: /optimize <file or description>"
    prompt = (
        f"Optimization request: {args}\n\n"
        "Read the relevant code, identify bottlenecks or clarity issues, "
        "and apply targeted improvements. "
        "Benchmark or profile with run_bash if meaningful. "
        "Explain the trade-offs of each change."
    )
    return engine.query(prompt)


# ── /test ─────────────────────────────────────────────────────────────────────

def cmd_test(args: str, session, engine) -> str:
    """
    Run tests.
    /test                   → discover and run all tests
    /test tests/test_foo.py → run specific test file
    /test -k payment        → pass args to test runner
    """
    # Detect test runner
    cwd = session.cwd
    runners = [
        (f"pytest {args} -v", "pytest.ini", "setup.cfg", "pyproject.toml"),
        (f"python3 -m pytest {args} -v", None),
        (f"python3 run_tests.py {args}", "run_tests.py"),
    ]

    for runner_cmd, *markers in runners:
        if markers[0] is None or any(
            os.path.exists(os.path.join(cwd, m)) for m in markers if m
        ):
            result = subprocess.run(
                runner_cmd, shell=True, capture_output=True, text=True,
                cwd=cwd, timeout=300,
            )
            out = (result.stdout + result.stderr).strip()
            if len(out) > 6000:
                out = out[:3000] + f"\n... [truncated] ...\n" + out[-2500:]
            return f"$ {runner_cmd}\n\n{out}"

    return "No test runner found. Run: /test <pytest-args> or specify a test file."


# ── /debug ────────────────────────────────────────────────────────────────────

def cmd_debug(args: str, session, engine) -> str:
    """
    Debug an issue using retrieval + code tools.
    /debug payment stuck in PENDING after gateway timeout
    """
    if not args:
        return "Usage: /debug <description of the issue>"
    prompt = (
        f"Debug this issue: {args}\n\n"
        "Investigation protocol:\n"
        "1. Use search_modules / search_symbols to locate relevant code\n"
        "2. Read function bodies to understand the normal flow\n"
        "3. Use trace_callers / trace_callees to follow the execution path\n"
        "4. Check log patterns with get_log_patterns for observability\n"
        "5. Form 3–5 hypotheses ranked by likelihood\n"
        "6. For each: name the exact log pattern or code path that confirms/denies it\n"
        "7. State the fastest safe mitigation\n\n"
        "Answer only from code you have actually read. "
        "No speculation beyond what the source shows."
    )
    return engine.query(prompt)


# ── /explain ─────────────────────────────────────────────────────────────────

def cmd_explain(args: str, session, engine) -> str:
    """
    Explain how something works in the codebase.
    /explain UPI collect flow
    /explain Euler.API.Gateway.Gateway.Razorpay.Flow
    """
    if not args:
        return "Usage: /explain <concept, module, or function>"
    prompt = (
        f"Explain how {args} works.\n\n"
        "Use search_modules + get_module to orient, then read relevant function bodies. "
        "Trace the flow end-to-end. Reference exact module paths and function IDs."
    )
    return engine.query(prompt)


# ── /implement ────────────────────────────────────────────────────────────────

def cmd_implement(args: str, session, engine) -> str:
    """
    Implement a new feature or change.
    /implement add rate-limiting middleware to the API gateway
    """
    if not args:
        return "Usage: /implement <description of what to build>"
    prompt = (
        f"Implement: {args}\n\n"
        "Process:\n"
        "1. Search existing code for relevant patterns to follow\n"
        "2. Read the key files you need to modify\n"
        "3. Write the implementation (edit_file / write_file)\n"
        "4. Run tests if available\n\n"
        "Follow existing code style and patterns. "
        "Never invent new abstractions when an existing pattern covers the case."
    )
    return engine.query(prompt)


# ── /lint ─────────────────────────────────────────────────────────────────────

def cmd_lint(args: str, session, engine) -> str:
    """Run linter on a file or the whole project."""
    target = args or "."
    cwd    = session.cwd

    for linter in (f"ruff check {target}", f"flake8 {target}",
                   f"pylint {target}", f"biome check {target}"):
        tool = linter.split()[0]
        if subprocess.run(f"which {tool}", shell=True,
                          capture_output=True).returncode == 0:
            result = subprocess.run(
                linter, shell=True, capture_output=True, text=True, cwd=cwd)
            return (result.stdout + result.stderr).strip() or "No issues found."

    return "No linter found. Install ruff: pip install ruff"


# ── Registry ──────────────────────────────────────────────────────────────────

CMD_CODE: dict[str, tuple] = {
    "search":     (cmd_search,     "Search indexed codebase for a concept or identifier"),
    "find":       (cmd_find,       "Find files (glob) or search content"),
    "brief":      (cmd_brief,      "Codebase overview (optionally for a service/topic)"),
    "refactor":   (cmd_refactor,   "LLM-guided refactor with file edits"),
    "optimize":   (cmd_optimize,   "Analyse and improve code performance or clarity"),
    "test":       (cmd_test,       "Run tests [optional: test file or pytest args]"),
    "debug":      (cmd_debug,      "Debug an issue using retrieval + code tools"),
    "explain":    (cmd_explain,    "Explain a concept, module, or function"),
    "implement":  (cmd_implement,  "Implement a feature or change"),
    "lint":       (cmd_lint,       "Run linter on file or project"),
}
