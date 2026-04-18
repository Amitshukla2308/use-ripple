"""
Stage 11 — Build commit_rationale_index from git_history.json.

Filters for commits with message length >100 chars that aren't boilerplate,
indexes them by (repo::file_path) key for use in get_why_context.

Output: artifacts/commit_rationale_index.json
  { "repo::path": [{"msg": "...", "date": "...", "hash": "..."}] }

Usage:
  python3 build/11_build_commit_rationale.py [git_history.json] [output.json]
"""
import json, pathlib, re, sys, collections

GH_PATH   = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                          "/home/beast/projects/workspaces/juspay/git_history.json")
OUT_PATH  = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else
                          "/home/beast/projects/workspaces/juspay/artifacts/commit_rationale_index.json")

BOILERPLATE = re.compile(
    r"^(merge|bump|wip|fix typo|update changelog|update readme|revert|chore:|"
    r"style:|fmt:|format|bump version|auto.?generated|release \d|version \d)",
    re.IGNORECASE,
)
MAX_PER_MODULE = 5
MAX_MSG_LEN    = 250

def main():
    with open(GH_PATH) as f:
        data = json.load(f)

    index: dict[str, list] = collections.defaultdict(list)

    for repo in data["repositories"]:
        rname = repo["name"]
        for c in repo["commits"]:
            msg = (c.get("message") or "").strip()
            if len(msg) <= 100 or BOILERPLATE.match(msg):
                continue
            date  = str(c.get("date", ""))[:10]
            sha   = c.get("hash", "")[:8]
            entry = {"msg": msg[:MAX_MSG_LEN], "date": date, "hash": sha}
            for fp in c.get("files_changed", []):
                path = fp.get("path", "") if isinstance(fp, dict) else str(fp)
                if not path:
                    continue
                key = f"{rname}::{path}"
                bucket = index[key]
                if len(bucket) < MAX_PER_MODULE:
                    bucket.append(entry)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(dict(index), f)

    total_entries = sum(len(v) for v in index.values())
    print(f"commit_rationale_index: {len(index):,} paths, {total_entries:,} entries → {OUT_PATH}")

if __name__ == "__main__":
    main()
