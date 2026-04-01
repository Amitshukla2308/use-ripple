"""
tools/__init__.py — Unified tool registry for HyperCode CLI.

Combines:
  • Retrieval tools  — codebase intelligence (delegates to tools.py + retrieval_engine.py)
  • Coding tools     — file I/O, bash, glob, grep, sub-agent

CODING_TOOL_SCHEMAS   : JSON schemas for coding tools only (safe to use without RE)
RETRIEVAL_TOOL_SCHEMAS: JSON schemas for retrieval tools (require RE.initialize())
ALL_TOOL_SCHEMAS      : Full list passed to the LLM

CODING_DISPATCH       : fn_name → callable (coding tools)
RETRIEVAL_DISPATCH    : fn_name → callable (retrieval tools — populated lazily)
ALL_DISPATCH          : merged dispatch dict used by the engine
"""
import pathlib
import sys

# Ensure repo root and serve/ are importable
_REPO = pathlib.Path(__file__).parent.parent.parent.parent   # apps/cli/tools → repo root
_SERVE = _REPO / "serve"
for _p in (str(_REPO), str(_SERVE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from .bash_tool  import run_bash
from .file_tools import read_file, write_file, edit_file, glob_files, grep_files
from .agent_tool import run_agent
from ._extended_tools import EXTENDED_TOOL_SCHEMAS, EXTENDED_DISPATCH


# ════════════════════════════════════════════════════════════════════════════
# CODING TOOL SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

CODING_TOOL_SCHEMAS: list[dict] = [

    {"type": "function", "function": {
        "name": "run_bash",
        "description": (
            "Execute a shell command and return its output.\n\n"
            "Use for: git operations, running tests/builds, installing packages, "
            "checking system state, file manipulation that is easier in shell.\n\n"
            "Rules:\n"
            "- Prefer non-interactive commands (avoid prompts)\n"
            "- Use absolute paths or assume cwd is the project root\n"
            "- For file reading, prefer read_file (preserves line numbers)\n"
            "- For destructive operations, confirm with the user first\n"
            "- Never run commands that fork background processes (use & sparingly)"
        ),
        "parameters": {"type": "object", "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to run."
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 120). Increase for slow builds."
            },
        }, "required": ["command"]},
    }},

    {"type": "function", "function": {
        "name": "read_file",
        "description": (
            "Read a file with line numbers.\n\n"
            "Always read before editing — the Edit tool requires knowing the exact "
            "existing content. Line numbers help you reference specific locations.\n\n"
            "Use offset + limit to read a section of a large file:\n"
            "  read_file('src/foo.py', offset=100, limit=50)  → lines 100–149"
        ),
        "parameters": {"type": "object", "properties": {
            "file_path": {"type": "string", "description": "File path (absolute or relative to cwd)."},
            "offset":    {"type": "integer", "description": "1-based line number to start from (default: 1)."},
            "limit":     {"type": "integer", "description": "Maximum lines to return (default: 2000)."},
        }, "required": ["file_path"]},
    }},

    {"type": "function", "function": {
        "name": "write_file",
        "description": (
            "Write content to a file (creates or completely overwrites).\n\n"
            "Use for new files or complete rewrites. "
            "For targeted changes to existing files, use edit_file instead — "
            "it is safer and shows exactly what changed."
        ),
        "parameters": {"type": "object", "properties": {
            "file_path": {"type": "string", "description": "File path to write (creates parent dirs if needed)."},
            "content":   {"type": "string", "description": "Full file content to write."},
        }, "required": ["file_path", "content"]},
    }},

    {"type": "function", "function": {
        "name": "edit_file",
        "description": (
            "Replace an exact string in a file.\n\n"
            "Rules:\n"
            "- old_string MUST appear verbatim in the file (read_file first if unsure)\n"
            "- old_string must be unique in the file — add surrounding lines if needed\n"
            "- Preserves all surrounding content; only the matched string is replaced\n"
            "- Use replace_all=true to rename across the entire file\n\n"
            "Prefer this over write_file for existing files — minimal diff, lower risk."
        ),
        "parameters": {"type": "object", "properties": {
            "file_path":   {"type": "string", "description": "Path to the file to edit."},
            "old_string":  {"type": "string", "description": "Exact text to replace (must be unique in the file)."},
            "new_string":  {"type": "string", "description": "Replacement text."},
            "replace_all": {"type": "boolean", "description": "Replace all occurrences (default: false)."},
        }, "required": ["file_path", "old_string", "new_string"]},
    }},

    {"type": "function", "function": {
        "name": "glob_files",
        "description": (
            "Find files by glob pattern. Returns paths sorted by modification time.\n\n"
            "Examples:\n"
            "  glob_files('**/*.py')              → all Python files\n"
            "  glob_files('src/**/*.ts')          → TypeScript in src/\n"
            "  glob_files('tests/test_*.py')      → test files\n\n"
            "Use to discover file locations before reading or editing them."
        ),
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "Glob pattern (supports ** for recursive)."},
            "path":    {"type": "string", "description": "Base directory to search from (default: cwd)."},
        }, "required": ["pattern"]},
    }},

    {"type": "function", "function": {
        "name": "grep_files",
        "description": (
            "Search file contents for a regex pattern.\n\n"
            "Returns matching lines with file:line references.\n"
            "Uses ripgrep when available (fast), falls back to Python re.\n\n"
            "Examples:\n"
            "  grep_files('def process_payment')          → find function definitions\n"
            "  grep_files('TODO|FIXME', file_glob='*.py') → find all TODOs in Python files\n"
            "  grep_files('import.*openai', case_insensitive=True)"
        ),
        "parameters": {"type": "object", "properties": {
            "pattern":          {"type": "string", "description": "Regex pattern to search for."},
            "path":             {"type": "string", "description": "Directory to search (default: cwd)."},
            "file_glob":        {"type": "string", "description": "Restrict to files matching this glob (e.g. '*.py')."},
            "case_insensitive": {"type": "boolean", "description": "Case-insensitive match (default: false)."},
            "context_lines":    {"type": "integer", "description": "Lines of context around each match (default: 0)."},
        }, "required": ["pattern"]},
    }},

    {"type": "function", "function": {
        "name": "run_agent",
        "description": (
            "Delegate a focused subtask to a child AI agent.\n\n"
            "Use when a sub-problem is well-scoped and independent:\n"
            "- Summarise a large file or set of results\n"
            "- Research a specific concept and return a structured answer\n"
            "- Run a bounded investigation (e.g. 'find all callers of X')\n\n"
            "The child agent has the same tools. Returns the child's answer.\n"
            "Cap: 10 tool calls per sub-agent to prevent runaway cost."
        ),
        "parameters": {"type": "object", "properties": {
            "prompt":         {"type": "string", "description": "The focused task for the sub-agent."},
            "system_context": {"type": "string", "description": "Extra context to include in the sub-agent's system prompt."},
        }, "required": ["prompt"]},
    }},
] + EXTENDED_TOOL_SCHEMAS


CODING_DISPATCH: dict = {
    "run_bash":   lambda a: run_bash(
        a.get("command", ""), a.get("timeout"), a.get("cwd")),
    "read_file":  lambda a: read_file(
        a.get("file_path", ""), a.get("offset", 1), a.get("limit")),
    "write_file": lambda a: write_file(
        a.get("file_path", ""), a.get("content", "")),
    "edit_file":  lambda a: edit_file(
        a.get("file_path", ""), a.get("old_string", ""), a.get("new_string", ""),
        a.get("replace_all", False)),
    "glob_files": lambda a: glob_files(
        a.get("pattern", ""), a.get("path")),
    "grep_files": lambda a: grep_files(
        a.get("pattern", ""), a.get("path"), a.get("file_glob"),
        a.get("case_insensitive", False), a.get("context_lines", 0)),
    "run_agent":  lambda a: run_agent(
        a.get("prompt", ""), a.get("system_context", "")),
}
CODING_DISPATCH.update(EXTENDED_DISPATCH)


# ════════════════════════════════════════════════════════════════════════════
# RETRIEVAL TOOL SCHEMAS + DISPATCH  (mirrors tools.py at repo root)
# Populated lazily — only valid after RE.initialize() has been called.
# ════════════════════════════════════════════════════════════════════════════

def _load_root_tools():
    """
    Load repo-root tools.py by explicit file path.
    Avoids `import tools` which would circularly resolve to this package
    when _CLI_DIR is on sys.path.
    """
    import importlib.util as _ilu
    _root = _REPO / "tools.py"
    if not _root.exists():
        return None
    # Re-use cached module if already loaded
    _cache_key = "_hr_root_tools"
    import sys as _sys
    if _cache_key in _sys.modules:
        return _sys.modules[_cache_key]
    _spec = _ilu.spec_from_file_location(_cache_key, _root)
    _mod  = _ilu.module_from_spec(_spec)
    _sys.modules[_cache_key] = _mod
    _spec.loader.exec_module(_mod)
    return _mod


def _get_retrieval_schemas() -> list[dict]:
    """Return retrieval tool schemas from the repo-root tools.py."""
    try:
        T = _load_root_tools()
        return list(T.AGENT_TOOLS) if T else []
    except Exception:
        return []


def _get_retrieval_dispatch() -> dict:
    """Return retrieval tool dispatch from the repo-root tools.py."""
    try:
        T = _load_root_tools()
        return dict(T.TOOL_DISPATCH) if T else {}
    except Exception:
        return {}


def build_tool_registry(include_retrieval: bool = True) -> tuple[list[dict], dict]:
    """
    Build the complete tool list and dispatch for the engine.

    Returns:
        (schemas, dispatch) — pass schemas to the LLM, dispatch to the executor.
    """
    schemas  = list(CODING_TOOL_SCHEMAS)
    dispatch = dict(CODING_DISPATCH)

    if include_retrieval:
        ret_schemas  = _get_retrieval_schemas()
        ret_dispatch = _get_retrieval_dispatch()
        schemas  = ret_schemas + schemas   # retrieval first (contextually primary)
        dispatch = {**ret_dispatch, **dispatch}   # coding tools override on collision

    return schemas, dispatch
