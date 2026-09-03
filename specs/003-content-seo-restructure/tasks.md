# Tasks: Content Restructure & SEO Copy

**Input**: Design documents from `specs/003-content-seo-restructure/` (spec.md, plan.md)

**Tests**: No test tasks — static site. Validation = invariant/fact/keyword/word-count audits described in plan.md.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [x] T001 Capture pre-rewrite invariants (ids, asset srcs, class set) and baseline word count (1,276) for regression comparison

## Phase 2: User Story 1+2 — Narrative restructure & SEO copy (Priority: P1)

- [x] T002 [US1] Rewrite all 8 sections in `site/index.html` per plan: single-purpose sections, deduplicated topics (bandwidth → edge-ai hook; TLE → architecture; docker → testing; duplicate architecture SVG removed), SEO-aware H2s and opening sentences
- [x] T003 [US1] Add `.section-lead` and `.section-sub-block` narrative helper styles to `site/assets/css/layout.css`
- [x] T004 [US2] Rewrite `<title>` and `<meta name="description">` within length budgets; sync og/twitter titles + descriptions and JSON-LD `name`/`description`
- [x] T005 [US2] Tighten verbose paragraphs (two condensing passes) until word count ≤ baseline while keeping every keyword phrase naturally present

## Phase 3: User Story 3 — Zero regression (Priority: P2)

- [x] T006 [US3] Verify: ids/srcs/classes identical to pre-rewrite set; single H1; no duplicate ids; every img keeps alt + width/height; all 36 fact anchors present; all 18 target keywords present; all URLs serve 200
- [x] T007 [US3] Confirm design/JS untouched (only `index.html` + one CSS addition) and report before/after metrics for the owner read-through

## Dependencies

- T002/T004/T005 all land in `site/index.html` (sequential edits within one file)
- T006 regression suite runs after the final copy state

## Implementation strategy

- Full restructure + SEO copy implemented as one pass, tightened iteratively against the
  word-count and fact-anchor gates; final step is the owner's read-through in a browser.
