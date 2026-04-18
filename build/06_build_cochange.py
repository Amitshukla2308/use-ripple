"""
Stage 6 — Build evolutionary coupling graph from git history.

Streams one commit at a time (O(1) memory).
Handles truncated/incomplete JSON files gracefully — writes partial results.
"""
import argparse, json, math, pathlib, sys, time
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations

try:
    import ijson
except ImportError:
    raise SystemExit("pip install ijson")

HALF_LIFE_DAYS = 180.0  # 6-month half-life for exponential decay
_REF_TS: float = 0.0    # set in build() after GIT_HISTORY is known


def _find_max_ts(path) -> float:
    """Quick pre-scan: find the latest commit timestamp in git_history.json."""
    max_ts = 0.0
    try:
        with open(path, "rb") as f:
            for prefix, event, value in ijson.parse(f, use_float=True):
                if event in ("number", "string") and prefix.endswith(
                    (".timestamp", ".date", ".authored_date")
                ):
                    try:
                        ts = float(value) if isinstance(value, (int, float)) else None
                        if ts is None:
                            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
                                        "%Y-%m-%d %H:%M:%S %z"):
                                try:
                                    dt = datetime.strptime(str(value)[:25], fmt[:25])
                                    if dt.tzinfo is None:
                                        dt = dt.replace(tzinfo=timezone.utc)
                                    ts = dt.timestamp(); break
                                except ValueError:
                                    pass
                        if ts and ts > max_ts:
                            max_ts = ts
                    except Exception:
                        pass
    except Exception:
        pass
    return max_ts if max_ts > 0 else time.time()

parser = argparse.ArgumentParser(description="Build co-change index from git history")
parser.add_argument("--git-history", type=pathlib.Path,
                    default=pathlib.Path("/home/beast/projects/workspaces/juspay/git_history.json"))
parser.add_argument("--output", type=pathlib.Path, default=None,
                    help="Output path (default: <artifact-dir>/cochange_index.json)")
parser.add_argument("--artifact-dir", type=pathlib.Path, default=None)
parser.add_argument("--min-weight", type=int, default=None,
                    help="Min co-change weight (default: auto based on repo size)")
_args = parser.parse_args()

GIT_HISTORY = _args.git_history
if _args.output:
    OUT_PATH = _args.output
elif _args.artifact_dir:
    OUT_PATH = _args.artifact_dir / "cochange_index.json"
else:
    OUT_PATH = GIT_HISTORY.parent / "cochange_index.json"

SRC_EXTS   = {".hs", ".rs", ".hs-boot", ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java"}
SKIP_DIRS  = {".stack-work", "test", "tests", "spec", "mock", "node_modules", "__pycache__", ".git", "venv", ".venv"}
TOP_K      = 30
MAX_FILES  = 40  # skip mega-commits


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


def _decay(ts_value) -> float:
    """Return exp-decay weight for a commit timestamp (Unix epoch or ISO str)."""
    try:
        if isinstance(ts_value, (int, float)):
            commit_ts = float(ts_value)
        else:
            from datetime import datetime, timezone
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    commit_ts = datetime.strptime(str(ts_value)[:25], fmt[:len(str(ts_value)[:25])]).replace(tzinfo=timezone.utc).timestamp()
                    break
                except ValueError:
                    pass
            else:
                return 1.0  # fallback: no decay
        days_ago = max(0.0, (_REF_TS - commit_ts) / 86400.0)
        return math.pow(2.0, -days_ago / HALF_LIFE_DAYS)
    except Exception:
        return 1.0


def build():
    global _REF_TS
    print("Pre-scanning git history for max timestamp...", flush=True)
    _REF_TS = _find_max_ts(str(GIT_HISTORY))
    print(f"  REF_TS = {_REF_TS:.0f} ({datetime.fromtimestamp(_REF_TS).strftime('%Y-%m-%d')})", flush=True)

    cochange       = defaultdict(lambda: defaultdict(int))
    cochange_decay = defaultdict(lambda: defaultdict(float))
    total_commits = 0
    skipped       = 0
    current_repo  = None
    current_ts    = None
    truncated     = False

    print(f"Streaming {GIT_HISTORY}...", flush=True)

    with open(GIT_HISTORY, "rb") as f:
        parser = ijson.parse(f, use_float=True)
        in_commit    = False
        commit_files = []

        try:
            for prefix, event, value in parser:

                # Track current repo name
                if prefix == "repositories.item.name" and event == "string":
                    current_repo = value
                    continue

                # Detect commit start
                if prefix == "repositories.item.commits.item" and event == "start_map":
                    in_commit    = True
                    commit_files = []
                    current_ts   = None
                    continue

                # Capture commit timestamp (any of the common field names)
                if in_commit and prefix in (
                    "repositories.item.commits.item.timestamp",
                    "repositories.item.commits.item.date",
                    "repositories.item.commits.item.authored_date",
                ) and event in ("number", "string"):
                    if current_ts is None:
                        current_ts = value
                    continue

                # Collect only files_changed paths (ignore diff/body/other fields)
                if in_commit and event == "string" and "files_changed" in prefix and prefix.endswith(".path"):
                    if is_source(value):
                        commit_files.append(value)
                    continue

                # Commit ends — process it
                if prefix == "repositories.item.commits.item" and event == "end_map":
                    in_commit = False
                    total_commits += 1

                    if 2 <= len(commit_files) <= MAX_FILES and current_repo:
                        mods = [to_module(current_repo, fp) for fp in commit_files]
                        dw   = _decay(current_ts) if current_ts is not None else 1.0
                        for a, b in combinations(mods, 2):
                            cochange[a][b] += 1
                            cochange[b][a] += 1
                            cochange_decay[a][b] += dw
                            cochange_decay[b][a] += dw
                    elif len(commit_files) > MAX_FILES:
                        skipped += 1

                    if total_commits % 5000 == 0:
                        print(f"  {total_commits:,} commits  {len(cochange):,} modules  "
                              f"repo={current_repo}", flush=True)
                    continue

        except Exception as exc:
            truncated = True
            print(f"\nWARNING: JSON parsing stopped at {total_commits:,} commits: {exc}", flush=True)
            print("Writing partial results...", flush=True)

    status = "PARTIAL (file truncated)" if truncated else "COMPLETE"
    print(f"\n{status}: {total_commits:,} commits processed  {skipped} mega-commits skipped",
          flush=True)
    print(f"Unique modules with co-change partners: {len(cochange):,}", flush=True)

    # Auto-scale MIN_WEIGHT based on repo size (small repos need lower threshold)
    if _args.min_weight is not None:
        MIN_WEIGHT = _args.min_weight
    elif total_commits < 200:
        MIN_WEIGHT = 2
    elif total_commits < 1000:
        MIN_WEIGHT = 2
    else:
        MIN_WEIGHT = 3

    # Filter: keep only pairs with weight >= MIN_WEIGHT, cap at TOP_K per module
    # Sort by flat weight (coverage gating), but also store decay_weight for ranking
    edges, total_pairs = {}, 0
    for mod, partners in cochange.items():
        decay_map = cochange_decay.get(mod, {})
        filtered = sorted(
            [{"module": m, "weight": w, "decay_weight": round(decay_map.get(m, float(w)), 4)}
             for m, w in partners.items() if w >= MIN_WEIGHT],
            key=lambda x: -x["weight"]
        )[:TOP_K]
        if filtered:
            edges[mod] = filtered
            total_pairs += len(filtered)

    print(f"After filter (weight>={MIN_WEIGHT}): {len(edges):,} modules  "
          f"{total_pairs:,} edges", flush=True)

    index = {
        "meta": {
            "total_commits":  total_commits,
            "truncated":      truncated,
            "total_modules":  len(edges),
            "total_pairs":    total_pairs,
            "min_weight":     MIN_WEIGHT,
            "decay_half_life_days": HALF_LIFE_DAYS,
            "decay_ref_ts":   int(_REF_TS),
        },
        "edges": edges,
    }

    OUT_PATH.write_text(json.dumps(index, separators=(",", ":")))
    size_mb = OUT_PATH.stat().st_size / (1024 * 1024)
    print(f"\nWritten: {OUT_PATH}  ({size_mb:.1f}MB)", flush=True)

    print("\nSample co-change edges:")
    for mod, partners in list(edges.items())[:5]:
        svc = mod.split("::")[0]
        name = "::".join(mod.split("::")[1:])
        print(f"  [{svc}] {name}")
        for p in partners[:3]:
            p_svc  = p["module"].split("::")[0]
            p_name = "::".join(p["module"].split("::")[1:])
            print(f"    -> [{p_svc}] {p_name}  (w={p['weight']})")


if __name__ == "__main__":
    build()
