# The Room: Cross-Persona Synthesis & Debate

**Date:** 2026-04-01
**Participants:** VP Engineering (Biz), Senior PM (Prod), ML Scientist (Sci)

---

## Round 1: What's the actual problem we're solving?

**Biz:** We keep building features but we haven't nailed the positioning. Are we a developer tool, a platform, or research infrastructure? The answer determines everything — pricing, buyer, distribution, engineering priorities.

**Prod:** From daily usage, I'll tell you what we ARE: we're the only tool that can answer "what breaks if I change this?" across service boundaries. That's not a developer tool. That's an **engineering safety net**. Every other question we answer (how does X work, who calls Y) is table stakes — Copilot and Cursor will catch up. The blast radius + co-change combination is where we're truly differentiated.

**Sci:** Agree on co-change being the moat. But here's the thing nobody's said yet — **we don't even use co-change in our main search path**. Look at `unified_search()`: it fuses vector + BM25 via RRF. Co-change is ONLY used in `get_blast_radius()`. That's like having a secret weapon in your vault but fighting with your fists.

**Biz:** Wait — so our biggest competitive advantage isn't even wired into the core product?

**Sci:** Correct. Hypothesis H4 in my memo: integrating co-change into the main RRF fusion should improve cross-service retrieval by ≥5% NDCG. That's a quick win AND a paper.

---

## Round 2: What should we build vs. what should we research?

**Prod:** I have a clear #1: **PR Blast Radius Bot**. We already have `pr_analyzer.py`. It already computes blast radius. It's NOT wired into CI/CD. If we made a GitHub Action that comments on every PR with "these modules are likely affected", we'd have adoption overnight. Zero ML needed. Pure engineering.

**Biz:** That's the "sell to the VP" play. A dashboard showing "HyperRetrieval prevented 12 cross-service incidents this month" is how I justify the infrastructure cost. But it's not a moat — anyone can build a CI check.

**Prod:** The moat is the co-change data. Nobody else has 111K weighted module pairs from git history. The CI check is the delivery vehicle; the data is the moat.

**Sci:** I want to push on something bigger. The PR bot is a feature. What if the RESEARCH enabled a category of features that nobody else can build? Here's what I mean:

The three things we uniquely have:
1. **Co-change pairs** (111K, weighted) — evolutionary coupling
2. **Leiden clusters with LLM summaries** — business-context-aware grouping
3. **Cross-service import graph** (8,706 edges) — structural topology

Nobody has all three. The research question is: **do these signals contain information that text-based systems fundamentally cannot learn?**

If we prove that co-change-aware embeddings find things that text embeddings miss (like the splitPayment vs splitSettlement example), that's not just a paper — it's proof that our entire approach is structurally superior.

---

## Round 3: The splitPayment test

**Prod:** Let me make this concrete. Engineers regularly ask about "split payment" and get results mixed with "split settlement." These are completely different flows:
- Split payment = splitting a single payment across multiple methods (card + UPI)
- Split settlement = splitting merchant settlement across multiple bank accounts

Current search confuses them because the text is similar. But in git, `splitPayment` modules NEVER co-change with `splitSettlement` modules. The co-change graph knows they're different worlds.

**Sci:** That's a perfect test case. Before any training, just measure: how many confusable pairs exist? How often does current search mix them up? This is the "Quick Win" from my memo — run it today, 30 minutes of scripting, and you have a concrete number.

**Biz:** If that number is high (say 30%+ of queries return confusable results), that's a clear business case: "Our improved embeddings eliminate cross-domain confusion." If it's low, we need a different story.

---

## Round 4: What do we actually do in the next 4 weeks?

### Week 1 — Data analysis (Scientist leads)

**Sci:** Three analyses, no ML training:

1. **Co-change vs import graph overlap**: What % of co-change pairs are also import-connected? If high, signals are redundant. If low (<40%), they're complementary — publishable finding alone.

2. **Confusable pair census**: Find all function pairs where cosine similarity > 0.85 but co-change weight = 0. These are the cases current search gets wrong. Count them. Curate the top 20 most egregious (like splitPayment/splitSettlement).

3. **Cold-start validation**: For modules with <3 commits, do synthetic co-change edges (from call graph) predict real co-change that appears later? Mask recent history and check.

**Prod:** Can you also measure how often the chat app's retrieval returns results from the wrong service? I see this constantly — ask about a gateway function, get results from euler-db.

**Sci:** Yes — I'll add cross-service precision to the analysis.

### Week 2 — The experiment (Scientist leads, Product evaluates)

**Sci:** Based on Week 1 findings, two paths:

**Path A** (if confusable pairs are common): Train co-change contrastive embeddings. Use the confusable pairs as hard negatives. Measure recall improvement on held-out co-change pairs + the curated disambiguation set.

**Path B** (if co-change adds signal beyond import graph): Integrate co-change into the main `unified_search()` RRF fusion. No embedding training needed — just add co-change as a third retrieval signal alongside vector and BM25. Measure NDCG improvement.

**Prod:** I'll prepare the 50-query evaluation set for blind A/B testing. Mix of:
- Simple lookups (should be fast, correct)
- Cross-service flows (where co-change should help)
- Confusable terms (where disambiguation matters)
- Temporal questions (baseline — we expect these to fail)

### Week 3 — Integration + evaluation (Product leads)

**Prod:** If the experiment shows improvement:
- Wire improved search into both Chainlit and MCP
- Run the 50-query A/B with Juspay engineers
- Measure: retrieval precision, answer quality (1-5 blind score), time-to-useful-answer

### Week 4 — Ship or publish (Business leads)

**Biz:** Two deliverables, not one:

1. **Internal**: PR Blast Radius Bot as a GitHub Action. Uses existing `pr_analyzer.py` + improved retrieval. Ships to all 12 repos.

2. **External**: Research report / paper draft with findings from the embedding experiment. Whether it's positive or negative, the analysis of co-change vs import vs semantic signal complementarity is publishable.

---

## Convergence: The Three Bets

| Bet | Owner | Timeline | Success metric |
|-----|-------|----------|----------------|
| **Co-change signal analysis** (is the signal real?) | Scientist | Week 1 | Complementarity ratio, confusable pair count |
| **Improved retrieval** (does it help?) | Scientist + Product | Week 2-3 | Recall@10 gain ≥15%, A/B win rate ≥60% |
| **PR Blast Radius Bot** (does it ship?) | Product + Business | Week 3-4 | Deployed to ≥3 repos, ≥10 PR comments generated |

---

## Key Disagreements (Unresolved)

**Should we train new embeddings or just add co-change to RRF?**
- Sci: Embeddings are the publishable path. RRF addition is an engineering win but not novel.
- Prod: I don't care about the paper — I care about search quality. If RRF integration gives 80% of the benefit at 10% of the effort, do that first.
- Biz: Do both. RRF first (ships in days), embeddings in parallel (publishes in months).

**Should we fix temporal queries (git history, ownership) or double down on structural?**
- Prod: Temporal is the #1 gap. Engineers ask "what changed" constantly.
- Biz: Temporal is a feature. Structural is a moat. Moat first.
- Sci: Structural research enables temporal features later (if you understand co-change patterns, you can predict future changes).

**Is 94K symbols enough for a paper, or do we need a second codebase?**
- Sci: For an industry paper, one production codebase is fine (it's real, not synthetic). For a top venue (ICSE, FSE), we'd want a second open-source codebase to show generalization.
- Biz: We could index a large open-source project (Kubernetes, Linux kernel) as the second dataset. Build pipeline already supports multiple languages.

---

## Next Actions

1. **Scientist**: Run the three Week 1 analyses. Write results to `research/data/`. No code changes.
2. **Product**: Curate the 50-query evaluation set. Write to `research/data/eval_queries.jsonl`.
3. **Business**: Draft the PR Blast Radius Bot spec. Write to `research/reports/blast_radius_bot_spec.md`.
4. **All**: Reconvene after Week 1 data analysis to decide Path A vs Path B.
