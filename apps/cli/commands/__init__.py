"""
commands/__init__.py — HyperCode slash command registry.

All /commands are registered here and dispatched by hrcode.py.
Each command handler receives (args_str, session, engine) and returns a string.

Equivalent to codetoolcli's command system — 60+ commands ported and
renamed for Ripple conventions.
"""
from __future__ import annotations
import os
import sys
import pathlib

# Ensure CLI dir is importable
_CLI_DIR = pathlib.Path(__file__).parent.parent
if str(_CLI_DIR) not in sys.path:
    sys.path.insert(0, str(_CLI_DIR))

from .git_commands     import CMD_GIT
from .code_commands    import CMD_CODE
from .session_commands import CMD_SESSION
from .system_commands  import CMD_SYSTEM

# ── Master registry ───────────────────────────────────────────────────────────
# Each entry: (handler_fn, one_line_description)
COMMANDS: dict[str, tuple] = {
    **CMD_GIT,
    **CMD_CODE,
    **CMD_SESSION,
    **CMD_SYSTEM,
}


def dispatch(name: str, args: str, session, engine) -> str | None:
    """
    Look up and run a /command.
    Returns the output string, or None if command not found.
    """
    entry = COMMANDS.get(name.lower())
    if entry is None:
        return None
    handler, _desc = entry
    try:
        return handler(args.strip(), session, engine)
    except Exception as exc:
        import traceback
        return f"Command /{name} failed: {exc}\n{traceback.format_exc()[:600]}"


def help_text() -> str:
    """Return formatted help listing all commands."""
    lines = ["HyperCode slash commands:\n"]
    categories = {
        "Git": CMD_GIT,
        "Code": CMD_CODE,
        "Session": CMD_SESSION,
        "System": CMD_SYSTEM,
    }
    for cat, cmds in categories.items():
        lines.append(f"  [{cat}]")
        for name, (_, desc) in sorted(cmds.items()):
            lines.append(f"    /{name:<22} {desc}")
        lines.append("")
    lines.append("Type /help <command> for details.")
    return "\n".join(lines)
