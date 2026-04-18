"""Tests for find_dead_code() in retrieval_engine."""
import sys, pathlib, json, tempfile, os
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "serve"))

import retrieval_engine as RE

ARTIFACT_DIR = pathlib.Path.home() / "projects/workspaces/juspay/artifacts"


def _inject_activity(data: dict):
    RE.activity_index.clear()
    RE.activity_index.update(data)


print("TEST 1: unavailable when activity_index empty")
_inject_activity({})
r = RE.find_dead_code()
assert r["source"] == "unavailable", f"Expected unavailable, got {r}"
print("  PASS")

print("\nTEST 2: real activity_index — 180d threshold returns candidates")
if (ARTIFACT_DIR / "activity_index.json").exists():
    _inject_activity(json.loads((ARTIFACT_DIR / "activity_index.json").read_text()))
    r = RE.find_dead_code(threshold_days=180)
    assert r["total"] >= 100, f"Expected >=100 stale modules, got {r['total']}"
    assert r["total"] <= len(RE.activity_index) * 0.5, \
        f"Too broad: {r['total']} / {len(RE.activity_index)}"
    assert all(m["days_stale"] >= 180 for m in r["modules"]), "days_stale check failed"
    assert r["modules"][0]["days_stale"] >= r["modules"][-1]["days_stale"], \
        "Not sorted stalest-first"
    print(f"  PASS ({r['total']} stale, showing {r['showing']})")
else:
    print("  SKIP (no activity_index.json)")

print("\nTEST 3: service filter")
if RE.activity_index:
    r = RE.find_dead_code(threshold_days=180, service="euler-db")
    for m in r["modules"]:
        assert "euler-db" in m["service"].lower(), f"Service filter failed: {m['service']}"
    print(f"  PASS (euler-db: {r['total']} stale)")

print("\nTEST 4: threshold parameter — 365d returns fewer than 180d")
if RE.activity_index:
    r180 = RE.find_dead_code(threshold_days=180)
    r365 = RE.find_dead_code(threshold_days=365)
    assert r365["total"] <= r180["total"], \
        f"365d ({r365['total']}) should be <= 180d ({r180['total']})"
    print(f"  PASS (180d={r180['total']}, 365d={r365['total']})")

print("\nTEST 5: synthetic data — correctness")
from datetime import date, timedelta
today_str = date.today().isoformat()
old_str = (date.today() - timedelta(days=200)).isoformat()
recent_str = (date.today() - timedelta(days=30)).isoformat()
_inject_activity({
    "OldModule": {"last_touched_date": old_str, "repo": "svc-a", "total_commits": 5,
                  "activity_50": 0, "activity_200": 0, "activity_score": 0},
    "RecentModule": {"last_touched_date": recent_str, "repo": "svc-a", "total_commits": 20,
                     "activity_50": 3, "activity_200": 8, "activity_score": 0.5},
})
r = RE.find_dead_code(threshold_days=180)
mods = [m["module"] for m in r["modules"]]
assert "OldModule" in mods, "OldModule (200d stale) should appear"
assert "RecentModule" not in mods, "RecentModule (30d) should not appear"
print(f"  PASS")

print("\nAll 5 tests PASSED")
