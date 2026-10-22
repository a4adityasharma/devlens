# DevLens AI — Build Log & Continuation Guide

Last updated: 2026-09-24 (session 12 — Phase 9 complete)
Purpose of this file: so you (or any other AI tool) can pick this project up
at any point without losing context.

---

## 1. The Overall Plan (10 Phases)

| Phase | Content | Status |
|---|---|---|
| 0 | Define MVP scope (languages, repo size limit, feature list) | ✅ Done |
| 1 | Foundation — monorepo, Docker Compose, DB schema, API skeleton | ✅ Done |
| 2 | Repository Manager — clone, scan, metadata | ✅ Done |
| 3 | Code Intelligence — Tree-sitter, AST, symbol extraction | ✅ Done |
| 4 | Knowledge Graph — Neo4j relationships (IMPORTS/CALLS/INHERITS/...) | ✅ Done (CONTAINS/DEFINES/IMPORTS/CALLS; INHERITS not yet — see gaps) |
| 5 | Semantic Search — chunking, embeddings, Qdrant | ✅ Done (search endpoint working; real embedding quality unverified — see gaps) |
| 6 | RAG Chat — hybrid retrieval (vector + graph) + LLM + citations | ✅ Done (chat endpoint working, citation grounding verified; real LLM output quality unverified — see gaps) |
| 7 | Agent System — Security / Testing / Architecture / Docs / Performance / Review agents via LangGraph | 🟡 Partial (Security + Architecture + Testing[Stage A] + Documentation + Performance Agents done; 2 more not started) |
| 8 | Validation Layer — reject ungrounded agent findings against Neo4j/AST | ⏳ Not started |
| 9 | Dashboard — full React UI (health score, per-agent tabs, graph viz, chat) | ✅ Complete |
| 10 | Evaluation + Deployment — metrics, Docker, docs, research writeup | ⏳ Not started |

MVP language scope: **Python, JavaScript, TypeScript** (Java later).
MVP repo size limit: **≤ 10,000 files** (enforced in code, see `MAX_REPO_FILES`).

---

## 2. What Is Actually Implemented Right Now

### Working end-to-end (tested against real GitHub repos across two sessions)

`POST /api/repositories` now runs the **full pipeline built so far** as one
chained background task:

```
clone (GitPython) → scan (languages/frameworks/entry points) → status "ready"
   → create RepositoryAnalysis (pinned to current commit hash)
   → Tree-sitter parse every .py/.js/.jsx/.ts/.tsx file
   → aggregate symbols + stats → analysis status "completed"
```

**Session 1** verified Module 1 (clone/scan) against `octocat/Hello-World`
and confirmed URL validation rejects malformed input with a 400.

**Session 2** verified Module 2 (Tree-sitter/AST) two ways:
- Unit tests against fixture files in all 3 MVP languages
  (`tests/test_ast_extractor.py`, 4 tests, all passing) — confirms classes,
  methods (with correct `parent`), top-level functions (with parsed
  parameter lists, including `*args`/`**kwargs` and JS arrow-function
  assignments), and imports are all extracted correctly per language.
- **Live full-pipeline run against the real `pallets/flask` repo**
  (236 files, 83 Python source files): correctly parsed and returned via
  `GET /api/repositories/{id}/analyses/latest` —
  `1019 functions, 160 classes, 443 methods, 648 imports, 2270 total
  symbols`, tied to the exact commit hash cloned. Sample output (imports
  from `src/flask/cli.py`) confirmed real file paths and 1-indexed line
  numbers matching the actual source.

### Important fix from this session — pin your Tree-sitter deps correctly

`tree-sitter-languages` (the "one package, all grammars" bundle originally
listed in requirements.txt) is **broken** against `tree-sitter>=0.22`: its
pinned Cython bindings call `Language(ptr)` with an ABI the new
`tree_sitter.Language` constructor doesn't accept, raising
`TypeError: __init__() takes exactly 1 argument (2 given)` at parse time.
Fixed by switching to the actively-maintained **per-language packages**
(`tree-sitter-python`, `tree-sitter-javascript`, `tree-sitter-typescript`),
which work correctly with `tree-sitter==0.26.0`. `requirements.txt` and
`app/analyzer/parser.py` already reflect this — don't revert to the bundle.

### Session 3 — Module 3: Neo4j Knowledge Graph (Phase 4)

Two things happened this session, in order:

**1. Fixed a real bug found while building call-tracking into the AST
extractor.** Adding CALLS relationships required the extractor to also
capture call expressions (`svc.login(...)`, `generate_token(...)`) tagged
with their enclosing function/method. While wiring this up, a pre-existing
gap surfaced: in JavaScript/TypeScript, `const token = someCall(x)` —
a call sitting as the *value* of a variable declarator — was silently
**not walked at all**, because the `lexical_declaration` handler only
recursed into a declarator's value when that value was itself a function
definition (arrow fn / function expression), not for arbitrary
expressions. Fixed in `app/analyzer/ast_extractor.py`'s `_walk_js` by
dispatching on the whole declarator node (so the value is checked as a
direct child, matching the same pattern the rest of the walker already
relies on) instead of skipping straight to the value. Covered by
`test_javascript_call_extraction` (see its docstring/comment referencing
this exact case) so it can't silently regress.

**2. Built the graph module** (`app/knowledge/`):
- `neo4j_client.py` — thin wrapper around the official `neo4j` driver
  (`run_query`, `run_write`, `verify_connectivity`, one driver per process).
- `graph_builder.py` — the actual graph-shaping logic, split into a pure
  function `build_write_plan(repository_id, symbols) -> list[WriteStep]`
  (no I/O — takes the flat `symbols` list, returns Cypher + params in
  order) and `build_knowledge_graph(client, repository_id, symbols)` which
  executes that plan against any object with a `.run_write()` method.
  Writes `(:Repository)-[:CONTAINS]->(:File)-[:DEFINES]->(:Class|:Function)`,
  `(:Class)-[:CONTAINS]->(:Method)`, `(:File)-[:IMPORTS]->(:Module)`, and
  `(:Function|:Method|:Class)-[:CALLS]->(:Callable)`. Every repository's
  subgraph is cleared and rewritten from scratch on each analysis run (no
  stale nodes after re-analysis).
- `app/services/graph_service.py` — orchestrator mirroring
  `analysis_service.py`'s pattern: pulls `RepositoryAnalysis.symbols`,
  calls the builder, records a `graph` summary back onto
  `RepositoryAnalysis.stats`. **Fails soft**: if Neo4j isn't reachable
  (`verify_connectivity()` returns False), it raises `GraphBuildSkipped`
  rather than crashing the pipeline — the repository and its parsed
  symbols remain fully usable even with no graph backend running, which
  matters because this sandbox has no live Neo4j instance to test against.
- Wired into `app/api/routes/repositories.py`'s chained background task:
  `ingest → code intelligence → graph build`, with the graph step wrapped
  in `try/except GraphBuildSkipped: pass`.

**No live Neo4j instance is reachable in this sandbox** (not in the
allowed network domains, no local server), so this phase could not be
smoke-tested against a *running* database the way Phases 1-3 were tested
against real GitHub repos. What *was* verified without a live DB:
- 6 new unit tests (`tests/test_graph_builder.py`) exercise
  `build_write_plan`/`build_knowledge_graph` against a mock client that
  captures every Cypher call — confirming exactly which nodes/edges get
  created from a given symbols list, including that calls are correctly
  split into "from a Function" vs "from a Method" (different Cypher, since
  Method lookup needs the extra `parent` match), and that a module-level
  call with no enclosing function is correctly skipped rather than
  crashing.
- 2 more unit tests (`tests/test_graph_service.py`) confirm the
  unreachable-Neo4j soft-fail path, and that stats get merged (not
  overwritten) when the graph build does succeed.
- Ran `build_write_plan`/`build_knowledge_graph` against the **real**
  multi-language symbol set from `tests/fixtures/` (all 3 languages
  together, 29 symbols) via a capturing mock — correctly produced 3 files,
  3 classes, 6 functions, 7 methods, 4 imports, 9 call-relationship
  candidates split 4-from-function / 5-from-method.
- Ran the full HTTP pipeline end-to-end one more time
  (`octocat/Hello-World`) to confirm `ingest → code intelligence → graph
  build` doesn't crash the request when Neo4j is absent — repo reached
  `status: "ready"`, analysis reached `status: "completed"`, no traceback
  in the server log.

**Whoever picks this up next with a live Neo4j (via `docker compose up`)
should do the live verification this session couldn't**: run
`docker compose up neo4j`, re-analyze a repo (or call
`run_graph_build` directly against a `RepositoryAnalysis`), then open
`http://localhost:7474` and run
`MATCH (f:File)-[:DEFINES]->(fn:Function) RETURN f.path, fn.name LIMIT 20`
to confirm the mock-verified logic produces the same shape against a real
database. This is the single most important unverified assumption in the
codebase right now.

### Session 4 — stronger Neo4j verification + Module 4: Qdrant Semantic Search (Phase 5)

**Part 1 — closed the gap from session 3's note above, as far as this
sandbox allows.** Docker still isn't available here (checked again this
session: no `docker` binary, and Neo4j isn't in Ubuntu's standard apt repos
— it's JVM-based and hosted outside the allowed network domains), so a
*real* Neo4j still couldn't be started. Instead, built
`tests/neo4j_simulator.py` — a small in-memory interpreter that implements
actual MERGE/MATCH/UNWIND semantics for graph_builder.py's specific fixed
set of Cypher templates (not general Cypher). This is meaningfully
stronger than session 3's mock-that-just-counts-calls: 6 new tests in
`tests/test_graph_builder_live_semantics.py` assert on real resulting
graph shape — e.g. that `Class -[:CONTAINS]-> Method` actually links the
*correct* class (not just that a write happened), that CALLS resolution
correctly fans out to every same-named method when two unrelated classes
both define `save()` (the documented "by_name" ambiguity from
graph_builder.py's docstring, now proven rather than just described), and
that re-running against an unchanged repo doesn't duplicate nodes/edges.
**This still isn't a live Neo4j** — it doesn't catch real Cypher syntax
errors, index behavior, or version quirks. That remains open; see the next
person's checklist at the end of this file.

**Part 2 — built Phase 5 (Semantic Search) and, unlike Neo4j, got REAL
verification for most of it.** `qdrant-client` has a genuine embedded
local mode (`QdrantClient(":memory:")`) — confirmed working in this
session — that runs the actual Qdrant query engine in-process with no
server. This let `tests/test_embedding_service.py` exercise the *real*
chunk → embed → upsert → cosine-similarity-search round trip, not a mock.
That real testing caught two genuine bugs before they'd have shipped:

1. **Chunk IDs weren't valid Qdrant point IDs.** The first version used a
   raw SHA-1 hex digest as each chunk's id; Qdrant rejects that (`Point id
   ... is not a valid UUID`) — point IDs must be an unsigned int or a
   UUID. Fixed by deriving a deterministic `uuid5` from the same identity
   string instead. A mock-based test would never have caught this, since a
   mock doesn't validate what a real ID format has to look like.
2. **The offline embedder's tokenizer didn't split compound identifiers.**
   `authenticate_user` was treated as one opaque token, so a search query
   for "authenticate" shared zero tokens with a chunk containing only
   `authenticate_user` — real search results ranked an unrelated chunk
   first. Fixed by splitting on snake_case/camelCase boundaries before
   lowercasing (initially got the ordering backwards — lowercased first,
   which destroys the case signal camelCase-splitting needs — caught by
   the same real test, fixed on the second pass).

What OpenAI's embeddings API (the production path, `OpenAIEmbedder` in
`app/embeddings/embedder.py`) does **not** have: `api.openai.com` is
outside this sandbox's allowed network domains (only `api.anthropic.com`
is reachable, and Anthropic has no embeddings endpoint), and no
`OPENAI_API_KEY` is configured anyway. So `OpenAIEmbedder` is written
carefully (batching, lazy import so the `openai` package isn't required
unless this class is actually used) but has **never been exercised against
a live API in any session**. `HashingEmbedder` — a deterministic,
dependency-free bag-of-words fallback — is what every test above actually
runs against; it's real enough to prove the pipeline plumbing works
end-to-end, but explicitly NOT semantically meaningful the way a real
embedding model is (see its docstring). Whoever has real OpenAI/embedding
API access should verify `OpenAIEmbedder` before trusting search quality
for anything beyond this sandbox's plumbing-level verification.

**Full pipeline re-verified end-to-end via live HTTP** (same pattern as
sessions 1-3): submitted `pallets/flask` again through
`POST /api/repositories`, waited for `ingest → parse → graph-build-attempt
→ embedding-attempt` to complete — reached `status: "ready"` /
`"completed"` with no traceback, `stats.embedding` correctly `null`
because this sandbox has no long-running Qdrant *server* at `QDRANT_URL`
(only the in-memory mode used inside tests) so `EmbeddingSkipped` fired and
was caught, exactly as designed. Also directly verified
`POST /{id}/search` returns `200 []` (not a 500) when nothing's been
embedded yet, and `404` for an unknown repository id.

**40 tests passing** at the end of this session (up from 18 at the start).

### Session 5 — Module 5: RAG Chat (Phase 6)

Closed-loose-end check first, honestly: still no Docker/live Neo4j (checked
again — same result as sessions 3-4), and while `api.anthropic.com` **is**
network-reachable from this sandbox (unlike `api.openai.com`), no
`ANTHROPIC_API_KEY` is configured here either, so a live LLM call still
couldn't happen this session. Proceeded straight to building Phase 6 with
that constraint acknowledged up front, same as Phase 5's `OpenAIEmbedder`
situation.

**Extended the Neo4j simulator (`tests/neo4j_simulator.py`) to support read
queries, not just the write queries from Phase 4.** Added a `run_query()`
method with the same identity-dispatch pattern as `run_write()`, covering
the 4 CALLS-neighbor lookup templates `app/retrieval/hybrid_retriever.py`
uses (function vs. method caller, outgoing vs. incoming). This meant the
graph-expansion half of hybrid retrieval could be tested against a graph
actually built by `build_knowledge_graph()` — real traversal over real
(simulated) relationship data, not a canned mock response — the same
verification-depth upgrade Phase 4 got in session 4, now extended to reads.

**Built, in order:**
- `app/retrieval/hybrid_retriever.py` — `build_context()` (pure function,
  vector hits + optional graph expansions -> one text blob with explicit
  `[SOURCE: file:start-end]` markers per block) and `graph_expand()` +
  `retrieve()` (the I/O adapters, calling `search_repository()` from Phase
  5 and the Neo4j client for CALLS neighbors). Vector search failing
  (Qdrant unreachable, `EmbeddingSkipped`) surfaces as empty hits, not a
  crash — same soft-fail philosophy every service in this project uses.
- `app/services/chat_service.py` — `_call_llm()` (Anthropic API, lazy
  import, raises `ChatSkipped` if no key configured) and, more
  importantly, `_extract_and_validate_citations()`: a **pure function**
  that parses the LLM's claimed `Sources:` section and drops — silently,
  not "fixes" or "fuzzy-matches" — any citation that doesn't exactly match
  a real `[SOURCE: ...]` marker from what was actually retrieved. This is
  the concrete implementation of architecture doc §14/§29's "every claim
  must be traceable to a real file/line" requirement, and it's the one
  piece of this phase that's genuinely, thoroughly tested: 7 unit tests
  cover valid citations, hallucinated line numbers, citations to files
  never retrieved, mixed valid/invalid lists, and the no-sources-section
  case — all pure logic, zero mocking needed. Two more tests confirm the
  guarantee holds through the full (LLM-mocked) `answer_question()` flow,
  including one that specifically plants a fabricated source next to a
  real one in the mocked LLM output and confirms only the real one
  survives.
- Wired the existing (previously unused) `ChatSession`/`ChatMessage`
  models into a new `POST /repositories/{id}/chat` endpoint: creates a
  session if `session_id` is omitted, persists both the user's message and
  the assistant's (validated) answer, 404s if the repository or session
  doesn't exist, 503s (not a crash) if `ChatSkipped` fires.

**Verified live via HTTP** (real server, real SQLite, real repo through the
full pipeline, same pattern every session has used):
- `POST /{id}/chat` on an unknown repository → `404`.
- `POST /{id}/chat` against `octocat/Hello-World` (no parseable files, so
  zero retrieval hits) → `200` with "couldn't find relevant code", no LLM
  call attempted at all — confirms the early-return path avoids wasting an
  LLM call when retrieval has nothing to offer.
- `POST /{id}/chat` against `pallets/flask` after a full pipeline run →
  same "couldn't find" `200`, because this sandbox has no long-running
  Qdrant *server* (only the in-memory mode tests use), so `EmbeddingSkipped`
  → empty hits, exactly as designed — **not yet directly observed**: a live
  `503` from `ChatSkipped` when hits genuinely exist but no API key is
  set. Confirmed that specific path instead via FastAPI's `TestClient`
  with `answer_question` mocked to raise `ChatSkipped` (`503` with the
  right detail message came back correctly), and separately confirmed a
  full two-turn conversation (session continuation, message persistence,
  cross-repository session-id rejection) via `TestClient` with
  `answer_question` mocked to a canned successful response.

**What's still unverified**: real LLM call quality/behavior (`_call_llm`
has never executed against a live model — every test and every live HTTP
check mocked or short-circuited around it), and by extension whether
Claude reliably follows the "only cite what's in `[SOURCE: ...]` markers,
copy them exactly" instruction in practice rather than just in principle.
The citation *validator* is thoroughly tested; what's untested is how
often a real model's output needs it to actually catch something.

**59 tests passing** at the end of this session (up from 40 at the start).

### Session 6 — Module 6: Security Agent (Phase 7, partial)

Started Phase 7 per the plan: one agent only, Security Agent first,
wrapping a deterministic scanner rather than asking an LLM to find
vulnerabilities unaided (architecture doc §16).

**Tool choice, decided by what's actually installable here** (same
approach every prior phase took — check the environment before committing
to a tool): Bandit installs cleanly but is Python-only. Semgrep covers
Python **and** JS/TS in one tool, matching the project's actual MVP
language scope, so it's the better fit. Installing it alongside the rest
of the stack initially failed — misdiagnosed at first as "a pre-existing
system PyJWT package conflicts with pip install semgrep in this specific
sandbox" and worked around with an isolated venv + a `SEMGREP_BIN` env
var. **That diagnosis was wrong, caught two sessions later (session 7)
when a fresh sandbox reset forced a real `pip install -r requirements.txt`
from scratch**: the actual cause was that this project's own
`requirements.txt` pinned `pydantic==2.9.2` and `uvicorn==0.30.6`, both
too old for `mcp` (semgrep's own dependency, used for its MCP-server
feature, requires `pydantic>=2.11.0` and `uvicorn>=0.31.1`) — a real
conflict in this project's dependency pins that would have broken a clean
Docker build too, not a sandbox quirk at all. Fixed properly in session 7
by relaxing those two pins; see that session's notes for the full story
and why the venv workaround masked the real bug for a session.

**More importantly: semgrep's rule *registry* (`--config=auto`, or a
registry ruleset ID like `p/security-audit`) lives at semgrep.dev, which
has never been reachable from any session's sandbox.** Rather than skip
real scanning entirely, wrote a small local custom ruleset
(`app/agents/rules/security_rules.yaml`) — 7 rules across Python and
JS/TS covering shell injection, eval/exec code injection, SQL injection
via string concatenation, and hardcoded credentials. This needs zero
network access and was verified for real: a fixture repo
(`tests/security_fixtures/vulnerable_repo/`) was hand-built with one
planted instance of each vulnerability type plus deliberately-safe
functions, and the real semgrep binary correctly flagged every planted
vulnerability and zero false positives on the safe code.

**One rule needed a real fix during that verification** — the initial SQL
injection pattern only matched string concatenation happening *inline*
inside `cursor.execute(...)`, missing the equally common case of building
the query string in a separate variable first, then executing it. Fixed
with a second pattern using semgrep's multi-line metavariable matching
(`$QUERY = "..." + ...` ... `$CURSOR.execute($QUERY)`) to trace the
variable across statements. Caught because the test fixture used the
more realistic two-statement form, not because of any automated check —
worth remembering when writing new rules: test against realistic code
shape, not the simplest possible inline case.

**Built:**
- `app/agents/security_scanner.py` — `run_semgrep()` (subprocess wrapper,
  raises `ScannerUnavailable` if the binary's missing, `ScannerError` on
  timeout/bad output) and `parse_semgrep_result()` (raw semgrep JSON ->
  the common finding shape).
- `app/services/security_agent_service.py` — `run_security_scan()`
  orchestrates scan -> validate -> persist as `Finding` rows (the
  previously-unused table from architecture doc §23), plus
  `_validate_finding()`: before persisting, checks the claimed file
  actually exists under the repo root and the claimed line is within the
  file's real line count — the same "verify before trusting" principle
  `chat_service.py`'s citation validator uses, applied to a scanner's
  output instead of an LLM's.
- **Explicit design decision, as instructed rather than defaulted**:
  wired as an on-demand `POST /repositories/{id}/analyze/security`
  endpoint, NOT a fourth step chained onto `POST /repositories` — a
  semgrep scan is real wall-clock time on top of parsing/graph/embedding,
  and isn't needed for every ingestion. Also added
  `GET /repositories/{id}/findings` to list accumulated findings across
  scans.

**A second real bug, caught only by live-testing against a real cloned
repository, not by any unit test**: `parse_semgrep_result()`'s original
version checked `raw_path.is_absolute()` to decide whether to compute a
path relative to the repo root — but semgrep echoes back paths in
whatever form the *target* was passed in, not necessarily relative to the
repo root specifically. Every unit test in this project so far happens to
pass an absolute path (fixtures under `tests/`, or `tmp_path` in pytest),
which coincidentally made the absolute-path branch always fire and always
work. `repository.local_path` in the real pipeline, though, is genuinely
a **relative** path (`storage/repos/<uuid>`, from `REPO_STORAGE_PATH`'s
default) — hitting the untested branch, which then treated semgrep's
CWD-relative path as if it were already repo-root-relative, producing a
mangled path that failed `_validate_finding()`'s file-existence check for
100% of real findings. Confirmed live: `POST /{id}/analyze/security`
against a real cloned `pallets/flask` returned `findings_created: 0,
findings_rejected: 2` before the fix. Fixed by resolving *both* the
result path and repo root to absolute, canonical paths before computing
the relative path — no more branching on which form either happened to
arrive in. Re-verified live after the fix: same Flask clone now returns
`findings_created: 2, findings_rejected: 0`, both findings' file
paths/lines confirmed correct. Added a regression test
(`test_parse_semgrep_result_correct_with_relative_repo_root`) that
specifically constructs the relative-path case rather than relying on
`tmp_path`'s absolute form, so this can't silently reappear.

**This is now the second scanner-category tool in this project (after
Qdrant) that got genuinely real, no-mock verification** — both bugs above
were found by running the actual tool against actual files/repos, not by
inspecting code or writing more mocks.

**72 tests passing** at the end of this session (up from 59 at the start).

### Session 7 — sandbox reset + corrected a misdiagnosed dependency bug from session 6

**This session started with the sandbox's filesystem having reset between
turns** (a fresh environment, no prior work present) — recovered by
extracting the previously-delivered `devlens-ai.zip` from
`/mnt/user-data/outputs/`, which had survived the reset, rather than
rebuilding from scratch. Worth knowing if this happens again: check the
outputs directory before assuming everything is lost.

**That recovery forced a real, from-scratch `pip install -r
requirements.txt`** — which session 6 had never actually done, because it
had installed semgrep into a separate isolated venv specifically to route
around what it diagnosed as "a pre-existing system PyJWT package conflicts
with installing semgrep here." That diagnosis was incomplete. The real,
from-scratch install failed with a much more informative error:
`pydantic==2.9.2` (this project's own pin, present since session 1) is
incompatible with `mcp==1.29.0`, which is `semgrep==1.176.0`'s own hard
dependency (used for semgrep's MCP-server feature) and requires
`pydantic>=2.11.0`. A second, related conflict surfaced right behind it:
`mcp` also requires `uvicorn>=0.31.1`, while this project pinned
`uvicorn==0.30.6`.

**This means session 6's `SEMGREP_BIN`/isolated-venv workaround was
masking a real bug in this project's own `requirements.txt`, not routing
around a sandbox quirk.** It would have broken a genuine `pip install -r
requirements.txt` in a clean Docker build too — the previous session's own
claim that "a clean Docker image... should just work with, no workaround
needed there" was untested and wrong.

**Fixed properly this session**: relaxed the two conflicting pins to
`pydantic==2.13.5` and `uvicorn[standard]==0.53.0` (the versions pip's
resolver actually picked once given room to work) — confirmed compatible
with FastAPI 0.115.0's own dependency range (`pydantic<3.0.0,>=1.7.4`, per
its published metadata) before committing to them, not just guessed.
Verified with a real, complete, single-environment install: `pip install
--break-system-packages --ignore-installed -r requirements.txt` succeeds,
`semgrep` resolves directly on `PATH` with no `SEMGREP_BIN` override
needed, and the full 73-test suite passes. Re-ran the live HTTP pipeline
one more time (`pallets/flask`, full ingestion + `POST
/{id}/analyze/security`) with the corrected single environment — same
correct result as session 6's fix (`findings_created: 2,
findings_rejected: 0`), now with genuine confidence the dependency
resolution itself works, not just the application code on top of it.

Corrected `security_scanner.py`'s and `test_security_scanner.py`'s
docstrings, and this file's session 6 write-up and Known Gaps entry, to
stop describing this as sandbox-specific. `--ignore-installed` was still
needed in *this* session's sandbox specifically (a Debian-managed system
PyJWT that pip can't uninstall in-place) — that part genuinely is
environment-specific and is a normal, common `pip`-in-a-managed-Python
situation, not a project bug; a fresh Docker image (no pre-existing system
PyJWT) shouldn't need that flag at all.

**Lesson for future sessions, stated plainly**: when a dependency install
fails, don't stop at the first plausible-looking cause (the PyJWT error
message was real and visible — it just wasn't the *whole* story, and the
venv workaround "solved" the visible symptom without ever testing whether
the full stack could resolve together). Try the full, real,
single-environment install before reaching for a workaround, especially
before writing that workaround into permanent documentation as if it were
a verified conclusion.

**73 tests passing** — unchanged from session 6's end (this session fixed
infrastructure, didn't add features).

### Session 8 — Module 7: Architecture Agent (Phase 7, second of seven)

**Second agent, and a genuinely different design outcome than the
Security Agent** — this one is pure in-memory computation over
`RepositoryAnalysis.symbols` (no subprocess, no external tool), so instead
of "check what's installable" (session 6's question), this session's
question was "measure whether it's cheap enough to chain automatically."
Benchmarked `analyze_architecture()` against a real 6,233-symbol repo
(`pallets/flask`, re-cloned fresh this session): **~3ms**. Chained it into
the automatic pipeline as a fourth best-effort step, unlike the Security
Agent's deliberately-on-demand endpoint — a genuinely different answer to
the same "chain or on-demand?" question the previous session raised,
reached by measuring rather than copying the prior decision.

**Architecture doc §18's core instruction — "this agent shouldn't invent
architecture, it should use [real data] to determine [structure]" — is
enforced structurally, not just by convention**: `architecture_analyzer.py`
has no LLM call anywhere in it. Layers come from a directory-keyword
heuristic (falls back to the immediate parent directory name, title-cased,
when no keyword matches — an honest "this repo doesn't use conventional
layer names" result rather than a forced fit). Edges come from reusing the
same by-name CALLS resolution `graph_builder.py` already established
(same documented ambiguity tradeoff, verified with an equivalent test:
`test_build_layer_graph_ambiguous_callee_name_creates_multiple_edges`).

**Real verification took an interesting form here — no external tool to
test against (unlike Qdrant/Semgrep), so the strongest test is
self-analysis**: ran the Architecture Agent on DevLens AI's own backend
source code. It correctly found `Services`, `Models`, `Routes`,
`Knowledge`, `Embeddings`, `Agents` etc. as real layers, and correctly
found real edges — `Routes -> Services` (API routes calling service
functions), `Services -> Knowledge` (graph/embedding/chat services calling
the Neo4j/Qdrant client wrappers), `Services -> Embeddings`, and so on —
that are all independently, obviously true of this project's actual
structure to anyone who's read the code in earlier sessions. This is
asserted directly in `test_architecture_agent_self_analysis_finds_real_layers`,
not just eyeballed. A second real-world check against `pallets/flask`
(live HTTP, full pipeline) produced an honest, if slightly noisy, picture
of Flask's actual layout (`Flask`, `Sansio`, `Tests`, `Flaskr`, `Task App`,
`Js Example` — all genuinely real Flask directory names, correctly
including that Flask's large test suite has heavy real dependencies on
its core `sansio`/`flask` modules) — not a cleaned-up or invented
simplification.

**New model, deliberately not overloading an existing one**: added
`GeneratedArtifact` (`generated_artifacts` table, mentioned but unmodeled
in the architecture doc) rather than shoehorning a Mermaid diagram into
the `Finding` table, which is shaped for security-style findings
(severity/category/file/line) that don't fit a diagram's actual content.

Added `GET /repositories/{id}/architecture` to read the latest diagram —
unlike the Security Agent's `POST /analyze/security`, this is a plain
`GET` since generation already happened automatically during ingestion,
consistent with the chained-not-on-demand decision above.

**13 new tests, all against real data — no mocking needed or possible**
for this module, since it's pure computation: `test_architecture_analyzer.py`
(10 tests: keyword matching, fallback behavior, the flat-fixtures
zero-edges case, the self-analysis case, ambiguous-callee fan-out, Mermaid
syntax) and `test_architecture_agent_service.py` (3 tests: persistence,
empty-symbols and None-symbols edge cases).

**86 tests passing** at the end of this session (up from 73 at the start).

### Session 9 — Module 8: Testing Agent, Stage A only (Phase 7, third of seven)

The most involved agent so far — architecture doc §17's own pipeline
(AST -> identify untested functions -> LLM generates a test -> validate)
spans three genuinely different verification situations, handled
separately rather than glossed over:

**Step 1 (`app/agents/test_coverage_analyzer.py`) — pure, deterministic,
real-verified, same standard as the Architecture Agent.** A function
counts as "tested" if some `call` symbol from a file matching common test
conventions (`test_*.py`, `*_test.py`, `*.test.js`, `*.spec.ts`, or a
`tests`/`test`/`__tests__` directory) references it by name. Self-analysis
on this project's own backend — same dogfooding approach as the
Architecture Agent — turned up a real, previously undocumented finding:
**`clone_repository`, `scan_repository`, `ingest_repository`, and
`run_code_intelligence` — core Module-1/3 pipeline functions — have zero
direct pytest unit-test coverage**, confirmed by grepping `tests/` for
their names before asserting it. They were only ever verified via live
HTTP/curl checks across many sessions (see sessions 1-3's notes), which is
real verification but not the same as an automated regression test. This
is now locked into `test_self_analysis_finds_known_real_coverage_gaps`
rather than just noted in passing — a good demonstration of the Testing
Agent actually finding something true and useful about this very
codebase, not just running without crashing.

**Step 2 (`app/agents/test_generator.py`) — needs an LLM, inherits
`chat_service.py`'s exact unverified-quality situation.** Written against
the Anthropic API; `api.anthropic.com` is reachable from this sandbox but
no key is configured, so — same as every LLM-touching module in this
project — every test mocks `_call_llm` directly. No new gap here, just the
same one chat_service.py already documented, now duplicated in a second
module.

**Step 3 (`app/agents/test_validator.py`) — the one with a real safety
dimension, and the one this session put the most care into.** Architecture
doc §17 explicitly warns against executing arbitrary generated code on the
host. Rather than skip validation or fake it, built "Stage A": everything
checkable WITHOUT execution — does it parse (Tree-sitter's `has_error`,
verified against both a valid and a deliberately-broken example for
Python, JS, and TypeScript), does it actually reference the target
symbol (catches a test for the wrong function, or a hallucinated name),
does it look like a test (recognized framework import or assertion
present). **Stage B — real sandboxed execution — is explicitly NOT
built.** This isn't a "ran out of time" gap stated apologetically; it's a
deliberate scope boundary, because building it properly needs a genuine
isolation story (separate container, gVisor/Firecracker, hosted execution
service) that's real infrastructure work, not a code change, and bolting
on `subprocess.run(generated_code)` in the same container the backend
runs in would defeat the entire point of the doc's warning. Every place
this module's output surfaces (its own docstring, the orchestrator's
docstring, the API endpoint's docstring) says explicitly that returned
code has NOT been executed — this is stated at every layer on purpose, so
it can't get lost in a later session's summary.

**Orchestration (`app/services/testing_agent_service.py`) — another
explicit, measured design decision, not a default.** Scoped to **one
function per request** (`POST /repositories/{id}/generate-test` with a
`file`/`symbol_name` body), not "generate tests for every untested
function" — an LLM call per function is real cost/latency (unlike the
Architecture Agent's ~3ms), and generating dozens of tests in one
unreviewed batch would be a worse experience than picking one at a time.
A test that fails Stage A validation is returned to the caller (with the
specific failure reasons) but is NOT persisted — reuses the
`GeneratedArtifact` table the Architecture Agent added
(`agent="testing"`, `artifact_type="generated_test"`) rather than a new
one.

**Verified live, both required negative-path demos plus the full HTTP
stack**: `test_test_validator.py` proves the validator rejects a
syntactically broken generated test AND a test referencing a nonexistent
function (the two demos this file's own plan for this session explicitly
required, not just a happy-path check). Beyond the unit tests, ran the
full `POST /repositories/{id}/generate-test` endpoint via FastAPI's
`TestClient` against a real (if manually-seeded, since Hello-World has no
real Python functions to target) analysis, with only the LLM call mocked
— confirmed a valid generated test gets `persisted: true` with a real
`artifact_id`, and an invalid one gets `persisted: false` with the
validation failure surfaced, exactly matching the unit-tested behavior at
the HTTP layer too. Also confirmed `404` for an unknown repository, an
unknown symbol, and a repository with no analysis yet, and `503` when no
`ANTHROPIC_API_KEY` is configured (the actual live case in this sandbox).

**24 new tests** across four new test files — coverage analysis (8,
including the two self-analysis assertions above), the validator (9,
including both required negative-path demos), the generator (2, mocked
LLM), and the orchestrator (5, real source-reading and real validation,
LLM mocked).

**110 tests passing** at the end of this session (up from 86 at the
start).

### Session 10 — Module 9: Documentation Agent (Phase 7, fourth of seven) + a DRY refactor

**Refactor first, before the new agent**: sessions 6/9's `chat_service.py`
and `test_generator.py` each had their own near-identical
`_call_llm`/`*Skipped` pair. Session 9's own notes flagged this as worth
extracting "at this point" — this session was the third near-identical
copy about to be written for the Documentation Agent, so it actually
happened. New `app/agents/llm_client.py`: one shared `call_llm()` and one
shared `LLMSkipped`. Each module keeps its own named exception
(`ChatSkipped`, `TestGenerationSkipped`, new `DocGenerationSkipped`) by
catching `LLMSkipped` and re-raising — existing route-level exception
handling (`except ChatSkipped`, etc.) didn't need to change at all.
Verified safe before proceeding: ran `test_chat_service.py` and
`test_test_generator.py`/`test_testing_agent_service.py` immediately after
the refactor (not just at the end of the session) — all passed unchanged,
confirming `get_settings()`'s `@lru_cache` means `chat_service.settings`
and `llm_client.settings` are the same object, so existing tests that
monkeypatch `app.services.chat_service.settings.ANTHROPIC_API_KEY` still
correctly affect the shared call path. One real test fix was still needed:
`test_test_generator.py` had patched
`app.agents.test_generator.settings.ANTHROPIC_API_KEY` directly, which
broke once `test_generator.py` no longer holds its own `settings`
reference — updated to patch `app.agents.llm_client.settings` instead.

**The Documentation Agent itself is a different shape of problem than the
first three agents — its ENTIRE value is the LLM call**, unlike the
Architecture Agent (no LLM at all) or the Security/Testing Agents (LLM is
one step among several deterministic ones). There's no way to keep the
risky part small here. Instead, the prompt and the grounding check were
co-designed together, mirroring `chat_service.py`'s `[SOURCE: ...]`-marker
approach: the system prompt requires backtick-wrapping for any file path
or function/class/method name claimed to be real, which turns "did the
model hallucinate a reference" from a fuzzy prose-parsing problem into a
mechanical one — extract every backtick span, check it against the real
file/symbol sets from `RepositoryAnalysis.symbols`.

**One real bug caught immediately by testing, before it shipped**: the
first version of the path-vs-symbol classifier
(`_PATH_LIKE_RE = r"[\w./-]+\.\w+$|/"`) matched `` `AuthService.login` ``
as a file path (it has a dot followed by word characters at the end),
so a perfectly legitimate dotted method reference was checked against the
*files* set instead of the *symbols* set and wrongly flagged as
ungrounded. Fixed by classifying on a real signal — a slash, or a
trailing segment matching a known file extension (`.py`, `.js`, etc.) —
rather than "has a dot in it," which a dotted symbol reference also has.
Caught by three failing tests on first run, not discovered later.

**Unlike the Testing Agent's Stage A (binary parse/no-parse gate),
grounding here is informational, not a persistence gate** — a README with
one stray ungrounded mention among fifty correct ones is still mostly
useful, so `run_documentation_generation()` always persists and attaches
the grounding report to the artifact rather than rejecting outright. This
is a deliberate difference from the Testing Agent, not an inconsistency:
generated code that doesn't parse is useless, but generated prose with
one hallucinated reference usually isn't.

**Architecture doc §19's "never overwrite repository files" requirement
was verified as an actual behavior, not just a docstring claim**: the live
HTTP test seeded a real `README.md` on disk, generated a new "readme"
document via the API, and re-read the file from disk afterward to confirm
it was byte-for-byte unchanged — the generated content only ever reaches
a new `GeneratedArtifact` database row.

**Verified live end-to-end** via `TestClient` (real repo creation, a
manually-seeded analysis + real README file since `octocat/Hello-World`
has no real Python functions to ground against, LLM mocked as usual):
`400` for an unknown `doc_type`, `503` with no `ANTHROPIC_API_KEY`
configured (the real live case here), and a `200` generation run where
the mocked output deliberately included one real reference and one
fabricated file path (`config/settings.py`) — confirmed the fabricated
one was correctly caught and surfaced in the response's `grounding` field,
and confirmed the on-disk README was untouched.

**17 new tests**: 11 for `doc_generator.py` (7 for the grounding checker,
including both required negative-path demos — a fabricated file and a
fabricated symbol — plus the dotted-reference bug fix; 4 for generation
orchestration with the LLM mocked) and 6 for
`documentation_agent_service.py` (real context-gathering — README reading,
symbol grouping — with only the LLM mocked).

**127 tests passing** at the end of this session (up from 110 at the
start).

### Session 11 — Module 10: Performance Agent (Phase 7, fifth of seven)

**Deliberately built LLM-free**, mirroring the Architecture Agent's
precedent rather than the Security/Testing/Documentation Agents' — per
architecture doc §20's own framing, cyclomatic complexity is an
objective, decades-old metric (McCabe, 1976), so a raw number + a
fixed-template recommendation is arguably *more* trustworthy for "is this
function too complex" than LLM prose would be, not a corner cut. This
was an open question in the plan (section 4's own notes asked "is an LLM
needed at all here?") and this session answered it: no.

**Complexity computed by re-parsing each function's own source slice**
(same source-slicing technique as `chunker.py`) with Tree-sitter, counting
McCabe decision-point nodes. The exact node type sets were determined by
*inspecting real Tree-sitter output*, not assumed from grammar docs — two
things would have been easy to get wrong without checking: JS/TS's
`&&`/`||` don't have their own node type (they're a `binary_expression`
whose `operator` field must be checked — a naive "count all
`binary_expression` nodes" approach would wrongly count ordinary
arithmetic like `a + b` as a decision point, which
`test_javascript_binary_expression_arithmetic_does_not_count` locks in),
and JS "else if" chains are nested `if_statement`s with no separate
elif-equivalent node the way Python has `elif_clause`.

**Verified against hand-computed expected values, not just "runs without
crashing"** — every complexity test traces the exact decision points by
hand before asserting the number (e.g. "1 base + if + boolean_operator +
for + if + boolean_operator = 6") the same way session 8's Architecture
Agent verification worked backward from known-true structure. One test's
*own* hand-count was wrong on first run (forgot to count the first `if`
in an else-if chain, expected 3, correct answer is 4) — caught by the
test failing, fixed by recomputing, not by adjusting the code to match a
wrong expectation.

**A real bug caught during self-analysis, from a path mistake I made
myself**: ran `analyze_performance(Path('.'), symbols_from_app_dir)` —
inconsistent roots (symbols were relative to `app/`, but I passed the
parent `backend/` directory as local_path) — which caused every complexity
check to silently fail closed (file-not-found → skip) while still
reporting Large Function findings correctly (since those don't need a
file read). The result looked plausible — six real findings, no crash —
which is exactly why it was dangerous: only manually cross-checking one
specific function's complexity by hand caught that an entire category of
findings was silently missing. Fixed by correcting the path, not the
code (the function itself was right); documented as a gap since the
silent-skip-on-mismatched-paths behavior (consistent with `chunker.py`'s
existing pattern) makes this exact mistake easy to make again.

**Benchmarked before deciding chain-vs-on-demand, per this project's
established practice**: ~126ms against a real 6,233-symbol repository
(`pallets/flask`) — meaningfully slower than the Architecture Agent's
~3ms (this one does real file I/O and re-parses every function's source
slice), but still negligible next to the clone/parse/graph/embedding
steps already in the pipeline. Chained automatically, same reasoning as
the Architecture Agent. Findings persist as `Finding` rows
(`agent="performance"`) — reusing the Security Agent's table rather than
`GeneratedArtifact`, since a location-scoped finding with a severity/
category is exactly that table's shape, not a whole-repo artifact's.

**Verified live end-to-end** against real `pallets/flask` through the
full HTTP pipeline: 44 real findings auto-generated during ingestion,
all independently spot-checkable (Flask's own test suite genuinely has
several 50-90-line test functions — this is honest, unmanufactured
output, the same "show your work" bar every prior agent was held to).
`GET /{id}/findings` (already existing, not agent-scoped) surfaces these
alongside Security Agent findings with no new endpoint needed.

**19 new tests**: 16 for `performance_analyzer.py` (hand-computed
complexity values across Python and JS/TS, the arithmetic-vs-logical
`binary_expression` distinction, large-function detection, and
self-analysis locking in a specific known-complex function in this
project's own codebase) and 3 for `performance_agent_service.py`
(persistence, clean-code/empty-symbols edge cases).

**146 tests passing** at the end of this session (up from 127 at the
start).

```
devlens-ai/
├── docker-compose.yml            postgres, redis, neo4j, qdrant, backend, worker, frontend
├── .env.example / .env
├── README.md
├── docs/PROGRESS.md              (this file)
│
├── backend/
│   ├── requirements.txt          fastapi, sqlalchemy, celery, redis, gitpython,
│   │                             neo4j-driver, qdrant-client, tree-sitter (deps
│   │                             pre-listed for Phases 3–6, not all used yet)
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py               FastAPI app, CORS, table creation, /health
│   │   ├── core/
│   │   │   ├── config.py         pydantic-settings, env vars, ignored dirs
│   │   │   └── database.py       SQLAlchemy engine/session
│   │   ├── models/models.py      Repository, RepositoryAnalysis, Finding,
│   │   │                         ChatSession, ChatMessage (Postgres tables
│   │   │                         from architecture doc §24)
│   │   ├── schemas/repository.py Pydantic request/response models
│   │   ├── analyzer/                   <-- Module 2 (Phase 3), fully working
│   │   │   ├── parser.py               TreeSitterParserPool: one cached
│   │   │   │                          Parser per language (py/js/ts/tsx),
│   │   │   │                          parse_file() -> ParsedFile
│   │   │   ├── ast_extractor.py        extract_symbols_from_file(): walks
│   │   │   │                          the Tree-sitter tree, emits the
│   │   │   │                          common Symbol representation
│   │   │   │                          (class/function/method/import) —
│   │   │   │                          separate walkers for Python vs JS/TS
│   │   │   │                          grammars, unified output shape
│   │   │   └── repository_analyzer.py  analyze_repository(): walks the
│   │   │                              whole cloned repo (same ignored-dirs
│   │   │                              logic as Module 1), aggregates
│   │   │                              symbols + per-type/per-language counts
│   │   ├── knowledge/                  <-- Modules 3+4 (Phases 4-5)
│   │   │   ├── neo4j_client.py         Neo4jClient: run_query/run_write/
│   │   │   │                          verify_connectivity wrapper around
│   │   │   │                          the official `neo4j` driver. Still
│   │   │   │                          UNVERIFIED against a live Neo4j (none
│   │   │   │                          reachable — see session 3+4 notes)
│   │   │   ├── graph_builder.py        build_write_plan() (pure, testable
│   │   │   │                          without a DB) + build_knowledge_graph()
│   │   │   │                          (executes the plan). Writes
│   │   │   │                          Repository/File/Class/Function/Method/
│   │   │   │                          Module nodes + CONTAINS/DEFINES/
│   │   │   │                          IMPORTS/CALLS relationships. Verified
│   │   │   │                          via tests/neo4j_simulator.py (real
│   │   │   │                          MERGE/MATCH semantics, in-memory)
│   │   │   └── qdrant_client.py        VectorStoreClient: ensure_collection/
│   │   │                              upsert/delete_by_repository/search/
│   │   │                              verify_connectivity wrapper around
│   │   │                              `qdrant-client`. REAL-verified via
│   │   │                              Qdrant's local (":memory:") mode —
│   │   │                              see session 4 notes, this is the one
│   │   │                              external dependency in the project
│   │   │                              with genuine (not simulated/mocked)
│   │   │                              test coverage.
│   │   ├── embeddings/                 <-- Module 4 (Phase 5)
│   │   │   ├── chunker.py              chunk_repository(): slices real
│   │   │   │                          source text by each symbol's
│   │   │   │                          file/line_start/line_end (function/
│   │   │   │                          class/method only) into Chunk objects
│   │   │   │                          with a deterministic uuid5 id
│   │   │   └── embedder.py             Embedder ABC + OpenAIEmbedder
│   │   │                              (production path, UNVERIFIED — no
│   │   │                              network access to api.openai.com in
│   │   │                              this sandbox, no API key configured)
│   │   │                              + HashingEmbedder (deterministic
│   │   │                              offline fallback, snake_case/
│   │   │                              camelCase-aware tokenizer, what every
│   │   │                              test actually runs against) +
│   │   │                              get_embedder() factory
│   │   ├── retrieval/                   <-- Module 5 (Phase 6)
│   │   │   └── hybrid_retriever.py     build_context() (pure — hits +
│   │   │                              optional graph expansions -> one
│   │   │                              text blob with [SOURCE: file:start-
│   │   │                              end] markers per block) +
│   │   │                              graph_expand() (Neo4j CALLS-neighbor
│   │   │                              lookup, function-vs-method query
│   │   │                              split mirroring graph_builder.py) +
│   │   │                              retrieve() (top-level: vector search
│   │   │                              via embedding_service + graph
│   │   │                              expansion, merged). Verified via
│   │   │                              neo4j_simulator.py's new run_query()
│   │   │                              support (real traversal over a real
│   │   │                              simulated graph) + real local Qdrant.
│   │   ├── agents/                      <-- Modules 6-10 (Phase 7, 5
│   │   │   │                          of 7 agents done: Security,
│   │   │   │                          Architecture, Testing[Stage A],
│   │   │   │                          Documentation, Performance)
│   │   │   ├── llm_client.py           call_llm() + LLMSkipped — shared
│   │   │   │                          Anthropic API adapter, extracted in
│   │   │   │                          session 10 after the third
│   │   │   │                          near-identical copy was about to be
│   │   │   │                          written. Used by chat_service.py,
│   │   │   │                          test_generator.py, doc_generator.py
│   │   │   │                          — each keeps its own named
│   │   │   │                          *Skipped exception by catching
│   │   │   │                          LLMSkipped and re-raising.
│   │   │   ├── rules/security_rules.yaml  7 local, offline Semgrep rules
│   │   │   │                          (Python + JS/TS) — deliberately NOT
│   │   │   │                          using semgrep's registry/--config=auto,
│   │   │   │                          which needs semgrep.dev (unreachable
│   │   │   │                          in every session so far)
│   │   │   ├── security_scanner.py     run_semgrep() (subprocess wrapper
│   │   │   │                          around the real semgrep binary,
│   │   │   │                          REAL-verified — see session 6/7) +
│   │   │   │                          parse_semgrep_result() (raw JSON ->
│   │   │   │                          common finding shape; fixed a real
│   │   │   │                          path-resolution bug in session 6)
│   │   │   ├── architecture_analyzer.py  infer_layer() (directory-keyword
│   │   │   │                          heuristic, falls back to parent dir
│   │   │   │                          name) + build_layer_graph() (layers
│   │   │   │                          + CALLS-based cross-layer edges,
│   │   │   │                          reusing graph_builder.py's by-name
│   │   │   │                          resolution) + generate_mermaid().
│   │   │   │                          Pure computation, no LLM, no
│   │   │   │                          external tool — REAL-verified via
│   │   │   │                          self-analysis (see session 8) since
│   │   │   │                          there's no external engine to test
│   │   │   │                          against the way Qdrant/Semgrep had.
│   │   │   ├── test_coverage_analyzer.py  find_untested_symbols(): pure,
│   │   │   │                          deterministic, REAL-verified via
│   │   │   │                          self-analysis (session 9) — found a
│   │   │   │                          genuine, previously-undocumented gap
│   │   │   │                          in THIS project's own test suite
│   │   │   │                          (clone_repository/scan_repository/
│   │   │   │                          ingest_repository/run_code_intelligence
│   │   │   │                          have zero direct pytest coverage)
│   │   │   ├── test_generator.py       generate_test(): needs an LLM
│   │   │   │                          (via llm_client.py as of session
│   │   │   │                          10) — every test mocks _call_llm
│   │   │   ├── test_validator.py       validate_generated_test(): Stage A
│   │   │   │                          only (parse check, target-symbol
│   │   │   │                          reference check, "looks like a
│   │   │   │                          test" check) — NEVER executes
│   │   │   │                          generated code. Stage B (real
│   │   │   │                          sandboxed execution) is explicitly
│   │   │   │                          NOT built — a deliberate scope
│   │   │   │                          boundary requiring real
│   │   │   │                          infrastructure (containerization/
│   │   │   │                          isolation), not a code change. See
│   │   │   │                          this module's own docstring and
│   │   │   │                          session 9's notes for why, stated
│   │   │   │                          at every layer that touches its
│   │   │   │                          output so it can't get lost later.
│   │   │   ├── doc_generator.py        generate_documentation() (needs an
│   │   │   │                          LLM, via llm_client.py) +
│   │   │   │                          check_grounding() (PURE, real-
│   │   │   │                          tested: extracts every backtick-
│   │   │   │                          wrapped span from generated prose
│   │   │   │                          and checks it against real file/
│   │   │   │                          symbol sets — a fabricated
│   │   │   │                          `` `file.py` `` or `` `ClassName`
│   │   │   │                          `` gets caught the same way
│   │   │   │                          chat_service.py's [SOURCE: ...]
│   │   │   │                          markers do). Fixed a real
│   │   │   │                          path-vs-symbol misclassification
│   │   │   │                          bug this session — see session 10
│   │   │   │                          notes.
│   │   │   └── performance_analyzer.py  compute_complexity() (real McCabe
│   │   │                              cyclomatic complexity via Tree-
│   │   │                              sitter decision-point counting,
│   │   │                              verified against HAND-COMPUTED
│   │   │                              expected values, not just "runs
│   │   │                              without crashing") +
│   │   │                              analyze_performance() (large-
│   │   │                              function + high-complexity
│   │   │                              detection). Deliberately LLM-free
│   │   │                              (see session 11 notes for why this
│   │   │                              was a deliberate choice, mirroring
│   │   │                              the Architecture Agent's precedent).
│   │   ├── services/
│   │   │   ├── repository_service.py   <-- Module 1, fully working
│   │   │   │       - validate_github_url()
│   │   │   │       - clone_repository()
│   │   │   │       - scan_repository()      language/framework/entrypoint detection
│   │   │   │       - ingest_repository()    orchestrates the above + DB writes
│   │   │   ├── analysis_service.py     <-- Phase 3 orchestrator
│   │   │   │       - run_code_intelligence()  creates RepositoryAnalysis
│   │   │   │         pinned to current commit hash, calls
│   │   │   │         analyzer.repository_analyzer, persists symbols+stats
│   │   │   ├── graph_service.py        <-- Phase 4 orchestrator
│   │   │   │       - run_graph_build()  pulls analysis.symbols, calls
│   │   │   │         graph_builder, merges a "graph" summary into
│   │   │   │         analysis.stats. Raises GraphBuildSkipped (caught by
│   │   │   │         the caller) if Neo4j isn't reachable — degrades
│   │   │   │         gracefully instead of failing the whole pipeline.
│   │   │   ├── embedding_service.py    <-- Phase 5 orchestrator
│   │   │   │       - run_embedding()    chunk -> embed -> ensure_collection
│   │   │   │         -> delete_by_repository (clears stale points) ->
│   │   │   │         upsert. Raises EmbeddingSkipped if Qdrant unreachable
│   │   │   │         — same soft-fail pattern as graph_service.py.
│   │   │   │       - search_repository()  standalone semantic search,
│   │   │   │         used by /search AND by hybrid_retriever.py directly.
│   │   │   ├── chat_service.py         <-- Phase 6 orchestrator
│   │   │   │       - _extract_and_validate_citations()  PURE function,
│   │   │   │         the core grounding guarantee: drops (doesn't "fix")
│   │   │   │         any LLM-claimed source that doesn't exactly match a
│   │   │   │         real [SOURCE: ...] marker from retrieval. Thoroughly
│   │   │   │         unit-tested, zero mocking needed.
│   │   │   │       - _call_llm()  Anthropic API call, lazy import, raises
│   │   │   │         ChatSkipped if ANTHROPIC_API_KEY unset. UNVERIFIED
│   │   │   │         against a live model in any session — no key
│   │   │   │         configured here (api.anthropic.com IS network-
│   │   │   │         reachable in this sandbox, unlike api.openai.com,
│   │   │   │         but that's necessary not sufficient without a key).
│   │   │   │       - answer_question()  top-level: retrieve -> call LLM ->
│   │   │   │         validate citations. Every test mocks _call_llm.
│   │   │   ├── security_agent_service.py  <-- Phase 7 orchestrator (Security Agent)
│   │   │   │       - run_security_scan()  scan -> validate -> persist as
│   │   │   │         Finding rows. Raises SecurityScanSkipped if semgrep
│   │   │   │         isn't installed — same soft-fail shape as
│   │   │   │         graph_service.py/embedding_service.py.
│   │   │   │       - _validate_finding()  PURE function: rejects any
│   │   │   │         finding whose file/line doesn't correspond to real
│   │   │   │         content on disk, mirroring chat_service.py's
│   │   │   │         citation-dropping philosophy applied to scanner
│   │   │   │         output instead of LLM output.
│   │   │   ├── architecture_agent_service.py  <-- Phase 7 orchestrator (Architecture Agent)
│   │   │   │       - run_architecture_analysis()  calls
│   │   │   │         architecture_analyzer, persists a GeneratedArtifact
│   │   │   │         (Mermaid diagram + layer/edge data). No soft-fail
│   │   │   │         path needed — no external service involved.
│   │   │   ├── testing_agent_service.py  <-- Phase 7 orchestrator (Testing Agent)
│   │   │   │       - list_untested_symbols()  read-only wrapper around
│   │   │   │         test_coverage_analyzer, backs GET /{id}/untested.
│   │   │   │       - run_test_generation()  ONE symbol per call
│   │   │   │         (deliberate — see this module's own docstring for
│   │   │   │         why, an LLM call per function is real cost/latency
│   │   │   │         unlike the Architecture Agent): reads real source
│   │   │   │         text -> generate_test() (LLM) ->
│   │   │   │         validate_generated_test() (Stage A, real) -> persists
│   │   │   │         as a GeneratedArtifact ONLY if valid. Raises
│   │   │   │         SymbolNotFound / propagates TestGenerationSkipped.
│   │   │   ├── documentation_agent_service.py  <-- Phase 7 orchestrator (Documentation Agent)
│   │   │           - run_documentation_generation()  ONE doc_type per
│   │   │             call (same one-thing-per-request reasoning as the
│   │   │             Testing Agent): gathers REAL context (file list +
│   │   │             symbols from RepositoryAnalysis.symbols, existing
│   │   │             README from disk if present, latest Architecture
│   │   │             Agent artifact if present) -> generate_documentation()
│   │   │             (LLM) -> check_grounding() -> ALWAYS persists as a
│   │   │             GeneratedArtifact, with the grounding report
│   │   │             attached as informational data, not a pass/fail gate
│   │   │             (unlike the Testing Agent's Stage A) — see this
│   │   │             module's own docstring for why that's a deliberate
│   │   │             difference, not an inconsistency. NEVER writes to
│   │   │             any file in the cloned repo — verified live in
│   │   │             session 10 (seeded a real README, generated a new
│   │   │             doc via the API, re-read the file from disk
│   │   │             afterward to confirm it was untouched).
│   │   └── performance_agent_service.py  <-- Phase 7 orchestrator (Performance Agent)
│   │               - run_performance_analysis()  calls performance_analyzer,
│   │                 persists Finding rows (agent="performance"). No LLM, no
│   │                 subprocess, no soft-fail path — chained automatically
│   │                 (measured ~126ms against a real 6,000+-symbol repo, see
│   │                 session 11 notes for the actual benchmark).
│   ├── api/routes/repositories.py  POST/GET/GET-by-id/DELETE /api/repositories
│   │                              + GET /{id}/analyses,
│   │                                GET /{id}/analyses/latest,
│   │                                POST /{id}/search,
│   │                                POST /{id}/chat,
│   │                                POST /{id}/analyze/security,
│   │                                GET /{id}/findings,
│   │                                GET /{id}/architecture,
│   │                                GET /{id}/untested,
│   │                                POST /{id}/generate-test,
│   │                                POST /{id}/generate-doc
│   │                              POST /repositories chains
│   │                              ingest_repository()
│   │                              -> run_code_intelligence()
│   │                              -> run_graph_build() (best-effort)
│   │                              -> run_embedding() (best-effort)
│   │                              -> run_architecture_analysis()
│   │                              -> run_performance_analysis()
│   │                              (both always run — no external service,
│   │                              ~3ms / ~126ms respectively even for a
│   │                              6,000+-symbol repo).
│   │                              POST /{id}/chat creates/continues a
│   │                              ChatSession, persists ChatMessages
│   │                              (with validated sources), 404 on
│   │                              unknown repo/session, 503 if
│   │                              ChatSkipped fires.
│   │                              POST /{id}/analyze/security is
│   │                              DELIBERATELY on-demand, NOT chained
│   │                              onto POST /repositories (see
│   │                              security_agent_service.py's module
│   │                              docstring for why) — 404 if no
│   │                              analysis exists yet, 503 if
│   │                              SecurityScanSkipped fires.
│   │                              GET /{id}/architecture just reads
│   │                              the latest auto-generated diagram
│   │                              (no POST needed — see above).
│   │                              GET /{id}/findings is NOT agent-scoped
│   │                              — returns Security AND Performance
│   │                              findings together, no new endpoint was
│   │                              needed for the Performance Agent.
│   │                              POST /{id}/generate-test targets
│   │                              ONE file+symbol_name per request
│   │                              (deliberate, see above) — returns
│   │                              the generated code + validation
│   │                              result even when rejected
│   │                              (persisted: false), 404 if
│   │                              repo/analysis/symbol missing, 503
│   │                              if TestGenerationSkipped fires.
│   │                              **Generated code is NEVER
│   │                              executed** — Stage A validation
│   │                              only, see test_validator.py.
│   │                              POST /{id}/generate-doc targets ONE
│   │                              doc_type per request (readme |
│   │                              architecture_overview | setup_guide
│   │                              | api_reference) — 400 for an
│   │                              unknown doc_type, 404 if repo/
│   │                              analysis missing, 503 if
│   │                              DocGenerationSkipped fires. Always
│   │                              persists; grounding issues are
│   │                              surfaced in the response, not a
│   │                              rejection. **Never writes to any
│   │                              file in the scanned repository.**
│   └── workers/
│       ├── celery_app.py     Celery configured against Redis
│       └── repository_worker.py   same ingest_repository() as a Celery task
│                             (not yet wired as the default path — API
│                             currently uses FastAPI BackgroundTasks for
│                             simplicity; swap one line to go async, see
│                             comment in repositories.py)
│   └── tests/
│       ├── conftest.py                 auto-sets sqlite DATABASE_URL for
│       │                              local test runs, no manual env needed
│       ├── test_repository_service.py  3 passing unit tests (Module 1)
│       ├── test_ast_extractor.py       7 passing unit tests (Module 2,
│       │                              incl. call extraction)
│       ├── test_graph_builder.py       6 passing unit tests (Module 3,
│       │                              mock-client based — see section 2)
│       ├── neo4j_simulator.py          NOT a test file itself — an
│       │                              in-memory Cypher-semantics
│       │                              interpreter for graph_builder.py's
│       │                              write queries AND (as of session 5)
│       │                              hybrid_retriever.py's read queries,
│       │                              used by:
│       ├── test_graph_builder_live_semantics.py  6 passing tests (Module 3)
│       │                              asserting on real resulting graph
│       │                              shape via the simulator above
│       ├── test_graph_service.py       2 passing unit tests (Module 3
│       │                              orchestration + soft-fail path)
│       ├── test_chunker.py             5 passing unit tests (Module 4,
│       │                              real temp files, no mocking needed)
│       ├── test_embedder.py            7 passing unit tests (Module 4,
│       │                              HashingEmbedder determinism/shape/
│       │                              "similar text scores higher" sanity)
│       ├── test_embedding_service.py   4 passing tests (Module 4) — REAL
│       │                              round trip against Qdrant's local
│       │                              (":memory:") engine, not a mock
│       ├── test_hybrid_retriever.py    8 passing tests (Module 5) — pure
│       │                              build_context() tests + graph_expand()
│       │                              against a real simulated graph +
│       │                              full retrieve() against real Qdrant
│       │                              AND the simulator together
│       ├── test_chat_service.py        11 passing tests (Module 5) — 7
│       │                              pure citation-validation tests, 4
│       │                              orchestration tests with the LLM
│       │                              call mocked (see chat_service.py's
│       │                              module docstring for why that one
│       │                              external call can't get real-engine
│       │                              verification the way Qdrant did)
│       └── fixtures/sample.{py,js,ts}  known-good parse targets,
│                                       including call sites
│       ├── test_security_scanner.py    8 passing tests (Module 6) — REAL
│       │                              semgrep binary against a real
│       │                              fixture repo with planted
│       │                              vulnerabilities, not a mock
│       ├── test_security_agent_service.py  6 passing tests (Module 6) —
│       │                              real scan through the full
│       │                              orchestration + pure validation
│       │                              logic tests
│       └── security_fixtures/vulnerable_repo/app.py,server.js
│                                       hand-built Python + JS files with
│                                       one planted instance of each
│                                       vulnerability category the local
│                                       ruleset covers, plus safe functions
│                                       that must NOT trigger any finding —
│                                       kept OUT of tests/fixtures/ (not
│                                       tests/fixtures/security_fixtures/)
│                                       specifically so it doesn't get
│                                       swept into the unrelated
│                                       multi-language-fixture walk other
│                                       tests do over that whole directory
│                                       (this exact coupling bug happened
│                                       once already this session — fixed
│                                       by moving the directory, not by
│                                       special-casing the other test)
│       ├── test_architecture_analyzer.py  10 passing tests (Module 7) —
│       │                              REAL data throughout: existing
│       │                              multi-language fixtures AND
│       │                              self-analysis of this project's own
│       │                              backend source (asserts real,
│       │                              previously-known layers/edges)
│       ├── test_architecture_agent_service.py  3 passing tests (Module 7)
│       │                              — persistence + empty/None-symbols
│       │                              edge cases
│       ├── test_test_coverage_analyzer.py  8 passing tests (Module 8) —
│       │                              REAL data, incl. self-analysis
│       │                              finding a genuine, previously-
│       │                              undocumented gap in THIS project's
│       │                              own test suite (see session 9)
│       ├── test_test_validator.py      9 passing tests (Module 8) — REAL
│       │                              Tree-sitter parsing throughout,
│       │                              incl. both required negative-path
│       │                              demos (syntactically broken test,
│       │                              test referencing a nonexistent
│       │                              function) — this is the safety-
│       │                              relevant validator, held to the
│       │                              same real-verification bar as
│       │                              Qdrant/Semgrep despite having no
│       │                              external tool to test against
│       ├── test_test_generator.py      2 passing tests (Module 8) — LLM
│       │                              call mocked (same as
│       │                              test_chat_service.py's pattern)
│       ├── test_testing_agent_service.py  5 passing tests (Module 8) —
│       │                              real source-reading + real Stage A
│       │                              validation, only the LLM call
│       │                              mocked; proves a rejected
│       │                              generated test genuinely isn't
│       │                              persisted, not just returned
│       ├── test_doc_generator.py       11 passing tests (Module 9) — 7
│       │                              for the grounding checker (PURE,
│       │                              real-tested, both required
│       │                              negative-path demos: fabricated
│       │                              file + fabricated symbol), 4 for
│       │                              generation orchestration (LLM
│       │                              mocked)
│       ├── test_documentation_agent_service.py  6 passing tests
│       │                              (Module 9) — real context
│       │                              gathering (README reading, symbol
│       │                              grouping), only the LLM mocked
│       ├── test_performance_analyzer.py  16 passing tests (Module 10) —
│       │                              HAND-COMPUTED expected complexity
│       │                              values (not just "doesn't crash"),
│       │                              incl. the arithmetic-vs-logical
│       │                              binary_expression distinction and
│       │                              self-analysis locking in a known
│       │                              real complex function
│       └── test_performance_agent_service.py  3 passing tests (Module
│                                       10) — persistence + clean-code/
│                                       empty-symbols edge cases
│
└── frontend/
    ├── package.json / vite.config.ts / tailwind.config.js / tsconfig.json
    ├── Dockerfile
    └── src/
        ├── main.tsx / App.tsx
        ├── types/repository.ts
        ├── services/api.ts        axios client (create/list/get repository)
        └── pages/RepositoriesPage.tsx   submit URL, poll list every 3s,
                                          shows status badges + error messages
```

### Deliberately NOT built yet (per architecture doc §36, "what not to build initially")
2 of the 7 agents (Review — Security, Architecture, Testing[Stage A],
Documentation, and Performance Agents are done), Stage B of the
Testing Agent (real sandboxed execution of generated tests — a
deliberate scope boundary, not an oversight, see session 9 notes), the
LangGraph orchestrator (not needed yet with five independent
agents — see session 6/8/9/10/11 notes), validation layer beyond each agent's
own output-level checks, health-score dashboard, graph visualization (the
Architecture Agent's Mermaid output isn't rendered anywhere in the
frontend yet — Phase 9's job), Kubernetes, Java support (Python/JS/TS
only per MVP scope), INHERITS relationships (class inheritance is parsed
by the
grammars but not yet extracted as a symbol — see gaps below).

---

## 3. How To Resume This Project Yourself

```bash
cd backend && pip install -r requirements.txt
export DATABASE_URL="sqlite:///./dev.db"
uvicorn app.main:app --reload
# in another terminal
cd frontend && npm install && npm run dev
```
Or `docker compose up --build` for the full stack with real Postgres/Neo4j/Qdrant.

Run tests: `cd backend && pytest`

---

## 4. Next Immediate Step: Phase 7 continued — Review Agent (sixth of seven)

**First, close out three loose ends from Phases 4-6** (unchanged for six
sessions now — still open, still small, do before or in parallel):
- **Neo4j**: still never verified against a live instance in any session
  (sessions 3-11, same result each time — no Docker, no apt package,
  JVM-based service outside the allowed network here). `tests/neo4j_simulator.py`
  gives real confidence in the *logic* (including read/traversal queries as
  of session 5), not in real Cypher/Neo4j compatibility. If you have Docker
  access, this is still the single most important thing to verify.
- **Real embedding + LLM quality**: `OpenAIEmbedder` and every LLM call
  behind `app/agents/llm_client.py` (used by `chat_service.py`,
  `test_generator.py`, `doc_generator.py`) are written but never exercised
  against a live API in any session (no `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`
  configured here, and `api.openai.com` isn't network-reachable either
  way). The Review Agent below will very likely need an LLM (unlike the
  Architecture/Performance Agents) — worth fixing first if you have either
  key, since it'll be a fourth module riding on this same unverified path.
- Optional/cheap: INHERITS relationships (still not done — Tree-sitter
  exposes the data, `ast_extractor.py` doesn't walk it yet).
- **From session 9, still worth acting on**: self-analysis found this
  project's own `clone_repository`, `scan_repository`, `ingest_repository`,
  and `run_code_intelligence` have zero direct pytest coverage (verified
  only via live HTTP checks across many sessions). Writing real unit tests
  for these (a temp git repo fixture, not a live GitHub clone) would close
  a genuine gap in this project's own test suite.

**Sessions 6, 8, 9, 10, and 11 each completed one agent** (Security,
Architecture, Testing[Stage A], Documentation, Performance — see their
notes above), each demoing real output against a real repo, satisfying
the "do not move to the next agent until..." condition each time. Move
to the sixth (and per architecture doc §15-21, LAST individually-scoped)
agent now.

**Review Agent** (architecture doc §21), in order:

1. Architecture doc §21 frames this as acting "like a senior developer,"
   evaluating readability, maintainability, naming, complexity, error
   handling, design patterns, SOLID principles, and duplication — a much
   fuzzier brief than any prior agent's. Some of this overlaps with the
   Performance Agent's already-computed metrics (complexity, size) —
   reuse `app.agents.performance_analyzer.compute_complexity` rather than
   recomputing it; don't duplicate that work a second time in this agent
   the way the LLM-call pattern was duplicated three times before
   session 10's refactor.
2. **This agent almost certainly needs an LLM** — "is this naming clear,"
   "does this violate single-responsibility" aren't mechanically
   checkable the way cyclomatic complexity is. Use
   `app/agents/llm_client.py` from the start (don't write a fourth
   near-copy of the pattern — extract to shared code has already
   happened once, so there's no excuse to duplicate it a second time
   after that lesson).
3. **Every finding must point to a specific file/line/code snippet with a
   concrete reason and recommendation** — architecture doc §21 explicitly
   rules out vague output like "your code can be improved." This is a
   grounding problem again, structurally similar to the Documentation
   Agent's: have the LLM cite exact file:line spans for each finding, and
   validate those spans actually correspond to something real in
   `RepositoryAnalysis.symbols` before persisting (reuse or closely mirror
   `chat_service.py`'s citation-validation pattern rather than inventing a
   fourth grounding mechanism from scratch — this project now has three:
   `chat_service.py`'s `[SOURCE: ...]` markers, `doc_generator.py`'s
   backtick-wrapped mentions, and `test_validator.py`'s Stage A checks;
   look at what they share before writing a new one).
4. Persist as `Finding` (same table as Security/Performance — a
   file/line-scoped review comment with a category/severity fits that
   shape, not `GeneratedArtifact`).
5. On-demand or chained? An LLM call is involved (see point 2), so lean
   toward on-demand like the Security/Testing/Documentation Agents —
   but if the review can be scoped per-file rather than per-repo (mirroring
   the Testing Agent's per-function and Documentation Agent's
   per-doc-type scoping), that's probably the right granularity here too,
   for the same cost/latency reasons.
6. Tests: the grounding/citation-validation piece is pure logic and gets
   real test coverage (same standard as `test_validator.py`/
   `doc_generator.check_grounding`'s tests) — mock only the LLM call
   itself. Include at least one required negative-path demo: an
   LLM-claimed finding whose file/line doesn't correspond to anything
   real, and confirm it's dropped rather than trusted, same bar every
   prior grounding mechanism was held to.

**After the Review Agent, all seven individually-scoped agents from
architecture doc §15-21 are done.** At that point, reconsider whether the
LangGraph orchestrator (mentioned in the original plan, not built —
sessions 6/8/9/10/11 each independently concluded it wasn't needed yet
with only one new agent at a time) is worth adding now that there are
six-going-on-seven agents that could plausibly run together on one
request, or whether the existing pattern (each agent's own service module,
called individually by whichever endpoint needs it) has scaled fine
without one. Don't add LangGraph reflexively just because the original
plan mentioned it — decide based on whether the existing pattern is
actually straining, the same "decide deliberately, don't default" standard
every agent's on-demand-vs-chained question was held to.

Do **not** start Phase 8 (the repo-wide Validation Layer, architecture doc
§23 — distinct from each agent's own output-level checks already built)
until the Review Agent demos a real finding with a validated file/line
citation against a real repo, AND demos the grounding mechanism actually
rejecting a fabricated one — same bar every prior agent met.

---

## 5. How To Continue With Other AI Tools

This project is intentionally modular so different tools can pick up
different phases. Use whichever of these you have available.

### A. Claude Code (recommended for backend/infra phases 3–8)
Best for: multi-file backend work, running tests, iterating against a real
Docker Compose stack.

Prompt to paste into Claude Code, run from inside `devlens-ai/`:
```
Read docs/PROGRESS.md and README.md first. Modules 1-10 (Repository Manager,
Tree-sitter, Neo4j graph, Qdrant semantic search, RAG chat, Security Agent,
Architecture Agent, Testing Agent[Stage A only], Documentation Agent,
Performance Agent) are built — do not modify
app/services/repository_service.py, app/analyzer/*, app/knowledge/*,
app/embeddings/*, app/retrieval/*, app/services/chat_service.py,
app/agents/*, app/services/security_agent_service.py,
app/services/architecture_agent_service.py,
app/services/testing_agent_service.py,
app/services/documentation_agent_service.py, or
app/services/performance_agent_service.py's public interfaces without
good reason.

Two things were built but never verified against real external services in
any session so far (no Docker/Neo4j, no OpenAI/Anthropic API keys
configured in that sandbox even though api.anthropic.com was reachable):
1. app/knowledge/graph_builder.py — verify against a real Neo4j via
   `docker compose up neo4j`, using tests/neo4j_simulator.py's asserted
   behavior (tests/test_graph_builder_live_semantics.py,
   tests/test_hybrid_retriever.py) as the spec for what a live database
   should also produce.
2. app/embeddings/embedder.py's OpenAIEmbedder AND every LLM call behind
   app/agents/llm_client.py (shared by chat_service.py, test_generator.py,
   doc_generator.py) — if you have API keys, set them in .env, re-run
   analysis + chat + test-generation + doc-generation on a real repo, and
   confirm real quality. The Review Agent you're about to build will very
   likely need this same LLM path (a fourth module riding on it) — worth
   fixing first if you can.

Also worth knowing: app/agents/security_scanner.py runs semgrep via
subprocess. `pip install -r requirements.txt` should put it directly on
PATH — an earlier session (6) misdiagnosed an install failure as a
sandbox-specific PyJWT conflict and routed around it with a separate venv;
the real cause (session 7) was this project's own pydantic/uvicorn pins
being too old for semgrep's `mcp` dependency, since fixed. If
`pytest tests/test_security_scanner.py` fails with "semgrep binary not
found", do a full from-scratch `pip install -r requirements.txt` and read
the actual resolver error before assuming a sandbox quirk — don't repeat
that mistake.

Also: session 9's Testing Agent found a real, previously-undocumented gap
in THIS project's own test suite — clone_repository, scan_repository,
ingest_repository, and run_code_intelligence (core Module 1/3 functions)
have zero direct pytest coverage, verified only via live HTTP checks
across many sessions. Writing real unit tests for these (a temp git repo
fixture, not a live GitHub clone) is worthwhile, low-risk work if you have
spare time.

Then implement the Review Agent (sixth of seven — Security, Architecture,
Testing[Stage A], Documentation, and Performance are done) exactly as
scoped in docs/PROGRESS.md section 4. Unlike the Performance Agent, this
one almost certainly needs an LLM (readability/naming/SOLID-principle
judgment isn't mechanically checkable) — use the shared
app/agents/llm_client.py from the start, don't write a fourth near-copy
of that pattern (it was already extracted once specifically to prevent
this). Every finding must cite a specific file/line and be validated
against RepositoryAnalysis.symbols before persisting — this project now
has three different grounding mechanisms (chat_service.py's [SOURCE: ...]
markers, doc_generator.py's backtick-wrapped mentions, test_validator.py's
Stage A checks); look at what they share before inventing a fourth one
from scratch. Persist as Finding (same table as Security/Performance).
Decide deliberately whether this is on-demand or chained, and at what
granularity (per-repo vs per-file, mirroring the Testing/Documentation
Agents' per-item scoping). Get real test coverage on the grounding logic
specifically (mock only the LLM call), including a required negative-path
demo: a fabricated file/line citation that gets correctly dropped, not
trusted. Demo a real finding against a real repo. This is the last of the
seven individually-scoped agents from architecture doc §15-21 — once it's
done, read docs/PROGRESS.md section 4's note about whether the LangGraph
orchestrator is actually needed yet before adding it reflexively, and
consider whether Phase 8's repo-wide validation layer (distinct from each
agent's own output-level checks) is the more valuable next step. Update
docs/PROGRESS.md's status table and file map.
```

### B. Cursor / Windsurf (good for frontend dashboard, Phase 9)
Open the `frontend/` folder. Prompt:
```
This is DevLens AI, an existing Vite + React + TS + Tailwind app (see
src/pages/RepositoriesPage.tsx for the existing pattern: axios calls to
/api, polling for status). Build the repository detail page at
src/pages/RepositoryDetailPage.tsx with tabs for Overview / Security /
Architecture / Testing / Performance / Documentation / Chat / Graph,
matching the dashboard mockup in the architecture doc (health score,
findings counts, tech stats). Wire routing with react-router-dom (already
a dependency). Leave existing files' exports unchanged so RepositoriesPage
keeps working.
```

### C. ChatGPT / any chat LLM (good for the research/evaluation writeup, Phase 10)
Prompt:
```
I'm building DevLens AI, a repository-aware RAG + multi-agent code analysis
platform (architecture: Tree-sitter AST -> Neo4j graph + Qdrant vectors ->
hybrid retrieval -> LangGraph agents -> evidence validation -> Postgres ->
React dashboard). I need to design an evaluation methodology for my
research report covering: retrieval Recall@K, answer groundedness,
hallucination rate, and per-agent precision/recall/F1 against a labeled set
of known vulnerabilities. Propose a concrete experimental protocol,
including which open-source repos to use as benchmarks and how to construct
ground-truth labels without excessive manual annotation.
```

### D. Any AI coding tool — generic per-module prompt template
For any phase you haven't started, this template works with almost any
tool (Claude Code, Cursor, Copilot Workspace, Devin, etc.):
```
Project: DevLens AI (repo attached / in this workspace).
Read docs/PROGRESS.md for full context — do not re-plan the architecture,
it's fixed. Implement ONLY [Phase N: <name>] as scoped in docs/PROGRESS.md.
Do not touch files belonging to already-completed phases listed in
docs/PROGRESS.md section 2 unless a bug there is blocking your phase.
When done, update docs/PROGRESS.md's status table and "what's implemented"
section to reflect the new state, so the next session/tool has an accurate
handoff.
```

**Golden rule for every handoff**: whichever tool works on this next should
update this file's status table before stopping. That's what keeps this
resumable across sessions and tools.

---

## 6. Standalone Fallback: Build DevLens AI From Scratch, By Module

If you want to hand the *entire* project (not just the next phase) to a
single AI tool/session as one big prompt, use this — it reproduces the
module boundaries from the architecture doc so the tool builds it
incrementally instead of dumping 10k lines at once:

```
Build "DevLens AI": a repository-aware code intelligence platform that
converts source code into structured knowledge, indexes it, retrieves
relevant context, and lets specialised AI agents reason over it with
evidence-backed answers. Build it as a set of independent modules, in this
exact order, and get each one fully working (with a smoke test against a
real small public GitHub repo) before starting the next:

MODULE 1 — Repository Manager: FastAPI + SQLAlchemy + Postgres. Endpoint
POST /repositories accepts a GitHub URL, clones it (GitPython), scans files
skipping .git/node_modules/venv/__pycache__/dist/build, detects languages
(Python/JS/TS for MVP) by extension, detects frameworks/package managers/
entry points, stores repository + repository_analyses (with commit_hash)
tables in Postgres. Return 202 with repository_id, poll via GET.

MODULE 2 — Code Parsing Engine: Tree-sitter parsing of every source file
into a common AST representation: {type, name, file, line_start, line_end,
parameters}, covering classes/functions/methods/imports/decorators.

MODULE 3 — Relationship Extraction + Neo4j: extract IMPORTS/CALLS/CONTAINS/
INHERITS/IMPLEMENTS/USES/DEFINES relationships from the AST and write them
into a Neo4j graph rooted at (:Repository)-[:CONTAINS]->(:File)-[:DEFINES]->
(:Function/:Class).

MODULE 4 — Code Chunking + Embeddings + Qdrant: chunk code by semantic unit
(function/class/method, not fixed character count), embed each chunk, store
in Qdrant with metadata (repository_id, file, symbol, type, language,
start_line, end_line).

MODULE 5 — Hybrid Retrieval + RAG Chat: given a natural-language question,
run both vector search (Qdrant) and graph traversal (Neo4j), merge into a
single context, send to an LLM, and return an answer with a "Sources:
file:line" list. Every claim must be traceable to a real file/line.

MODULE 6 — Multi-Agent System (LangGraph): build a Security Agent first
(wrap Semgrep/Bandit/Gitleaks output, don't rely purely on LLM judgment),
then Architecture Agent (Neo4j+AST -> Mermaid diagram), then Testing Agent
(find untested functions, generate pytest/jest tests, run them sandboxed —
never execute generated code directly on the host), then Documentation,
Performance, and Code Review agents. Add one agent at a time.

MODULE 7 — Evidence Validation Layer: before persisting any agent finding,
check that the referenced file/line/symbol/relationship actually exists in
the AST/Neo4j data; reject findings that don't validate.

MODULE 8 — Dashboard: React + TypeScript + Tailwind. Repository submission
screen, overview with health score, per-agent findings tabs, code explorer,
knowledge graph visualization, and a chat UI with source citations.

Constraints: keep the LLM as the reasoning layer on top of deterministic
parsing/graph/vector data, never as the sole source of truth. Enforce an MVP
repo size limit (~10,000 files). Use Docker Compose for postgres/redis/
neo4j/qdrant. After each module, run a smoke test end-to-end against a real
small public repo (e.g. octocat/Hello-World or a slightly larger real
project) and show the output before moving to the next module.
```

---

## 7. Known Gaps / Things To Watch

- API currently runs ingestion via FastAPI `BackgroundTasks`, not Celery —
  fine for demo repos, will block the request worker under load. Wire the
  `run_ingestion_task.delay()` Celery path (already written) before using
  large repos.
- No Alembic migrations yet — tables are created via
  `Base.metadata.create_all()`. Add Alembic before the schema is considered
  stable (Phase 3+ will add columns/tables).
- No auth/user model yet — architecture doc mentions a `users` table but it
  wasn't in MVP scope; add before any multi-tenant deployment.
- `requirements.txt` includes `neo4j`, `qdrant-client`, `openai` etc. — as
  of session 4, `qdrant-client` (and its local in-memory mode) is
  genuinely exercised by tests; `neo4j` and `openai` are imported and
  exercised in *logic* but never against their real remote services in
  this sandbox (no live Neo4j, no network access to api.openai.com).
- `RepositoryAnalysis.symbols` stores the full symbol list as one JSON blob.
  Fine for MVP-sized repos (Flask's 2270 symbols serialized without issue),
  but a very large repo (near the 10,000-file MAX_REPO_FILES ceiling) could
  produce a symbols blob large enough to be worth moving to a dedicated
  `symbols` table with proper indexing — not urgent, but flag if a demo repo
  feels slow to load on the `/analyses/latest` endpoint.
- `tree-sitter-languages` (bundled multi-grammar package) is INCOMPATIBLE
  with `tree-sitter>=0.22` — do not add it back. Use the per-language
  packages already pinned in requirements.txt. See section 2 for details.
- **The Neo4j graph builder (Module 3) has never run against a live Neo4j
  instance, in any session.** No Docker is available in this sandbox and
  Neo4j isn't in Ubuntu's standard apt repos (checked again in session 4).
  Session 4 upgraded verification from "mock that counts calls"
  (`tests/test_graph_builder.py`) to "in-memory interpreter that actually
  implements the MERGE/MATCH semantics and produces a real resulting graph"
  (`tests/neo4j_simulator.py` + `tests/test_graph_builder_live_semantics.py`)
  — meaningfully stronger, but still not a real Neo4j server, so it can't
  catch real Cypher syntax errors or version-specific quirks. This is
  still the single highest-priority thing to verify before trusting the
  graph for Phase 6 retrieval. See section 4's first bullet for how.
- CALLS relationship resolution is name-only (see `graph_builder.py`'s
  module docstring) — `obj.save()` links to *every* `save` method/function
  in the repo, not just the "correct" one. This is a known, documented MVP
  simplification, not a bug — proven (not just described) by
  `test_ambiguous_callee_name_fans_out_to_all_matches`. Every such
  relationship is tagged `match_type: "by_name"` in Neo4j so this is
  visible/filterable later.
- INHERITS relationships are not extracted yet — Tree-sitter's grammars
  expose the data (`class_definition.superclasses` in Python,
  `class_heritage` in JS/TS) but `ast_extractor.py` doesn't walk it. Small
  addition, noted in section 4.
- Module-level calls (a call expression sitting directly in a file's
  top-level scope, not inside any function/method) are silently skipped by
  `graph_builder.py`'s `build_write_plan()` rather than creating a
  synthetic "module" caller node — see `test_module_level_call_with_no_enclosing_function_is_skipped`.
  Revisit if module-level orchestration code turns out to matter for a
  specific repo you're analyzing.
- **`OpenAIEmbedder` (`app/embeddings/embedder.py`) has never been called
  against a real API, in any session.** `api.openai.com` is outside this
  sandbox's allowed network domains and no `OPENAI_API_KEY` is configured.
  Every test, and the one live pipeline run in session 4, used
  `HashingEmbedder` — a deterministic offline bag-of-words fallback that's
  explicitly NOT semantically meaningful (see its docstring). Search
  *works* end-to-end (verified against real Qdrant), but search *quality*
  for real natural-language queries is unverified until someone with API
  access swaps in a real embedding model.
- Two real bugs were caught and fixed in session 4 specifically *because*
  testing ran against Qdrant's real local engine instead of a mock — worth
  knowing about if similar patterns show up elsewhere: (1) Qdrant point
  IDs must be an unsigned int or valid UUID, a raw hash-hex string is
  rejected; `chunker.py`'s `_chunk_id()` now uses `uuid5`. (2) A naive
  identifier tokenizer that doesn't split `snake_case`/`camelCase` makes
  bag-of-words search useless for code (`authenticate_user` shares no
  tokens with a query for "authenticate"); `embedder.py`'s `_tokenize()`
  now splits on both boundaries, case-sensitively, before lowercasing.
- The Qdrant collection (`devlens_code_chunks` in
  `app/services/embedding_service.py`) is a single global collection with
  a `repository_id` payload filter, not one collection per repository —
  this was the "simpler, recommended for MVP" option from the original
  Phase 5 plan. Verified to correctly scope search results per-repository
  (`test_run_embedding_scopes_results_to_repository`), but revisit if a
  huge number of repositories ever makes one shared collection a
  performance concern.
- `run_embedding()` calls `client.ensure_collection()` on every single
  ingestion, which calls `get_collections()` — cheap, but if this ever
  shows up as a bottleneck under load, cache the "collection already
  exists" check instead of re-querying every time.
- **`chat_service.py`'s `_call_llm` has never been exercised against a
  live model, in any session.** `api.anthropic.com` is network-reachable
  from this sandbox (unlike `api.openai.com`), but no `ANTHROPIC_API_KEY`
  is configured, so every test and every live HTTP check either mocked
  this call or short-circuited around it (empty retrieval hits -> early
  return before the LLM is ever called). The citation *validator*
  (`_extract_and_validate_citations`) is thoroughly tested as pure logic;
  what's genuinely unverified is whether a real model reliably produces
  the `Sources:` format the system prompt asks for, and how often the
  validator actually needs to catch a hallucinated citation in practice
  vs. in the specifically-constructed test cases.
- `POST /{id}/chat`'s `503` (LLM unconfigured) path was verified via
  FastAPI's `TestClient` with `answer_question` mocked to raise
  `ChatSkipped`, not via a live server hitting a repo with real retrieval
  hits — every live-server HTTP check in session 5 happened to hit the
  earlier "no retrieval hits at all" path instead (no running Qdrant
  server + `octocat/Hello-World` has no parseable files either way).
  Functionally equivalent code path, but worth a live re-check if you have
  a running Qdrant to get real hits with.
- The graph-expansion side of hybrid retrieval (`graph_expand()` in
  `app/retrieval/hybrid_retriever.py`) inherits Neo4j's unverified-against-
  a-real-database status (see the Neo4j bullet above) — it's tested against
  `tests/neo4j_simulator.py`'s now-extended read-query support, same
  caveat as everything else built on that simulator.
- `hybrid_retriever.py`'s CALLS-neighbor lookup only goes one hop and only
  follows CALLS (not CONTAINS/DEFINES/IMPORTS) — architecture doc §13's
  hybrid retrieval concept doesn't mandate a specific hop count or
  relationship set, this was a deliberate MVP scope cut, not an oversight.
  Revisit if one-hop CALLS context proves insufficient for real questions
  once real LLM verification happens.
- `chat_service.py`'s citation validator requires an **exact** match
  (`file:start-end` string equality) between what the LLM outputs and a
  real `[SOURCE: ...]` marker — no fuzzy matching, no tolerance for the
  LLM reformatting line numbers slightly differently. This is intentional
  (see the module's docstring: "worse to have false confidence in a wrong
  source than no citation"), but means a real model that paraphrases the
  source format instead of copying it verbatim will have its citations
  dropped even if it was "right" in spirit. Worth watching once real LLM
  output is available to inspect.
- **CORRECTED (session 7) — this used to say semgrep needed a
  sandbox-specific isolated venv; that was a misdiagnosis.** The real
  cause was `requirements.txt` pinning `pydantic==2.9.2` and
  `uvicorn==0.30.6`, both incompatible with `mcp` (semgrep's own
  dependency), which is a real bug that would break a clean Docker install
  too — not sandbox-specific at all. Fixed by relaxing those two pins to
  `pydantic==2.13.5` / `uvicorn[standard]==0.53.0`. Verified with a full,
  real, single-environment `pip install -r requirements.txt` (see session
  7 notes for the whole story). If a future dependency addition produces a
  similarly confusing pip error, do the full from-scratch install and read
  the resolver's actual conflict chain before reaching for a workaround —
  don't repeat this mistake.
- The local security ruleset (`app/agents/rules/security_rules.yaml`) is
  intentionally small (7 rules, 2 languages) — real coverage breadth (SSRF,
  path traversal, insecure deserialization, XSS, etc.) is nowhere near what
  semgrep's actual registry rulesets (`p/security-audit`, `p/owasp-top-ten`)
  would provide, but those require network access to semgrep.dev that
  isn't available in this sandbox. If a deployment environment CAN reach
  semgrep.dev, switching to a registry config is a meaningful quality
  upgrade, not just a nice-to-have — the local rules are a sandbox-driven
  compromise, not the intended long-term ruleset.
- The Security Agent's hardcoded-credential rules use a regex pattern on
  variable names (`API_KEY`, `SECRET_KEY`, etc.) — this will miss secrets
  assigned to unconventionally-named variables and may false-positive on
  test fixtures/examples that intentionally contain fake-looking secrets
  (arguably correct behavior for an MVP scanner, but worth knowing if a
  scanned repo's test suite lights up with findings).
- `run_security_scan()`'s findings are tied to a `RepositoryAnalysis` via
  `analysis_id`, but nothing currently re-validates a finding if the
  underlying file changes between the analysis that findings are attached
  to and a later re-scan — re-running `/analyze/security` creates a fresh
  batch of findings rather than diffing against or superseding the
  previous batch (see `GET /{id}/findings`'s docstring: it deliberately
  returns full history, not just latest). Fine for MVP, but a real product
  would likely want explicit "resolved"/"superseded" states, not just an
  ever-growing list.
- Two agents now exist with genuinely different verification depths for
  the same underlying reason (external tool/service availability in this
  sandbox): Qdrant and Semgrep got real, no-mock end-to-end verification;
  Neo4j and any LLM call did not. Keep this asymmetry in mind when judging
  how much to trust each subsystem — it reflects sandbox constraints, not
  a deliberate difference in how carefully each was built.
- The Architecture Agent's layer-detection keyword map
  (`app/agents/architecture_analyzer.py`'s `_LAYER_KEYWORDS`) is a fixed
  English-language vocabulary (`services`, `controllers`, `models`, etc.)
  — a repo using different naming conventions (non-English directory
  names, an unconventional layout, or a monorepo with deeply nested
  package structures) will fall back to raw parent-directory names
  throughout, which is still honest (no forced/wrong labeling) but less
  informative than true layer detection would be. Extending the keyword
  list is cheap; making the fallback smarter (e.g. clustering by import
  relationships rather than naming) is a bigger lift, not attempted here.
- The Architecture Agent's cross-layer edges inherit the exact same
  by-name CALLS ambiguity as `graph_builder.py` (see that module's own
  gap entry above) — a common method name shared across layers can
  create a cross-layer edge that doesn't reflect a real dependency. Same
  documented tradeoff, same reasoning, now duplicated across two modules;
  worth factoring into a shared helper if a third agent needs the same
  resolution logic.
- The Mermaid diagram's layer nodes have no stable identity across
  re-analyses (`generate_mermaid()` assigns `L0, L1, ...` by alphabetical
  sort order each time) — fine for a single rendered diagram, but if a
  future frontend feature wants to animate/diff a repo's architecture
  changing over time, this would need stable per-layer IDs instead of
  resorting from scratch on every analysis.
- **Stage B of the Testing Agent (real sandboxed execution of generated
  tests) is explicitly NOT built** — this is the single most significant
  scope boundary in Phase 7 so far, stated plainly rather than buried: a
  test that passes Stage A validation has been checked for syntax,
  target-symbol reference, and "looks like a test" — it has NEVER been
  run, so there is no guarantee it actually passes, or even that it
  wouldn't error at import time for a reason Stage A can't catch (a
  missing fixture, a wrong relative import, etc.). Anything downstream of
  `POST /{id}/generate-test` (a future frontend, a future agent) must not
  present Stage-A-passing output as "verified" or "working" — only as
  "passed static checks, not executed."
- `test_coverage_analyzer.py`'s "is this called from a test file"
  detection is name-based only (same category of limitation as
  `graph_builder.py`'s CALLS resolution and `architecture_analyzer.py`'s
  edges) — a function only exercised indirectly (called through a mock,
  invoked only via a pytest fixture that itself isn't named in a direct
  call, or covered by an integration/HTTP-level test that never
  references the function by its Python/JS name at all) will be
  misclassified as untested. This project's own live-HTTP-verified-but-
  not-unit-tested functions (found via self-analysis, see session 9) are
  a real-world example of a *different* kind of gap this same limitation
  would NOT have caught on its own — those functions genuinely have no
  test-file call referencing them, so the detector was right about them,
  but a function covered only by an HTTP-level integration test elsewhere
  could look identically "untested" while actually being reasonably
  covered. Worth remembering when interpreting this agent's output as a
  coverage percentage rather than a list of candidates to review.
- `run_test_generation()` reads source text via a fresh
  `local_path / file` read on every call rather than reusing
  `app.embeddings.chunker.chunk_repository()`'s already-computed chunks —
  minor duplication (both do "read lines `start`–`end` from a file"), not
  a correctness issue, but a candidate for consolidation if a fourth
  agent needs the same source-slicing logic again.
- The Testing Agent's framework-hint detection
  (`testing_agent_service._detect_framework_hint`) is a file-extension
  guess (`pytest` for `.py`, `jest` for `.js`/`.ts`) rather than actually
  checking what test framework the repository uses (e.g. inspecting
  `requirements.txt`/`package.json` for `pytest`/`unittest`/`mocha`/
  `jasmine`). Fine for the MVP's Python/JS/TS scope where pytest and jest
  are reasonable defaults, but a repo using `unittest` or `mocha`
  specifically will get a generated test nudged toward the wrong
  framework's conventions.
- **`doc_generator.py`'s grounding check only catches what the LLM
  bothers to backtick.** The prompt instructs the model to wrap every real
  file/symbol reference in backticks, but nothing stops a model from
  describing a fabricated behavior in plain prose without ever naming a
  specific nonexistent file or function — "the project includes built-in
  rate limiting" with no backticked claim at all would sail through
  ungrounded-mention-free, even if false. This is the same fundamental
  limit as `chat_service.py`'s citation approach (it can only check
  claims that take a checkable form) — worth remembering that
  `fully_grounded: true` means "no checkable claim was found to be
  false," not "every claim in this document is true."
- `check_grounding`'s path-vs-symbol classifier
  (`_looks_like_a_path`/`_KNOWN_FILE_EXTENSIONS`) is a fixed extension
  list — a repo using an unlisted file type (e.g. `.rs`, `.go`, `.java`,
  outside this project's Python/JS/TS MVP scope anyway) would have such
  files' backticked mentions checked against the *symbol* set instead of
  the *file* set, likely misclassifying them as ungrounded even if
  correct. Not a live concern given the MVP's language scope, but worth
  extending the list first if that scope ever grows.
- `run_documentation_generation()` always persists regardless of how
  ungrounded the output is — there's no threshold at which a document
  with, say, 90% fabricated references gets rejected the way the Testing
  Agent's Stage A rejects any unparseable test. This was a deliberate
  choice (see this session's notes: prose grounding is a matter of
  degree, not binary), but means a badly hallucinated document is still
  stored and returned, just with a `grounding` field a caller has to
  actually check rather than being protected from it automatically. A
  future iteration might add a configurable rejection threshold if this
  proves to be a problem once real LLM output is available to observe.
- The `app/agents/llm_client.py` refactor (session 10) centralizes the
  Anthropic API call but not the prompt-engineering patterns around it
  (the "require backticks/[SOURCE: ...] markers so output is mechanically
  checkable" approach is duplicated across chat_service.py's citations,
  doc_generator.py's grounding, and conceptually similar to
  test_validator.py's target-symbol check) — a further refactor extracting
  a shared "grounded-generation" helper is plausible if a fifth or sixth
  agent needs the same pattern again, but wasn't done this session since
  three genuinely different output shapes (chat answer, generated test,
  generated document) made a premature abstraction risk hiding real
  differences between them.
- **The path-mismatch bug from session 11's self-analysis debugging is a
  real, easy-to-repeat footgun, worth flagging explicitly**:
  `analyze_performance(local_path, symbols)` silently produces fewer
  findings (not an error) if `local_path` doesn't match the root the
  `symbols` were extracted relative to — a missing file just causes that
  symbol's complexity check to be skipped (same silent-skip pattern as
  `chunker.py`), so the output still looks plausible (real findings,
  no crash) while being incomplete. This exact mistake was made once
  during this session's own development and only caught by manually
  cross-checking one function's complexity by hand. Any future caller of
  `analyze_performance`/`run_performance_analysis` should double-check
  that `repository.local_path` and `analysis.symbols` genuinely came from
  the same analysis run (they do, via the normal pipeline — this is only
  a risk for someone calling these functions directly/manually, as a
  debugging session might).
- `performance_analyzer.py`'s complexity/size thresholds
  (`LARGE_FUNCTION_LINE_THRESHOLD = 50`, `HIGH_COMPLEXITY_THRESHOLD = 10`)
  are fixed constants with no configurability per repository or language
  — a 50-line threshold that's reasonable for application code may be
  noisy for, say, generated code or test files with long parametrized
  cases (Flask's own test suite is exactly this case — several of the 44
  findings against pallets/flask were large *test* functions, which is
  arguably lower-priority to flag than large production code). Not
  filtering test files out of performance analysis the way
  `test_coverage_analyzer.py` does for coverage was a deliberate scope
  cut (a large test function can still genuinely be worth splitting up),
  but worth knowing when reading the findings against a repo with a big
  test suite.
- Architecture doc §20 lists several other performance signals not
  attempted this session: potential N+1 queries, repeated computation,
  inefficient data structures, and duplicate logic. Complexity and size
  were the two signals with unambiguous, objective definitions
  (McCabe's formula; line count) — the others require either pattern-
  matching against framework-specific idioms (N+1 detection typically
  needs to recognize ORM call patterns) or cross-function comparison
  (duplicate logic), both meaningfully harder problems than what this
  session scoped. A future session could add these incrementally, the
  same "add one agent/signal at a time" discipline this whole phase has
  followed.
