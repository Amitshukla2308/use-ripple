"""
system_commands.py — System / meta slash commands.

Ported from codetoolcli: help, doctor, config, mcp, model.
"""
from __future__ import annotations
import os
import pathlib
import shlex
import shutil
import subprocess
import sys


# ── /help ────────────────────────────────────────────────────────────────────

def cmd_help(args: str, session, engine) -> str:
    """
    Show all commands, or details for a specific command.
    /help          → list everything
    /help commit   → details for /commit
    """
    _cmds_dir = pathlib.Path(__file__).parent
    if str(_cmds_dir) not in sys.path:
        sys.path.insert(0, str(_cmds_dir.parent))

    from commands import COMMANDS, help_text  # type: ignore

    if args:
        name  = args.strip().lstrip("/")
        entry = COMMANDS.get(name)
        if entry:
            handler, desc = entry
            doc = handler.__doc__ or "(no details)"
            return f"/{name} — {desc}\n\n{doc.strip()}"
        return f"Unknown command: /{name}\n\n{help_text()}"
    return help_text()


# ── /doctor ───────────────────────────────────────────────────────────────────

def cmd_doctor(args: str, session, engine) -> str:
    """
    Diagnose HyperCode environment: check LLM connectivity, retrieval engine,
    tool availability, and environment variables.
    """
    from engine import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL  # type: ignore

    checks = []

    # LLM config
    checks.append(f"  LLM_API_KEY   : {'✓ set' if LLM_API_KEY else '✗ missing'}")
    checks.append(f"  LLM_BASE_URL  : {LLM_BASE_URL or '(default OpenAI)'}")
    checks.append(f"  LLM_MODEL     : {LLM_MODEL}")

    # LLM connectivity
    try:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL or None)
        # Quick non-streaming test
        r = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=5,
        )
        checks.append(f"  LLM ping      : ✓ {r.choices[0].message.content!r}")
    except Exception as exc:
        checks.append(f"  LLM ping      : ✗ {exc}")

    # Retrieval engine
    try:
        import retrieval_engine as RE  # type: ignore
        if RE.G:
            checks.append(f"  Retrieval     : ✓ loaded — {RE.G.number_of_nodes():,} nodes")
        else:
            artifact_dir = os.environ.get("ARTIFACT_DIR", "")
            checks.append(f"  Retrieval     : ✗ not loaded  (ARTIFACT_DIR={artifact_dir or 'not set'})")
    except Exception as exc:
        checks.append(f"  Retrieval     : ✗ {exc}")

    # Tools
    for tool in ("rg", "git", "pytest", "bun"):
        # 🛡️ Sentinel: Safe executable path resolution
        found = shutil.which(tool) is not None
        checks.append(f"  {tool:<12}  : {'✓' if found else '○ optional'}")

    # ARTIFACT_DIR
    artifact_dir = os.environ.get("ARTIFACT_DIR", "")
    if artifact_dir:
        p = pathlib.Path(artifact_dir)
        checks.append(f"  ARTIFACT_DIR  : {'✓ ' + str(p) if p.exists() else '✗ not found: ' + artifact_dir}")
    else:
        checks.append(f"  ARTIFACT_DIR  : ○ not set (retrieval disabled)")

    # EMBED_SERVER_URL
    embed_url = os.environ.get("EMBED_SERVER_URL", "")
    checks.append(f"  EMBED_SERVER  : {embed_url or '○ not set'}")

    return "HyperCode doctor:\n" + "\n".join(checks)


# ── /config ───────────────────────────────────────────────────────────────────

def cmd_config(args: str, session, engine) -> str:
    """
    Show or set HyperCode configuration.
    /config                → show current settings
    /config model <name>   → change the LLM model for this session
    """
    parts = args.strip().split(None, 1)
    if not parts:
        # Show current config
        from engine import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL  # type: ignore
        lines = [
            "Current configuration:",
            f"  LLM_MODEL    = {LLM_MODEL}",
            f"  LLM_BASE_URL = {LLM_BASE_URL or '(OpenAI default)'}",
            f"  LLM_API_KEY  = {'<set>' if LLM_API_KEY else '<not set>'}",
            f"  ARTIFACT_DIR = {os.environ.get('ARTIFACT_DIR', '<not set>')}",
            f"  HRCODE_CWD   = {session.cwd}",
        ]
        return "\n".join(lines)

    cmd   = parts[0].lower()
    value = parts[1] if len(parts) > 1 else ""

    if cmd == "model":
        if not value:
            return "Usage: /config model <model-name>"
        import engine as _eng  # type: ignore
        _eng.LLM_MODEL = value
        os.environ["LLM_MODEL"] = value
        return f"LLM model changed to: {value}"

    return f"Unknown config key: {cmd}\nAvailable: model"


# ── /model ────────────────────────────────────────────────────────────────────

def cmd_model(args: str, session, engine) -> str:
    """
    Switch LLM model.
    /model                      → show current model
    /model reasoning-large      → switch to a different model
    """
    if not args:
        from engine import LLM_MODEL  # type: ignore
        return f"Current model: {LLM_MODEL}"
    return cmd_config(f"model {args}", session, engine)


# ── /mcp ─────────────────────────────────────────────────────────────────────

def cmd_mcp(args: str, session, engine) -> str:
    """
    Manage the HyperRetrieval MCP server.
    /mcp status    → check if MCP server is running on port 8002
    /mcp start     → start the MCP server
    /mcp stop      → stop the MCP server
    /mcp tools     → list available MCP tools
    """
    import socket
    parts = args.strip().split()
    sub   = parts[0].lower() if parts else "status"

    def _is_running() -> bool:
        try:
            with socket.create_connection(("127.0.0.1", 8002), timeout=1):
                return True
        except Exception:
            return False

    if sub == "status":
        running = _is_running()
        return f"MCP server (port 8002): {'✓ running' if running else '✗ not running'}"

    elif sub == "start":
        if _is_running():
            return "MCP server is already running on port 8002."
        script = pathlib.Path(__file__).parent.parent.parent.parent / "serve" / "mcp_server.py"
        if not script.exists():
            return f"mcp_server.py not found at {script}"
        subprocess.Popen(
            [sys.executable, str(script), "--http"],
            stdout=open(os.path.expanduser("~/mcp_server.log"), "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        import time
        time.sleep(2)
        return "MCP server started on port 8002." if _is_running() else \
               "MCP server may not have started. Check ~/mcp_server.log"

    elif sub == "stop":
        # 🛡️ Sentinel: Sanitize shell command by providing list without shell=True
        result = subprocess.run(["fuser", "-k", "8002/tcp"], capture_output=True, text=True)
        return "MCP server stopped." if result.returncode == 0 else \
               "Could not stop MCP server (may not be running)."

    elif sub == "tools":
        from tools import build_tool_registry  # type: ignore
        schemas, _ = build_tool_registry(include_retrieval=True)
        lines = [f"{len(schemas)} tools available:"]
        for s in schemas:
            fn = s.get("function", {})
            name = fn.get("name", "?")
            desc = (fn.get("description") or "").split("\n")[0][:60]
            lines.append(f"  {name:<28} {desc}")
        return "\n".join(lines)

    return f"Unknown sub-command: {sub}  (status | start | stop | tools)"


# ── /reload ───────────────────────────────────────────────────────────────────

def cmd_reload(args: str, session, engine) -> str:
    """Reload the retrieval index from ARTIFACT_DIR."""
    artifact_dir = args.strip() or os.environ.get("ARTIFACT_DIR", "")
    if not artifact_dir:
        return "ARTIFACT_DIR not set. Usage: /reload /path/to/artifacts"
    try:
        import retrieval_engine as RE  # type: ignore
        import pathlib as _pl
        RE.initialize(artifact_dir=_pl.Path(artifact_dir))
        return f"Retrieval engine reloaded from {artifact_dir}  ({RE.G.number_of_nodes():,} nodes)"
    except Exception as exc:
        return f"Reload failed: {exc}"


# ── /version ──────────────────────────────────────────────────────────────────

def cmd_version(args: str, session, engine) -> str:
    """Show HyperCode version and platform info."""
    import platform
    return (
        "HyperCode — codebase intelligence CLI for HyperRetrieval\n"
        f"Python   : {platform.python_version()}\n"
        f"Platform : {platform.system()} {platform.release()}\n"
        f"Session  : {session.id}"
    )


# ── Registry ──────────────────────────────────────────────────────────────────

CMD_SYSTEM: dict[str, tuple] = {
    "help":    (cmd_help,    "Show all commands (or /help <command> for details)"),
    "doctor":  (cmd_doctor,  "Diagnose environment: LLM, retrieval, tools"),
    "config":  (cmd_config,  "Show/set configuration (model, etc.)"),
    "model":   (cmd_model,   "Show or switch the LLM model"),
    "mcp":     (cmd_mcp,     "Manage MCP server (status | start | stop | tools)"),
    "reload":  (cmd_reload,  "Reload retrieval index from ARTIFACT_DIR"),
    "version": (cmd_version, "Show HyperCode version and platform info"),
}
