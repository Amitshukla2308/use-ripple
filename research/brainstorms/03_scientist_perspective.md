# Research Memo: HyperRetrieval from an ML Scientist's Perspective

**Author:** Research brainstorm (ML/code-intelligence perspective)
**Date:** 2026-03-31
**System under study:** HyperRetrieval — a 6-signal code retrieval platform indexing 94K symbols across 12 Haskell/Rust microservices

---

## 1. What's Genuinely Novel Here

### Signals no published system combines

Published code retrieval systems use at most 2-3 of these signals in isolation. HyperRetrieval has all six loaded simultaneously and fused at query time:

| Signal | Scale | What exists in literature | What HyperRetrieval adds |
|--------|-------|--------------------------|--------------------------|
| **Semantic vectors** | 94K symbols, 4096d (Qwen3-Embed-8B) | GraphCodeBERT (2021), CodeSage (2024), CodeBERT — all use smaller dims (768d), trained on Python/Java, not Haskell/Rust | Production-scale embeddings over a real enterprise Haskell codebase with cluster-purpose-enriched text (subsystem context baked into the embedding input) |
| **BM25 keyword index** | 94K symbols | Standard in Sourcegraph, GitHub code search, Cody | Nothing novel alone — the novelty is in the RRF fusion with all other signals |
| **Call graph** | 64K entries | CodeQL, Dependabot, Joern — static analysis tools, not retrieval | Used for *retrieval augmentation* (synthetic co-change injection, callee/caller traversal in context building), not just analysis |
| **Import graph** | 4,809 modules, 42K edges, 8,706 cross-service | Dependabot tracks package-level deps; no system uses module-level import graphs for *retrieval ranking* | Module-level import graph with cross-service edge classification; used for blast-radius computation and context expansion |
| **Co-change index** | 111K weighted pairs, 7,363 modules | Historage (2011), Ying et al. (2004) studied evolutionary coupling; Cody (2024) uses file-level co-edit for ranking | Module-level co-change with *weight thresholds* and *synthetic cold-start augmentation* from call graph — no published system does this bidirectional bootstrap |
| **Leiden cluster summaries** | AI-generated business-purpose per cluster | No published code RAG system enriches embeddings with LLM-generated cluster purpose descriptions | Cluster purpose text is *part of the embedding input* (see `node_to_text()` in `03_embed.py`: `"subsystem: {cluster_name}"`, `"purpose: {cluster_purpose}"`) — the embedding itself encodes business semantics, not just code syntax |

### The specific gap in the literature

- **GraphCodeBERT** (Guo et al., 2021): Uses data flow edges within a single function. Does not use inter-module call graphs, import graphs, or evolutionary coupling.
- **CodeSage** (Zhang et al., 2024): Contrastive learning on code+docs. Single-signal (semantic). No graph structure.
- **Cody** (Sourcegraph, 2024): Uses file-level co-edit history for reranking. Does not fuse with call graph or cluster summaries. No cross-service awareness.
- **RepoFormer** (Wu et al., 2024): Repository-level code completion. Uses file structure but not call graphs or co-change.
- **SWE-bench** / **SWE-Agent** (Yang et al., 2024): Evaluates end-to-end patch generation, not retrieval quality in isolation.

**The gap:** No published system fuses dense semantic search + BM25 + call graph + import graph + evolutionary coupling + LLM-generated cluster descriptions for code retrieval. HyperRetrieval does this with RRF fusion (`rrf_merge()`) and graph expansion (`module_graph_expand()`, `cochange_path_traverse()`).

---

## 2. Five Research Questions Worth Answering

### H1: Co-change-augmented retrieval improves cross-service recall

> **Hypothesis:** Adding co-change graph expansion to semantic+BM25 retrieval improves Recall@10 by >=15% for queries that span service boundaries, compared to semantic+BM25 alone.

**Rationale:** Cross-service queries are the hardest case — the relevant code lives in a different namespace, different language sometimes, and has no lexical overlap with the query. Co-change captures the "these things change together in practice" signal that is invisible to both embeddings and keyword search.

**Testable because:** We can construct a held-out evaluation set from the co-change index itself (modules with high co-change weight that are in different services) and measure whether the retrieval system returns the partner module.

### H2: Synthetic co-change from call graphs recovers signal for cold-start modules

> **Hypothesis:** For modules with <3 git commits (cold-start), synthetic co-change edges derived from the call graph recover >=60% of the co-change partners that would appear after 50+ commits.

**Rationale:** `_inject_synthetic_cochange()` uses call graph edges with weight=0.3 to bootstrap modules that have no git history. If this is validated, it means you can deploy the system on a new repo with minimal git history and still get useful co-change signal.

**Testable because:** We can simulate cold-start by masking the most recent N commits from the co-change builder and measuring overlap between synthetic edges and the real edges that would have been discovered.

### H3: Cluster-purpose-enriched embeddings outperform raw code embeddings

> **Hypothesis:** Embeddings generated from `node_to_text()` (which includes `cluster_name`, `cluster_purpose`, `service_role`, and `recent_changes`) achieve >=10% higher MRR on natural-language-to-code retrieval compared to embeddings of raw code/signature text alone.

**Rationale:** `node_to_text()` injects 5 signals beyond the code itself: subsystem name, purpose description, external dependencies, recent commit messages, and service role. This is a form of *metadata-augmented embedding* that hasn't been benchmarked in the code retrieval literature.

**Testable because:** We can re-embed a subset of nodes with a stripped-down `node_to_text()` (code-only) and compare retrieval quality on a held-out query set.

### H4: RRF fusion of 3+ heterogeneous signals outperforms any single signal and any 2-signal combination

> **Hypothesis:** RRF fusion of semantic vectors + BM25 + co-change graph traversal achieves a higher NDCG@20 than any single signal or any pairwise combination, with the marginal contribution of the third signal being >=5%.

**Rationale:** The current `unified_search()` fuses vector + BM25 via RRF. But co-change is only used in `get_blast_radius()`, not in the main search path. Integrating co-change into the main RRF fusion would be a new contribution.

**Testable because:** Ablation study — run the same query set with {vector}, {BM25}, {co-change}, {vector+BM25}, {vector+co-change}, {BM25+co-change}, {all three} and compare NDCG.

### H5: Import graph structure predicts co-change probability

> **Hypothesis:** Module pairs connected by import edges are >=3x more likely to co-change (weight>=3 in the co-change index) than pairs at import-distance >=3, and this predictive power holds after controlling for service membership.

**Rationale:** This tests whether the import graph and co-change graph carry redundant or complementary information. If import proximity strongly predicts co-change, the signals are partially redundant. If not, they are genuinely complementary and worth fusing.

**Testable because:** We have both graphs fully materialized. A logistic regression with features {import_distance, same_service, same_cluster} predicting {co-change >= 3} would answer this directly.

---

## 3. Data Analysis to Run First (Before Any ML Training)

### 3.1 Co-change signal quality

1. **Weight distribution:** Histogram of co-change weights across all 111K pairs. Is it power-law? What fraction of pairs have weight >= 10 (strong signal) vs. weight = 3 (minimum threshold, possibly noise)?

2. **Cross-service vs. intra-service ratio:** What fraction of co-change pairs cross service boundaries? If <5%, the co-change signal is mostly capturing intra-module locality (redundant with import graph). If >15%, it's capturing real cross-service coupling.

3. **Temporal stability:** Split git history into first-half and second-half. Compute co-change on each half separately. What is the Jaccard similarity of the top-10 partners per module? If <0.3, the signal is unstable and probably noise. If >0.5, it's a real structural property.

4. **Mega-commit contamination:** The builder skips commits touching >40 files. What fraction of total commits are skipped? What is the average weight contributed by commits in the 30-40 file range (potential near-mega-commits that add noise)?

### 3.2 Import graph structure

5. **Degree distribution:** In-degree and out-degree of the module import graph. Identify hub modules (high in-degree = widely imported, e.g., `euler-db` types). These hubs will dominate any graph-based expansion.

6. **Cross-service edge density:** 8,706 of 42K edges are cross-service (~20%). Which service pairs have the densest cross-service coupling? This tells us where co-change signal is most likely to add value.

### 3.3 Call graph coverage

7. **Call graph vs. import graph overlap:** For every edge in the import graph, does the call graph have at least one function-level call? The gap reveals modules that are imported but never directly called (type-only imports, re-exports).

8. **Synthetic co-change coverage:** After `_inject_synthetic_cochange()`, how many modules go from 0 co-change partners to >0? What is the average number of synthetic vs. real partners?

### 3.4 Cluster quality

9. **Cluster size distribution:** How many nodes per Leiden cluster? Clusters of size 1 are noise. Clusters of size >500 are too coarse.

10. **Cluster-service alignment:** Do clusters align with service boundaries, or do they span services? Cross-service clusters are the most interesting for retrieval because they identify cohesive subsystems that span the architecture.

### What would make me confident the signal is real

- Co-change temporal stability Jaccard > 0.4
- Cross-service co-change pairs > 10% of total
- Import graph predicts co-change with AUC > 0.7 but not > 0.95 (complementary, not redundant)
- Cluster-purpose embedding improvement over code-only is consistent across multiple query types

### What would make me suspicious the signal is noise

- Co-change weights follow a flat distribution (no heavy tail) — suggests uniform noise
- Temporal stability Jaccard < 0.2 — co-change partners are random
- >50% of co-change pairs are within the same module directory — just capturing file proximity
- Synthetic co-change edges dominate the index (>40% of all edges are synthetic)

---

## 4. Experiment Design for Top Research Question (H4: Multi-Signal RRF Fusion)

### Setup

**Evaluation dataset construction:**
Since there is no existing benchmark for multi-service Haskell/Rust retrieval, we construct one from the data itself:

1. **From co-change pairs:** Take the top-200 highest-weight cross-service co-change pairs. For each pair (A, B), formulate a query: "Find code related to [cluster_purpose of A]". The ground truth is that B should appear in the results (it co-changes with A but lives in a different service).

2. **From call graph:** Take 100 cross-service caller-callee pairs. Query with the caller's name/purpose. Ground truth: the callee should appear.

3. **From cluster summaries:** Take 50 clusters with clear purpose descriptions. Query with a paraphrase of the purpose. Ground truth: >=3 members of that cluster should appear in results.

Total: 350 query-relevance pairs with natural stratification across difficulty levels.

### Baseline

- **B1:** Semantic vector search only (`stratified_vector_search()`)
- **B2:** BM25 only (`bm25_search()`)
- **B3:** Keyword search only (`cross_service_keyword_search()`)

### Treatment conditions

- **T1:** Vector + BM25 via RRF (current `unified_search()`)
- **T2:** Vector + BM25 + co-change expansion via RRF
- **T3:** Vector + BM25 + import graph expansion via RRF
- **T4:** Vector + BM25 + co-change + import graph via RRF (full 4-signal)
- **T5:** T4 + cluster-purpose re-ranking (boost results whose cluster matches query cluster)

### Metrics

- **Recall@K** (K = 5, 10, 20): Does the ground-truth module appear in the top-K results?
- **MRR** (Mean Reciprocal Rank): How high does the ground-truth rank?
- **NDCG@20**: Graded relevance using co-change weight as relevance score
- **Cross-service Recall@10**: Recall measured only on ground-truth items in a different service from the query seed (the hard case)

### Minimum effect size worth publishing

- Recall@10 improvement of >=8% absolute (e.g., 0.45 -> 0.53) for the multi-signal treatment over the best single-signal baseline
- Cross-service Recall@10 improvement of >=15% absolute
- These thresholds are based on typical improvements reported in information retrieval literature (BM25 -> neural retrieval gains are typically 5-15%)

### Statistical rigor

- Bootstrap confidence intervals (1000 resamples) on all metrics
- Paired sign test between T4 and T1 per-query
- Report effect sizes (Cohen's d), not just p-values

---

## 5. What Would Fail (and How to Detect It Early)

### Failure mode 1: Co-change signal is noise

**Symptom:** Adding co-change to RRF fusion does not improve or actually *hurts* Recall@10.
**Early detection:** Run the temporal stability analysis (Section 3.1, item 3). If Jaccard < 0.2, the co-change signal is too noisy to help.
**Mitigation:** Raise `MIN_WEIGHT` from 3 to 10. Or use co-change only for re-ranking (not retrieval expansion).

### Failure mode 2: Evaluation set is circular

**Symptom:** Metrics look great but the improvement doesn't generalize.
**Root cause:** If we build the evaluation set from co-change pairs and then test whether co-change helps find those pairs, we're measuring tautology.
**Mitigation:** Ensure the evaluation set is constructed from *held-out* co-change pairs (temporal split: train on first 80% of commits, evaluate on pairs that appear only in the last 20%). Or use an entirely independent signal (developer-written queries, issue titles) for evaluation.

### Failure mode 3: Hub modules dominate

**Symptom:** Import graph expansion helps, but only because it always returns `euler-db` type modules (which are imported by everything).
**Early detection:** Check if the top-5 most-returned modules via graph expansion are all high-degree hubs. If so, apply degree-based damping (weight edges by 1/sqrt(degree)).
**Mitigation:** TF-IDF-style normalization on graph expansion: penalize modules that appear in many expansions.

### Failure mode 4: Embedding model is too good

**Symptom:** Semantic vector search alone achieves Recall@10 > 0.85, leaving no room for complementary signals.
**Early detection:** Run B1 first. If it's already excellent, pivot the research question to "when do graph signals help?" (characterizing the failure modes of dense retrieval).
**Mitigation:** Focus on the *hard* subset — cross-service queries where the relevant code has no lexical overlap with the query. Graph signals should matter most there.

### Failure mode 5: Haskell/Rust specificity limits generalizability

**Symptom:** Reviewers reject the paper because the codebase is Haskell/Rust and results may not transfer to Python/Java.
**Mitigation:** Frame the contribution as the *fusion framework*, not the specific results. Show ablation results that characterize *when* each signal helps, so readers can predict applicability to their own codebases.

---

## 6. Beyond Embeddings: Other ML Problems This Data Enables

### 6.1 Change Impact Prediction

**Problem:** Given a proposed code change (diff), predict which *other* modules will need to change.
**Data:** Co-change index provides supervised labels. Import graph + call graph provide features. This is a link prediction problem on a heterogeneous graph.
**Model:** GNN (e.g., R-GCN) on the combined import+call+co-change graph, trained to predict co-change probability for unseen module pairs.
**Value:** Automated "you forgot to update X" warnings in code review.

### 6.2 Automated Cross-Service Flow Discovery

**Problem:** Automatically discover end-to-end business flows (e.g., "payment authorization flow") by combining call graph traversal with cluster summaries.
**Data:** Call graph provides the execution paths. Cluster summaries provide business-level semantics. Co-change groups modules that participate in the same business process.
**Method:** Community detection on a weighted graph where edge weight = alpha * call_weight + beta * cochange_weight + gamma * import_weight. Then LLM-label each community with a flow name.
**Value:** Auto-generated architecture documentation that stays current.

### 6.3 Code Review Prioritization

**Problem:** Given a PR with N changed files, rank which files need the most careful review.
**Data:** Co-change index reveals which files have historically been "error-prone partners" (high co-change weight but no import edge — implicit coupling). Call graph depth reveals criticality (functions called transitively by many entry points).
**Method:** Combine (1) co-change anomaly score (file changed but its usual co-change partner was NOT changed), (2) call graph centrality (PageRank on the call graph), (3) blast radius size.
**Value:** Focus reviewer attention on the riskiest parts of a PR.

### 6.4 Test Selection (Predictive Test Ordering)

**Problem:** Given a code change, predict which tests are most likely to fail.
**Data:** Co-change index often links source modules to their test modules (they co-change by definition). Import graph shows test dependencies.
**Method:** For a changed module M, rank tests by: co-change_weight(M, test) + import_distance(M, test)^{-1}.
**Value:** Run the most relevant tests first in CI, reducing time-to-feedback.

### 6.5 Semantic Code Clone Detection

**Problem:** Find functionally similar code across services (potential for library extraction).
**Data:** High cosine similarity in the 4096d embedding space + different services + no import edge = likely semantic clone.
**Method:** Find all cross-service pairs with cosine > 0.92 and no import/call relationship. Rank by the number of such pairs per cluster.
**Value:** Identify library extraction opportunities (reduce code duplication across services).

### 6.6 Developer Expertise Modeling

**Problem:** Given a code change, recommend the best reviewer.
**Data:** Git history (already parsed for co-change) includes author information. Build an author-module affinity matrix.
**Method:** For each file in a PR, find the authors with the highest historical commit count in co-changing modules. Weight by recency.
**Value:** Automated reviewer suggestion that considers *implicit* expertise (author knows the modules that co-change with the changed files, not just the changed files themselves).

---

## 7. The Two-Paper Arc

### Paper 1: "HyperFuse: Multi-Signal Retrieval Fusion for Enterprise Code Intelligence"

**Venue:** ICSE 2027, FSE 2027, or ASE 2027 (software engineering)

**Contribution:**
1. A retrieval fusion framework that combines 6 heterogeneous signals (dense vectors, BM25, call graph, import graph, evolutionary coupling, cluster summaries) via RRF with graph-based expansion
2. A novel cold-start mechanism that bootstraps co-change signal from static call graphs (`_inject_synthetic_cochange()`)
3. An evaluation methodology for multi-service code retrieval using self-supervised benchmark construction
4. Ablation study showing the marginal contribution of each signal, with particular emphasis on when graph signals help (cross-service queries) vs. when they don't (intra-module queries)

**Key result (predicted):** The full 6-signal fusion achieves 15-25% higher cross-service Recall@10 than semantic search alone, with co-change and import graph contributing the most on cross-service queries.

**Framing:** This is NOT "we built a tool" (that's a demo paper). This is "we show that evolutionary coupling and structural graph signals provide complementary retrieval signal to dense embeddings, and we quantify when each signal matters."

### Paper 2: "GraphChange: Predicting Cross-Service Change Impact with Heterogeneous Code Graphs"

**Venue:** ICML 2027, NeurIPS 2027, or KDD 2027 (ML venue)

**Contribution:**
1. A heterogeneous graph neural network for change impact prediction, trained on the combined import+call+co-change graph
2. Node features from the 4096d Qwen3 embeddings (frozen, not fine-tuned) + structural features (degree, centrality, cluster ID)
3. Temporal evaluation: train on commits before time T, predict co-change for commits after T
4. Comparison with (a) embedding-only baselines, (b) graph-only baselines (GCN on import graph), (c) the full heterogeneous model

**Key result (predicted):** The heterogeneous graph model outperforms both embedding-only and graph-only baselines by 10-20% on precision@10 for change impact prediction, with the strongest gains on cross-service predictions.

**How they build on each other:**
- Paper 1 establishes that the signals are complementary (ablation study) and that fusion works for retrieval
- Paper 2 takes the same data but asks a *prediction* question (given a change, what else will change?) rather than a *retrieval* question (given a query, find relevant code)
- Paper 1's evaluation methodology (self-supervised benchmark from co-change) becomes Paper 2's training data
- Paper 2's GNN can become a learned fusion model that replaces Paper 1's hand-tuned RRF weights

---

## 8. Quick Wins: Publishable Analysis You Can Run Today

### Quick Win 1: "The Complementarity of Structural and Evolutionary Coupling in Enterprise Code" (empirical study)

**What to compute (no training required):**

```
For all 111K co-change pairs:
  1. Compute import_distance(A, B) using BFS on the import graph
  2. Compute call_graph_connected(A, B) from the call graph
  3. Compute same_service(A, B)
  4. Compute same_cluster(A, B)

Build a contingency table:
  - Import-connected AND co-change: X pairs
  - Import-connected but NOT co-change: Y pairs
  - NOT import-connected but co-change: Z pairs  <-- THIS IS THE INTERESTING QUADRANT
  - Neither: W pairs

Report:
  - What fraction of co-change pairs have NO import path? (implicit coupling)
  - What fraction of import-connected pairs do NOT co-change? (stable interfaces)
  - Correlation between co-change weight and import distance
  - Visualization: scatter plot of (import_distance, cochange_weight) colored by same_service
```

**Why it's publishable:** This characterization of the relationship between structural coupling (imports) and evolutionary coupling (co-change) at the *module* level in a *multi-service* codebase has not been done at this scale. Previous work (Oliva & Gerosa, 2015; Geipel & Schweitzer, 2012) studied single-repo Java projects.

**Time to run:** ~30 minutes of scripting, ~5 minutes of compute.

### Quick Win 2: "Cross-Service Evolutionary Coupling Patterns in Microservice Architectures"

**What to compute:**

```
For all cross-service co-change pairs (module A in service S1, module B in service S2):
  1. Group by (S1, S2) pair
  2. For each service pair: count pairs, mean weight, max weight
  3. Build a service-to-service coupling heatmap (12x12 matrix)
  4. Identify the top-20 highest-weight cross-service pairs
  5. For each: look up their cluster_purpose — do they share a business function?

Report:
  - Which service pairs are most tightly coupled by evolutionary evidence?
  - Does the coupling pattern match the expected architecture (order -> txns -> gateway)?
  - Are there surprising coupling patterns (services that shouldn't be coupled but are)?
```

**Why it's publishable:** Microservice architecture papers discuss service coupling in theory. This provides *empirical evidence* from a production codebase with 7,363 modules. The heatmap alone is a contribution — it shows where architectural assumptions break down.

### Quick Win 3: Embedding Space Topology Analysis

**What to compute:**

```
Load the 94K x 4096d embeddings from vectors.lance.
  1. Compute pairwise cosine similarity within each service (sample 1000 pairs per service)
  2. Compute pairwise cosine similarity across services (sample 5000 cross-service pairs)
  3. For co-change pairs: what is their cosine similarity distribution?
  4. For non-co-change pairs: what is their cosine similarity distribution?
  5. KS-test between the two distributions

Visualize:
  - t-SNE/UMAP of 5000 sampled nodes, colored by service
  - Same UMAP, colored by Leiden cluster
  - Overlay co-change edges on the UMAP — do they connect nearby points or distant ones?
```

**Why it's publishable:** If co-change pairs have significantly higher embedding similarity than random pairs, the signals are somewhat redundant. If they have similar or *lower* similarity, the signals are complementary — this is the interesting finding. The UMAP with co-change edges overlaid would be a visually compelling figure.

**Time to run:** ~1 hour (embedding loading + UMAP computation on 94K points with GPU).

---

## Summary: Recommended Research Priority

1. **Today:** Run Quick Win 1 (complementarity analysis) — it directly informs whether the multi-signal fusion story is real
2. **This week:** Construct the evaluation dataset (Section 4) and run the single-signal baselines
3. **Next 2 weeks:** Implement co-change integration into `unified_search()` and run the full ablation
4. **Month 1:** Write Paper 1 (HyperFuse) while the ablation results are fresh
5. **Month 2-3:** Build the GNN for Paper 2 using the infrastructure from Paper 1

The strongest publishable contribution is the **ablation study** — showing when each signal helps and when it doesn't. The ML community has many "we added X and got Y% improvement" papers. What's rare is a systematic study of *which signals are complementary vs. redundant* in code retrieval, backed by a real production codebase with 6 distinct signal types.
