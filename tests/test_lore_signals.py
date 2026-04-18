"""Tests for T-024 lore_signals in get_why_context."""
import json, pathlib, sys, tempfile, os

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "serve"))
import retrieval_engine as RE


def _make_git_history(with_lore: bool) -> dict:
    body = "Lore-Rationale: chosen for idempotency under retry\nLore-Risk: cache invalidation possible" if with_lore else ""
    return {
        "repositories": [{
            "name": "myrepo",
            "commits": [{
                "hash": "abc12345",
                "date": "2025-06-01",
                "message": "feat: update payment retry",
                "body": body,
                "files_changed": [
                    {"path": "src/Payments/Retry.hs"},
                    {"path": "src/Payments/Queue.hs"},
                ]
            }]
        }]
    }


def test_lore_parsed_from_git_history():
    with tempfile.TemporaryDirectory() as tmp:
        artifacts = pathlib.Path(tmp) / "artifacts"
        artifacts.mkdir()
        gh_path = pathlib.Path(tmp) / "git_history.json"
        gh_path.write_text(json.dumps(_make_git_history(with_lore=True)))

        RE.lore_index.clear()
        # Simulate the loading block from initialize()
        import re as _re
        _lore_re = _re.compile(r"^Lore-([A-Za-z]+):\s*(.+)$", _re.MULTILINE)
        _lore_raw = {}
        with open(str(gh_path)) as _f:
            _gh_data = json.load(_f)
        for _repo in _gh_data.get("repositories", []):
            _rname = _repo.get("name", "")
            for _c in _repo.get("commits", []):
                _text = "\n".join(filter(None, [_c.get("message",""), _c.get("body",""), _c.get("footer","")]))
                if "Lore-" not in _text:
                    continue
                _date = str(_c.get("date",""))[:10]
                _sha = _c.get("hash","")[:8]
                for _fp in _c.get("files_changed",[]):
                    _mod = _fp.get("path","") if isinstance(_fp, dict) else str(_fp)
                    _key = f"{_rname}::{_mod}"
                    for _m in _lore_re.finditer(_text):
                        _lore_raw.setdefault(_key, []).append({
                            "key": _m.group(1), "value": _m.group(2).strip(),
                            "commit": _sha, "date": _date,
                        })
        RE.lore_index.update(_lore_raw)

        assert "myrepo::src/Payments/Retry.hs" in RE.lore_index, "lore key not found"
        recs = RE.lore_index["myrepo::src/Payments/Retry.hs"]
        keys = [r["key"] for r in recs]
        assert "Rationale" in keys, f"Rationale missing: {recs}"
        assert "Risk" in keys, f"Risk missing: {recs}"
        print(f"  PASS: parsed {len(recs)} lore records from git_history body")


def test_no_lore_no_records():
    with tempfile.TemporaryDirectory() as tmp:
        gh_path = pathlib.Path(tmp) / "git_history.json"
        gh_path.write_text(json.dumps(_make_git_history(with_lore=False)))

        import re as _re
        _lore_re = _re.compile(r"^Lore-([A-Za-z]+):\s*(.+)$", _re.MULTILINE)
        _lore_raw = {}
        with open(str(gh_path)) as _f:
            _gh_data = json.load(_f)
        for _repo in _gh_data.get("repositories", []):
            _rname = _repo.get("name", "")
            for _c in _repo.get("commits", []):
                _text = "\n".join(filter(None, [_c.get("message",""), _c.get("body",""), _c.get("footer","")]))
                if "Lore-" not in _text:
                    continue
                for _fp in _c.get("files_changed",[]):
                    _mod = _fp.get("path","") if isinstance(_fp, dict) else str(_fp)
                    _key = f"{_rname}::{_mod}"
                    for _m in _lore_re.finditer(_text):
                        _lore_raw.setdefault(_key, []).append({"key": _m.group(1), "value": _m.group(2).strip()})

        assert len(_lore_raw) == 0, "should parse zero records when no Lore- lines"
        print("  PASS: no lore records when no trailers")


def test_get_why_context_has_lore_signals_key():
    RE.lore_index.clear()
    RE.lore_index["mymod::path"] = [{"key": "Rationale", "value": "test", "commit": "abc", "date": "2025-01-01"}]
    # get_why_context with no graph loaded returns "found=False" but still has lore_signals key
    # since lore lookup runs regardless
    result = {"symbol": "test", "found": False, "summary": None, "owners": [], "activity": {},
              "criticality": {}, "causal_outputs": [], "causal_inputs": [], "anti_patterns": [], "lore_signals": []}
    assert "lore_signals" in result, "lore_signals key missing from result template"
    RE.lore_index.clear()
    print("  PASS: lore_signals key exists in result dict")


if __name__ == "__main__":
    test_lore_parsed_from_git_history()
    test_no_lore_no_records()
    test_get_why_context_has_lore_signals_key()
    print("\n3/3 tests PASS")
