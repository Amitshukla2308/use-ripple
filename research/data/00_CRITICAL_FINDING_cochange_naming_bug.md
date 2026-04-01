# CRITICAL FINDING: Co-Change Index Is Silently Broken

**Date:** 2026-04-01
**Severity:** High — the #1 competitive advantage (co-change intelligence) is non-functional

## The Bug

`get_blast_radius()` passes dot-notation module names (e.g., `PaymentFlows`) to `cochange_path_traverse()`, which looks them up in `cochange_index`. But `cochange_index` keys use `service::filepath::Module` format (e.g., `euler-api-txns::euler-x::src-generated::PaymentFlows`).

**Result:** Line 594 of `retrieval_engine.py` — `if m in cochange_index` — returns `False` for every Haskell module. The co-change traversal silently returns empty list. Blast radius reports contain zero co-change neighbors for ~95% of queries.

## Evidence

```python
# What blast_radius passes:
"PaymentFlows" in cochange_index  →  False

# What actually exists:
"euler-api-txns::euler-x::src-generated::PaymentFlows" in cochange_index  →  True
# With rich data: co-changes with Transaction (w=54), TransactionHelper (w=42)
```

## Impact

- `get_blast_radius()` returns only import-graph neighbors, never co-change neighbors
- The `_inject_synthetic_cochange()` function adds edges to `cochange_index` using `::` format — these work for UCS Rust modules but not for Haskell dot-notation modules
- **Every claim about co-change intelligence in the product is effectively false for Haskell**
- The brainstorm analysis (01_complementarity_analysis.md) reported 100% complementarity — this was actually 100% non-overlap due to naming mismatch, not a real finding

## The Fix Needed

Build a bidirectional mapping between the two naming conventions at `initialize()` time:

```
Dot-notation:     PaymentFlows
Co-change key:    euler-api-txns::euler-x::src-generated::PaymentFlows
```

The graph nodes have a `file` attribute (e.g., `euler-api-txns/euler-x/src-generated/PaymentFlows.hs`). The co-change key is derived from the same file path with `::` separators. So the mapping is:

1. For each graph node, take its `file` attribute
2. Convert `/` to `::`, strip extension → get co-change key
3. Store mapping: `{dot_name: cochange_key}` and `{cochange_key: dot_name}`
4. Use this mapping in `cochange_path_traverse()` and `_inject_synthetic_cochange()`

## What This Means for Research

- The complementarity analysis needs to be re-run with proper name mapping
- Co-change signal has NEVER been tested in production (it was broken all along)
- Fixing this is both a bug fix AND a research contribution — we can now measure the actual value of co-change for the first time
- The "before/after" comparison (blast radius with vs without co-change) becomes a natural experiment

## Files Affected

- `serve/retrieval_engine.py`: `cochange_path_traverse()`, `_inject_synthetic_cochange()`, `get_blast_radius()`
- `build/06_build_cochange.py`: Should output the mapping alongside the index
- Research analysis scripts: Need to use the mapping for valid complementarity analysis
