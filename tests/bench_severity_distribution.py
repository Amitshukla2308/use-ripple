"""
bench_severity_distribution.py — Validate blast_radius severity tiering.

T-018 prediction: HIGH (cross-service) ≈ 71% of all tiered warnings.
This script samples seed modules from multiple services, calls get_blast_radius,
and measures the aggregate severity distribution.

Usage:
    ARTIFACT_DIR=/home/beast/projects/workspaces/juspay/artifacts \
    python3 tests/bench_severity_distribution.py [--seeds 20]
"""
import sys, os, pathlib, json, argparse, random

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "serve"))

os.environ["EMBED_SERVER_URL"] = ""  # keyword-only mode

parser = argparse.ArgumentParser()
parser.add_argument("--seeds", type=int, default=20, help="Number of seed modules to sample")
parser.add_argument("--hops", type=int, default=2)
args = parser.parse_args()

import retrieval_engine as engine

ARTIFACT_DIR = pathlib.Path(os.environ.get(
    "ARTIFACT_DIR", "/home/beast/projects/workspaces/juspay/artifacts"))
os.environ["ARTIFACT_DIR"] = str(ARTIFACT_DIR)
engine.initialize(load_embedder=False)

# Build list of modules with known services for seed selection
all_modules = []
if engine.MG is not None:
    for node, data in engine.MG.nodes(data=True):
        svc = data.get("service", "")
        if svc:
            all_modules.append((node, svc))

if not all_modules:
    print("ERROR: No modules with service info found.")
    sys.exit(1)

print(f"Available modules: {len(all_modules):,} across services")

# Sample seeds spread across services
services = list({svc for _, svc in all_modules})
print(f"Services: {len(services)}: {', '.join(sorted(services)[:8])}{'...' if len(services) > 8 else ''}")

random.seed(42)
# Pick seeds evenly distributed across services
per_service = max(1, args.seeds // len(services))
seeds = []
for svc in sorted(services):
    candidates = [m for m, s in all_modules if s == svc]
    seeds.extend(random.sample(candidates, min(per_service, len(candidates))))
seeds = seeds[:args.seeds]

print(f"\nRunning blast_radius on {len(seeds)} seed modules (hops={args.hops})...")

total = {"HIGH": 0, "MEDIUM": 0, "INFO": 0}
runs_with_high = 0
per_seed_results = []

for i, seed_mod in enumerate(seeds):
    result = engine.get_blast_radius([seed_mod], max_hops=args.hops)
    summary = result.get("severity_summary", {})
    if not summary:
        # Fallback: count from tiered_impact list
        for item in result.get("tiered_impact", []):
            sev = item.get("severity", "INFO")
            summary[sev] = summary.get(sev, 0) + 1

    h = summary.get("HIGH", 0)
    m = summary.get("MEDIUM", 0)
    inf = summary.get("INFO", 0)
    total_items = h + m + inf
    total["HIGH"] += h
    total["MEDIUM"] += m
    total["INFO"] += inf
    if h > 0:
        runs_with_high += 1

    seed_svc = engine.MG.nodes[seed_mod].get("service", "?") if engine.MG and seed_mod in engine.MG.nodes else "?"
    per_seed_results.append({
        "seed": seed_mod, "service": seed_svc,
        "HIGH": h, "MEDIUM": m, "INFO": inf, "total": total_items,
    })
    if (i + 1) % 5 == 0:
        print(f"  {i+1}/{len(seeds)} done...")

# Results
grand_total = total["HIGH"] + total["MEDIUM"] + total["INFO"]
print(f"\n{'='*55}")
print(f"Severity Distribution — {len(seeds)} seeds, {grand_total} tiered warnings")
print(f"{'='*55}")
if grand_total > 0:
    high_pct = 100 * total["HIGH"] / grand_total
    med_pct  = 100 * total["MEDIUM"] / grand_total
    inf_pct  = 100 * total["INFO"] / grand_total
    print(f"  HIGH   (cross-service): {total['HIGH']:5d}  ({high_pct:5.1f}%)")
    print(f"  MEDIUM (intra-service): {total['MEDIUM']:5d}  ({med_pct:5.1f}%)")
    print(f"  INFO   (review only):   {total['INFO']:5d}  ({inf_pct:5.1f}%)")
    print(f"\nT-018 prediction: HIGH ≈ 71%")
    print(f"Actual:           HIGH = {high_pct:.1f}%")
    gap = abs(high_pct - 71.0)
    verdict = "PASS ✓" if gap <= 10 else "INVESTIGATE"
    print(f"Gap from baseline: {gap:.1f}pp  →  {verdict}")
    print(f"\nSeeds with ≥1 HIGH warning: {runs_with_high}/{len(seeds)} ({100*runs_with_high/len(seeds):.0f}%)")
else:
    print("  No tiered warnings found — check artifact loading")

# Show per-seed table (top 5 by HIGH count)
per_seed_results.sort(key=lambda x: -x["HIGH"])
print(f"\nTop seeds by HIGH count:")
print(f"  {'Module':<55} {'Svc':<20} H  M  I")
for r in per_seed_results[:8]:
    print(f"  {r['seed'][:55]:<55} {r['service'][:20]:<20} {r['HIGH']:2d} {r['MEDIUM']:2d} {r['INFO']:2d}")
