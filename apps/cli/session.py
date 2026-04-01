"""
session.py — Session state, 4-type memory system, and auto-extraction.

Memory storage (mirrors Claude Code's memory system):
  ~/.hrcode/memory/<name>.md     — individual typed memory files (YAML frontmatter)
  ~/.hrcode/MEMORY.md            — index (one line per file, injected into context)
  ~/.hrcode/sessions/<id>.json   — conversation history
  ~/.hrcode/cost.json            — cumulative token usage

Memory types:
  user       — user's role, preferences, expertise
  feedback   — corrections and confirmed approaches from the user
  project    — ongoing work, decisions, deadlines
  reference  — where things live in external systems
"""
import json
import os
import pathlib
import re
import threading
import time
import uuid
from typing import Callable, Optional

_HRCODE_DIR   = pathlib.Path.home() / ".hrcode"
_SESSIONS_DIR = _HRCODE_DIR / "sessions"
_MEMORY_DIR   = _HRCODE_DIR / "memory"
_MEMORY_INDEX = _HRCODE_DIR / "MEMORY.md"
_COST_FILE    = _HRCODE_DIR / "cost.json"

MAX_HISTORY = int(os.environ.get("HRCODE_MAX_HISTORY", "20"))

# Auto-extraction thresholds (codetoolcli's shouldExtractMemory pattern)
_MEM_TOKEN_THRESHOLD = int(os.environ.get("HRCODE_MEM_TOKEN_THRESHOLD", "8000"))
_MEM_TOOL_THRESHOLD  = int(os.environ.get("HRCODE_MEM_TOOL_THRESHOLD",  "6"))
_MEM_MIN_TURNS       = int(os.environ.get("HRCODE_MEM_MIN_TURNS",       "2"))

# Lock so background threads don't race on MEMORY.md
_mem_lock = threading.Lock()

# Extraction prompt — tells the LLM what to mine from the conversation
_EXTRACT_SYSTEM = """\
You are a memory extraction assistant. Read the conversation and extract facts worth
remembering across future sessions. Output ONLY a JSON array (no markdown, no prose).

Each element must be:
{
  "name": "short_snake_case_filename",
  "type": "user|feedback|project|reference",
  "description": "one-line hook used to decide relevance in future sessions",
  "body": "memory content — for feedback/project: lead with the rule/fact, then **Why:** line and **How to apply:** line"
}

Memory types:
  user       — role, expertise, communication preferences
  feedback   — what to avoid or repeat (corrections AND confirmations)
  project    — ongoing work, decisions, deadlines (convert relative dates to absolute)
  reference  — where things live in external systems

What NOT to extract:
  - Code patterns, file paths, architecture derivable from the code
  - Git history, debugging solutions already fixed in code
  - Ephemeral task details only relevant to this conversation

Return [] if there is nothing worth saving.
"""


def _ensure_dirs() -> None:
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════════════════════
# TYPED MEMORY FILES
# ════════════════════════════════════════════════════════════════════════════

def memory_save_typed(name: str, type_: str, description: str, body: str) -> str:
    """
    Save a typed memory file with YAML frontmatter.
    Updates MEMORY.md index automatically.
    """
    _ensure_dirs()
    safe_name = re.sub(r"[^\w_-]", "_", name.lower().strip())[:60]
    file_path = _MEMORY_DIR / f"{safe_name}.md"

    content = (
        f"---\n"
        f"name: {safe_name}\n"
        f"description: {description.strip()}\n"
        f"type: {type_}\n"
        f"---\n\n"
        f"{body.strip()}\n"
    )

    with _mem_lock:
        file_path.write_text(content)
        _rebuild_memory_index()

    return f"Memory saved: {safe_name} ({type_})"


def _rebuild_memory_index() -> None:
    """Rebuild MEMORY.md from all files in ~/.hrcode/memory/. Call with _mem_lock held."""
    files = sorted(_MEMORY_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime)
    lines = ["# Memory Index\n"]
    for f in files:
        try:
            text = f.read_text()
            # Parse description from frontmatter
            m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
            desc = m.group(1).strip() if m else f.stem
            lines.append(f"- [{f.stem}]({f.name}) — {desc}")
        except Exception:
            continue
    _MEMORY_INDEX.write_text("\n".join(lines) + "\n")


def memory_list_typed() -> str:
    """Return all typed memory files grouped by type."""
    _ensure_dirs()
    files = sorted(_MEMORY_DIR.glob("*.md"))
    if not files:
        return "No memories saved yet."
    by_type: dict[str, list[str]] = {}
    for f in files:
        try:
            text = f.read_text()
            m_type = re.search(r"^type:\s*(.+)$", text, re.MULTILINE)
            m_desc = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
            t = (m_type.group(1).strip() if m_type else "unknown")
            d = (m_desc.group(1).strip() if m_desc else f.stem)
            by_type.setdefault(t, []).append(f"  - **{f.stem}**: {d}")
        except Exception:
            continue
    out = []
    for t, entries in sorted(by_type.items()):
        out.append(f"### {t.capitalize()}")
        out.extend(entries)
    return "\n".join(out)


def memory_delete(name: str) -> str:
    """Delete a typed memory file and rebuild index."""
    _ensure_dirs()
    safe = re.sub(r"[^\w_-]", "_", name.lower().strip())[:60]
    path = _MEMORY_DIR / f"{safe}.md"
    if not path.exists():
        # try partial match
        matches = list(_MEMORY_DIR.glob(f"*{safe}*.md"))
        if len(matches) == 1:
            path = matches[0]
        elif len(matches) > 1:
            return f"Ambiguous: {[p.stem for p in matches]}. Be more specific."
        else:
            return f"Memory '{name}' not found."
    with _mem_lock:
        path.unlink()
        _rebuild_memory_index()
    return f"Deleted memory: {path.stem}"


def memory_as_context() -> str:
    """
    Return MEMORY.md index + relevant memory bodies for injection into system prompt.
    Reads from typed files; falls back to legacy memory.md if present.
    """
    _ensure_dirs()
    parts: list[str] = []

    # New typed system
    if _MEMORY_INDEX.exists():
        index_text = _MEMORY_INDEX.read_text().strip()
        if index_text and index_text != "# Memory Index":
            parts.append(f"## Persistent Memory\n{index_text}")

    # Load all memory bodies (keep concise — inject full content)
    mem_files = sorted(_MEMORY_DIR.glob("*.md"))
    if mem_files:
        bodies: list[str] = []
        for f in mem_files:
            try:
                text = f.read_text()
                # Strip frontmatter
                body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL).strip()
                if body:
                    m_name = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
                    label  = m_name.group(1).strip() if m_name else f.stem
                    bodies.append(f"**[{label}]** {body}")
            except Exception:
                continue
        if bodies:
            parts.append("### Memory Details\n" + "\n\n".join(bodies))

    # Legacy flat memory.md fallback
    legacy = _HRCODE_DIR / "memory.md"
    if legacy.exists() and not mem_files:
        content = legacy.read_text().strip()
        if content:
            parts.append(f"## Notes\n{content}")

    return ("\n\n" + "\n\n".join(parts) + "\n") if parts else ""


# ════════════════════════════════════════════════════════════════════════════
# AUTO-EXTRACTION  (codetoolcli's SessionMemory pattern)
# ════════════════════════════════════════════════════════════════════════════

def should_extract_memory(
    turns_since_last: int,
    tokens_since_last: int,
    tools_since_last: int,
) -> bool:
    """
    Return True when the conversation has accumulated enough context to be worth
    mining for memories. Mirrors codetoolcli's shouldExtractMemory() logic.
    """
    if turns_since_last < _MEM_MIN_TURNS:
        return False
    token_trigger = tokens_since_last >= _MEM_TOKEN_THRESHOLD
    tool_trigger  = tools_since_last  >= _MEM_TOOL_THRESHOLD
    return token_trigger or tool_trigger


def extract_memories_async(
    messages: list[dict],
    llm_api_key: str,
    llm_base_url: str,
    llm_model: str,
) -> None:
    """
    Spawn a background daemon thread that calls the LLM to extract memories
    from the conversation and saves them to typed files.

    Non-blocking — returns immediately. Uses a lock to prevent concurrent writes.
    """
    def _run():
        try:
            from openai import OpenAI  # type: ignore
            client = OpenAI(api_key=llm_api_key, base_url=llm_base_url or None)

            # Build a concise conversation summary for extraction
            conv_lines: list[str] = []
            for msg in messages:
                role    = msg.get("role", "")
                content = msg.get("content") or ""
                if role in ("user", "assistant") and content:
                    label = "User" if role == "user" else "Assistant"
                    conv_lines.append(f"{label}: {str(content)[:800]}")

            if not conv_lines:
                return

            conv_text = "\n".join(conv_lines[-40:])  # last 40 message halves max

            resp = client.chat.completions.create(
                model=llm_model,
                messages=[
                    {"role": "system",  "content": _EXTRACT_SYSTEM},
                    {"role": "user",    "content": conv_text},
                ],
                temperature=0.1,
                max_tokens=2000,
            )

            raw = (resp.choices[0].message.content or "").strip()
            # Strip markdown code fences if present
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

            try:
                memories = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                print("[memory] extraction returned invalid JSON — skipping")
                return
            if not isinstance(memories, list):
                return

            for mem in memories:
                if not isinstance(mem, dict):
                    continue
                name  = mem.get("name", "")
                type_ = mem.get("type", "project")
                desc  = mem.get("description", "")
                body  = mem.get("body", "")
                if name and body:
                    memory_save_typed(name, type_, desc, body)

        except Exception as _e:
            print(f"[memory] background extraction error: {_e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


# ════════════════════════════════════════════════════════════════════════════
# LEGACY FLAT MEMORY  (kept for /memory add <note> command compatibility)
# ════════════════════════════════════════════════════════════════════════════

_LEGACY_MEMORY_FILE = _HRCODE_DIR / "memory.md"


def memory_add(note: str) -> str:
    """Append a quick note to the legacy flat memory file."""
    _ensure_dirs()
    try:
        existing  = _LEGACY_MEMORY_FILE.read_text() if _LEGACY_MEMORY_FILE.exists() else ""
        timestamp = time.strftime("%Y-%m-%d %H:%M")
        entry     = f"\n- [{timestamp}] {note.strip()}"
        _LEGACY_MEMORY_FILE.write_text(existing.rstrip() + entry + "\n")
        return f"Memory note saved: {note[:80]}"
    except Exception as exc:
        return f"Error saving memory: {exc}"


def memory_list() -> str:
    """Return flat notes + typed memory index."""
    typed = memory_list_typed()
    flat  = ""
    if _LEGACY_MEMORY_FILE.exists():
        content = _LEGACY_MEMORY_FILE.read_text().strip()
        if content:
            flat = f"\n\n### Quick Notes\n{content}"
    return (typed + flat) if (typed + flat).strip() else "No memories yet."


def memory_clear() -> str:
    """Clear all memories (typed files + index + legacy flat file)."""
    _ensure_dirs()
    removed = 0
    for f in _MEMORY_DIR.glob("*.md"):
        f.unlink()
        removed += 1
    if _MEMORY_INDEX.exists():
        _MEMORY_INDEX.write_text("# Memory Index\n")
    if _LEGACY_MEMORY_FILE.exists():
        _LEGACY_MEMORY_FILE.write_text("")
    return f"Cleared {removed} typed memories and quick notes."


# ════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ════════════════════════════════════════════════════════════════════════════

class Session:
    """
    Holds all state for one hrcode session:
      - conversation history (user/assistant pairs)
      - tool log
      - token & cost tracking
      - auto-extraction state
    """

    def __init__(self, session_id: str = None, cwd: str = None):
        _ensure_dirs()
        self.id         = session_id or uuid.uuid4().hex[:8]
        self.cwd        = cwd or os.getcwd()
        self.history: list[tuple[str, str]] = []
        self.tool_log:  list[dict] = []
        self.in_tokens  = 0
        self.out_tokens = 0
        self.turns      = 0
        self.started_at = time.time()
        self._path      = _SESSIONS_DIR / f"{self.id}.json"

        # Auto-extraction tracking
        self._last_extraction_turn:   int = 0
        self._last_extraction_tokens: int = 0
        self._last_extraction_tools:  int = 0

    # ── History ───────────────────────────────────────────────────────────────

    def add_turn(self, query: str, response: str) -> None:
        self.history.append((query, response[:12000]))
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]
        self.turns += 1

    def build_history_messages(self) -> list[dict]:
        """Convert (query, response) pairs to OpenAI message format."""
        msgs: list[dict] = []
        for q, r in self.history:
            msgs.append({"role": "user",      "content": q})
            msgs.append({"role": "assistant", "content": r})
        return msgs

    # ── Cost tracking ─────────────────────────────────────────────────────────

    def add_usage(self, in_tok: int, out_tok: int) -> None:
        self.in_tokens  += in_tok
        self.out_tokens += out_tok
        try:
            data = json.loads(_COST_FILE.read_text()) if _COST_FILE.exists() else {}
            data["total_in"]  = data.get("total_in",  0) + in_tok
            data["total_out"] = data.get("total_out", 0) + out_tok
            _COST_FILE.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def cost_summary(self) -> str:
        lines = [
            f"Session **{self.id}**",
            f"  Turns      : {self.turns}",
            f"  In  tokens : {self.in_tokens:,}",
            f"  Out tokens : {self.out_tokens:,}",
            f"  Tools used : {len(self.tool_log)}",
        ]
        if _COST_FILE.exists():
            try:
                data = json.loads(_COST_FILE.read_text())
                lines += [
                    "",
                    "Lifetime (all sessions):",
                    f"  In  tokens : {data.get('total_in',  0):,}",
                    f"  Out tokens : {data.get('total_out', 0):,}",
                ]
            except Exception:
                pass
        return "\n".join(lines)

    # ── Auto-extraction ───────────────────────────────────────────────────────

    def maybe_extract_memories(
        self,
        messages: list[dict],
        llm_api_key: str,
        llm_base_url: str,
        llm_model: str,
    ) -> None:
        """
        Called after each turn. Fires background memory extraction if thresholds met.
        Mirrors codetoolcli's post-sampling hook pattern.
        """
        turns_since  = self.turns      - self._last_extraction_turn
        tokens_since = self.in_tokens  - self._last_extraction_tokens
        tools_since  = len(self.tool_log) - self._last_extraction_tools

        if should_extract_memory(turns_since, tokens_since, tools_since):
            self._last_extraction_turn   = self.turns
            self._last_extraction_tokens = self.in_tokens
            self._last_extraction_tools  = len(self.tool_log)
            extract_memories_async(messages, llm_api_key, llm_base_url, llm_model)

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self) -> None:
        try:
            data = {
                "id":         self.id,
                "cwd":        self.cwd,
                "history":    self.history,
                "in_tokens":  self.in_tokens,
                "out_tokens": self.out_tokens,
                "turns":      self.turns,
                "started_at": self.started_at,
                "saved_at":   time.time(),
            }
            self._path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    @classmethod
    def load(cls, session_id: str) -> "Optional[Session]":
        _ensure_dirs()
        path = _SESSIONS_DIR / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            data    = json.loads(path.read_text())
            session = cls(session_id=data["id"], cwd=data.get("cwd"))
            session.history    = [tuple(h) for h in data.get("history", [])]
            session.in_tokens  = data.get("in_tokens",  0)
            session.out_tokens = data.get("out_tokens", 0)
            session.turns      = data.get("turns",      0)
            session.started_at = data.get("started_at", time.time())
            return session
        except Exception:
            return None

    @classmethod
    def list_recent(cls, n: int = 10) -> list[dict]:
        _ensure_dirs()
        sessions: list[dict] = []
        for p in sorted(_SESSIONS_DIR.glob("*.json"),
                        key=lambda x: x.stat().st_mtime, reverse=True)[:n]:
            try:
                data    = json.loads(p.read_text())
                history = data.get("history", [])
                preview = history[-1][0][:60] if history else "(empty)"
                sessions.append({
                    "id":      data["id"],
                    "turns":   data.get("turns", 0),
                    "preview": preview,
                    "mtime":   p.stat().st_mtime,
                })
            except Exception:
                continue
        return sessions
