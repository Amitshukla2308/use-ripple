"""AI-code provenance reader for Ripple.

Consumes provenance signals produced by vendor-agnostic AI-attribution tools
(Git AI, Agent Blame, Tabnine) and exposes them to `check_my_changes` so
critical Guard checks can be escalated on AI-generated lines.

Strategy: don't rebuild provenance tracking. Read what existing tools produce.

Supported backends:
  - git-notes  (default)  — reads `git notes --ref=ai-provenance`
  - json       (fallback) — reads a `.hr_provenance.json` file next to the repo
                             root; useful for tests and environments without
                             a real provenance tool

Interface:
  read_provenance(file_path: str | Path) -> dict[int, dict]
    Returns {line_number: {"agent": str, "session": str, "timestamp": str, ...}}
    Empty dict if no provenance data for this file.

  is_ai_line(file_path, line_number) -> bool
  count_ai_lines(file_path) -> int

Env vars:
  HR_PROVENANCE_BACKEND   - "git-notes" | "json" | "off" (default "git-notes")
  HR_PROVENANCE_REF       - git notes ref (default "ai-provenance")
  HR_PROVENANCE_JSON_PATH - path to JSON fallback (default ".hr_provenance.json"
                            resolved against the file's nearest git root)
"""
from __future__ import annotations
import json
import os
import pathlib
import subprocess
from functools import lru_cache


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _repo_root(path: pathlib.Path) -> pathlib.Path | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(path.parent if path.is_file() else path),
             "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return None
        return pathlib.Path(r.stdout.strip())
    except Exception:
        return None


def _parse_git_ai_note(note_text: str) -> dict:
    """Parse a Git AI Authorship Log note. Tolerates JSON or line-range format.
    Returns {line_number: metadata}."""
    out: dict = {}
    if not note_text.strip():
        return out
    # First try JSON
    try:
        data = json.loads(note_text)
    except Exception:
        data = None

    if isinstance(data, dict):
        # Expected Git AI shape: {"lines": [{"start":N,"end":M,"agent":"...","session":"..."}, ...]}
        entries = data.get("lines") or data.get("entries") or []
        for e in entries:
            try:
                s = int(e.get("start", e.get("line", 0)))
                end = int(e.get("end", s))
                meta = {k: v for k, v in e.items() if k not in ("start", "end", "line")}
                for ln in range(s, end + 1):
                    out[ln] = meta
            except Exception:
                continue
        return out

    # Fallback: parse line-range format "L12-15 agent=claude session=abc"
    for line in note_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if not parts or not parts[0].startswith("L"):
            continue
        rng = parts[0][1:]
        try:
            if "-" in rng:
                s, e = rng.split("-", 1)
                s_i, e_i = int(s), int(e)
            else:
                s_i = e_i = int(rng)
        except ValueError:
            continue
        meta = {}
        for kv in parts[1:]:
            if "=" in kv:
                k, v = kv.split("=", 1)
                meta[k.strip()] = v.strip()
        for ln in range(s_i, e_i + 1):
            out[ln] = meta
    return out


def _read_git_notes(file_path: pathlib.Path, ref: str) -> dict:
    root = _repo_root(file_path)
    if root is None:
        return {}
    try:
        rel = file_path.resolve().relative_to(root)
    except ValueError:
        return {}
    try:
        head_cp = subprocess.run(
            ["git", "-C", str(root), "log", "-n", "1", "--pretty=%H", "--", str(rel)],
            capture_output=True, text=True, timeout=5,
        )
        if head_cp.returncode != 0 or not head_cp.stdout.strip():
            return {}
        commit = head_cp.stdout.strip()
        notes_cp = subprocess.run(
            ["git", "-C", str(root), "notes", f"--ref={ref}", "show", commit],
            capture_output=True, text=True, timeout=5,
        )
        if notes_cp.returncode != 0:
            return {}
        all_lines = _parse_git_ai_note(notes_cp.stdout)
        filtered: dict = {}
        for ln, meta in all_lines.items():
            note_file = meta.get("file") or meta.get("path")
            if note_file and note_file != str(rel):
                continue
            filtered[ln] = meta
        return filtered
    except Exception:
        return {}


def _read_json(file_path: pathlib.Path) -> dict:
    root = _repo_root(file_path) or file_path.parent
    candidate = pathlib.Path(_env("HR_PROVENANCE_JSON_PATH",
                                    str(root / ".hr_provenance.json")))
    if not candidate.is_file():
        return {}
    try:
        data = json.loads(candidate.read_text())
    except Exception:
        return {}
    try:
        rel = str(file_path.resolve().relative_to(root))
    except ValueError:
        rel = str(file_path)
    entries = data.get("files", {}).get(rel, [])
    out: dict = {}
    for e in entries:
        s = int(e.get("start", e.get("line", 0)))
        end = int(e.get("end", s))
        meta = {k: v for k, v in e.items() if k not in ("start", "end", "line")}
        for ln in range(s, end + 1):
            out[ln] = meta
    return out


@lru_cache(maxsize=512)
def read_provenance(file_path: str) -> tuple:
    """Return a sorted tuple of (line_number, metadata_json_str) for `file_path`.

    Tuple form keeps lru_cache hashable. Consumers usually call the convenience
    helpers below.
    """
    backend = _env("HR_PROVENANCE_BACKEND", "git-notes")
    if backend == "off":
        return ()
    p = pathlib.Path(file_path)
    if backend == "json":
        d = _read_json(p)
    elif backend == "git-notes":
        d = _read_git_notes(p, _env("HR_PROVENANCE_REF", "ai-provenance"))
    else:
        d = {}
    return tuple(sorted((ln, json.dumps(meta, sort_keys=True)) for ln, meta in d.items()))


def provenance_dict(file_path: str) -> dict:
    return {ln: json.loads(meta) for ln, meta in read_provenance(file_path)}


def is_ai_line(file_path: str, line_number: int) -> bool:
    return any(ln == line_number for ln, _ in read_provenance(file_path))


def count_ai_lines(file_path: str) -> int:
    return len(read_provenance(file_path))


def summarize(file_paths: list) -> dict:
    """Aggregate across a set of files. Returns {total_ai_lines, files_with_ai, by_file}."""
    total = 0
    by_file = {}
    files_with_ai = 0
    for fp in file_paths or []:
        c = count_ai_lines(fp)
        if c > 0:
            files_with_ai += 1
            by_file[fp] = c
            total += c
    return {"total_ai_lines": total, "files_with_ai": files_with_ai, "by_file": by_file}
