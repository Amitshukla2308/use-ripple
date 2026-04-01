"""
HyperRetrieval Data Analysis: Co-change vs Import Graph
Produces three analysis reports.
"""
import json
import sys
from collections import defaultdict, Counter
import time

COCHANGE_PATH = "/home/beast/projects/workspaces/juspay/artifacts/cochange_index.json"
GRAPH_PATH = "/home/beast/projects/workspaces/juspay/artifacts/graph_with_summaries.json"
OUT_DIR = "/home/beast/projects/hyperretrieval/research/data"

def extract_service(module_name):
    """Extract service name from module like 'euler-api-gateway::src::...'"""
    parts = module_name.split("::")
    return parts[0] if parts else module_name

def load_cochange():
    print("[1/4] Loading co-change index...")
    t0 = time.time()
    with open(COCHANGE_PATH) as f:
        data = json.load(f)
    print(f"  Loaded in {time.time()-t0:.1f}s. {data['meta']['total_modules']} modules, {data['meta']['total_pairs']} pairs")
    return data

def load_graph_import_adjacency():
    """Load graph and build module-level import adjacency (within 1 hop)."""
    print("[2/4] Loading graph and building import adjacency...")
    t0 = time.time()
    with open(GRAPH_PATH) as f:
        data = json.load(f)
    print(f"  Graph loaded in {time.time()-t0:.1f}s")

    nodes = data['nodes']
    edges = data['edges']

    # Build node_id -> module map
    id_to_module = {}
    all_modules = set()
    for n in nodes:
        nid = n['id']
        mod = n.get('module')
        if mod:
            id_to_module[nid] = mod
            all_modules.add(mod)

    # Build module-level adjacency from import edges (where to is a module)
    import_adj = defaultdict(set)
    import_count = 0
    for e in edges:
        if e.get('kind') == 'import':
            from_mod = e['from']
            to_mod = e['to']
            if from_mod in all_modules and to_mod in all_modules and from_mod != to_mod:
                import_adj[from_mod].add(to_mod)
                import_adj[to_mod].add(from_mod)  # bidirectional for connectivity check
                import_count += 1

    # Also add call edges mapped to modules
    call_count = 0
    # For call edges, 'from' is a node ID. We need to find which module 'to' belongs to.
    # 'to' is a short function name - we need to build a name->modules index
    # Actually, let's use a different approach: group nodes by module, then for call edges
    # if source module != target module, add adjacency.
    # But 'to' in call edges is just a short name like 'build_authorize_request', not a node ID.
    # Let's try to resolve: build name -> set of modules
    name_to_modules = defaultdict(set)
    for n in nodes:
        name_to_modules[n['name']].add(n.get('module'))

    for e in edges:
        if e.get('kind') == 'calls':
            from_id = e['from']
            to_name = e['to']
            from_mod = id_to_module.get(from_id)
            if from_mod and to_name in name_to_modules:
                for to_mod in name_to_modules[to_name]:
                    if to_mod and to_mod != from_mod:
                        import_adj[from_mod].add(to_mod)
                        import_adj[to_mod].add(from_mod)
                        call_count += 1

    print(f"  Import adjacency: {len(import_adj)} modules, {import_count} import edges, {call_count} call edges mapped")

    # Free memory
    del data, nodes, edges, id_to_module, name_to_modules
    return import_adj, all_modules


def analysis_1_complementarity(cochange_data, import_adj):
    """What % of co-change pairs are NOT import-connected within 2 hops?"""
    print("[3/4] Analysis 1: Complementarity...")
    edges = cochange_data['edges']

    # Build 2-hop closure for import graph
    # For each module, its 2-hop neighbors = direct neighbors + neighbors of neighbors
    # We'll check on-the-fly to avoid huge memory

    total_pairs = 0
    connected_1hop = 0
    connected_2hop = 0
    not_connected = 0
    not_connected_by_weight = defaultdict(int)
    total_by_weight = defaultdict(int)

    seen_pairs = set()

    for mod_a, partners in edges.items():
        for p in partners:
            mod_b = p['module']
            weight = p['weight']
            pair = tuple(sorted([mod_a, mod_b]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            total_pairs += 1

            # Bucket weight
            if weight <= 5:
                wbucket = str(weight)
            elif weight <= 10:
                wbucket = "6-10"
            elif weight <= 20:
                wbucket = "11-20"
            else:
                wbucket = "21+"
            total_by_weight[wbucket] += 1

            # Check 1-hop
            neighbors_a = import_adj.get(mod_a, set())
            if mod_b in neighbors_a:
                connected_1hop += 1
                connected_2hop += 1
                continue

            # Check 2-hop
            found_2hop = False
            for neighbor in neighbors_a:
                if mod_b in import_adj.get(neighbor, set()):
                    found_2hop = True
                    break

            if found_2hop:
                connected_2hop += 1
            else:
                not_connected += 1
                not_connected_by_weight[wbucket] += 1

    complementarity = not_connected / total_pairs * 100 if total_pairs > 0 else 0

    # Build report
    report = f"""# Analysis 1: Co-change vs Import Graph Complementarity

## Summary

| Metric | Value |
|--------|-------|
| Total unique co-change pairs (weight >= 3) | {total_pairs:,} |
| Import-connected (1-hop) | {connected_1hop:,} ({connected_1hop/total_pairs*100:.1f}%) |
| Import-connected (within 2-hop) | {connected_2hop:,} ({connected_2hop/total_pairs*100:.1f}%) |
| NOT import-connected (within 2-hop) | {not_connected:,} ({not_connected/total_pairs*100:.1f}%) |
| **Complementarity ratio** | **{complementarity:.1f}%** |

## Interpretation

The complementarity ratio of **{complementarity:.1f}%** means that {complementarity:.1f}% of evolutionary
coupling relationships (modules that frequently change together) cannot be discovered
through structural analysis of imports and call graphs alone.

This represents the unique value that co-change analysis adds on top of static code analysis.

## Complementarity by Weight Bucket

| Weight | Total Pairs | Not Connected | Complementarity |
|--------|-------------|---------------|-----------------|
"""
    for wb in ["3", "4", "5", "6-10", "11-20", "21+"]:
        tot = total_by_weight.get(wb, 0)
        nc = not_connected_by_weight.get(wb, 0)
        pct = nc / tot * 100 if tot > 0 else 0
        report += f"| {wb} | {tot:,} | {nc:,} | {pct:.1f}% |\n"

    report += f"""
## Methodology

- Co-change pairs: all module pairs with co-change weight >= 3 from {cochange_data['meta']['total_commits']:,} commits
- Import graph: built from import edges (module-to-module) and call edges (function-to-function, mapped to modules)
- 2-hop check: module A and B are "import-connected" if there exists a path of length <= 2 in the undirected import graph
- Services indexed: {', '.join(cochange_data['meta']['repos_indexed'])}
"""

    with open(f"{OUT_DIR}/01_complementarity_analysis.md", "w") as f:
        f.write(report)
    print(f"  Complementarity ratio: {complementarity:.1f}%")
    print(f"  Saved to {OUT_DIR}/01_complementarity_analysis.md")


def analysis_2_statistics(cochange_data):
    """Co-change distribution statistics."""
    print("[3/4] Analysis 2: Distribution statistics...")
    edges = cochange_data['edges']
    meta = cochange_data['meta']

    # Collect all unique pairs with weights
    seen_pairs = set()
    all_weights = []
    partners_per_module = defaultdict(int)
    cross_service = 0
    intra_service = 0

    for mod_a, partners in edges.items():
        partners_per_module[mod_a] = len(partners)
        for p in partners:
            mod_b = p['module']
            weight = p['weight']
            pair = tuple(sorted([mod_a, mod_b]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            all_weights.append(weight)

            svc_a = extract_service(mod_a)
            svc_b = extract_service(mod_b)
            if svc_a == svc_b:
                intra_service += 1
            else:
                cross_service += 1

    total_pairs = len(all_weights)

    # Weight distribution
    weight_buckets = Counter()
    for w in all_weights:
        if w <= 5:
            weight_buckets[str(w)] += 1
        elif w <= 10:
            weight_buckets["6-10"] += 1
        elif w <= 20:
            weight_buckets["11-20"] += 1
        else:
            weight_buckets["21+"] += 1

    # Partners per module distribution
    partner_counts = sorted(partners_per_module.values())
    n = len(partner_counts)
    median_partners = partner_counts[n // 2] if n > 0 else 0
    p90_partners = partner_counts[int(n * 0.9)] if n > 0 else 0
    p99_partners = partner_counts[int(n * 0.99)] if n > 0 else 0
    max_partners = partner_counts[-1] if n > 0 else 0
    mean_partners = sum(partner_counts) / n if n > 0 else 0

    # Find module with most partners
    max_partner_module = max(partners_per_module, key=partners_per_module.get)

    # Cold start: modules in graph but not in cochange
    modules_with_cochange = set(edges.keys())
    # total modules from meta
    total_modules_in_index = meta['total_modules']
    cold_start = total_modules_in_index - len(modules_with_cochange)

    # Top co-change pairs by weight
    top_pairs = sorted(seen_pairs, key=lambda p: next(
        pp['weight'] for pp in edges[p[0]] if pp['module'] == p[1]
    ) if p[0] in edges else 0, reverse=True)

    # Rebuild weight lookup
    pair_weights = {}
    for mod_a, partners in edges.items():
        for p in partners:
            pair = tuple(sorted([mod_a, p['module']]))
            pair_weights[pair] = p['weight']

    top_10 = sorted(pair_weights.items(), key=lambda x: x[1], reverse=True)[:10]

    report = f"""# Analysis 2: Co-change Distribution Statistics

## Weight Distribution

| Weight | Pairs | % of Total |
|--------|-------|------------|
"""
    for wb in ["3", "4", "5", "6-10", "11-20", "21+"]:
        cnt = weight_buckets.get(wb, 0)
        pct = cnt / total_pairs * 100 if total_pairs > 0 else 0
        report += f"| {wb} | {cnt:,} | {pct:.1f}% |\n"

    report += f"""| **Total** | **{total_pairs:,}** | **100%** |

## Partners Per Module Distribution

| Metric | Value |
|--------|-------|
| Total modules with co-change data | {len(modules_with_cochange):,} |
| Mean partners per module | {mean_partners:.1f} |
| Median partners per module | {median_partners} |
| P90 partners per module | {p90_partners} |
| P99 partners per module | {p99_partners} |
| Max partners per module | {max_partners} |
| Module with most partners | `{max_partner_module}` |

## Cold-Start Modules

| Metric | Value |
|--------|-------|
| Total modules in co-change index | {total_modules_in_index:,} |
| Modules WITH co-change partners | {len(modules_with_cochange):,} |
| Modules with ZERO co-change partners (cold-start) | {cold_start:,} ({cold_start/total_modules_in_index*100:.1f}%) |

Note: "Cold-start" modules have no co-change signal. For these modules, retrieval must
rely entirely on structural (import/call) analysis or semantic similarity.

## Cross-Service vs Intra-Service

| Type | Pairs | % |
|------|-------|---|
| Intra-service (same repo) | {intra_service:,} | {intra_service/total_pairs*100:.1f}% |
| Cross-service (different repo) | {cross_service:,} | {cross_service/total_pairs*100:.1f}% |
| **Total** | **{total_pairs:,}** | **100%** |

## Top 10 Strongest Co-change Pairs

| Rank | Module A | Module B | Weight |
|------|----------|----------|--------|
"""
    for i, (pair, w) in enumerate(top_10, 1):
        # Shorten module names for readability
        a_short = "::".join(pair[0].split("::")[-3:])
        b_short = "::".join(pair[1].split("::")[-3:])
        report += f"| {i} | `{a_short}` | `{b_short}` | {w} |\n"

    report += f"""
## Source Data

- Total commits analyzed: {meta['total_commits']:,}
- Repos: {', '.join(meta['repos_indexed'])}
- Minimum co-change weight threshold: {meta['min_weight']}
- Top-K partners per module: {meta['top_k']}
"""

    with open(f"{OUT_DIR}/02_cochange_statistics.md", "w") as f:
        f.write(report)
    print(f"  Saved to {OUT_DIR}/02_cochange_statistics.md")


def analysis_3_service_coupling(cochange_data):
    """Service boundary analysis."""
    print("[4/4] Analysis 3: Service coupling...")
    edges = cochange_data['edges']

    # Per-service stats
    service_modules = defaultdict(set)  # service -> set of modules
    service_cross_modules = defaultdict(set)  # service -> modules with cross-service partners
    service_pair_weight = defaultdict(int)  # (svc_a, svc_b) -> total weight
    service_pair_count = defaultdict(int)  # (svc_a, svc_b) -> number of pairs

    seen_pairs = set()

    for mod_a, partners in edges.items():
        svc_a = extract_service(mod_a)
        service_modules[svc_a].add(mod_a)
        for p in partners:
            mod_b = p['module']
            weight = p['weight']
            svc_b = extract_service(mod_b)
            service_modules[svc_b].add(mod_b)

            pair = tuple(sorted([mod_a, mod_b]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            if svc_a != svc_b:
                service_cross_modules[svc_a].add(mod_a)
                service_cross_modules[svc_b].add(mod_b)
                svc_pair = tuple(sorted([svc_a, svc_b]))
                service_pair_weight[svc_pair] += weight
                service_pair_count[svc_pair] += 1

    # Sort services
    all_services = sorted(service_modules.keys())

    report = """# Analysis 3: Service Boundary Coupling

## Per-Service Cross-Boundary Exposure

| Service | Total Modules | Modules with Cross-Service Partners | Exposure % |
|---------|---------------|-------------------------------------|------------|
"""
    for svc in all_services:
        total = len(service_modules[svc])
        cross = len(service_cross_modules.get(svc, set()))
        pct = cross / total * 100 if total > 0 else 0
        report += f"| {svc} | {total:,} | {cross:,} | {pct:.1f}% |\n"

    # Top 10 service pairs
    top_pairs = sorted(service_pair_weight.items(), key=lambda x: x[1], reverse=True)[:10]

    report += """
## Top 10 Service Pairs by Total Co-change Weight

| Rank | Service A | Service B | Total Weight | Pair Count | Avg Weight |
|------|-----------|-----------|-------------|------------|------------|
"""
    for i, (pair, total_w) in enumerate(top_pairs, 1):
        count = service_pair_count[pair]
        avg = total_w / count if count > 0 else 0
        report += f"| {i} | {pair[0]} | {pair[1]} | {total_w:,} | {count:,} | {avg:.1f} |\n"

    # Full service-pair matrix (for services with any cross-coupling)
    report += """
## Cross-Service Coupling Matrix (Total Weight)

Shows total co-change weight between each service pair. Only pairs with weight > 0 shown.

| Service A | Service B | Weight | Pairs |
|-----------|-----------|--------|-------|
"""
    for pair, w in sorted(service_pair_weight.items(), key=lambda x: x[1], reverse=True):
        count = service_pair_count[pair]
        report += f"| {pair[0]} | {pair[1]} | {w:,} | {count:,} |\n"

    report += """
## Interpretation

- **Exposure %**: The fraction of a service's modules that have evolutionary coupling
  to modules in other services. High exposure means the service is tightly coupled at
  the implementation level, regardless of what the API boundaries suggest.
- **Top service pairs**: These represent the strongest cross-service evolutionary coupling.
  Changes in one service frequently require changes in the paired service.
- This data is valuable for: team coordination, deploy ordering, blast radius estimation,
  and identifying candidates for service merging or better API boundaries.
"""

    with open(f"{OUT_DIR}/03_service_coupling.md", "w") as f:
        f.write(report)
    print(f"  Saved to {OUT_DIR}/03_service_coupling.md")


def main():
    t_start = time.time()

    cochange_data = load_cochange()
    import_adj, all_graph_modules = load_graph_import_adjacency()

    analysis_1_complementarity(cochange_data, import_adj)
    del import_adj  # free memory

    analysis_2_statistics(cochange_data)
    analysis_3_service_coupling(cochange_data)

    print(f"\nAll analyses complete in {time.time()-t_start:.1f}s")
    print(f"Results saved to {OUT_DIR}/")


if __name__ == "__main__":
    main()
