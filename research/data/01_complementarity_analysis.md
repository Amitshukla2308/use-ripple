# Analysis 1: Co-change vs Import Graph Complementarity

## Summary

| Metric | Value |
|--------|-------|
| Total unique co-change pairs (weight >= 3) | 69,009 |
| Import-connected (1-hop) | 0 (0.0%) |
| Import-connected (within 2-hop) | 0 (0.0%) |
| NOT import-connected (within 2-hop) | 69,009 (100.0%) |
| **Complementarity ratio** | **100.0%** |

## Interpretation

The complementarity ratio of **100.0%** means that 100.0% of evolutionary
coupling relationships (modules that frequently change together) cannot be discovered
through structural analysis of imports and call graphs alone.

This represents the unique value that co-change analysis adds on top of static code analysis.

## Complementarity by Weight Bucket

| Weight | Total Pairs | Not Connected | Complementarity |
|--------|-------------|---------------|-----------------|
| 3 | 19,653 | 19,653 | 100.0% |
| 4 | 12,699 | 12,699 | 100.0% |
| 5 | 8,419 | 8,419 | 100.0% |
| 6-10 | 17,745 | 17,745 | 100.0% |
| 11-20 | 7,377 | 7,377 | 100.0% |
| 21+ | 3,116 | 3,116 | 100.0% |

## Methodology

- Co-change pairs: all module pairs with co-change weight >= 3 from 138,117 commits
- Import graph: built from import edges (module-to-module) and call edges (function-to-function, mapped to modules)
- 2-hop check: module A and B are "import-connected" if there exists a path of length <= 2 in the undirected import graph
- Services indexed: basilisk-v3, euler-api-customer, euler-api-gateway, euler-api-order, euler-api-pre-txn, euler-api-txns, euler-db, euler-drainer, graphh, haskell-sequelize, token_issuer_portal_backend
