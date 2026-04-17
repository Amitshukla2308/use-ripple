"""
Multi-language comment extraction via tree-sitter.
Used by Guard to check comment-code alignment in Haskell, Rust, JS, Go, Groovy.

Supports: python, haskell, rust, javascript, typescript, go, groovy, java, kotlin
"""
from __future__ import annotations
import functools
from dataclasses import dataclass


@dataclass
class Comment:
    line: int        # 1-indexed
    text: str        # cleaned comment text (no delimiters)
    raw: str         # original source fragment
    language: str


_LANG_MAP = {
    "python":     "tree_sitter_python",
    "haskell":    "tree_sitter_haskell",
    "rust":       "tree_sitter_rust",
    "javascript": "tree_sitter_javascript",
    "typescript": "tree_sitter_javascript",  # uses JS grammar
    "go":         "tree_sitter_go",
    "groovy":     "tree_sitter_groovy",
    "java":       "tree_sitter_java",
    "kotlin":     "tree_sitter_kotlin",
}

_COMMENT_NODES = {
    "python":     {"comment"},
    "haskell":    {"comment", "ncomment"},
    "rust":       {"line_comment", "block_comment"},
    "javascript": {"comment"},
    "go":         {"comment"},
    "groovy":     {"comment"},
    "java":       {"line_comment", "block_comment"},
    "kotlin":     {"multiline_comment", "line_comment"},
}


@functools.lru_cache(maxsize=16)
def _get_parser(language: str):
    try:
        import tree_sitter
        mod_name = _LANG_MAP[language]
        lang_mod = __import__(mod_name)
        lang = tree_sitter.Language(lang_mod.language())
        parser = tree_sitter.Parser(lang)
        return parser
    except Exception:
        return None


def extract_comments(source: str, language: str) -> list[Comment]:
    """Extract all comments from source code using tree-sitter AST."""
    lang = language.lower()
    if lang not in _LANG_MAP:
        return _fallback_extract(source, lang)

    parser = _get_parser(lang)
    if parser is None:
        return _fallback_extract(source, lang)

    tree = parser.parse(source.encode())
    comments = []
    node_types = _COMMENT_NODES.get(lang, {"comment", "line_comment", "block_comment"})

    def walk(node):
        if node.type in node_types:
            raw = source[node.start_byte:node.end_byte]
            text = _clean_comment(raw, lang)
            if text:
                comments.append(Comment(
                    line=node.start_point[0] + 1,
                    text=text,
                    raw=raw,
                    language=lang,
                ))
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    return comments


def _clean_comment(raw: str, language: str) -> str:
    """Strip comment delimiters and whitespace."""
    text = raw.strip()
    # Haskell: -- comment or {- ... -}
    if text.startswith("--"):
        return text[2:].strip()
    if text.startswith("{-") and text.endswith("-}"):
        return text[2:-2].strip()
    # Rust/JS/Go/Groovy: // comment or /* ... */
    if text.startswith("//"):
        return text[2:].strip()
    if text.startswith("/*") and text.endswith("*/"):
        return text[2:-2].strip()
    # Python: # comment
    if text.startswith("#"):
        return text[1:].strip()
    return text


def _fallback_extract(source: str, language: str) -> list[Comment]:
    """Regex fallback for languages not in tree-sitter map."""
    import re
    comments = []
    patterns = {
        "python": r"#(.*)",
        "haskell": r"--(.*)",
        "rust": r"//(.*)",
        "javascript": r"//(.*)",
        "typescript": r"//(.*)",
        "go": r"//(.*)",
        "groovy": r"//(.*)",
    }
    pat = patterns.get(language, r"#(.*)|//(.*)")
    for i, line in enumerate(source.splitlines(), 1):
        m = re.search(pat, line)
        if m:
            text = next(g for g in m.groups() if g is not None).strip()
            if text:
                comments.append(Comment(line=i, text=text, raw=line, language=language))
    return comments


def detect_language(filename: str) -> str | None:
    """Infer language from file extension."""
    ext_map = {
        ".py": "python", ".hs": "haskell", ".lhs": "haskell",
        ".rs": "rust", ".js": "javascript", ".ts": "typescript",
        ".jsx": "javascript", ".tsx": "typescript",
        ".go": "go", ".groovy": "groovy", ".gradle": "groovy",
        ".java": "java", ".kt": "kotlin",
    }
    from pathlib import Path
    return ext_map.get(Path(filename).suffix.lower())
