# Perpetual Analyst — Architecture & Implementation Specification

Status: v0.1 design (2026-06-10)
Owner: solo developer
Guiding rule: **the Analyst Agent is the product; everything else is plumbing.**

---

## 1. Product description

Perpetual Analyst is a personal AI analyst that follows the topics you care about so you don't have to. You tell it what you're tracking (AI, geopolitics, a market, a research field) and where to look (RSS feeds, arXiv categories, newsletters, sites). Every day it reads what's new, but unlike a news aggregator it doesn't just summarize — it maintains a persistent, evolving understanding of each topic: running theses it defends or revises, open questions it's tracking, patterns it noticed weeks ago that today's news confirms or contradicts. Each morning it sends a short Telegram briefing written from that accumulated perspective: what actually changed, why it matters given everything it already knows, what it now believes differently, and what to watch next. The longer it runs, the better its judgment gets — that continuity of analytical memory is the entire point.

---

## 2. MVP scope

### In version 1

| Capability | Why it's in |
|---|---|
| Topics + sources defined in a YAML/CLI config | Cheapest possible input surface |
| RSS/Atom ingestion + article text extraction | Covers RSS, arXiv (has RSS), most blogs, many newsletters |
| Manual document drop folder (`inbox/` for PDFs, .md, .txt) | Lets the analyst work before any pipeline exists |
| SQLite storage for everything (items, memory, theses, reports) | Zero ops |
| **Analyst Agent**: one LLM-driven analysis run per topic per day | The product |
| Persistent analyst memory: topic dossier, theses, observation log | The thing that makes it an analyst, not a summarizer |
| Daily report generation (Markdown) + archive | Core output |
| Telegram delivery (digest message + full report as file) | Core delivery |
| Simple retrieval: SQLite FTS5 keyword search over past items/observations, upgraded to embeddings only if needed | Supports "connect new to old" cheaply |
| Scheduler: one cron/Task Scheduler entry that runs the daily pipeline | Automation |

### Deliberately out of version 1

- Web UI / dashboard (CLI + Telegram only)
- Multi-user support (schema has a `users` table for future-proofing; code assumes one user)
- Source discovery / recommendation (Phase 5)
- YouTube transcripts, Twitter/X, paywalled scraping, email-newsletter parsing (add fetchers later behind the same interface)
- Vector database, rerankers, GraphRAG, knowledge graphs
- Multi-agent orchestration of any kind — one analyst, one loop
- Real-time/intraday alerts (daily cadence only)
- Chat-with-your-analyst interactivity over Telegram (nice Phase 4+ add-on, not MVP)

The test for V1 done: *after two weeks of daily runs, the reports visibly reference earlier developments and revised theses — i.e., the analyst demonstrably remembers.*

---

## 3. Core user workflow

1. **Add a topic** — `analyst topic add "AI frontier labs" --brief "Track model releases, safety policy, compute trends"`. The brief seeds the topic dossier and tells the analyst what the user actually cares about.
2. **Add sources** — `analyst source add --topic ai-frontier-labs --type rss --url https://...`. Or edit `config/sources.yaml`. Sources can be shared across topics. Manual input: drop a PDF/markdown file into `inbox/<topic-slug>/`; it's ingested on the next run.
3. **Ingestion (automated, daily, before the analyst runs)** — fetchers pull new entries since the last run, extract clean text (trafilatura), dedupe by URL/content hash, store as `items` rows, index into FTS.
4. **Analyst run (per topic)** — the agent receives: the topic brief, the current dossier, active theses, recent observations, yesterday's report section, and today's new items (triaged). It produces: a topic analysis (report section) **and** structured memory updates (new observations, thesis changes, dossier edits, open-question updates) in one structured-output call (or a short tool loop — see §7).
5. **Memory evolution** — observations are appended; theses are updated in place with a change log; the dossier is the analyst's rewritten "current state of understanding" per topic; weekly, the analyst compacts its own memory (promote/expire observations).
6. **Report assembly + Telegram** — topic sections are composed into one daily report; an executive digest (≤ ~3,000 chars) goes to Telegram as a message, the full report attached as a `.md` file. Stored in `reports` for the analyst to read tomorrow.

---

## 4. System architecture

One Python process, run on a schedule. Modules, not services.

```
                ┌────────────────────────────────────────────┐
                │                daily_run.py                │
                └────────────────────────────────────────────┘
                      │              │                │
              1. ingest        2. analyze        3. deliver
                      │              │                │
   ┌──────────────────▼──┐   ┌───────▼────────┐   ┌───▼─────────────┐
   │ ingestion/          │   │ analyst/  ★    │   │ delivery/       │
   │  fetchers (rss,     │   │  agent.py      │   │  telegram.py    │
   │  file inbox, web)   │   │  memory.py     │   │  report_render  │
   │  extract.py         │   │  theses.py     │   └─────────────────┘
   │  dedupe.py          │   │  prompts/      │
   └─────────┬───────────┘   │  triage.py     │
             │               └───────┬────────┘
             ▼                       ▼
   ┌─────────────────────────────────────────────┐
   │ store/  — SQLite (sqlite3 + FTS5)           │
   │  items, chunks, topics, sources, theses,    │
   │  observations, dossiers, reports            │
   └─────────────────────────────────────────────┘
             ▲
   ┌─────────┴───────────┐
   │ retrieval/          │  FTS5 keyword search (V1)
   │  search.py          │  optional: embeddings.py (sqlite-vec) later
   └─────────────────────┘
```

**Tech stack**

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.12 | |
| LLM | Anthropic API — `claude-opus-4-8` for the analyst run, `claude-haiku-4-5` for item triage/summaries | Adaptive thinking (`thinking={"type": "adaptive"}`) on the analyst call; structured outputs via `client.messages.parse()` + Pydantic |
| Storage | SQLite, one file (`analyst.db`), FTS5 virtual tables | No server, easy backup |
| Embeddings (optional, Phase 2+) | Voyage AI (`voyage-3.5`) or local `sentence-transformers`, vectors in `sqlite-vec` | Only if FTS proves insufficient |
| Fetching | `feedparser`, `httpx`, `trafilatura` (extraction), `pypdf` (inbox PDFs) | |
| Telegram | `python-telegram-bot` (send-only in V1) | |
| Scheduling | OS cron / Windows Task Scheduler calling `python -m perpetual_analyst.daily_run` | No in-process scheduler to babysit |
| Config | `config/topics.yaml`, `config/sources.yaml`, `.env` for keys | |
| CLI | `typer` | `analyst topic add`, `analyst run --topic x --dry-run`, etc. |

**Data flow:** sources → fetch → extract/dedupe → `items` → triage (Haiku: relevance score + 2-line summary per item) → analyst run (Opus: reasoning over triaged items + memory) → memory writes + report section → report assembly → Telegram.

The triage step exists to protect the analyst's context: the expensive model sees 10–30 distilled items per topic, not 200 raw articles.

---

## 5. Database schema (SQLite)

```sql
-- single-user now, multi-user later
CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  telegram_chat_id TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE topics (
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  slug TEXT UNIQUE NOT NULL,            -- 'ai-frontier-labs'
  name TEXT NOT NULL,
  brief TEXT,                           -- what the user cares about; seeds the dossier
  active INTEGER DEFAULT 1,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE sources (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,                   -- 'rss' | 'inbox' | 'web' | future: 'youtube', 'github'
  url TEXT,
  name TEXT,
  active INTEGER DEFAULT 1,
  last_fetched_at TEXT,
  fetch_error_count INTEGER DEFAULT 0,
  quality_score REAL,                   -- Phase 5: analyst-rated signal quality
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE topic_sources (             -- many-to-many
  topic_id INTEGER REFERENCES topics(id),
  source_id INTEGER REFERENCES sources(id),
  PRIMARY KEY (topic_id, source_id)
);

CREATE TABLE items (                     -- fetched documents
  id INTEGER PRIMARY KEY,
  source_id INTEGER REFERENCES sources(id),
  url TEXT,
  content_hash TEXT UNIQUE,             -- dedupe
  title TEXT,
  author TEXT,
  published_at TEXT,
  fetched_at TEXT DEFAULT (datetime('now')),
  raw_text TEXT,                        -- extracted clean text
  triage_summary TEXT,                  -- Haiku 2-liner
  triage_score REAL,                    -- 0-1 relevance from triage
  status TEXT DEFAULT 'new'             -- 'new' | 'analyzed' | 'skipped'
);
CREATE VIRTUAL TABLE items_fts USING fts5(title, raw_text, content='items', content_rowid='id');

-- chunks+embeddings table only created when/if vector retrieval is enabled (Phase 2+)
CREATE TABLE chunks (
  id INTEGER PRIMARY KEY,
  item_id INTEGER REFERENCES items(id),
  chunk_index INTEGER,
  text TEXT,
  embedding BLOB                        -- or a sqlite-vec virtual table keyed by chunk id
);

-- ANALYST MEMORY ---------------------------------------------------

CREATE TABLE dossiers (                  -- one living document per topic
  topic_id INTEGER PRIMARY KEY REFERENCES topics(id),
  content TEXT NOT NULL,                -- markdown, analyst-maintained, ~1-2K tokens budget
  updated_at TEXT
);

CREATE TABLE theses (
  id INTEGER PRIMARY KEY,
  topic_id INTEGER REFERENCES topics(id),
  statement TEXT NOT NULL,              -- 'Open-weight models will reach frontier parity within 12 months'
  rationale TEXT,
  confidence REAL,                      -- 0-1, analyst-assessed
  status TEXT DEFAULT 'active',         -- 'active' | 'confirmed' | 'revised' | 'retired'
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT
);

CREATE TABLE thesis_updates (            -- audit trail of revisions
  id INTEGER PRIMARY KEY,
  thesis_id INTEGER REFERENCES theses(id),
  change TEXT NOT NULL,                 -- what changed and why
  confidence_before REAL,
  confidence_after REAL,
  triggered_by_item_id INTEGER REFERENCES items(id),
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE observations (              -- the analyst's insight log
  id INTEGER PRIMARY KEY,
  topic_id INTEGER REFERENCES topics(id),
  kind TEXT NOT NULL,                   -- 'fact' | 'signal' | 'pattern' | 'contradiction' | 'question'
  content TEXT NOT NULL,
  importance INTEGER DEFAULT 2,         -- 1 minor / 2 notable / 3 significant
  source_item_ids TEXT,                 -- JSON array of item ids (citations)
  status TEXT DEFAULT 'active',         -- 'active' | 'promoted' (into dossier) | 'expired'
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE VIRTUAL TABLE observations_fts USING fts5(content, content='observations', content_rowid='id');

CREATE TABLE reports (
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  report_date TEXT UNIQUE,
  digest_text TEXT,                     -- what went to Telegram
  full_markdown TEXT,
  delivered_at TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
```

Design notes: memory is **structured rows, not opaque blobs**, so it can be queried, budgeted, and expired. `thesis_updates` and `observations.source_item_ids` give every claim a citation trail.

---

## 6. RAG design (kept deliberately small)

**V1 retrieval is keyword search, not vectors.** FTS5 over `items` and `observations` answers the analyst's actual question — "have I seen something related before?" — well enough for a single user's corpus. Add embeddings only when you observe FTS missing semantic matches.

- **Chunking (when embeddings arrive):** ~1,000-token chunks, 100-token overlap, split on paragraph boundaries; only embed items with `triage_score ≥ 0.4`. Store in `chunks` / sqlite-vec. One embedding call per batch via Voyage.
- **Retrieval in the analyst run:** for each of today's triaged items, pull (a) top-5 related past observations and (b) top-3 related past items (FTS match on title + key terms, recency-weighted). These get injected into the analyst prompt as "related prior context", pre-grouped per new item.
- **Past reports:** the analyst always receives yesterday's full topic section verbatim, plus the digest lines from the last 7 days. Older reports are reachable only through observations (which is what they distilled into). This is the main anti-repetition mechanism: the model literally sees what it told the user yesterday and is instructed "do not restate anything already reported unless its meaning changed."
- **Citations:** every item is presented to the model with a stable ID (`[item:482]`). The analyst must tag claims with these IDs; the renderer converts them to numbered footnote links (title + URL) in the report. Observations store `source_item_ids` the same way, so even month-old conclusions remain traceable.
- **Repetition guard (cheap and effective):** before finalizing a topic section, the pipeline FTS-matches each report bullet against the last 7 days of report text; high-overlap bullets get flagged back to the model in a single revision pass — or in V1, simply rely on the "yesterday's section in context + explicit instruction" approach and skip the second pass.

Retrieval exists to *feed the analyst's working memory*, not to answer user queries. There is no user-facing search in V1.

---

## 7. Analyst Agent behavior

One agent, one structured call per topic per day (with the option to grow into a small tool loop later).

**The call:** `claude-opus-4-8`, adaptive thinking, `effort: high`, structured output (Pydantic) returning:

```python
class TopicAnalysis(BaseModel):
    report_section_markdown: str          # the user-facing analysis
    new_observations: list[NewObservation]    # kind, content, importance, item_ids
    thesis_updates: list[ThesisUpdate]        # thesis_id|new, statement, confidence, change_rationale
    dossier_edits: str | None                 # full replacement dossier text, only if it changed
    open_questions: list[str]                 # current open-question set (full replacement)
    watch_next: list[str]
    nothing_significant: bool                  # permission to be quiet
```

**Context assembled for the call (in caching-friendly order):** fixed analyst persona/system prompt → topic brief → dossier → active theses (+ last update each) → last 7 days of digest lines → yesterday's topic section → active observations (importance-sorted, budgeted) → today's triaged items with related-prior-context attached.

**Responsibilities, encoded in the system prompt:**

1. **Summarize selectively** — cover what's new, at the depth it deserves; most items deserve one line or silence.
2. **Judge importance** — explicitly rank today's developments; "most important development" must be argued, not just picked.
3. **Detect change** — the unit of analysis is the *delta*: what is different from yesterday's understanding, not what happened.
4. **Connect** — tie new items to prior observations/theses by ID ("this confirms [obs:91] from May 28").
5. **Maintain theses** — every active thesis must be touched at least implicitly: confirmed, pressured, or unaffected. Confidence moves require a stated reason (logged to `thesis_updates`).
6. **Spot emerging trends** — when ≥3 related signals accumulate in observations, propose a `pattern` observation or a new thesis.
7. **Separate epistemic categories** — reported facts vs. analyst inference vs. speculation are labeled distinctly in the report (e.g., "Fact / Read / Speculation").
8. **Flag uncertainty and contradiction** — a dedicated section; conflicting sources are surfaced, not averaged away.
9. **Explain why it matters** — every "important" item carries a so-what tied to the user's brief.
10. **Track unresolved questions** — open questions persist day to day until answered or retired; the analyst must notice when one gets answered.
11. **Recommend monitoring** — "watch next" items, and (later) flags like "this topic needs a better primary source."
12. **Be quiet when nothing happened** — `nothing_significant: true` produces a one-line entry. A daily analyst that manufactures significance trains the user to ignore it. This is the single most important behavioral rule.

**Long-run character:** calibrated (records its misses — a thesis retired counts as a learning event, summarized in the dossier), conservative about novelty (three weak signals ≠ a trend), explicit about memory ("I noted on May 14 that…"), and stable in voice. A weekly self-review run (same agent, different prompt) reads the week's observations and performs memory compaction (§8) plus a short "what I got wrong/right this week" note appended to the dossier.

---

## 8. Analyst memory design

Three tiers, each with an explicit budget so memory cannot bloat:

| Tier | Table | Lifetime | Budget | Written by |
|---|---|---|---|---|
| **Dossier** (durable understanding) | `dossiers` | permanent, rewritten | ~1.5K tokens per topic | analyst (full rewrite when it changes) |
| **Theses** (positions) | `theses` (+ updates) | until retired | ≤ 7 active per topic | analyst, with audit trail |
| **Observations** (working memory) | `observations` | 30–90 days unless promoted | ~3K tokens injected per run (importance-sorted) | analyst, append-only |

Rules:

- **Promotion:** during the weekly compaction run, observations that proved durable (referenced repeatedly, importance 3, or underpinning a thesis) are merged into the dossier and marked `promoted`. The dossier is the only place long-term conclusions live.
- **Expiry:** importance-1 observations expire after 30 days, importance-2 after 90, automatically (`status='expired'`); they remain queryable via FTS but are never auto-injected. Nothing is deleted — only excluded from context.
- **Thesis revision:** theses are never silently edited. A revision writes a `thesis_updates` row and bumps `updated_at`; retirement requires a stated reason. Stale check: any thesis untouched for 30 days gets explicitly flagged to the analyst ("revisit or retire").
- **Temporary vs. durable:** observations are temporary by default; durability is *earned* via promotion. This one-way ratchet keeps the permanent store small and high-signal.
- **Bloat control is structural, not behavioral:** budgets are enforced by the context assembler (it truncates by importance/recency), not by hoping the model writes less.

---

## 9. Daily report format (Markdown template)

```markdown
# Daily Intelligence Brief — {date}

## Executive summary
{3–6 sentences, cross-topic, written last by the analyst}

## Most important developments
1. **{headline}** — {why it matters} [^1]
   *Fact:* … *Read:* … 

## Topic: {topic name}
### What's new
### Changes since yesterday          <- delta vs. yesterday's section
### Thesis updates                   <- only theses that moved, with confidence before→after
### Emerging patterns                <- omit if none
### Contradictions & uncertainties   <- omit if none
### Analyst notes                    <- inference/speculation, clearly labeled
(repeat per topic; topics with nothing_significant get one line)

## Open questions
- {persisting questions, with age: "open 12 days"}

## Things to watch next
- …

## Sources reviewed
{count by source; footnote list of cited items with links}
```

Sections with nothing to say are omitted, not filled. The report is stored verbatim and is part of tomorrow's context.

---

## 10. Telegram integration

- **Digest message:** ≤ ~3,000 characters (Telegram hard limit 4,096), HTML parse mode (more robust than Markdown V2 escaping). Structure: 🎯 exec summary → top 3 developments (one line + why each) → thesis changes if any → "watch next". No per-topic exhaustiveness — the digest is the analyst's editorial judgment of what you must see.
- **Full report:** attached to the same chat as `brief-2026-06-10.md` via `send_document`. One message + one file per day; never split the digest across multiple messages (split messages read as spam).
- **Voice:** first person, confident, terse — "I'm raising my confidence on X; yesterday's Y filing is the third signal this month." The digest is the analyst talking, not a table of contents.
- **Failure handling:** if Telegram send fails, the report is still stored; next run retries undelivered reports.
- **V1 is send-only.** Inbound commands (`/why`, `/thesis list`, ad-hoc questions) are a Phase 4+ feature; they require a webhook/polling listener and conversational state — real scope.

---

## 11. Source discovery (deferred feature — Phase 5)

- **Finding candidates:** a weekly job gives the analyst a `web_search` tool (Anthropic server-side tool) with the topic brief + dossier and asks for 3–5 candidate sources (feeds/sites) it believes would have improved this week's analysis, citing the gap each fills. Additionally, mine outbound links: domains repeatedly cited *by* existing high-quality items are natural candidates.
- **Ranking signal quality:** per source, track (a) triage hit-rate (share of fetched items scoring ≥0.4), (b) citation rate (share of items actually cited in reports), (c) uniqueness (how often it was the *only* source for a cited development), (d) freshness lead (did it carry developments before other sources). Combine into `sources.quality_score`.
- **Ongoing evaluation:** the weekly self-review surfaces the bottom decile ("Source X produced 40 items, 0 cited in 6 weeks — recommend dropping") and the discovery candidates.
- **User approval:** recommendations land in the weekly report and as Telegram inline buttons (✅ add / ❌ dismiss) — sources are never auto-added or auto-removed. Trial mode: new sources start `probation` for 3 weeks before counting toward topic noise.

---

## 12. Implementation plan

**Phase 1 — Analyst prototype with manual input + memory (the product, proven cheap)**
DB schema + store layer; `inbox/` file ingestion only; analyst run for one topic; dossier/theses/observations read+write; report printed to stdout/file. *Exit test: feed it 5 days of hand-picked articles one day at a time; day-5 report must reference day-1 context.*

**Phase 2 — Source ingestion + retrieval**
RSS fetcher, trafilatura extraction, dedupe, Haiku triage; FTS5 indexes + related-context retrieval wired into the analyst prompt; sources/topics CLI + YAML config.

**Phase 3 — Automated daily reports via Telegram**
Report assembler (multi-topic), digest writer, Telegram sender (message + file), delivery tracking/retry; cron/Task Scheduler entry; structured logging + a `--dry-run` flag.

**Phase 4 — Memory & thesis maturity**
Weekly compaction run (promotion/expiry), stale-thesis flagging, thesis audit trail surfaced in reports ("confidence 0.6→0.8 over 3 weeks"), memory budgets enforced in the context assembler, prompt-caching pass (stable prefix ordering).

**Phase 5 — Source discovery & quality**
Per-source quality metrics, weekly discovery run with web search, approval flow via Telegram buttons, probation lifecycle.

---

## 13. Folder structure

```
perpetual-analyst/
├── SPEC.md
├── pyproject.toml
├── .env.example                  # ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
├── config/
│   ├── topics.yaml
│   └── sources.yaml
├── inbox/                        # manual document drop, per-topic subfolders
├── data/
│   ├── analyst.db
│   └── reports/                  # rendered markdown archive
├── src/perpetual_analyst/
│   ├── __init__.py
│   ├── daily_run.py              # orchestrator entry point
│   ├── cli.py                    # typer app
│   ├── analyst/                  # ★ the product
│   │   ├── agent.py              # context assembly + LLM call + output handling
│   │   ├── memory.py             # dossier/observation/thesis read-write, budgets, compaction
│   │   ├── theses.py
│   │   ├── triage.py             # Haiku relevance pass
│   │   ├── schemas.py            # Pydantic output models
│   │   └── prompts/
│   │       ├── analyst_system.md
│   │       ├── weekly_review.md
│   │       └── digest.md
│   ├── ingestion/
│   │   ├── base.py               # Fetcher protocol
│   │   ├── rss.py
│   │   ├── inbox.py
│   │   └── extract.py
│   ├── retrieval/
│   │   └── search.py             # FTS now; embeddings.py later
│   ├── store/
│   │   ├── db.py                 # connection, migrations
│   │   └── models.py
│   ├── report/
│   │   ├── assemble.py
│   │   └── render.py             # citations → footnotes, template
│   └── delivery/
│       └── telegram.py
└── tests/
```

---

## 14. First 10 development tasks (hand to a coding agent)

1. **Project skeleton + DB layer.** `pyproject.toml`, package layout above, `store/db.py` creating the full §5 schema with a tiny migration mechanism. Tests: schema creates, FTS triggers sync.
2. **Memory module.** `analyst/memory.py`: CRUD for dossier/observations/theses, `thesis_updates` audit writes, importance/recency-budgeted `build_memory_context(topic_id, token_budget)` returning prompt-ready text. Tests with fake data.
3. **Analyst schemas + prompt.** `analyst/schemas.py` (Pydantic models from §7) and `prompts/analyst_system.md` encoding the 12 behavioral rules.
4. **Analyst agent call.** `analyst/agent.py`: assemble context (caching-friendly order: stable system prompt first), call `claude-opus-4-8` via `client.messages.parse()` with adaptive thinking, persist all returned memory writes transactionally. Include a replayable `--dry-run` that prints the assembled prompt without calling the API.
5. **Inbox ingestion.** `ingestion/inbox.py`: watch `inbox/<topic>/` for .md/.txt/.pdf, extract text (pypdf), hash-dedupe, write `items`. End-to-end Phase 1 test: 3 docs → analyst run → report file + memory rows.
6. **Thesis lifecycle.** `analyst/theses.py`: apply `ThesisUpdate`s (create/revise/retire), enforce ≤7 active, stale-flagging query (30 days untouched), render "Thesis updates" report fragment with confidence before→after.
7. **RSS ingestion + triage.** `ingestion/rss.py` (feedparser + trafilatura, since-last-fetch, error counting) and `analyst/triage.py` (Haiku batch call: score + 2-line summary per item; mark `status`).
8. **Retrieval.** `retrieval/search.py`: FTS5 query helpers `related_observations(text, topic, k)` / `related_items(text, topic, k)` with recency weighting; wire "related prior context" blocks into agent context assembly.
9. **Report assembly + rendering.** `report/`: merge topic sections, exec-summary + digest call (`prompts/digest.md`), `[item:N]` → footnote conversion, write `reports` row + markdown file to `data/reports/`.
10. **Telegram delivery + scheduler entry.** `delivery/telegram.py` (HTML digest ≤3,000 chars + document attach, retry of undelivered), `daily_run.py` orchestrating ingest→triage→analyze-per-topic→assemble→deliver with per-stage error isolation (one failing topic must not kill the run), plus a documented cron/Task Scheduler line.

---

## 15. Risks and simplifications (be strict)

**Where this project dies if you let it:**

1. **Multi-agent theater.** You will be tempted: a "researcher agent," a "critic agent," a "fact-checker agent," debating crews. Don't. One model call with good context beats five calls with fragmented context, at 5× less cost and complexity. The only legitimate second "agent" is the Haiku triage pass, and that's a function, not an agent. Revisit only if you have evals proving the single analyst is the bottleneck.
2. **Memory science projects.** Knowledge graphs, entity resolution, episodic/semantic memory taxonomies, reflection trees — all seductive, all unnecessary. Three tables with budgets and an expiry rule deliver 90% of the value. The dossier-as-rewritten-markdown is crude and that's the point: the model is good at maintaining a document; it's bad at maintaining your ontology.
3. **RAG maximalism.** No vector DB service, no rerankers, no hybrid fusion, no GraphRAG in a single-user corpus of a few thousand documents. FTS5 first. You can add sqlite-vec in an afternoon *when you observe a concrete retrieval failure*, not before. The retrieval bar here is "remind the analyst of plausibly related prior notes," not "win BEIR."
4. **Ingestion sprawl.** Every new source type (YouTube, X, email, Discord…) is a parser you'll maintain forever. RSS + a drop folder covers a shocking fraction of real intelligence diets. Add fetchers only for sources you've proven you read.
5. **Report inflation.** The failure mode of daily AI reports is that they're impressive for a week and ignored by week three because everything is "significant." The `nothing_significant` escape hatch, omitted-when-empty sections, and the ≤3,000-char digest are load-bearing product decisions. Guard them.
6. **Cost drift.** One Opus call per topic per day + Haiku triage is the budget. If you find yourself adding revision loops, self-critique passes, and weekly mega-runs, check the bill: with ~5 topics this should stay in the tens of dollars per month. Use prompt caching (stable system prompt first, volatile items last) from day one.
7. **The real risk: building infrastructure instead of judgment.** Every hour on fetchers is an hour not spent reading the analyst's output and tuning its prompt, memory budgets, and thesis behavior. The product lives in `analyst/prompts/` and `memory.py`. Phase 1 deliberately has *no pipeline at all* so you confront the product first.

**Simplest useful version, restated:** a cron job that reads RSS into SQLite, one Claude call per topic that reads its own notes and writes new ones, and a Telegram message. Everything beyond that must justify itself against the question: *does this make the analyst's reasoning measurably better?*
