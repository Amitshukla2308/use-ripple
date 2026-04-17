"""Verify provenance_reader against a synthesized JSON fallback.

Creates a .hr_provenance.json under a temp git repo, points the env at it,
and asserts the reader returns correct line→metadata data.
"""
import json, os, pathlib, subprocess, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from serve.provenance_reader import (
    provenance_dict, is_ai_line, count_ai_lines, summarize, read_provenance
)


tmp = tempfile.mkdtemp()
subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
subprocess.run(["git", "-C", tmp, "config", "user.email", "t@t.com"], check=True)
subprocess.run(["git", "-C", tmp, "config", "user.name", "t"], check=True)

src_path = pathlib.Path(tmp) / "sample.py"
src_path.write_text("\n".join(f"line {i}" for i in range(1, 21)) + "\n")

subprocess.run(["git", "-C", tmp, "add", "sample.py"], check=True)
subprocess.run(["git", "-C", tmp, "commit", "-qm", "init"], check=True)

prov = {
    "files": {
        "sample.py": [
            {"start": 3, "end": 5,  "agent": "claude",  "session": "abc"},
            {"start": 10, "end": 10, "agent": "cursor",  "session": "def"},
        ]
    }
}
(pathlib.Path(tmp) / ".hr_provenance.json").write_text(json.dumps(prov))

os.environ["HR_PROVENANCE_BACKEND"] = "json"
read_provenance.cache_clear()

print("TEST 1: provenance_dict returns expected line→meta")
d = provenance_dict(str(src_path))
print(f"  lines flagged: {sorted(d.keys())}")
assert sorted(d.keys()) == [3, 4, 5, 10], f"got {sorted(d.keys())}"
assert d[3]["agent"] == "claude"
assert d[10]["agent"] == "cursor"
print("  PASS\n")

print("TEST 2: is_ai_line and count_ai_lines")
assert is_ai_line(str(src_path), 4)
assert not is_ai_line(str(src_path), 6)
assert count_ai_lines(str(src_path)) == 4
print("  PASS\n")

print("TEST 3: summarize across multiple files")
extra = pathlib.Path(tmp) / "other.py"
extra.write_text("hello\n")
summary = summarize([str(src_path), str(extra), str(pathlib.Path(tmp) / "missing.py")])
print(f"  summary: {summary}")
assert summary["total_ai_lines"] == 4
assert summary["files_with_ai"] == 1
print("  PASS\n")

print("TEST 4: backend=off returns empty")
os.environ["HR_PROVENANCE_BACKEND"] = "off"
read_provenance.cache_clear()
assert provenance_dict(str(src_path)) == {}
assert summarize([str(src_path)])["total_ai_lines"] == 0
print("  PASS\n")

print("=== provenance_reader VERIFIED ===")
