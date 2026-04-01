"""
session_commands.py — Session management slash commands.

Ported from codetoolcli: memory, cost, status, clear, context.
"""
from __future__ import annotations
import os
import sys
import pathlib


# ── /memory ──────────────────────────────────────────────────────────────────

def cmd_memory(args: str, session, engine) -> str:
    """
    Manage persistent memory notes.
    /memory                  → list all notes
    /memory add <note>       → add a note
    /memory clear            → clear all notes
    """
    _cli = pathlib.Path(__file__).parent.parent
    if str(_cli) not in sys.path:
        sys.path.insert(0, str(_cli))
    from session import memory_add, memory_list, memory_clear  # type: ignore

    parts = args.strip().split(None, 1)
    cmd   = parts[0].lower() if parts else ""
    rest  = parts[1] if len(parts) > 1 else ""

    if cmd == "add":
        if not rest:
            return "Usage: /memory add <note>"
        return memory_add(rest)
    elif cmd == "clear":
        return memory_clear()
    else:
        return memory_list()


# ── /cost ─────────────────────────────────────────────────────────────────────

def cmd_cost(args: str, session, engine) -> str:
    """Show token usage for this session and cumulative totals."""
    return session.cost_summary()


# ── /status ───────────────────────────────────────────────────────────────────

def cmd_status(args: str, session, engine) -> str:
    """Show current session state: cwd, history length, model, tool count."""
    _cli = pathlib.Path(__file__).parent.parent
    if str(_cli) not in sys.path:
        sys.path.insert(0, str(_cli))

    from engine import LLM_MODEL  # type: ignore

    try:
        from tools import build_tool_registry  # type: ignore
        schemas, _ = build_tool_registry(include_retrieval=True)
        n_tools = len(schemas)
    except Exception:
        n_tools = 7  # coding tools minimum

    # Check retrieval engine
    try:
        import retrieval_engine as RE  # type: ignore
        re_loaded = RE.G is not None
        n_symbols = RE.G.number_of_nodes() if re_loaded else 0
    except Exception:
        re_loaded = False
        n_symbols = 0

    lines = [
        f"Session ID  : {session.id}",
        f"Working dir : {session.cwd}",
        f"History     : {len(session.history)} turns",
        f"LLM model   : {LLM_MODEL}",
        f"Tools       : {n_tools}",
        f"Retrieval   : {'loaded — ' + f'{n_symbols:,} nodes' if re_loaded else 'not loaded'}",
        f"In tokens   : {session.in_tokens:,}",
        f"Out tokens  : {session.out_tokens:,}",
    ]
    return "\n".join(lines)


# ── /clear ────────────────────────────────────────────────────────────────────

def cmd_clear(args: str, session, engine) -> str:
    """Clear conversation history for this session."""
    session.history = []
    return "Conversation history cleared."


# ── /context ─────────────────────────────────────────────────────────────────

def cmd_context(args: str, session, engine) -> str:
    """Show the current conversation context (last N turns)."""
    if not session.history:
        return "No conversation history yet."
    n = int(args.strip()) if args.strip().isdigit() else len(session.history)
    lines = []
    for i, (q, r) in enumerate(session.history[-n:], 1):
        lines.append(f"[Turn {i}] User: {q[:120]}")
        lines.append(f"         Asst: {r[:200]}\n")
    return "\n".join(lines)


# ── /cd ───────────────────────────────────────────────────────────────────────

def cmd_cd(args: str, session, engine) -> str:
    """Change the working directory for this session."""
    target = args.strip() or os.path.expanduser("~")
    p = pathlib.Path(target)
    if not p.is_absolute():
        p = pathlib.Path(session.cwd) / p
    p = p.resolve()
    if not p.is_dir():
        return f"Not a directory: {p}"
    session.cwd = str(p)
    os.environ["HRCODE_CWD"] = str(p)
    return f"cwd → {p}"


# ── /pwd ─────────────────────────────────────────────────────────────────────

def cmd_pwd(args: str, session, engine) -> str:
    """Show the current working directory."""
    return session.cwd


# ── /save ────────────────────────────────────────────────────────────────────

def cmd_save(args: str, session, engine) -> str:
    """Save current session to disk."""
    session.save()
    return f"Session {session.id} saved to ~/.hrcode/sessions/{session.id}.json"


# ── /sessions ────────────────────────────────────────────────────────────────

def cmd_sessions(args: str, session, engine) -> str:
    """List recent sessions."""
    _cli = pathlib.Path(__file__).parent.parent
    if str(_cli) not in sys.path:
        sys.path.insert(0, str(_cli))
    from session import Session  # type: ignore

    recent = Session.list_recent(10)
    if not recent:
        return "No saved sessions found."
    lines = ["Recent sessions:"]
    for s in recent:
        import time as _time
        age = _time.strftime("%Y-%m-%d %H:%M",
                             _time.localtime(s["mtime"]))
        lines.append(f"  {s['id']}  [{s['turns']} turns]  {age}  {s['preview']!r}")
    return "\n".join(lines)


# ── Registry ──────────────────────────────────────────────────────────────────

CMD_SESSION: dict[str, tuple] = {
    "memory":   (cmd_memory,   "Manage persistent memory notes (add / list / clear)"),
    "cost":     (cmd_cost,     "Show token usage for this session + lifetime total"),
    "status":   (cmd_status,   "Show session state, model, tools, retrieval status"),
    "clear":    (cmd_clear,    "Clear conversation history"),
    "context":  (cmd_context,  "Show last N conversation turns"),
    "cd":       (cmd_cd,       "Change working directory for this session"),
    "pwd":      (cmd_pwd,      "Show current working directory"),
    "save":     (cmd_save,     "Save session to disk"),
    "sessions": (cmd_sessions, "List recent saved sessions"),
}
