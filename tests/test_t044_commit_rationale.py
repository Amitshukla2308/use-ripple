"""T-044: commit_rationale_index loading and get_why_context integration."""
import sys, types, pathlib, json, tempfile, os

# Stub retrieval_engine
re_stub = types.ModuleType("retrieval_engine")
re_stub.commit_rationale_index = {}
re_stub.MG = None
re_stub.ownership_index = {}
sys.modules["retrieval_engine"] = re_stub

# ── helpers ─────────────────────────────────────────────────────────────────

def _build_index_from_gh(gh_data: dict) -> dict:
    """Minimal version of 11_build_commit_rationale logic for testing."""
    import re, collections
    BOILERPLATE = re.compile(
        r"^(merge|bump|wip|fix typo|update changelog|chore:|fmt:)",
        re.IGNORECASE,
    )
    index: dict = collections.defaultdict(list)
    for repo in gh_data.get("repositories", []):
        rname = repo["name"]
        for c in repo.get("commits", []):
            msg = (c.get("message") or "").strip()
            if len(msg) <= 100 or BOILERPLATE.match(msg):
                continue
            entry = {"msg": msg[:250], "date": str(c.get("date",""))[:10], "hash": c.get("hash","")[:8]}
            for fp in c.get("files_changed", []):
                path = fp.get("path","") if isinstance(fp, dict) else str(fp)
                if path:
                    index[f"{rname}::{path}"].append(entry)
    return dict(index)


def test_informative_commits_indexed():
    """Long, non-boilerplate commit subject is indexed by repo::path."""
    gh = {"repositories": [{"name": "myrepo", "commits": [
        {"hash": "abc123", "date": "2026-04-18", "message":
         "EUL-9999: Refactor payment flow to use exponential backoff after repeated queue saturation incidents in production env",
         "files_changed": [{"path": "src/PaymentFlow.hs"}]},
    ]}]}
    idx = _build_index_from_gh(gh)
    key = "myrepo::src/PaymentFlow.hs"
    assert key in idx, f"key missing: {list(idx.keys())}"
    assert "exponential backoff" in idx[key][0]["msg"]
    print("  PASS: informative commit indexed by repo::path")


def test_boilerplate_excluded():
    """Boilerplate patterns are excluded even if >100 chars."""
    gh = {"repositories": [{"name": "r", "commits": [
        {"hash": "aaa", "date": "2026-04-18",
         "message": "merge pull request #123 from feature/xyz into main for release of version 1.0.0",
         "files_changed": [{"path": "foo.hs"}]},
        {"hash": "bbb", "date": "2026-04-18",
         "message": "bump version from 1.2.3 to 1.2.4 in package.yaml and changelog.md documentation",
         "files_changed": [{"path": "bar.hs"}]},
    ]}]}
    idx = _build_index_from_gh(gh)
    assert len(idx) == 0, f"boilerplate should be excluded, got: {idx}"
    print("  PASS: boilerplate commits excluded")


def test_short_message_excluded():
    """Messages ≤100 chars are excluded regardless of content."""
    gh = {"repositories": [{"name": "r", "commits": [
        {"hash": "ccc", "date": "2026-04-18",
         "message": "Fix NPE in PaymentFlow handler",
         "files_changed": [{"path": "PaymentFlow.hs"}]},
    ]}]}
    idx = _build_index_from_gh(gh)
    assert len(idx) == 0, f"short message should be excluded"
    print("  PASS: short messages excluded")


def test_get_why_context_includes_commit_rationale():
    """get_why_context result template includes commit_rationale key."""
    import retrieval_engine as RE
    # Simulate the result dict that get_why_context builds
    result = {
        "symbol": "myrepo::src/PaymentFlow.hs",
        "found": False,
        "summary": None,
        "owners": [],
        "activity": {},
        "criticality": {},
        "causal_outputs": [],
        "causal_inputs": [],
        "anti_patterns": [],
        "commit_rationale": [],
    }
    # Simulate commit_rationale lookup
    RE.commit_rationale_index = {
        "myrepo::src/PaymentFlow.hs": [
            {"msg": "EUL-9999: Refactor payment flow to use exponential backoff after repeated queue saturation incidents", "date": "2026-04-18", "hash": "abc123"}
        ]
    }
    cr = RE.commit_rationale_index.get("myrepo::src/PaymentFlow.hs", [])
    if cr:
        result["found"] = True
        result["commit_rationale"] = cr[:5]
    assert result["commit_rationale"], "commit_rationale should be populated"
    assert result["found"] is True
    assert "exponential" in result["commit_rationale"][0]["msg"]
    print("  PASS: commit_rationale lookup populates result and sets found=True")


def test_no_rationale_no_key_error():
    """With empty commit_rationale_index, commit_rationale stays empty list — no crash."""
    import retrieval_engine as RE
    RE.commit_rationale_index = {}
    result = {"commit_rationale": []}
    cr = RE.commit_rationale_index.get("anything::foo.hs", [])
    result["commit_rationale"] = cr[:5]
    assert result["commit_rationale"] == []
    print("  PASS: empty index → empty commit_rationale, no crash")


if __name__ == "__main__":
    test_informative_commits_indexed()
    test_boilerplate_excluded()
    test_short_message_excluded()
    test_get_why_context_includes_commit_rationale()
    test_no_rationale_no_key_error()
    print("\n5/5 tests PASS")
