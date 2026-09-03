# Feature Specification: Content Restructure & SEO Copy

**Feature Directory**: `specs/003-content-seo-restructure`

**Created**: 2026-09-03

**Status**: Draft

**Input**: User description: "Reorganize the contents of every section" + "improve the texts inside for better SEO". Clarifications resolved: full restructure (sections may reorder AND internal blocks may move); wording may be tightened/condensed/merged/re-titled; primary goal is better narrative flow; SEO copy improvement is a secondary goal of the same pass. Constitution principle IV amended (v1.1.0) to authorize this.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One flowing story from problem to proof (Priority: P1)

A first-time visitor (or internship reviewer) reads top to bottom and follows a
single logical arc — the maritime threat, the sensor that sees it, the
constraint that forces edge AI, the system that delivers it, the model that
detects, the console that acts, the engineering quality behind it, and the
outlook. Each section hands off to the next; ideas are not repeated across
sections; every section is balanced (no text-heavy walls, no orphan visuals).

**Why this priority**: The user's stated goal is better narrative flow; the
whole page is the deliverable.

**Independent Test**: Reading the page top-to-bottom without the nav, a new
reader can say what each section's single job is and why the next section
follows; spot-checks confirm no paragraph-level idea appears in two sections.

**Acceptance Scenarios**:

1. **Given** the reorganized page, **When** read top to bottom, **Then** each
   section's content is internally ordered (context → explanation → evidence →
   visual) and hands off to the next section.
2. **Given** the previous page's ideas, **When** audited for duplication,
   **Then** repeated explanations (e.g., the bandwidth bottleneck, the
   high-level architecture diagram, docker/ops proof) appear once, in the
   section where they matter most.
3. **Given** a skim by an evaluator, **Then** headings and first paragraphs of
   each section alone convey the story.

### User Story 2 - Copy optimized for search engines (Priority: P1)

People searching terms like "dark vessel detection", "Sentinel-1 SAR vessel
detection", or "edge AI satellite" can find the page, and search engines can
clearly tell what each part of the page covers. Headings carry the topics, the
first paragraphs state them, the meta description sells the page in one
sentence, and nothing reads like keyword stuffing.

**Why this priority**: The user explicitly asked for SEO-improved texts; this
builds on the image/technical SEO from feature 001.

**Independent Test**: Check the visible text against a target-keyword list:
every major topic keyword appears naturally in a heading or first paragraph;
the page's title and meta description contain the primary phrases within
standard length budgets; content reads naturally to a human.

**Acceptance Scenarios**:

1. **Given** the target keyword list (dark vessel detection, maritime domain
   awareness, Sentinel-1 SAR, SAR vessel detection, edge AI satellite / orbital
   edge computing, YOLOv8, INT8 quantization, ONNX, microservices architecture,
   ground station dashboard, CI/CD), **When** the page text is scanned,
   **Then** each term appears naturally at least once, most within a heading or
   the first ~2 sentences of its section.
2. **Given** the rewritten title and meta description, **When** length is
   measured, **Then** the title ≤ ~70 characters and the description ≤ ~160
   characters, each containing a primary keyword.
3. **Given** a human read, **When** sentences are evaluated for fluency,
   **Then** keywords appear in contextually natural phrasing (no forced lists,
   no repeated exact phrases in adjacent sentences).

### User Story 3 - Every fact survives, everything still works (Priority: P2)

The restructure is a rewrite, not a lossy edit: all numbers, product names,
technologies, ports, endpoints, and the downloadable report remain accurate and
reachable, and the SEO/asset/accessibility guarantees from the earlier features
still hold.

**Why this priority**: Constitution IV (amended) requires truthfulness; features
001–002 must not regress.

**Independent Test**: A "fact anchor" checklist (every statistic, named
technology, port, endpoint, diagram caption, image alt, and the report link) is
verified present and accurate after the rewrite; the previous features' audits
re-pass.

**Acceptance Scenarios**:

1. **Given** the list of fact anchors (6 microservices, 122 tests / 115 passed /
   7 skipped / 0 failed / 60% coverage, 5 pipelines, 75% compression, 4 job
   stages, INT8 = 25% memory / 8-bit weights, ports 8000/8001/8002/8003/8004/8501,
   512×512 .npy tiles, VH polarization, Z1/Z2/Z3, NORAD 39634, Sentinel-1A,
   SatNOGS → Celestrak → cache, Copernicus Data Space Ecosystem, Global Fishing
   Watch, Redis pub/sub, Docker Compose, Streamlit, SGP4, ONNX Runtime,
   GitHub Actions), **When** the new text is checked, **Then** every anchor is
   present with unchanged meaning.
2. **Given** the reorganized markup (moved figures, possibly reordered or
   retitled sections), **When** links, figure ids, nav anchors, scrollspy ids,
   alts, captions, JSON-LD references, and sitemap paths are audited, **Then**
   nothing is broken and every image reference still resolves.
3. **Given** a keyboard/mobile pass, **Then** the page remains navigable,
   headings descend h1 → h2 → h3 without skips, and no horizontal overflow
   appears at 375px.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The page MUST be restructured into a single narrative arc; each of
  the 8 content sections gets a single clear purpose, internally ordered as
  context → explanation → evidence → visual, with explicit handoffs between
  sections.
- **FR-002**: Repeated ideas MUST be consolidated to one place: the bandwidth
  bottleneck belongs with the edge-computing motivation; the architecture
  diagram and docker/runtime proof appear once each; TLE/zone material sits with
  the services they illustrate.
- **FR-003**: Every section's H2 MUST be reworded to be short, scannable, and
  naturally keyword-bearing; section text and H3s MUST echo the same topic
  without repeating exact phrases.
- **FR-004**: Every section MUST open with 1–2 sentences that state the topic
  and include its primary search phrase; verbose paragraphs MUST be condensed
  and merged where the same idea is explained twice.
- **FR-005**: The page `<title>` and `<meta name="description">` MUST be
  rewritten (title ≤ ~70 chars, description ≤ ~160 chars) with primary keywords
  kept front-loaded and truthful.
- **FR-006**: JSON-LD `name`/`caption` fields and figure captions MUST be
  updated to stay consistent with any reworded headings, and alt text MUST stay
  descriptive and unique.
- **FR-007**: All fact anchors (spec US3 acceptance 1) MUST remain present and
  accurate; no claim may change meaning.
- **FR-008**: Section ids, nav links, scrollspy id list, figure ids, and any
  anchor references MUST be updated consistently — no dead anchors, one
  `id="main"`, single H1, correct heading hierarchy.
- **FR-009**: The rewrite MUST NOT add new assets, dependencies, or page
  weight; the 001 SEO/asset audits and 002 UI checks MUST still pass, and the
  report PDF MUST stay downloadable.
- **FR-010**: The writing MUST avoid keyword stuffing: no identical keyword
  phrase more than once per two adjacent sentences, no forced keyword lists.

### Key Entities *(include if feature involves data)*

- **Narrative arc**: ordered list of section purposes with handoff sentences.
- **Fact anchors**: the immutable set of claims/numbers/terms from US3/1.
- **Target keywords**: the search phrases to weave in naturally (US2/1).
- **Section identity**: section id ↔ heading ↔ nav label ↔ first paragraph ↔
  figures ↔ JSON-LD/sitemap caption consistency map.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of fact anchors present and accurate after the rewrite.
- **SC-002**: ≥ 90% of target keywords appear in visible text, each in natural
  phrasing; ≥ half appear in a heading or first paragraph.
- **SC-003**: No idea-level duplication: an audit of the 5 known repeated
  topics (bandwidth bottleneck, architecture diagram, docker runtime proof,
  INT8 compression, microservices description) finds each addressed once.
- **SC-004**: Total visible word count is not higher than today's baseline and
  ideally ≥ 10% lower, despite added SEO phrasing.
- **SC-005**: Title/meta description lengths within budget; single H1; heading
  hierarchy valid; zero broken anchors or image references; audits of features
  001 and 002 re-pass unchanged.

## Assumptions

- This feature rewrites page copy and structure only within `site/`; images,
  PDF, robots/sitemap paths, and the design/UI system are unchanged.
- Primary search audience is technical (engineers, space/maritime researchers,
  internship reviewers); tone stays professional, not marketing-fluffy.
- Keywords are derived from the page's real topics (no invented topics);
  density targets favor natural language over ranking games.
- Nav labels may be reworded if headings change, but the section count stays 8
  and the single-page architecture stays.
- English copy only; the report PDF content is out of scope.
- The owner (FrancKINANI) approves all reordering and rewording via the plan
  validation step before implementation.
