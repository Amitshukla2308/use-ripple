"""
Stage 5 — Validate and summarise packaged artifacts.
Verifies that graph_with_summaries.json and vectors.lance are present in ARTIFACT_DIR.
Input:  $OUTPUT_DIR/graph_with_summaries.json   (written by stage 4)
        $ARTIFACT_DIR/vectors.lance/             (written by stage 3)
        $ARTIFACT_DIR/graph_with_summaries.json  (written by stage 4)
Output: validates artifacts; copies graph JSON from output→artifact if needed.
"""
import json, pathlib, shutil, sys, os

PIPELINE_DIR = pathlib.Path(__file__).parent
OUT_DIR      = pathlib.Path(os.environ.get("OUTPUT_DIR",    PIPELINE_DIR / "output"))
ARTIFACT_DIR = pathlib.Path(os.environ.get("ARTIFACT_DIR", PIPELINE_DIR / "demo_artifact"))
ARTIFACT_DIR.mkdir(exist_ok=True)



def main():
    print("=== Stage 5: Packaging demo artifact ===")

    # 1. graph_with_summaries.json — copy from output→artifact if artifact is stale/missing
    src = OUT_DIR / "graph_with_summaries.json"
    dst = ARTIFACT_DIR / "graph_with_summaries.json"
    if src.exists() and (not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime):
        shutil.copy2(src, dst)
        print(f"  Copied graph_with_summaries.json ({src.stat().st_size // 1024 // 1024}MB)")
    elif dst.exists():
        print(f"  graph_with_summaries.json already in artifact ({dst.stat().st_size // 1024 // 1024}MB)")
    else:
        print("  ERROR: graph_with_summaries.json not found. Run stage 4 first.")
        sys.exit(1)

    # 2. vectors.lance — already written by stage 3
    lance_dir = ARTIFACT_DIR / "vectors.lance"
    if lance_dir.exists():
        size_mb = sum(f.stat().st_size for f in lance_dir.rglob("*") if f.is_file()) // (1024*1024)
        print(f"  vectors.lance present ({size_mb}MB)")
    else:
        print("  ERROR: vectors.lance not found. Run stage 3 first.")
        sys.exit(1)

    # 3. cochange_index.json — optional (stage 6, skipped in standard pipeline)
    cochange = ARTIFACT_DIR / "cochange_index.json"
    if cochange.exists():
        print(f"  cochange_index.json present ({cochange.stat().st_size // 1024 // 1024}MB)")
    else:
        print("  cochange_index.json not found (stage 6 skipped — OK)")

    # 4. Summary
    total_size = sum(
        f.stat().st_size for f in ARTIFACT_DIR.rglob("*") if f.is_file()
    )
    print(f"\n  Artifact dir: {ARTIFACT_DIR}")
    print(f"  Total size:   {total_size / (1024**2):.0f}MB")
    print(f"\n  Contents:")
    for f in sorted(ARTIFACT_DIR.iterdir()):
        if f.is_file():
            print(f"    {f.name:40s} {f.stat().st_size // (1024*1024):5d}MB")
        elif f.is_dir():
            sz = sum(x.stat().st_size for x in f.rglob("*") if x.is_file())
            print(f"    {f.name + '/':40s} {sz // (1024*1024):5d}MB")
    print(f"\n✓ Artifacts ready. Start serve/ servers to use them.")


if __name__ == "__main__":
    main()
