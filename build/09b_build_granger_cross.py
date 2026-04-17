#!/usr/bin/env python3
"""
09b_build_granger_cross.py — Cross-service Granger causality index.

Unlike 09_build_granger.py (intra-service), this:
1. Sorts ALL commits across ALL repos by ISO date (calendar time)
2. Tests pairs from cross_cochange_index.json (cross-repo pairs only)
3. Output: granger_cross_index.json

Why calendar sort matters: the existing intra-service builder uses sequential
JSON order (newest-first within each repo). For cross-service pairs, repo order
in JSON would create spurious lags. Calendar sort ensures real temporal proximity.

Usage:
  python3 09b_build_granger_cross.py [git_history.json] [artifact_dir]
"""
import json, pathlib, sys, time, re
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

try:
    import ijson
except ImportError:
    raise SystemExit("pip install ijson")
try:
    from statsmodels.tsa.stattools import grangercausalitytests
except ImportError:
    raise SystemExit("pip install statsmodels")

# ── Config ───────────────────────────────────────────────────────────────────
GIT_HISTORY = pathlib.Path(
    sys.argv[1] if len(sys.argv) > 1
    else "/home/beast/projects/workspaces/juspay/git_history.json"
)
ARTIFACT = pathlib.Path(
    sys.argv[2] if len(sys.argv) > 2
    else "/home/beast/projects/workspaces/juspay/artifacts"
)
CROSS_COCHANGE = ARTIFACT / "cross_cochange_index.json"
OUT_PATH       = ARTIFACT / "granger_cross_index.json"

SRC_EXTS   = {".hs", ".rs", ".hs-boot", ".py", ".ts", ".js", ".go"}
SKIP_DIRS  = {".stack-work", "test", "tests", "spec", "mock", "node_modules", "__pycache__"}
MAX_FILES  = 40
MAX_LAG    = 5
P_THRESHOLD = 0.05
MIN_COMMITS = 8   # lower than intra-service (30) — cross-service modules change less
MIN_COCHANGE_WEIGHT = 5
MAX_PAIRS   = 60_000  # cap to keep runtime reasonable; sort by weight desc


def is_source(path: str) -> bool:
    p = pathlib.PurePosixPath(path)
    if p.suffix not in SRC_EXTS:
        return False
    return not (set(p.parts) & SKIP_DIRS)


def to_module(repo: str, fpath: str) -> str:
    p = fpath
    for ext in SRC_EXTS:
        p = p.replace(ext, "")
    return f"{repo}::{p.replace('/', '::')}"


def parse_date(date_str: str) -> float:
    """Parse ISO 8601 date string → UTC timestamp."""
    # Handle +05:30 style offsets (not supported by fromisoformat pre-3.11)
    s = date_str.strip()
    # Replace Z with +00:00
    s = s.replace("Z", "+00:00")
    # Try direct parse (Python 3.11+)
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        pass
    # Manual offset extraction
    m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([+-]\d{2}):(\d{2})$", s)
    if m:
        base_str, sign_h, mins = m.group(1), m.group(2), m.group(3)
        dt = datetime.fromisoformat(base_str)
        offset_seconds = (int(sign_h[1:]) * 60 + int(mins)) * 60 * (-1 if sign_h[0] == "-" else 1)
        return dt.timestamp() - offset_seconds
    # Fallback: parse YYYY-MM-DD
    return datetime.fromisoformat(s[:10]).timestamp()


def build():
    # ── Step 1: Load cross-repo pairs to test ──────────────────────────────
    print(f"Loading cross co-change index from {CROSS_COCHANGE}...", flush=True)
    with open(CROSS_COCHANGE) as f:
        xcc = json.load(f)

    edges = xcc.get("edges", xcc)
    pair_weights: dict = {}
    for mod_a, neighbors in edges.items():
        if mod_a == "meta":
            continue
        if not isinstance(neighbors, list):
            continue
        repo_a = mod_a.split("::")[0]
        for nb in neighbors:
            mod_b = nb.get("module", "")
            repo_b = mod_b.split("::")[0]
            if repo_a == repo_b:
                continue  # skip intra-service (handled by 09_build_granger.py)
            w = nb.get("weight", 0)
            if w >= MIN_COCHANGE_WEIGHT:
                pair = tuple(sorted([mod_a, mod_b]))
                pair_weights[pair] = max(pair_weights.get(pair, 0), w)

    # Sort by weight desc, cap at MAX_PAIRS (test strongest signals first)
    top_pairs = sorted(pair_weights, key=lambda p: pair_weights[p], reverse=True)[:MAX_PAIRS]
    print(f"  Cross-repo pairs weight>={MIN_COCHANGE_WEIGHT}: {len(pair_weights):,}", flush=True)
    print(f"  Testing top {len(top_pairs):,} pairs by weight", flush=True)

    modules_of_interest = set()
    for a, b in top_pairs:
        modules_of_interest.add(a)
        modules_of_interest.add(b)
    print(f"  Modules of interest: {len(modules_of_interest):,}", flush=True)

    # ── Step 2: Load ALL commits, sort by calendar date ───────────────────
    print(f"\nLoading {GIT_HISTORY} (pass 1: collect + sort by date)...", flush=True)
    all_commits = []  # list of (timestamp, repo, [module_keys])
    current_repo = None
    current_date = None
    commit_files = []
    in_commit = False

    with open(GIT_HISTORY, "rb") as f:
        parser = ijson.parse(f, use_float=True)
        try:
            for prefix, event, value in parser:
                if prefix == "repositories.item.name" and event == "string":
                    current_repo = value
                    continue
                if prefix == "repositories.item.commits.item" and event == "start_map":
                    in_commit = True
                    commit_files = []
                    current_date = None
                    continue
                if in_commit and prefix.endswith(".date") and event == "string":
                    current_date = value
                    continue
                if in_commit and event == "string" and "files_changed" in prefix and prefix.endswith(".path"):
                    if is_source(value):
                        commit_files.append(value)
                    continue
                if prefix == "repositories.item.commits.item" and event == "end_map":
                    in_commit = False
                    if current_date and 1 <= len(commit_files) <= MAX_FILES and current_repo:
                        try:
                            ts = parse_date(current_date)
                            mods = {to_module(current_repo, fp) for fp in commit_files}
                            mods_relevant = mods & modules_of_interest
                            if mods_relevant:
                                all_commits.append((ts, frozenset(mods_relevant)))
                        except Exception:
                            pass
        except Exception as exc:
            print(f"Warning: parse stopped: {exc}", flush=True)

    print(f"Collected {len(all_commits):,} relevant commits", flush=True)
    all_commits.sort(key=lambda x: x[0])
    print(f"Sorted by date: {len(all_commits):,} commits", flush=True)

    # ── Step 3: Build per-module sequential index series ──────────────────
    module_commits: dict[str, list] = defaultdict(list)
    for idx, (ts, mods) in enumerate(all_commits):
        for m in mods:
            module_commits[m].append(idx)

    total_commits = len(all_commits)
    print(f"Tracked {len(module_commits):,} modules across {total_commits:,} sorted commits",
          flush=True)

    # ── Step 4: Granger tests ─────────────────────────────────────────────
    print(f"\nRunning Granger tests on {len(top_pairs):,} cross-service pairs (max_lag={MAX_LAG})...",
          flush=True)

    granger_results = {}
    tested = 0
    significant = 0
    skipped = 0
    t0 = time.time()

    for pair_idx, (mod_a, mod_b) in enumerate(top_pairs):
        if pair_idx % 2000 == 0 and pair_idx > 0:
            elapsed = time.time() - t0
            rate = pair_idx / elapsed
            remaining = (len(top_pairs) - pair_idx) / rate
            print(f"  {pair_idx:,}/{len(top_pairs):,}  "
                  f"significant: {significant}  ETA: {remaining:.0f}s", flush=True)

        c_a = set(module_commits.get(mod_a, []))
        c_b = set(module_commits.get(mod_b, []))

        if len(c_a) < MIN_COMMITS or len(c_b) < MIN_COMMITS:
            skipped += 1
            continue

        # Dense binary time series over the union range
        all_idx = sorted(c_a | c_b)
        if not all_idx:
            skipped += 1
            continue
        lo, hi = all_idx[0], all_idx[-1]
        length = hi - lo + 1
        if length < MAX_LAG + 5:
            skipped += 1
            continue

        ts_a = np.zeros(length, dtype=np.float32)
        ts_b = np.zeros(length, dtype=np.float32)
        for i in c_a:
            if lo <= i <= hi:
                ts_a[i - lo] = 1.0
        for i in c_b:
            if lo <= i <= hi:
                ts_b[i - lo] = 1.0

        data = np.column_stack([ts_b, ts_a])
        tested += 1

        try:
            res = grangercausalitytests(data, maxlag=MAX_LAG, verbose=False)
            # a→b: does A Granger-cause B?
            p_a2b = min(res[lag][0]["ssr_chi2test"][1] for lag in range(1, MAX_LAG + 1))
            best_lag_a2b = min(range(1, MAX_LAG + 1),
                               key=lambda lag: res[lag][0]["ssr_chi2test"][1])

            data2 = np.column_stack([ts_a, ts_b])
            res2 = grangercausalitytests(data2, maxlag=MAX_LAG, verbose=False)
            p_b2a = min(res2[lag][0]["ssr_chi2test"][1] for lag in range(1, MAX_LAG + 1))
            best_lag_b2a = min(range(1, MAX_LAG + 1),
                               key=lambda lag: res2[lag][0]["ssr_chi2test"][1])

            if p_a2b < P_THRESHOLD:
                key = f"{mod_a}→{mod_b}"
                granger_results[key] = {
                    "source": mod_a, "target": mod_b,
                    "best_lag": best_lag_a2b, "p_value": round(p_a2b, 6),
                    "weight": pair_weights.get((mod_a, mod_b), pair_weights.get((mod_b, mod_a), 0)),
                }
                significant += 1

            if p_b2a < P_THRESHOLD:
                key = f"{mod_b}→{mod_a}"
                granger_results[key] = {
                    "source": mod_b, "target": mod_a,
                    "best_lag": best_lag_b2a, "p_value": round(p_b2a, 6),
                    "weight": pair_weights.get((mod_a, mod_b), pair_weights.get((mod_b, mod_a), 0)),
                }
                significant += 1

        except Exception:
            pass

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s", flush=True)
    print(f"Tested: {tested:,}  Skipped: {skipped:,}  Significant: {significant:,}", flush=True)

    out = {
        "metadata": {
            "total_commits_sorted": total_commits,
            "pairs_tested": tested,
            "significant_results": significant,
            "p_threshold": P_THRESHOLD,
            "max_lag": MAX_LAG,
            "min_commits": MIN_COMMITS,
            "min_cochange_weight": MIN_COCHANGE_WEIGHT,
            "mode": "cross-service-calendar-sorted",
        },
        "causal_pairs": granger_results,
    }
    with open(OUT_PATH, "w") as f:
        json.dump(out, f)
    print(f"Written to {OUT_PATH}", flush=True)
    print(f"Significant cross-service causal pairs: {significant:,}", flush=True)


if __name__ == "__main__":
    build()
