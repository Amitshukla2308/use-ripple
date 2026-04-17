"""
Multi-language Guard checker using tree-sitter comment extraction.
Handles Haskell, Rust, JavaScript, Go — languages not covered by the
Python-regex-based comment_code_checker.py.

O-8 Milestone 3: extends Guard to >= 3 languages deterministically.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass
class MLFinding:
    file: str
    line: int
    pattern: str
    severity: str   # critical | warning | info
    message: str
    comment: str = ""
    code: str = ""


_IMPERATIVE_LOCK = re.compile(
    r"^(?:acquire|lock|hold|take|grab|withMVar|withMutex|modifyMVar|"
    r"atomically)\b.*\b(?:lock|mutex|mvar|semaphore|guard)\b",
    re.IGNORECASE,
)
_BEFORE_MUTATION = re.compile(
    r"\bbefore\b.*\b(?:modif|updat|writ|set|assign|mutate|insert|push|append)\w*",
    re.IGNORECASE,
)

# Language-specific lock acquire / release patterns
_LOCK_ACQUIRE = {
    "haskell": re.compile(r"\b(withMVar|takeMVar|modifyMVar|withMutex|atomically|lock)\b"),
    "rust":    re.compile(r"\.(lock|write|read)\s*\(\s*\)|\bMutex::|RwLock::|lock\.lock\b"),
    "go":      re.compile(r"\.(Lock|RLock)\s*\(\s*\)"),
    "javascript": re.compile(r"\b(acquire|lock)\s*\("),
}
_LOCK_RELEASE = {
    "haskell": re.compile(r"\b(putMVar|releaseMVar|unlock)\b"),
    "rust":    re.compile(r"\b(drop\s*\(|unlock|MutexGuard)\b"),
    "go":      re.compile(r"\.(Unlock|RUnlock)\s*\(\s*\)"),
    "javascript": re.compile(r"\b(release|unlock)\s*\("),
}
_TRANSACTION_ACQUIRE = {
    "haskell": re.compile(r"\b(atomically|runDB|withTransaction|begin)\b"),
    "rust":    re.compile(r"\b(begin_transaction|transaction|begin\b)\b"),
}
_TRANSACTION_COMMIT = {
    "haskell": re.compile(r"\b(commit|runDB|atomically)\b"),
    "rust":    re.compile(r"\.(commit|rollback)\s*\("),
}

_STATE_MUTATION = re.compile(
    r"(?:"
    r"\w+\s*\[.+?\]\s*="       # dict/array assignment x[k] = v
    r"|\w+\.\w+\s*="           # attribute assignment x.y = v
    r"|insert\s*\("            # map/hashmap insert
    r"|push\s*\("              # vec push
    r"|modify\s*\("            # mutable reference modify
    r"|writeIORef\s+"          # Haskell IORef write
    r"|atomicWriteIORef\s+"    # Haskell atomic IORef write
    r")"
)


def check_multilang_guard(source: str, filename: str, language: str) -> list[MLFinding]:
    """Run Guard checks on non-Python source using tree-sitter comment extraction."""
    from serve.tree_sitter_extractor import extract_comments
    findings: list[MLFinding] = []
    lines = source.splitlines()
    comments = extract_comments(source, language)

    acq_pat = _LOCK_ACQUIRE.get(language)
    rel_pat = _LOCK_RELEASE.get(language)

    for cmt in comments:
        cmt_lower = cmt.text.lower()
        _has_lock_word = ("lock" in cmt_lower or "mutex" in cmt_lower or "mvar" in cmt_lower)
        # Check 1: imperative lock comment + premature release
        if (acq_pat and rel_pat and _has_lock_word and
                (_IMPERATIVE_LOCK.match(cmt.text) or _BEFORE_MUTATION.search(cmt.text))):
            # Find acquire line after comment
            acq_line = None
            for j in range(cmt.line, min(cmt.line + 5, len(lines))):
                if acq_pat.search(lines[j]):
                    acq_line = j
                    break
            if acq_line is None:
                continue
            # Find release line
            rel_line = None
            for j in range(acq_line + 1, min(acq_line + 40, len(lines))):
                if rel_pat.search(lines[j]):
                    rel_line = j
                    break
            if rel_line is None:
                continue
            # Check for state mutations after release
            for k in range(rel_line + 1, min(rel_line + 10, len(lines))):
                stripped = lines[k].strip()
                if not stripped:
                    continue
                if _STATE_MUTATION.search(lines[k]):
                    findings.append(MLFinding(
                        file=filename, line=rel_line + 1,
                        pattern="lock-premature-release",
                        severity="critical",
                        message=(
                            f"Lock released (line {rel_line+1}) before promised state "
                            f"mutation (line {k+1}) — comment says '{cmt.text[:60]}'"
                        ),
                        comment=cmt.text,
                        code=f"{lines[rel_line].strip()} → {lines[k].strip()}",
                    ))
                    break

        # Check 2: comment-action mismatch in non-Python
        if _IMPERATIVE_LOCK.match(cmt.text) and acq_pat:
            # Comment promises locking — check that acquire actually follows
            found_acquire = False
            for j in range(cmt.line, min(cmt.line + 5, len(lines))):
                if acq_pat.search(lines[j]):
                    found_acquire = True
                    break
            if not found_acquire:
                findings.append(MLFinding(
                    file=filename, line=cmt.line,
                    pattern="comment-action-mismatch",
                    severity="warning",
                    message=f"Comment promises locking but no acquire found within 5 lines",
                    comment=cmt.text,
                    code=lines[cmt.line - 1].strip() if cmt.line <= len(lines) else "",
                ))

    # Haskell-specific: withMVar/withMutex bracket scope check
    # withMVar/modifyMVar uses a lambda — mutations after the bracket call are outside the lock
    if language == "haskell":
        _bracket_pat = re.compile(r"\b(withMVar|withMutex|modifyMVar)\s+\w+")
        _haskell_mutation = re.compile(r"\b(writeIORef|atomicWriteIORef|modifyIORef|putMVar|"
                                       r"writeSTRef|insert|modify|update)\b")
        for cmt in comments:
            if not (_IMPERATIVE_LOCK.match(cmt.text) or _BEFORE_MUTATION.search(cmt.text)):
                continue
            # Find withMVar call after the comment
            bracket_line = None
            bracket_indent = None
            for j in range(cmt.line, min(cmt.line + 10, len(lines))):
                if _bracket_pat.search(lines[j]):
                    bracket_line = j
                    bracket_indent = len(lines[j]) - len(lines[j].lstrip())
                    break
            if bracket_line is None:
                continue
            # Find the end of the withMVar block — look for a line at <= bracket indentation
            # that isn't the bracket line itself (i.e., code outside the lambda)
            for k in range(bracket_line + 1, min(bracket_line + 25, len(lines))):
                stripped = lines[k].strip()
                if not stripped or stripped.startswith("--"):
                    continue
                curr_indent = len(lines[k]) - len(lines[k].lstrip())
                if curr_indent <= bracket_indent and _haskell_mutation.search(lines[k]):
                    findings.append(MLFinding(
                        file=filename, line=bracket_line + 1,
                        pattern="lock-premature-release",
                        severity="critical",
                        message=(
                            f"State mutation (line {k+1}) is outside withMVar/withMutex scope "
                            f"(bracket at line {bracket_line+1}) — comment promises lock protection"
                        ),
                        comment=cmt.text,
                        code=f"{lines[bracket_line].strip()} → {lines[k].strip()}",
                    ))
                    break

    return findings


def scan_file_multilang(filepath: str) -> list[MLFinding]:
    """Scan a single file for multi-language Guard findings."""
    from serve.tree_sitter_extractor import detect_language
    language = detect_language(filepath)
    if language in (None, "python"):
        return []  # Python handled by comment_code_checker.py
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            source = f.read()
    except OSError:
        return []
    return check_multilang_guard(source, filepath, language)
