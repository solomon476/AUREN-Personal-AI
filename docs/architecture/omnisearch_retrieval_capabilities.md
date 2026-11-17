# Omnisearch Retrieval Capabilities & Scope

**Phase:** Phase 3C.5.2 Corrective Specification (ARCH-01)  
**Status:** Accepted Architecture Documentation  
**Date:** 2026-11-17  

---

## 1. Overview & Architectural Boundaries

AUREN provides two distinct retrieval subsystems, intentionally decoupled according to use case and computational requirements:

1. **Memory Context Injection (`MemoryRetriever` — Phase 3C.3):**
   - **Mode:** Hybrid semantic vector similarity ($S_{\text{sem}}$) + lexical match ($S_{\text{lex}}$).
   - **Backing Store:** PostgreSQL `search_memories_hybrid_rpc` with pgvector or SQLite in-memory cosine fallback.
   - **Scope:** Active memories only. Used during chat session assembly to supply personal memory context.

2. **Omnisearch (`OmnisearchService` — Phase 3C.5 / 3C.5.2):**
   - **Mode:** Strictly lexical token matching and query coverage ($S_{\text{lex}}$).
   - **Backing Store:** Direct indexed queries across 6 personal data entities (`conversations`, `messages`, `memories`, `tasks`, `projects`, `goals`).
   - **Scope:** Broad multi-source discovery. Used in the frontend Omnisearch bar and conversational context injection for historical search triggers.

---

## 2. Source Coverage Matrix

| Source Entity | Search Strategy | Matching Details | Semantic Vector Support |
| :--- | :--- | :--- | :--- |
| **Conversations** | Lexical Substring & Tokens | Title substring, token matching | No |
| **Messages** | Lexical Substring & Tokens | Content search, token coverage | No |
| **Memories** | Lexical Filtering & Tokens | `list_memories(query=...)` + snippet extraction | Lexical in Omnisearch; Semantic in `MemoryRetriever` |
| **Tasks** | SQL LIKE / Lexical Scoring | `list_tasks(query=...)` over title, description, tags | No |
| **Projects** | SQL LIKE / Lexical Scoring | `list_projects(query=...)` over name, description | No |
| **Goals** | SQL LIKE / Lexical Scoring | `list_goals(query=...)` over title, description | No |
| **Journal Entries** | **Excluded** | Journal entries are strictly excluded by privacy policy | No |

---

## 3. Scoring & Relevance Metric

The score returned by Omnisearch is calculated by `_lexical_score()`:

$$S_{\text{score}} = \text{round}\left(\text{clamp}\left(\frac{|T_{\text{query}} \cap T_{\text{target}}|}{|T_{\text{query}}|} + R_{\text{recency}} + B_{\text{exact}}, 0.0, 1.0\right), 4\right)$$

Where:
- $\frac{|T_{\text{query}} \cap T_{\text{target}}|}{|T_{\text{query}}|}$ is the token coverage ratio (fraction of search terms present in the document).
- $B_{\text{exact}}$ is an exact phrase match bonus ($+0.3$).
- $R_{\text{recency}}$ is a bounded exponential decay bonus for recent records.

### UI Labeling Requirement (UX-01)
In the frontend UI, this score is displayed as **`X% keyword coverage`** with a clarifying tooltip, rather than an ambiguous "match %" or "confidence %", ensuring users understand it measures lexical presence rather than epistemic certainty or semantic similarity.
