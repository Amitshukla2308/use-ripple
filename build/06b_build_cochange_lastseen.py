"""
Stage 6b — Build co-change last-seen sidecar for query-time decay reranking (T-039).

Streams git_history.json once. For each co-change pair, records the most recent
commit timestamp where they co-changed together.

Output: cochange_lastseen.json
  { "mod_a::mod_b": unix_timestamp_float, ... }
  Keys are alphabetically sorted: min(a,b) + "::" + max(a,b)

Used by retrieval_engine.py to apply decay weighting at query time:
  reranked_weight = flat_weight * exp(-lambda * (now - lastseen).days / 180)

T-034 found: decay reranking gives +1.91pp recall@10 (tested on existing filtered pairs).
T-038 failure: build-time decay weighting loses 29% coverage. Query-time reranking avoids this.
"""
import argparse, json, math, pathlib
from datetime import datetime, timezone

try:
    import ijson
except ImportError:
    raise SystemExit("pip install ijson")

parser = argparse.ArgumentParser()
parser.add_argument("--git-history", type=pathlib.Path,
                    default=pathlib.Path("/home/beast/projects/workspaces/juspay/git_history.json"))
parser.add_argument("--output", type=pathlib.Path, default=None)
parser.add_argument("--artifact-dir", type=pathlib.Path, default=None)
args = parser.parse_args()

if args.output:
    OUT_PATH = args.output
elif args.artifact_dir:
    OUT_PATH = args.artifact_dir / "cochange_lastseen.json"
else:
    OUT_PATH = args.git_history.parent / "cochange_lastseen.json"

SRC_EXTS = {".hs", ".rs", ".hs-boot", ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java"}
SKIP_DIRS = {".stack-work", "test", "tests", "spec", "mock", "node_modules", "__pycache__", ".git", "venv", ".venv"}
MAX_FILES = 40


def is_source(path: str) -> bool:
    p = pathlib.PurePosixPath(path)
    if p.suffix not in SRC_EXTS: return False
    return not (set(p.parts) & SKIP_DIRS)


def to_module(repo: str, fpath: str) -> str:
    p = fpath
    for ext in SRC_EXTS: p = p.replace(ext, "")
    return f"{repo}::{p.replace('/', '::')}"


def parse_ts(value) -> float | None:
    try:
        if isinstance(value, (int, float)):
            return float(value)
        ts = str(value).strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(ts[:len(fmt) + 5], fmt)
                if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except ValueError:
                continue
    except Exception:
        pass
    return None


print(f"Streaming {args.git_history}...", flush=True)

lastseen: dict[str, float] = {}
total_commits = 0; n_with_ts = 0
current_repo = None
commit_files: list[str] = []
commit_timestamp = None

from itertools import combinations

with open(args.git_history, "rb") as f:
    p = ijson.parse(f, use_float=True)
    try:
        for prefix, event, value in p:
            if prefix == "repositories.item.name" and event == "string":
                current_repo = value
            elif prefix == "repositories.item.commits.item" and event == "start_map":
                commit_files = []; commit_timestamp = None
            elif prefix.endswith((".timestamp", ".date", ".authored_date")) and event in ("string", "number"):
                if commit_timestamp is None: commit_timestamp = value
            elif event == "string" and "files_changed" in prefix and prefix.endswith(".path"):
                if is_source(value): commit_files.append(value)
            elif prefix == "repositories.item.commits.item" and event == "end_map":
                total_commits += 1
                ts = parse_ts(commit_timestamp) if commit_timestamp else None
                if ts and 2 <= len(commit_files) <= MAX_FILES and current_repo:
                    n_with_ts += 1
                    mods = [to_module(current_repo, fp) for fp in commit_files]
                    for a, b in combinations(mods, 2):
                        key = min(a, b) + "::" + max(a, b)
                        if key not in lastseen or lastseen[key] < ts:
                            lastseen[key] = ts
                if total_commits % 10000 == 0:
                    print(f"  {total_commits:,} commits  {len(lastseen):,} pairs", flush=True)
    except Exception as exc:
        print(f"WARNING: stopped at {total_commits:,} commits: {exc}", flush=True)

print(f"\nComplete: {total_commits:,} commits, {n_with_ts:,} with timestamps, {len(lastseen):,} co-change pairs", flush=True)

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_PATH, "w") as f:
    json.dump(lastseen, f)
print(f"Saved → {OUT_PATH}  ({OUT_PATH.stat().st_size / 1e6:.1f} MB)", flush=True)

# Quick sanity: show the most recent 3 pairs
now = datetime.now(tz=timezone.utc).timestamp()
top3 = sorted(lastseen.items(), key=lambda x: -x[1])[:3]
print("\nMost recently co-changed pairs:")
for pair, ts in top3:
    days = (now - ts) / 86400
    mods = pair.split("::", 1)
    print(f"  {days:.0f}d ago: {mods[0][:60]}...")
