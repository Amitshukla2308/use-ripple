"""
Stage 9 — Build Granger causality index for directional co-change prediction.

For each co-change pair, tests whether changes to module A Granger-cause
changes to module B (and vice versa). This adds directionality to co-change:
instead of "A and B changed together 15 times," we learn "changes to A
predict future changes to B with lag 2."

Streams git_history.json (same as 06_build_cochange.py).
Tests only existing co-change pairs (from cochange_index.json).

Output: granger_index.json — directional causal relationships with lag and p-value.

Requirements: pip install ijson statsmodels numpy
"""
import json, pathlib, sys, time
from collections import defaultdict
from datetime import datetime

import numpy as np

try:
    import ijson
except ImportError:
    raise SystemExit("pip install ijson")

try:
    from statsmodels.tsa.stattools import grangercausalitytests
except ImportError:
    raise SystemExit("pip install statsmodels")

# ── Config ──────────────────────────────────────────────────────────────────
GIT_HISTORY = pathlib.Path(
    sys.argv[1] if len(sys.argv) > 1
    else "/home/beast/projects/workspaces/juspay/git_history.json"
)
ARTIFACT = pathlib.Path(
    sys.argv[2] if len(sys.argv) > 2
    else "/home/beast/projects/workspaces/juspay/artifacts"
)
COCHANGE_PATH = ARTIFACT / "cochange_index.json"
OUT_PATH      = ARTIFACT / "granger_index.json"

SRC_EXTS   = {".hs", ".rs", ".hs-boot"}
SKIP_DIRS  = {".stack-work", "test", "tests", "spec", "mock", "node_modules", "__pycache__"}
MAX_FILES  = 40        # skip mega-commits (same as 06_build_cochange.py)
MAX_LAG    = 5         # test lags 1-5
P_THRESHOLD = 0.05     # significance threshold
MIN_COMMITS = 30       # need enough data points for statistical test
MIN_COCHANGE_WEIGHT = 5  # only test pairs with >= this many co-changes


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


def build():
    # ── Step 1: Load co-change pairs to know what to test ──
    print(f"Loading co-change index from {COCHANGE_PATH}...", flush=True)
    with open(COCHANGE_PATH) as f:
        cochange_index = json.load(f)

    # Build set of pairs worth testing
    edges = cochange_index.get("edges", cochange_index)
    pairs_to_test = set()
    for mod_a, neighbors in edges.items():
        if mod_a == "meta":
            continue
        for neighbor in neighbors:
            mod_b = neighbor["module"]
            weight = neighbor.get("weight", 0)
            if weight >= MIN_COCHANGE_WEIGHT:
                pair = tuple(sorted([mod_a, mod_b]))
                pairs_to_test.add(pair)

    print(f"  Co-change pairs with weight >= {MIN_COCHANGE_WEIGHT}: {len(pairs_to_test):,}",
          flush=True)

    # Collect all modules involved in pairs
    modules_of_interest = set()
    for a, b in pairs_to_test:
        modules_of_interest.add(a)
        modules_of_interest.add(b)
    print(f"  Modules of interest: {len(modules_of_interest):,}", flush=True)

    # ── Step 2: Stream git history, build per-module commit participation ──
    print(f"\nStreaming {GIT_HISTORY}...", flush=True)
    # module_commits[mod] = sorted list of commit indices where mod was touched
    module_commits = defaultdict(list)
    commit_idx = 0
    current_repo = None
    truncated = False

    with open(GIT_HISTORY, "rb") as f:
        parser = ijson.parse(f, use_float=True)
        in_commit = False
        commit_files = []

        try:
            for prefix, event, value in parser:
                if prefix == "repositories.item.name" and event == "string":
                    current_repo = value
                    continue

                if prefix == "repositories.item.commits.item" and event == "start_map":
                    in_commit = True
                    commit_files = []
                    continue

                if in_commit and event == "string" and "files_changed" in prefix and prefix.endswith(".path"):
                    if is_source(value):
                        commit_files.append(value)
                    continue

                if prefix == "repositories.item.commits.item" and event == "end_map":
                    in_commit = False

                    if 1 <= len(commit_files) <= MAX_FILES and current_repo:
                        mods = set(to_module(current_repo, fp) for fp in commit_files)
                        # Only record modules we care about
                        for m in mods:
                            if m in modules_of_interest:
                                module_commits[m].append(commit_idx)
                        commit_idx += 1
                    elif len(commit_files) > MAX_FILES:
                        commit_idx += 1  # still count for timeline

                    if commit_idx % 10000 == 0:
                        print(f"  {commit_idx:,} commits  {len(module_commits):,} tracked modules",
                              flush=True)
                    continue

        except Exception as exc:
            truncated = True
            print(f"\nWARNING: JSON parsing stopped at {commit_idx:,} commits: {exc}",
                  flush=True)

    total_commits = commit_idx
    print(f"\n{'PARTIAL' if truncated else 'COMPLETE'}: {total_commits:,} commits",
          flush=True)
    print(f"Tracked modules: {len(module_commits):,}", flush=True)

    # ── Step 3: Run Granger causality tests ──
    print(f"\nRunning Granger tests on {len(pairs_to_test):,} pairs (max_lag={MAX_LAG})...",
          flush=True)

    granger_results = {}
    tested = 0
    significant = 0
    skipped_low_data = 0
    t0 = time.time()

    for pair_idx, (mod_a, mod_b) in enumerate(pairs_to_test):
        if pair_idx % 1000 == 0 and pair_idx > 0:
            elapsed = time.time() - t0
            rate = pair_idx / elapsed
            remaining = (len(pairs_to_test) - pair_idx) / rate
            print(f"  {pair_idx:,}/{len(pairs_to_test):,}  "
                  f"significant: {significant}  "
                  f"ETA: {remaining:.0f}s", flush=True)

        commits_a = set(module_commits.get(mod_a, []))
        commits_b = set(module_commits.get(mod_b, []))

        if len(commits_a) < MIN_COMMITS or len(commits_b) < MIN_COMMITS:
            skipped_low_data += 1
            continue

        # Build binary time series (sparse → dense over relevant range)
        all_commits = sorted(commits_a | commits_b)
        if len(all_commits) < MIN_COMMITS:
            skipped_low_data += 1
            continue

        # Use only the range where both modules are active
        min_c = all_commits[0]
        max_c = all_commits[-1]
        length = max_c - min_c + 1

        if length < MIN_COMMITS + MAX_LAG:
            skipped_low_data += 1
            continue

        # Build dense binary vectors
        ts_a = np.zeros(length, dtype=float)
        ts_b = np.zeros(length, dtype=float)
        for c in commits_a:
            if min_c <= c <= max_c:
                ts_a[c - min_c] = 1.0
        for c in commits_b:
            if min_c <= c <= max_c:
                ts_b[c - min_c] = 1.0

        # Test A→B: does A Granger-cause B?
        for direction, x, y, src, tgt in [
            ("A→B", ts_a, ts_b, mod_a, mod_b),
            ("B→A", ts_b, ts_a, mod_b, mod_a),
        ]:
            data = np.column_stack([y, x])  # grangercausalitytests expects [effect, cause]
            try:
                results = grangercausalitytests(data, maxlag=MAX_LAG, verbose=False)
                # Find best lag (lowest p-value)
                best_lag = None
                best_p = 1.0
                best_f = 0.0
                for lag in range(1, MAX_LAG + 1):
                    if lag in results:
                        # Use ssr_ftest (most common)
                        p_val = results[lag][0]["ssr_ftest"][1]
                        f_val = results[lag][0]["ssr_ftest"][0]
                        if p_val < best_p:
                            best_p = p_val
                            best_lag = lag
                            best_f = f_val

                if best_p < P_THRESHOLD and best_lag is not None:
                    key = f"{src}→{tgt}"
                    granger_results[key] = {
                        "source": src,
                        "target": tgt,
                        "best_lag": best_lag,
                        "p_value": round(best_p, 6),
                        "f_statistic": round(best_f, 3),
                    }
                    significant += 1

            except Exception:
                pass  # Some series are too short or constant

        tested += 1

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s", flush=True)
    print(f"Tested: {tested:,}  Skipped (low data): {skipped_low_data:,}", flush=True)
    print(f"Significant causal relationships (p<{P_THRESHOLD}): {significant:,}", flush=True)

    # ── Step 4: Write output ──
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump({
            "metadata": {
                "total_commits": total_commits,
                "pairs_tested": tested,
                "significant_results": significant,
                "p_threshold": P_THRESHOLD,
                "max_lag": MAX_LAG,
                "min_cochange_weight": MIN_COCHANGE_WEIGHT,
                "truncated": truncated,
            },
            "causal_pairs": granger_results,
        }, f, indent=2)

    print(f"\nWrote {OUT_PATH} ({significant:,} causal pairs)", flush=True)


if __name__ == "__main__":
    build()
