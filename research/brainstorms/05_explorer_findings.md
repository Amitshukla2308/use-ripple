# Explorer Findings: R&D Landscape for HyperRetrieval

**Date**: 2026-03-31
**Scope**: arxiv papers (2024-2026), GitHub repos, agent frameworks
**Goal**: Identify breakthroughs, competitors, and opportunities for HyperRetrieval's plug-and-play code intelligence platform

---

## Breakthrough Papers

### 1. Retrieval-Augmented Code Generation: A Survey with Focus on Repository-Level Approaches
- **Link**: https://arxiv.org/abs/2510.04905
- **Date**: October 2025
- **Summary**: Comprehensive survey covering RAG-based code generation from Jan 2023 to Aug 2025. Catalogs retrieval strategies, context construction, and generation approaches for repository-scale tasks.
- **Why it matters for HyperRetrieval**: This is THE definitive survey of our problem space. It maps the entire landscape of how retrieval signals (lexical, semantic, structural) feed into code generation. Validates our multi-signal approach.
- **Steal/Adopt**: Their taxonomy of retrieval strategies. They found lexical-matching retrievers often miss relevant code -- confirms our BM25+vectors hybrid is the right call. Study their "context construction" phase for how to assemble retrieved chunks into effective prompts.

### 2. RepoGraph: Enhancing AI Software Engineering with Repository-level Code Graph
- **Link**: https://arxiv.org/abs/2410.14684
- **Date**: October 2024
- **Summary**: A plug-in module that builds repository-level code graphs and serves as navigation for AI software engineers. Boosts SWE-bench performance across multiple agent architectures.
- **Why it matters for HyperRetrieval**: RepoGraph is architecturally closest to what we're building. It proves that a code graph layer, when plugged into existing agents, dramatically improves their performance. This validates our entire thesis.
- **Steal/Adopt**: Their graph schema design and how they make it pluggable into different agent scaffolds (SWE-Agent, etc.). Study their extensibility model -- they tested on CrossCodeEval too.

### 3. Code Graph Model (CGM): A Graph-Integrated LLM for Repository-Level SE Tasks
- **Link**: https://arxiv.org/abs/2505.16901
- **Date**: May 2025
- **Summary**: Integrates repository code graphs directly into LLM attention mechanisms via a specialized adapter. Uses 7 node types and 5 edge types. Achieved 43% on SWE-bench Lite with open-source Qwen2.5-72B.
- **Why it matters for HyperRetrieval**: Shows how to deeply integrate graph structure into LLM reasoning, not just as retrieved context but as architectural input. Their node/edge taxonomy for code graphs is well-thought-out.
- **Steal/Adopt**: Their 7-node-type, 5-edge-type graph schema. Consider whether our graph could be serialized into a format that feeds into LLM attention, not just prompt context. Their adapter architecture for graph-to-LLM integration.

### 4. GraphCoder: Repository-Level Code Completion via Code Context Graph
- **Link**: https://arxiv.org/abs/2406.07003
- **Date**: June 2024 (ASE 2024)
- **Summary**: Coarse-to-fine retrieval using Code Context Graphs (CCG) that capture control-flow, data-dependence, and control-dependence between statements. Two-stage: graph-based retrieval then LLM generation.
- **Why it matters for HyperRetrieval**: Their CCG concept maps closely to our call graph + import graph signals. The coarse-to-fine retrieval strategy (first find relevant files, then find relevant functions, then find relevant statements) is a pattern we should adopt.
- **Steal/Adopt**: The coarse-to-fine retrieval pipeline. Their representation of control-flow and data-dependence as graph edges alongside call/import edges.

### 5. cAST: Enhancing Code RAG with Structural Chunking via Abstract Syntax Tree
- **Link**: https://arxiv.org/abs/2506.15655
- **Date**: June 2025 (EMNLP 2025 Findings)
- **Summary**: Proposes AST-aware chunking that recursively breaks large AST nodes into smaller chunks while preserving semantic boundaries. Boosts Recall@5 by 4.3 points on RepoEval, Pass@1 by 2.67 on SWE-bench.
- **Why it matters for HyperRetrieval**: We already use tree-sitter for parsing. This paper shows that HOW you chunk code matters enormously for retrieval quality. Line-based chunking breaks semantic structures.
- **Steal/Adopt**: Their recursive AST chunking algorithm. The open-source implementation at https://github.com/yilinjz/astchunk uses tree-sitter, same as us. Direct integration opportunity.

### 6. Knowledge Graph Based Repository-Level Code Generation
- **Link**: https://arxiv.org/abs/2505.14394
- **Date**: May 2025
- **Summary**: Builds knowledge graphs from code repositories to improve code generation, evaluated on EvoCodeBench. Outperforms baseline approaches significantly.
- **Why it matters for HyperRetrieval**: Validates code knowledge graphs as a retrieval layer. Their evaluation on EvoCodeBench (evolutionary code benchmark) is relevant to our co-change signal.
- **Steal/Adopt**: Their knowledge graph construction pipeline and how they map code entities to KG triples.

### 7. GraphRAG: Retrieval-Augmented Generation with Graphs (Survey)
- **Link**: https://arxiv.org/abs/2501.00309
- **Date**: January 2025
- **Summary**: Comprehensive survey of graph-enhanced RAG. Covers graph-structured knowledge representation, graph-based retrieval, and structure-aware integration. Microsoft's GraphRAG showed 15% improvement over vanilla vector retrieval on legacy code migration tasks.
- **Why it matters for HyperRetrieval**: We already have graph signals. This survey maps the design space for how to combine them with vector retrieval. The "Practical GraphRAG" paper specifically tested on legacy code migration -- an enterprise use case we should target.
- **Steal/Adopt**: Their framework for combining graph traversal with vector similarity. The community detection approach for generating "community summaries" at different granularities (we already use Leiden -- this shows how to use those clusters for retrieval).

### 8. Codebase-Memory: Tree-Sitter-Based Knowledge Graphs for LLM Code Exploration via MCP
- **Link**: https://arxiv.org/html/2603.27277v1
- **Date**: March 2026
- **Summary**: Parses codebases using Tree-Sitter across 66 languages, stores graph in SQLite, exposes 14 structural query tools via MCP. Features multi-phase build pipeline, 6-strategy call resolution, and Louvain community detection.
- **Why it matters for HyperRetrieval**: THIS IS EXTREMELY CLOSE TO WHAT WE'RE BUILDING. Same tech stack (tree-sitter, SQLite, MCP), similar pipeline (multi-phase build), similar signals (call graph, community detection). We need to study this carefully.
- **Steal/Adopt**: Their 14 MCP tool definitions, their 6-strategy call resolution approach, their SQLite schema design. Compare their Louvain clustering with our Leiden clustering.

### 9. Enhancing Change Impact Prediction by Integrating Evolutionary Coupling with Software Change Relationships
- **Link**: https://dl.acm.org/doi/10.1145/3674805.3686668
- **Date**: 2024 (ESEM 2024)
- **Summary**: Integrates evolutionary coupling (co-change patterns) with software change relationships for change impact prediction. Fine-grained co-change relationship analysis from evolution history mining.
- **Why it matters for HyperRetrieval**: Directly validates our co-change signal. Shows how evolutionary coupling can predict blast radius -- exactly what our blast radius agent needs.
- **Steal/Adopt**: Their method for combining structural relationships (call graph) with evolutionary coupling (co-change) for impact prediction. This is the theoretical foundation for our blast radius agent.

### 10. Comprehensive Empirical Evaluation of Agent Frameworks on Code-centric SE Tasks
- **Link**: https://arxiv.org/html/2511.00872v1
- **Date**: November 2025
- **Summary**: Systematic evaluation of 7 agent frameworks across software development, vulnerability detection, and program repair tasks.
- **Why it matters for HyperRetrieval**: Provides empirical data on which agent patterns work best for different code tasks. Critical for designing our agent framework.
- **Steal/Adopt**: Their evaluation methodology and the framework characteristics that correlated with success on different task types.

### 11. Agentic AI Frameworks: Architectures, Protocols, and Design Challenges
- **Link**: https://arxiv.org/html/2508.10146v1
- **Date**: August 2025
- **Summary**: Surveys agentic AI frameworks, identifies limitations in generalizability and composability, recommends standardized benchmarks and universal agent communication protocols.
- **Why it matters for HyperRetrieval**: Frames the design space for our agent framework. MCP is called out as the key interoperability protocol.
- **Steal/Adopt**: Their taxonomy of agent communication patterns and composability strategies.

### 12. LocAgent: Graph-guided Agentic Framework for Code Localization
- **Link**: https://arxiv.org/abs/2503.09089 | GitHub: https://github.com/gersteinlab/LocAgent
- **Date**: March 2025 (ACL 2025)
- **Summary**: Graph-guided LLM agent that precisely localizes where in a codebase changes need to be made, using code graph structure to navigate.
- **Why it matters for HyperRetrieval**: Code localization is a core retrieval problem. Their graph-guided navigation approach could improve our code search agent.
- **Steal/Adopt**: Their graph traversal strategy for narrowing down from repo-level to exact location.

---

## Repos Worth Studying

### 1. Sourcegraph Cody
- **URL**: https://github.com/sourcegraph/cody-vs (VS extension) / https://sourcegraph.com
- **Stars**: Open core, enterprise product
- **Summary**: Multi-layered RAG architecture combining search API, code graph (SCIP), embeddings, and MCP. Three context layers: local file, local repo, remote repo. Recently unified search + chat + agents.
- **Architectural insight**: Their SCIP-based code graph reduces hallucinations (type errors, imaginary functions). The multi-layered context system (local file -> local repo -> remote repo) is a pattern we should adopt.
- **What they do better**: Production-grade code graph (SCIP), enterprise-scale indexing, and their OpenCtx protocol for pulling context from external tools (Jira, Linear, Notion).

### 2. OpenHands (formerly OpenDevin)
- **URL**: https://github.com/All-Hands-AI/OpenHands
- **Stars**: ~45k+
- **Summary**: Open platform for AI software developers. Sandboxed execution, multi-agent coordination, evaluation benchmarks. Supports custom agent implementations.
- **Architectural insight**: Their sandboxed execution model is critical for safety. AgentSkills library provides file editing utilities. The platform approach (implement any agent on top) is similar to our vision.
- **What they do better**: Sandboxed execution environment, established benchmark performance (SWE-bench), and the agent abstraction layer.

### 3. SWE-agent
- **URL**: https://github.com/SWE-agent/SWE-agent
- **Stars**: ~15k+
- **Summary**: Princeton NLP's agent for automatically fixing GitHub issues. NeurIPS 2024 paper. Also has mini-swe-agent (100-line version scoring >74% on SWE-bench verified).
- **Architectural insight**: The Agent-Computer Interface (ACI) design -- custom tools for the agent to interact with code. Their mini-agent proves that a small, well-designed tool set can outperform complex systems.
- **What they do better**: Purpose-built code editing tools (search, edit, navigation) that form a clean ACI. The 100-line mini-agent is a masterclass in minimal viable agent design.

### 4. Moatless Tools
- **URL**: https://github.com/aorwall/moatless-tools
- **Stars**: ~2k+
- **Summary**: LLM-based code editing in large codebases. Includes CodeIndex, SearchTree, and actions like FindClass, FindFunction, SemanticSearch. Claude 4 Sonnet achieves 70.8% on SWE-bench.
- **Architectural insight**: Their CodeIndex and action-based architecture (FindClass, FindFunction, FindCodeSnippet, SemanticSearch, ViewCode) is a clean decomposition of code intelligence operations.
- **What they do better**: The action/tool decomposition is very clean. Their tree search approach (moatless-tree-search) for exploring solution spaces is novel.

### 5. Aider
- **URL**: https://github.com/paul-gauthier/aider
- **Stars**: ~30k+
- **Summary**: Terminal-based AI coding assistant. Works with any LLM. pip install and go. Direct file editing on local machine.
- **Architectural insight**: Extreme simplicity -- no frontend, no sandbox, just terminal + LLM + file system. The "repo map" feature automatically identifies relevant files using tree-sitter and ctags.
- **What they do better**: Zero-friction setup (pip install, add API key, start coding). Their repo map is a lightweight code intelligence layer we should study.

### 6. Continue.dev
- **URL**: https://github.com/continuedev/continue
- **Stars**: ~25k+
- **Summary**: Open-source AI coding assistant for VS Code/JetBrains. Three modes: Chat, Plan, Agent. Self-hosted capable. Model-agnostic. CI/CD integration with AI code review checks.
- **Architectural insight**: The .continue/rules/ directory for team standards is a great pattern. Their embedding + reranking model pipeline for context. The CI/CD integration (AI checks on every PR) is what our PR review agent should target.
- **What they do better**: IDE integration, model flexibility (any provider), the rules system for team conventions, and the CI/CD pipeline for automated code review.

### 7. RAGFlow
- **URL**: https://github.com/infiniflow/ragflow
- **Stars**: ~70k
- **Summary**: Leading open-source RAG engine with Agent capabilities. Production-ready for enterprise chatbots, assistants, and data analysis.
- **Architectural insight**: Their "deep document understanding" approach -- not just chunking text but understanding document structure. The workflow builder for defining RAG pipelines.
- **What they do better**: Production hardening, enterprise features, and the visual workflow builder for RAG pipeline design.

### 8. Dify
- **URL**: https://github.com/langgenius/dify
- **Stars**: ~114k
- **Summary**: Open-source LLM app development platform with workflow builder, RAG pipelines, and agent capabilities. Visual tool for building AI applications.
- **Architectural insight**: Their workflow builder abstraction -- define tool-using agents and RAG pipelines with minimal code. The monitoring/usage tracking is enterprise-grade.
- **What they do better**: Visual workflow builder, production monitoring, and the sheer breadth of integrations.

### 9. Agentic Code Indexer
- **URL**: https://github.com/teabranch/agentic-code-indexer
- **Stars**: Small/new
- **Summary**: Code analysis and graph-based indexing using Neo4j, LLMs, and semantic embeddings. Multi-language support (Python, C#, JS/TS). Hybrid search combining vector similarity, entity lookup, and graph context expansion.
- **Architectural insight**: Their hybrid search system (vector + entity + graph expansion) is exactly our multi-signal approach. Neo4j for graph storage is heavier than our SQLite approach but more queryable.
- **What they do better**: Neo4j gives richer graph queries. Their graph context expansion (start from a node, expand outward) is a retrieval strategy we should adopt.

### 10. Code-Index-MCP
- **URL**: https://github.com/johnhuang316/code-index-mcp
- **Stars**: Small/new
- **Summary**: MCP server for code indexing and search. Uses tree-sitter for 7 core languages with fallback for 50+ file types. Designed for LLM integration.
- **Architectural insight**: Clean MCP-first design. The fallback strategy (specialized tree-sitter -> generic parsing) is pragmatic.
- **What they do better**: MCP-native design from day one. Simple, focused scope.

### 11. CodeRLM
- **URL**: https://github.com/JaredStewart/coderlm
- **Stars**: Small/new
- **Summary**: Tree-sitter-powered code indexing server. Builds symbol table with cross-references. Agents can search symbols, list functions, find callers, grep patterns.
- **Architectural insight**: The "targeted queries instead of loading everything into context" philosophy. Agents explore codebases through specific structural queries rather than bulk retrieval.
- **What they do better**: The query-driven exploration model -- agents ask specific structural questions rather than getting a dump of context.

### 12. Open Aware (by Qodo)
- **URL**: https://github.com/qodo-ai/open-aware
- **Stars**: New
- **Summary**: Code intelligence via MCP. Semantic understanding across multiple repositories with daily updated indexes. Goes beyond keyword search.
- **Architectural insight**: Multi-repo support with daily index updates. The MCP-first approach for serving code intelligence to any AI assistant.
- **What they do better**: Multi-repo support and the daily index refresh pipeline.

---

## Agent Frameworks Comparison

| Feature | **LangGraph** | **CrewAI** | **AutoGen (AG2)** | **DSPy** | **OpenHands** | **Claude Agent SDK** | **mcp-agent** |
|---|---|---|---|---|---|---|---|
| **Core paradigm** | Graph-based stateful workflows | Role-based agent teams | Conversational multi-agent | Programmatic prompt optimization | Platform for AI developers | Anthropic-native agents | MCP-native workflows |
| **MCP support** | Yes (via langchain-mcp-adapters) | Limited | Via Microsoft Agent Framework | No native | No native | First-class | First-class |
| **State management** | Excellent (graph state) | Basic | Conversation-based | Declarative | Sandboxed environment | Session-based | Temporal-backed |
| **Multi-agent** | Yes (supervisor, swarm patterns) | Yes (crew with roles) | Yes (group chat, debate) | No (single pipeline) | Yes (agent coordination) | Yes | Yes (composable) |
| **Code-specific** | No (general purpose) | No (general purpose) | No (general purpose) | No (general purpose) | Yes (code-focused) | No (general purpose) | No (general purpose) |
| **Production readiness** | High | Medium | Medium-High | Medium | High | High | Medium |
| **Community size** | Very large (LangChain ecosystem) | Large | Large (Microsoft-backed) | Medium (Stanford) | Large | Growing | Small |
| **Self-hosted** | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| **Best for HyperRetrieval** | Agent orchestration layer | Quick prototyping | Conversational agents | Prompt optimization | Agent execution model | MCP integration | MCP workflow patterns |

### Recommendation for HyperRetrieval

**Primary choice: LangGraph** for agent orchestration, because:
1. Graph-based workflows match our graph-centric architecture
2. Strong MCP support via langchain-mcp-adapters
3. Stateful workflows are critical for multi-step code analysis
4. Largest ecosystem and community
5. Production-grade with persistence and resumability

**Secondary: Claude Agent SDK** for MCP-native agents, because:
1. First-class MCP support (Anthropic created MCP)
2. Zero-trust security model fits enterprise requirements
3. Best integration with Claude models

**For prompt optimization: DSPy**, because:
1. Can automatically optimize our retrieval-to-generation prompts
2. Replaces manual prompt engineering with learned optimization
3. Could improve our ranking/reranking pipeline

**NOT recommended**: CrewAI (too high-level for our needs), AutoGen (conversational paradigm doesn't fit code analysis well).

---

## Competitive Landscape Summary

### Direct Competitors (doing similar things)
| Product | Approach | Our Advantage |
|---|---|---|
| **Sourcegraph Cody** | SCIP code graph + embeddings + MCP | We're open-source, self-hosted first. They're enterprise SaaS. We have co-change signal they don't. |
| **Codebase-Memory** | Tree-sitter + SQLite + MCP + Louvain | Very similar stack. We have more signals (6 vs their ~4). We have Leiden (better than Louvain). |
| **Agentic Code Indexer** | Neo4j + embeddings + LLM summaries | We're lighter (SQLite vs Neo4j). They have richer graph queries. |
| **GitHub Copilot** | Proprietary indexing + semantic search | We're open-source, self-hosted, air-gapped capable. They're cloud-only. |

### Indirect Competitors (adjacent space)
| Product | Approach | Relationship |
|---|---|---|
| **OpenHands** | Agent platform for code | Potential integration target -- our retrieval feeds their agents |
| **SWE-agent** | Agent for issue fixing | Potential integration target -- RepoGraph proved code graphs boost SWE-agent |
| **Moatless Tools** | Code editing with search | Their CodeIndex is simpler than ours; we could be their retrieval backend |
| **Continue.dev** | IDE AI assistant | Potential integration -- we provide the code intelligence, they provide the IDE UX |

---

## The Big Opportunities

Based on comprehensive analysis of 20+ papers, 15+ repos, and 7+ frameworks, here are the three things HyperRetrieval should build next:

### 1. GraphRAG-Enhanced Retrieval Pipeline (Highest Impact)

**What**: Upgrade our 6-signal retrieval to use GraphRAG patterns -- specifically, use Leiden clusters to generate hierarchical community summaries, then use these summaries as an additional retrieval layer.

**Why**: Microsoft's GraphRAG showed 15% improvement over vanilla vector retrieval. We ALREADY have the Leiden clusters. We just need to:
- Generate natural language summaries for each cluster ("This module handles authentication and session management")
- Create a hierarchical index: cluster summaries -> file summaries -> function summaries
- Use this hierarchy for coarse-to-fine retrieval (like GraphCoder's approach)

**Evidence**: Papers #7 (GraphRAG survey), #4 (GraphCoder coarse-to-fine), #6 (KG-based code gen), and the Codebase-Memory system all converge on this pattern.

**Effort**: Medium. We have the clusters. We need summary generation + hierarchical retrieval logic.

### 2. Plug-and-Play Agent Framework with MCP Tool Registry (Biggest Moat)

**What**: Build a composable agent framework where:
- Each agent is defined as a configuration (role, tools, retrieval signals, output format)
- All agents access code intelligence through our MCP tools
- Users can create custom agents by composing existing tools
- Ship 4 default agents: Code Search, Blast Radius, PR Review, Onboarding Guide

**Why**: No one has a plug-and-play agent framework specifically for code intelligence. OpenHands is general-purpose. SWE-agent is single-purpose. We can be the "agent framework for code understanding" where the retrieval layer is already solved.

**Architecture**: Use LangGraph for orchestration + our MCP server for tools. Each agent is a LangGraph workflow that uses MCP tools. The framework handles:
- Agent definition (YAML/JSON config)
- Tool composition (which MCP tools each agent can use)
- Signal selection (which of our 6 signals to activate per query)
- Output formatting (structured results for different consumers)

**Evidence**: Papers #10 (agent framework evaluation), #11 (agent architecture survey), the mcp-agent pattern, and the gap analysis showing no code-specific composable agent framework exists.

**Effort**: High. But this is our core differentiator.

### 3. AST-Aware Chunking + Adaptive Signal Weighting (Retrieval Quality)

**What**: Two improvements to retrieval quality:
1. Replace line-based chunking with cAST-style AST-aware chunking (paper #5). Use tree-sitter to create semantically coherent chunks.
2. Implement adaptive signal weighting -- learn which of our 6 signals matter most for different query types (semantic search queries weight vectors higher, "what breaks if I change X" queries weight co-change + call graph higher).

**Why**: cAST showed +4.3 Recall@5 improvement just from better chunking. And right now our signal fusion is likely static/equal-weighted. Different queries need different signal mixes.

**How**:
- Chunking: Integrate https://github.com/yilinjz/astchunk or implement the recursive AST chunking algorithm. We already use tree-sitter.
- Signal weighting: Start with heuristic rules (query classification -> signal weights), evolve to learned weights using DSPy-style optimization.

**Evidence**: Paper #5 (cAST), paper #1 (survey noting lexical retrievers miss code), DSPy framework for prompt/pipeline optimization.

**Effort**: Medium. AST chunking is a focused change. Signal weighting is an ongoing optimization.

---

## Bonus: Quick Wins We Can Implement This Week

1. **Study Codebase-Memory's 14 MCP tools** (https://arxiv.org/html/2603.27277v1) -- compare with our MCP tool set, identify gaps
2. **Add coarse-to-fine retrieval** -- first retrieve relevant clusters, then files within those clusters, then functions
3. **Benchmark against RepoGraph** -- plug our retrieval into SWE-agent and measure SWE-bench performance
4. **Add the cAST chunking library** as an optional chunking strategy alongside our current approach

---

## Key Sources and References

### Papers
- [RACG Survey](https://arxiv.org/abs/2510.04905) - Comprehensive RAG for code survey
- [RepoGraph](https://arxiv.org/abs/2410.14684) - Repository-level code graph
- [Code Graph Model](https://arxiv.org/abs/2505.16901) - Graph-integrated LLM
- [GraphCoder](https://arxiv.org/abs/2406.07003) - Code context graph retrieval
- [cAST](https://arxiv.org/abs/2506.15655) - AST-aware chunking
- [KG Code Gen](https://arxiv.org/abs/2505.14394) - Knowledge graph for code
- [GraphRAG Survey](https://arxiv.org/abs/2501.00309) - Graph-enhanced RAG
- [Codebase-Memory](https://arxiv.org/html/2603.27277v1) - Tree-sitter + MCP knowledge graph
- [Change Impact Prediction](https://dl.acm.org/doi/10.1145/3674805.3686668) - Evolutionary coupling
- [Agent Framework Evaluation](https://arxiv.org/html/2511.00872v1) - Code-centric agent comparison
- [Agentic AI Frameworks](https://arxiv.org/html/2508.10146v1) - Architecture survey
- [LocAgent](https://arxiv.org/abs/2503.09089) - Graph-guided code localization
- [DeepCode](https://arxiv.org/abs/2512.07921) - Open agentic coding
- [AgentCoder](https://arxiv.org/abs/2312.13010) - Multi-agent code generation
- [Practical GraphRAG](https://arxiv.org/abs/2507.03226) - Enterprise GraphRAG at scale
- [CodeRAG on Bigraph](https://arxiv.org/html/2504.10046v1) - Bigraph-based code retrieval
- [GVE-Leiden](https://arxiv.org/abs/2312.13936) - Fast parallel Leiden algorithm
- [Dynamic Leiden](https://arxiv.org/abs/2405.11658) - Dynamic community detection

### Repos
- [Sourcegraph Cody](https://sourcegraph.com) - Enterprise code intelligence
- [OpenHands](https://github.com/All-Hands-AI/OpenHands) - AI developer platform
- [SWE-agent](https://github.com/SWE-agent/SWE-agent) - GitHub issue solver
- [Moatless Tools](https://github.com/aorwall/moatless-tools) - Code editing agent
- [Aider](https://github.com/paul-gauthier/aider) - Terminal AI coding
- [Continue.dev](https://github.com/continuedev/continue) - Open-source IDE assistant
- [RAGFlow](https://github.com/infiniflow/ragflow) - RAG engine
- [Dify](https://github.com/langgenius/dify) - LLM app platform
- [Agentic Code Indexer](https://github.com/teabranch/agentic-code-indexer) - Neo4j code graphs
- [Code-Index-MCP](https://github.com/johnhuang316/code-index-mcp) - MCP code indexer
- [CodeRLM](https://github.com/JaredStewart/coderlm) - Tree-sitter symbol server
- [Open Aware](https://github.com/qodo-ai/open-aware) - MCP code intelligence
- [LocAgent](https://github.com/gersteinlab/LocAgent) - Graph-guided localization
- [ASTChunk](https://github.com/yilinjz/astchunk) - AST-aware code chunking
- [LangGraph MCP Adapters](https://github.com/langchain-ai/langchain-mcp-adapters) - LangGraph + MCP
- [mcp-agent](https://github.com/lastmile-ai/mcp-agent) - MCP-native agent framework
- [MCP Servers](https://github.com/modelcontextprotocol/servers) - Official MCP servers
- [Awesome-GraphRAG](https://github.com/DEEP-PolyU/Awesome-GraphRAG) - GraphRAG resource list
- [Awesome Repo-Level Code Gen](https://github.com/YerbaPage/Awesome-Repo-Level-Code-Generation) - Paper list

### Framework Comparisons
- [12 MCP Agent Frameworks Compared](https://clickhouse.com/blog/how-to-build-ai-agents-mcp-12-frameworks)
- [CrewAI vs LangGraph vs AutoGen vs OpenAgents](https://openagents.org/blog/posts/2026-02-23-open-source-ai-agent-frameworks-compared)
- [LangGraph vs AutoGen vs CrewAI Architecture Analysis](https://latenode.com/blog/platform-comparisons-alternatives/automation-platform-comparisons/langgraph-vs-autogen-vs-crewai-complete-ai-agent-framework-comparison-architecture-analysis-2025)
- [Best AI Agent Frameworks 2025](https://langwatch.ai/blog/best-ai-agent-frameworks-in-2025-comparing-langgraph-dspy-crewai-agno-and-more)
- [Air-Gapped AI Code Assistants](https://intuitionlabs.ai/articles/enterprise-ai-code-assistants-air-gapped-environments)

---

## Update: 2026-04-01 01:17

### New Papers

#### 13. InlineCoder: Repository-Level Code Generation via Context Inlining
- **Link**: https://arxiv.org/abs/2601.00376
- **Date**: January 2026
- **Summary**: Reframes repo-level code generation by inlining the target function into its call graph. Bidirectional inlining: upstream (inline into callers for usage context) and downstream (inline callees for dependency context). Outperforms RAG-based approaches on repo-level benchmarks.
- **Why it matters for HyperRetrieval**: Their call-graph-driven context assembly is directly applicable to our retrieval pipeline. Instead of returning flat search results, we could inline the target symbol into its call graph context -- exactly what our trace_callers/trace_callees tools provide.
- **Steal/Adopt**: The bidirectional inlining strategy. We already have call graph data; we should experiment with assembling retrieval context by inlining rather than concatenating.

#### 14. FeatureBench: Benchmarking Agentic Coding for Complex Feature Development
- **Link**: https://arxiv.org/abs/2602.10975
- **Date**: February 2026
- **Summary**: Benchmark with 200 tasks from 24 repos for evaluating end-to-end feature development. Claude 4.5 Opus (74.4% on SWE-bench) solves only 11.0% of FeatureBench tasks, exposing a massive gap between bug-fix and feature-development capabilities.
- **Why it matters for HyperRetrieval**: Feature development is a harder problem than bug fixing -- it requires understanding architectural patterns, not just locating bugs. Our multi-signal retrieval (especially cluster summaries + co-change) could help agents understand where new features should be placed.
- **Steal/Adopt**: Use FeatureBench as an evaluation target. If our retrieval layer helps agents score higher on FeatureBench, that's a compelling demo.

#### 15. Bridging Protocol and Production: MCP Design Patterns
- **Link**: https://arxiv.org/abs/2603.13417
- **Date**: March 2026
- **Summary**: Identifies three missing MCP primitives for production: identity propagation (CABP), adaptive tool budgeting (ATBA), and structured error recovery (SERF). Based on enterprise deployment lessons. Documents failure modes across 5 dimensions.
- **Why it matters for HyperRetrieval**: We expose 8 MCP tools. This paper tells us exactly what breaks when those tools go to production -- timeout cascades, identity context loss, and unstructured errors that confuse agents. Their production readiness checklist is directly actionable.
- **Steal/Adopt**: Implement ATBA (adaptive timeout budgets) for our MCP server. Add structured error semantics (SERF) to our tool responses so agents can self-correct. Review their 5-dimension failure taxonomy against our deployment.

#### 16. RepoRepair: Hierarchical Code Documentation for Repository-Level Program Repair
- **Link**: https://arxiv.org/abs/2603.01048
- **Date**: March 2026
- **Summary**: Generates hierarchical documentation (function -> file level) to help LLMs understand repo context for fault localization and repair. Achieves 45.7% on SWE-bench Lite. Key insight: LLM-generated summaries as semantic abstractions enable cross-file reasoning.
- **Why it matters for HyperRetrieval**: Validates our cluster summary approach (build/04_summarize.py). They generate file/function summaries to guide fault localization -- we already generate cluster summaries. We should extend to file-level and function-level summaries too.
- **Steal/Adopt**: Their hierarchical documentation generation pipeline. Compare their summarization approach with our 04_summarize.py output.

#### 17. MCP Tool Descriptions Are Smelly!
- **Link**: https://arxiv.org/abs/2602.14878
- **Date**: February 2026
- **Summary**: Empirical study of 856 tools across 103 MCP servers. Finds that poor tool descriptions significantly degrade agent performance. Proposes augmented descriptions that improve tool selection accuracy.
- **Why it matters for HyperRetrieval**: Our 8 MCP tools' descriptions directly affect how well LLMs use them. If our tool descriptions are "smelly" (vague, missing constraints, wrong granularity), agents will misuse our tools and waste tokens.
- **Steal/Adopt**: Audit our 8 MCP tool descriptions against their smell taxonomy. Apply their augmentation recommendations to improve tool selection by Claude/GPT.

#### 18. Self-Organizing Multi-Agent Systems for Continuous Software Development
- **Link**: https://arxiv.org/abs/2603.25928
- **Date**: March 2026
- **Summary**: Proposes an orchestrator-driven multi-agent system where agents operate autonomously through development phases. The orchestrator provides scheduling infrastructure without making SE decisions itself.
- **Why it matters for HyperRetrieval**: Validates our planned agent framework architecture. The orchestrator pattern (scheduling + tool access, not decision-making) aligns with our vision of composable agents that use MCP tools.
- **Steal/Adopt**: Their phase-based agent coordination pattern. Study how the orchestrator delegates to specialized agents without micromanaging.

#### 19. From Laboratory to Real-World: Benchmarking Agentic Code Reasoning at the Repository Level
- **Link**: https://arxiv.org/abs/2601.03731
- **Date**: January 2026
- **Summary**: Evaluates LLM agents on maintaining logical consistency across massive, real-world interdependent file systems. Focuses on the gap between lab benchmarks and production codebases.
- **Why it matters for HyperRetrieval**: Directly addresses the problem our platform solves -- agents struggle with real-world repo complexity. Better retrieval (our value proposition) should close this lab-to-production gap.
- **Steal/Adopt**: Their evaluation methodology for testing retrieval quality on real-world (not synthetic) repositories.

### New Repos

#### 13. Understand-Anything
- **URL**: https://github.com/Lum1104/Understand-Anything
- **Summary**: Claude Code plugin with multi-agent pipeline (5 agents: project scanner, file analyzer, architecture analyzer, tour builder, graph reviewer). Builds knowledge graph of every file, function, class, and dependency. Interactive web dashboard with graph visualization.
- **Why it matters**: Direct competitor as a Claude Code plugin. Their multi-agent pipeline for KG construction and the interactive visualization are features we should consider. Works across Claude Code, Cursor, Gemini CLI.
- **Steal/Adopt**: Their plugin architecture for Claude Code integration. The 5-agent analysis pipeline design.

#### 14. GitNexus
- **URL**: https://github.com/abhigyanpatwari/GitNexus
- **Summary**: Client-side knowledge graph creator that runs entirely in browser. Drop in a GitHub repo or ZIP file, get interactive knowledge graph with built-in Graph RAG agent. Zero-server architecture.
- **Why it matters**: Shows demand for code knowledge graphs with zero infrastructure. Their browser-only approach is the opposite of our server-side approach, but the Graph RAG agent integration is relevant.
- **Steal/Adopt**: Their Graph RAG agent implementation for querying code knowledge graphs.

#### 15. code-review-graph
- **URL**: https://github.com/tirth8205/code-review-graph
- **Summary**: Local knowledge graph for Claude Code. Claims 6.8x fewer tokens on code reviews, 49x fewer on daily coding. Builds persistent codebase map so Claude reads only relevant context.
- **Why it matters**: Validates token efficiency as a key selling point for code knowledge graphs. Their 6.8x/49x claims are the kind of metrics we should benchmark and publicize.
- **Steal/Adopt**: Their token efficiency measurement methodology. Use similar metrics for our MCP tools.

#### 16. ReSharper MCP Server
- **URL**: https://github.com/joshua-light/resharper-mcp
- **Summary**: MCP server embedded in Rider IDE exposing ReSharper's semantic code intelligence (definitions, references, type hierarchy) to AI agents. Works with actual codebase semantics instead of grep approximations.
- **Why it matters**: Shows IDE-embedded code intelligence exposed via MCP. Their approach (leverage existing IDE analysis) is complementary to ours (standalone indexer). For .NET codebases, this would outperform our tree-sitter parsing.
- **Steal/Adopt**: Their approach of wrapping existing language analysis tools (LSP, ReSharper) as MCP tools. Consider LSP integration as an alternative to tree-sitter for supported languages.

### Industry News

#### Sourcegraph Spins Out Amp as Independent Company
- **Date**: Late 2025 / Early 2026
- **URL**: https://sourcegraph.com/blog/why-sourcegraph-and-amp-are-becoming-independent-companies
- **Summary**: Sourcegraph split into two companies: Sourcegraph (code search) and Amp Inc. (coding agent). Amp has 3 modes: smart, rush, deep. Now uses GPT-5.4 in deep mode. Available as CLI and VS Code extension.
- **Why it matters**: Our closest enterprise competitor is now TWO companies. Sourcegraph keeps code search/intelligence, Amp focuses on agentic coding. This validates that code intelligence and agent execution are distinct products. We serve the code intelligence layer that agents like Amp consume.

#### Cursor Composer 2 + Automations + Cloud Agents
- **Date**: March 2026
- **URL**: https://cursor.com/blog/composer-2
- **Summary**: Cursor launched Composer 2 (their own coding model, $0.50/$2.50 per M tokens), automations (trigger agents from GitHub/Slack/Linear), self-hosted cloud agents, and JetBrains integration via Agent Client Protocol (ACP). Cursor hit $2B ARR with half of Fortune 500 using it.
- **Why it matters**: Cursor is building the full stack: model + agent + triggers + cloud execution. Their automations feature (agents triggered by events) is the CI/CD integration we planned. ACP (Agent Client Protocol) is a new protocol to watch alongside MCP. $2B ARR proves the market is massive.
- **What to learn**: Study ACP for potential support. Their event-triggered agent pattern should inform our PR review agent design. The self-hosted cloud agent model is what enterprises want.

#### GitHub Copilot Agentic Code Review (GA)
- **Date**: March 5, 2026
- **URL**: https://github.blog/changelog/2026-03-05-copilot-code-review-now-runs-on-an-agentic-architecture/
- **Summary**: Copilot code review now uses agentic tool-calling to gather full repository context before reviewing. Can pass suggestions directly to coding agent to auto-generate fix PRs. Runs on GitHub Actions. 60M+ code reviews completed.
- **Why it matters**: GitHub's agentic code review gathers repo context before commenting -- this is exactly what our PR review agent does with blast radius analysis. The "review -> auto-fix PR" loop is the workflow we should target. Running on GitHub Actions is the deployment model.
- **What to learn**: Their agentic review -> coding agent handoff pattern. Our blast radius signal could make this review smarter by showing co-change impact.

#### Claude Code: MCP Tool Search + Elicitation
- **Date**: January-March 2026
- **URL**: https://code.claude.com/docs/en/changelog
- **Summary**: Claude Code added MCP Tool Search (lazy loading, 85% token reduction) and MCP Elicitation (servers can request structured input mid-task). Tool search solves the "66k tokens consumed before typing anything" problem. Plugin deduplication prevents duplicate MCP connections.
- **Why it matters**: MCP Tool Search means our 8 tools won't bloat Claude Code's context window. Elicitation means our MCP server could ask clarifying questions mid-retrieval (e.g., "which service do you mean?"). Both features improve how our tools integrate with Claude Code.
- **What to learn**: Ensure our tool descriptions are optimized for Tool Search discovery. Implement elicitation in our MCP server for ambiguous queries.

#### OpenHands CLI + OpenHands Index
- **Date**: January-March 2026
- **URL**: https://openhands.dev/blog/openhands-index
- **Summary**: OpenHands released a pip-installable CLI (no Docker required) with accuracy similar to Claude Code. MIT licensed, model-agnostic. OpenHands Index benchmarks 9 models across providers. 65k+ GitHub stars.
- **Why it matters**: OpenHands going CLI-first and Docker-free lowers the barrier for integration with our MCP tools. Their model-agnostic approach means our retrieval layer could serve any model through OpenHands.
- **What to learn**: Test our MCP server integration with OpenHands CLI. Their benchmark methodology (OpenHands Index) could validate our retrieval improvements.

#### mini-swe-agent Supersedes SWE-agent
- **Date**: March 2026
- **URL**: https://github.com/SWE-agent/mini-swe-agent
- **Summary**: SWE-agent team officially recommends mini-swe-agent over the original. Simpler, more flexible, scores >74% on SWE-bench verified. v2 switched to tool calls by default (vs manual action parsing).
- **Why it matters**: The shift from complex agents to minimal agents continues. mini-swe-agent's 100-line design proves that good tools matter more than complex orchestration -- which is our thesis (provide great retrieval tools, let simple agents use them).
- **What to learn**: Test our MCP tools with mini-swe-agent. If our retrieval improves its SWE-bench score, that's a powerful integration story.

### Implications for HyperRetrieval Roadmap

1. **MCP Tool Quality is Critical**: Papers #15 and #17 show that MCP tool descriptions and production patterns directly impact agent performance. Audit and improve our 8 tool descriptions immediately.
2. **Call-Graph Context Assembly**: InlineCoder (#13) shows that inlining into call graphs beats flat RAG. We have the call graph -- we should experiment with inlining-based context assembly.
3. **FeatureBench as Eval Target**: Paper #14 exposes a massive gap in feature development. If our retrieval helps agents on FeatureBench, we have a compelling differentiator.
4. **Event-Triggered Agents**: Cursor's automations and Copilot's agentic review both show the market wants CI/CD-integrated agents. Our PR review agent should ship with GitHub Actions integration.
5. **Token Efficiency Metrics**: code-review-graph claims 6.8x-49x token savings. We should measure and publicize similar metrics for our MCP tools.
