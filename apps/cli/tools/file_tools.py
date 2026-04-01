"""
file_tools.py — File system tools: read, write, edit, glob, grep.

Ported from codetoolcli (FileReadTool, FileWriteTool, FileEditTool, GlobTool, GrepTool).
Uses only Python stdlib + optional ripgrep for fast grep.
"""
import glob as _glob
import os
import pathlib
import re
import subprocess

MAX_READ_LINES = int(os.environ.get("HRCODE_MAX_READ_LINES", "2000"))
MAX_READ_BYTES = int(os.environ.get("HRCODE_MAX_READ_BYTES", "102400"))  # 100 KB


def _cwd() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HRCODE_CWD") or os.getcwd())


def _resolve(path: str) -> pathlib.Path:
    p = pathlib.Path(path)
    resolved = (p if p.is_absolute() else _cwd() / p).resolve()
    # Guard: don't allow access outside cwd or home directory
    cwd = _cwd()
    home = pathlib.Path.home()
    if not (str(resolved).startswith(str(cwd)) or str(resolved).startswith(str(home))):
        raise PermissionError(f"Path {resolved} is outside allowed directories")
    return resolved


# ── read_file ─────────────────────────────────────────────────────────────────

def read_file(file_path: str, offset: int = 1, limit: int = None) -> str:
    """Read a file with 1-based line numbers. offset/limit narrow the window."""
    try:
        p = _resolve(file_path)
        if not p.exists():
            return f"File not found: {file_path}"
        if not p.is_file():
            return f"Not a file: {file_path}"

        size = p.stat().st_size
        effective_limit = limit or (MAX_READ_LINES if size > MAX_READ_BYTES else None)

        lines = p.read_text(errors="replace").splitlines()
        total = len(lines)

        start = max(0, (offset or 1) - 1)
        end   = min(total, start + (effective_limit or total))

        numbered = "\n".join(
            f"{i+1:4d}\t{line}" for i, line in enumerate(lines[start:end], start=start)
        )
        header = f"File: {file_path}  ({total} lines total"
        if start > 0 or end < total:
            header += f", showing lines {start+1}–{end}"
        header += ")"
        return f"{header}\n{numbered}"
    except Exception as exc:
        return f"Error reading {file_path}: {exc}"


# ── write_file ────────────────────────────────────────────────────────────────

def write_file(file_path: str, content: str) -> str:
    """Write content to a file (creates or overwrites)."""
    try:
        p = _resolve(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        lines = content.count("\n") + (1 if content else 0)
        return f"Written: {file_path}  ({lines} lines, {len(content):,} bytes)"
    except Exception as exc:
        return f"Error writing {file_path}: {exc}"


# ── edit_file ─────────────────────────────────────────────────────────────────

def edit_file(file_path: str, old_string: str, new_string: str,
              replace_all: bool = False) -> str:
    """
    Replace an exact string occurrence in a file.
    Fails if old_string is not found or is not unique (unless replace_all=True).
    """
    try:
        p = _resolve(file_path)
        if not p.exists():
            return f"File not found: {file_path}"

        content = p.read_text(errors="replace")
        count   = content.count(old_string)

        if count == 0:
            preview = old_string[:100].replace("\n", "↵")
            return (f"Error: string not found in {file_path}.\n"
                    f"Searched for: {preview!r}")

        if count > 1 and not replace_all:
            return (f"Error: string appears {count} times in {file_path}. "
                    "Add more surrounding context to make it unique, "
                    "or set replace_all=true to replace all occurrences.")

        if replace_all:
            new_content  = content.replace(old_string, new_string)
            replacements = count
        else:
            new_content  = content.replace(old_string, new_string, 1)
            replacements = 1

        p.write_text(new_content)
        return (f"Edited: {file_path}  "
                f"({replacements} replacement{'s' if replacements > 1 else ''})")
    except Exception as exc:
        return f"Error editing {file_path}: {exc}"


# ── glob_files ────────────────────────────────────────────────────────────────

def glob_files(pattern: str, path: str = None) -> str:
    """Find files matching a glob pattern. Returns paths sorted by modification time."""
    try:
        base = pathlib.Path(path or _cwd())
        full_pattern = (pattern if pathlib.Path(pattern).is_absolute()
                        else str(base / pattern))

        matches = _glob.glob(full_pattern, recursive=True)
        if not matches:
            return f"No files found matching: {pattern}"

        matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)

        lines = [f"Found {len(matches)} file(s) matching '{pattern}':"]
        for m in matches[:200]:
            try:
                rel = os.path.relpath(m, base)
            except ValueError:
                rel = m
            lines.append(f"  {rel}")
        if len(matches) > 200:
            lines.append(f"  ... and {len(matches) - 200} more")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error in glob: {exc}"


# ── grep_files ────────────────────────────────────────────────────────────────

def grep_files(pattern: str, path: str = None, file_glob: str = None,
               case_insensitive: bool = False, context_lines: int = 0) -> str:
    """Search file contents with a regex pattern. Uses rg when available."""
    base = str(path or _cwd())

    # ── Try ripgrep first (much faster) ──────────────────────────────────────
    try:
        args = ["rg", "--line-number", "--no-heading", "--color=never"]
        if case_insensitive:
            args.append("-i")
        if context_lines:
            args.extend(["-C", str(context_lines)])
        if file_glob:
            args.extend(["--glob", file_glob])
        args.extend(["--", pattern, base])

        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        output = result.stdout.strip()
        if output or result.returncode == 0:
            if not output:
                return f"No matches for '{pattern}'."
            lines = output.splitlines()
            if len(lines) > 500:
                output = "\n".join(lines[:500]) + f"\n... [{len(lines)-500} more lines]"
            return f"Grep '{pattern}':\n{output}"
    except FileNotFoundError:
        pass  # rg not available

    # ── Python stdlib fallback ────────────────────────────────────────────────
    flags = re.IGNORECASE if case_insensitive else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as e:
        return f"Invalid regex: {e}"

    results: list[str] = []
    search_path = pathlib.Path(base)

    for fp in search_path.rglob(file_glob or "*"):
        if not fp.is_file():
            continue
        try:
            for i, line in enumerate(fp.read_text(errors="replace").splitlines(), 1):
                if rx.search(line):
                    try:
                        rel = os.path.relpath(str(fp), base)
                    except ValueError:
                        rel = str(fp)
                    results.append(f"{rel}:{i}: {line}")
                    if len(results) >= 500:
                        break
        except Exception:
            continue
        if len(results) >= 500:
            break

    if not results:
        return f"No matches for '{pattern}'."
    return f"Grep '{pattern}' ({len(results)} matches):\n" + "\n".join(results)
