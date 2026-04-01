"""
bash_tool.py — Secure shell command execution with permission system.

Ported from codetoolcli BashTool — adapted for HyperRetrieval.
Runs commands with timeout, captures stdout/stderr, truncates oversized output.

Permission system:
  Dangerous commands (rm -rf, force push, DROP TABLE, etc.) are intercepted
  before execution. If an approval callback is registered (set by hrcode.py),
  the user is prompted. If no callback, dangerous commands are blocked.
"""
import os
import re
import subprocess
from typing import Callable, Optional

BASH_TIMEOUT = int(os.environ.get("HRCODE_BASH_TIMEOUT", "120"))
MAX_OUTPUT   = int(os.environ.get("HRCODE_MAX_OUTPUT",   "32768"))  # 32 KB

# ── Dangerous command patterns ────────────────────────────────────────────────
# Ordered from most to least destructive. Each is (label, compiled_regex).
_DANGEROUS = [
    ("recursive delete",       re.compile(r"\brm\s+(-\w*r\w*f|-\w*f\w*r)\b",        re.I)),
    ("delete root",            re.compile(r"\brm\b.*\s/\s*$")),
    ("force push",             re.compile(r"\bgit\s+push\b.*(-f\b|--force\b)",        re.I)),
    ("reset hard",             re.compile(r"\bgit\s+(reset|checkout)\b.*--hard\b",    re.I)),
    ("drop database/table",    re.compile(r"\b(DROP\s+(TABLE|DATABASE|SCHEMA))\b",    re.I)),
    ("disk overwrite",         re.compile(r"\bdd\b.*\bof=/dev/",                      re.I)),
    ("chmod 777 recursive",    re.compile(r"\bchmod\b.*-R.*777\b",                    re.I)),
    ("redirect to system file",re.compile(r">\s*/etc/\w+")),
    ("kill all processes",     re.compile(r"\bkillall\b|\bkill\s+-9\s+-1\b")),
    ("format disk",            re.compile(r"\b(mkfs|format)\b",                       re.I)),
    ("no-verify commit hook",  re.compile(r"\bgit\s+commit\b.*--no-verify\b",         re.I)),
]


def _is_dangerous(command: str) -> Optional[str]:
    """Return the label of the first matched dangerous pattern, or None."""
    for label, pattern in _DANGEROUS:
        if pattern.search(command):
            return label
    return None


# ── Approval callback ─────────────────────────────────────────────────────────
# hrcode.py sets this to a function(command, reason) -> bool
# Returns True to allow, False to block.
_APPROVAL_CALLBACK: Optional[Callable[[str, str], bool]] = None


def set_approval_callback(fn: Callable[[str, str], bool]) -> None:
    """Register the interactive approval prompt. Called by hrcode.py at startup."""
    global _APPROVAL_CALLBACK
    _APPROVAL_CALLBACK = fn


def _default_approval(command: str, reason: str) -> bool:
    """
    Fallback approval: asks the user on stdin.
    Used when set_approval_callback() was not called (e.g. non-interactive use).
    """
    try:
        print(f"\n⚠️  Dangerous command detected ({reason}):")
        print(f"   {command[:200]}")
        answer = input("Allow? [y/N] ").strip().lower()
        return answer in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


# ════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION
# ════════════════════════════════════════════════════════════════════════════

def run_bash(command: str, timeout: int = None, cwd: str = None) -> str:
    """Execute a bash command and return combined stdout/stderr."""
    if not command or not command.strip():
        return "Error: empty command."

    # ── Permission check ──────────────────────────────────────────────────────
    danger_reason = _is_dangerous(command)
    if danger_reason:
        callback = _APPROVAL_CALLBACK or _default_approval
        allowed  = callback(command, danger_reason)
        if not allowed:
            return (
                f"[BLOCKED] Command blocked ({danger_reason}). "
                "User did not approve. Choose a safer alternative."
            )

    effective_cwd     = cwd or os.environ.get("HRCODE_CWD") or os.getcwd()
    effective_timeout = timeout or BASH_TIMEOUT

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            cwd=effective_cwd,
            env={**os.environ},
        )
        stdout = (result.stdout or "").rstrip()
        stderr = (result.stderr or "").rstrip()

        parts: list[str] = []
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(f"[stderr]\n{stderr}")

        combined = "\n".join(parts).strip()

        if len(combined) > MAX_OUTPUT:
            half    = MAX_OUTPUT // 2
            clipped = len(combined) - MAX_OUTPUT
            combined = (
                combined[:half]
                + f"\n\n... [{clipped:,} chars truncated] ...\n\n"
                + combined[-half:]
            )

        prefix = f"[exit {result.returncode}]\n" if result.returncode != 0 else ""
        return f"{prefix}{combined}" if combined else (prefix.strip() or "[no output]")

    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {effective_timeout}s."
    except Exception as exc:
        return f"Error: {exc}"
