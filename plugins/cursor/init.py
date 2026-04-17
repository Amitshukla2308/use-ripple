#!/usr/bin/env python3
"""
Ripple Plugin Init — runs on workspace open.

Indexes the repo using git history only (zero-config, zero-GPU).
Produces co-change and ownership indexes in .ripple/artifacts/.
Typically completes in <5 seconds for repos under 50K commits.
"""
import subprocess
import sys
import pathlib

_PLUGIN_DIR = pathlib.Path(__file__).parent
_REPO_ROOT = _PLUGIN_DIR.parent.parent
_GUARDIAN_INIT = _REPO_ROOT / "apps" / "cli" / "guardian_init.py"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Ripple workspace init")
    parser.add_argument("--repo", type=pathlib.Path, default=".",
                        help="Path to git repo")
    args = parser.parse_args()

    repo = args.repo.resolve()
    artifact_dir = repo / ".ripple" / "artifacts"

    # Skip if already initialized
    cochange = artifact_dir / "cochange_index.json"
    ownership = artifact_dir / "ownership_index.json"
    if cochange.exists() and ownership.exists():
        print(f"Ripple: already indexed ({artifact_dir})")
        return 0

    if not _GUARDIAN_INIT.exists():
        print(f"Error: guardian_init.py not found at {_GUARDIAN_INIT}", file=sys.stderr)
        return 1

    print(f"Ripple: indexing {repo.name}...")
    result = subprocess.run(
        [sys.executable, str(_GUARDIAN_INIT), "--repo", str(repo)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode == 0:
        print(f"Ripple: ready! Artifacts at {artifact_dir}")
    else:
        print(f"Ripple init failed: {result.stderr[:200]}", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
