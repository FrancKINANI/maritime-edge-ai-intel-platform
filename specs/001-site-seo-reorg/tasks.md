# Tasks: SEO Image Optimization & Site Reorganization

**Input**: Design documents from `specs/001-site-seo-reorg/` (plan.md, spec.md, research.md, quickstart.md)

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md

**Tests**: No test tasks — the static site has no automated suite (constitution §Change Scope). Validation tasks run the quickstart.md reference audits instead.

**Organization**: Tasks are grouped by user story to enable independent verification of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1 SEO, US2 visitor experience/integrity, US3 maintainability)
- Include exact file paths in descriptions

## Path Conventions

- Feature area: `site/` only (repository root otherwise untouched)
- New asset root: `site/assets/{css,js,img/{diagrams,screenshots,brand},doc}`
- Docs: `specs/001-site-seo-reorg/*.md`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the target folder skeleton and confirm the image tooling works.

- [x] T001 Create empty target folders: `site/assets/css`, `site/assets/js`, `site/assets/img/diagrams`, `site/assets/img/screenshots`, `site/assets/img/brand`, `site/assets/doc`
- [x] T002 Verify isolated Pillow tooling runs (`uv run --with pillow python -c "import PIL; print(PIL.__version__)"`) without touching pyproject.toml/uv.lock

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Produce ALL final optimized image files and crawler files in their final locations under `site/assets/`. The old flat `site/images/` tree stays untouched until Phase 4 cleanup so nothing is ever in a broken state. ⚠️ No user-story work can finish before this phase.

- [x] T003 [P] Re-encode 4 screenshots (`ksf-space-maritime-edge-ai-intel-platform-{docker-monitoring,dashboard-upload,dashboard-satellite-query,dashboard-monitoring-events}.png`, 1902×1062) → JPEG, max width 1600, quality ~82 tuned per file to ≤250 KB, into `site/assets/img/screenshots/*.jpg`
- [x] T004 [P] Optimize `ksf.space-logo-high.png` (435×420, 140 KB) → same filename into `site/assets/img/brand/`, resized to ≤220px, PNG with alpha, ≤25 KB
- [x] T005 [P] Recompress 3 SAR JPEGs (`…-sar-{single-vessel,vessel-detection,multi-vessel-detection}.jpg`, 640×640) at q78–82 into `site/assets/img/screenshots/` (same names)
- [x] T006 [P] Move the 6 `.svg` diagrams AND their 6 `.drawio` partners from `site/images/` to `site/assets/img/diagrams/` (names unchanged)
- [x] T007 [P] Move `site/images/rapport_stage.pdf` → `site/assets/doc/rapport_stage.pdf`
- [x] T008 [P] Create `site/robots.txt` (User-agent: * / Allow: / + absolute Sitemap URL)
- [x] T009 [P] Create `site/sitemap.xml` listing the page + `<image:image>` entries for the 13 content images (final paths from T003–T006), all under the canonical base URL `https://franckinani.github.io/maritime-edge-ai-intel-platform/`

**Checkpoint**: `site/assets/` contains the complete, final, optimized asset set; old `site/images/` still intact.

---

## Phase 3: User Story 1 - Search engines understand and rank the page and images (Priority: P1) 🎯 MVP

**Goal**: index.html exposes correct SEO: descriptive filenames/alts/captions wired to the new paths, complete head metadata, structured data, lazy loading and dimensions.

**Independent Test**: quickstart §1 reference audit — zero missing image refs, every `<img>` has alt + width/height; quickstart §3 head spot-checks pass.

### Implementation for User Story 1 (all edits to `site/index.html`; sequential, same file)

- [x] T010 [US1] Replace the `<head>` block: keep charset/viewport/description/keywords/author/og:title/og:description; add `<link rel="canonical">`, `og:url`, `og:type=website`, `og:locale`, `og:image` (absolute URL to the new docker-monitoring.jpg), `og:image:alt`, `twitter:card=summary_large_image`, `theme-color`, and one JSON-LD `@graph` script (WebSite + Organization KSF Space Foundation + ImageObject entries for key diagrams/screenshots)
- [x] T011 [US1] Point the nav logo `<img>` to `assets/img/brand/ksf.space-logo-high.png` with width/height + descriptive alt
- [x] T012 [US1] Restructure the hero visual: keep `.hero-image-placeholder` wrapper, update src to `assets/img/diagrams/…architecture.svg`, add `fetchpriority="high"`, `decoding="async"`, alt, and keep `loading="eager"`
- [x] T013 [US1] Convert challenge + SAR section image blocks to `<figure class="image-placeholder">` + `<figcaption>`: update srcs to `assets/img/screenshots/…sar-*.jpg` and `assets/img/diagrams/…pipeline-comparison.svg`, add width/height (640×640 for jpg), refined unique alts, `loading="lazy"` + `decoding="async"`, preserve `onerror`/`.placeholder-fallback` for the SVG
- [x] T014 [US1] Convert Edge AI + Architecture section figures (`architecture.svg`, `data-flow.svg`, `zone-classification.svg`, `docker-monitoring.jpg`): new paths, width/height (1600×893 for jpg), alts, lazy-loading, preserved fallbacks
- [x] T015 [US1] Convert Detection + Dashboard + Testing section figures (`sar-vessel-detection.jpg`, `tle-fallback.svg`, 3 dashboard-*.jpg, `ci-pipeline.svg`): new paths, width/height, alts, lazy-loading, preserved fallbacks
- [x] T016 [US1] Wrap the hero + all 8 `<section>`s in `<main>`; keep every section `id`, nav anchor, heading, statistic, and copy byte-identical; keep footer landmark

**Independent test result**: quickstart §1 (a)(b) pass; §3 head checks pass; page content unchanged.

---

## Phase 4: User Story 2 - Visitors get a fast, tidy, unbroken site (Priority: P1)

**Goal**: old flat images removed only after every reference points at the new tree; byte budget verified; nothing broken.

- [x] T017 [US2] Delete the now-unreferenced old tree `site/images/` (all 17 files) once `rg -l "images/" site/index.html site/README.md` returns nothing except the PDF/doc references; leave `.nojekyll`
- [x] T018 [US2] Run quickstart §1c byte audit: total raster ≤ ~900 KB, no raster > 250 KB; re-encode any overshooting JPEG at lower quality/width and repeat until passing
- [x] T019 [US2] Diff content integrity: extract visible text from HEAD:site/index.html vs new `site/index.html` (strip tags/attrs) and confirm every heading, paragraph, statistic (6/122/5/75%, 115/7/0/60%), and the report filename appear identically

**Independent test result**: quickstart §1c and §5 pass; local serve (quickstart §2) shows all images rendering.

---

## Phase 5: User Story 3 - The author can maintain the site without guesswork (Priority: P2)

**Goal**: styles and script modularized; single maintenance guide matches the new reality.

- [x] T020 [US3] Split `site/style.css` verbatim by its `/* ===== … ===== */` sections into `site/assets/css/base.css` (reset/tokens/base elements), `site/assets/css/layout.css` (nav/hero/sections/content-grid/footer/download), `site/assets/css/components.css` (buttons/cards/callouts/placeholders/pills/tables/modes/testing/conclusion), and `site/assets/css/responsive.css` (all three `@media` blocks, loaded last); delete `site/style.css`
- [x] T021 [US3] Verify CSS split: selector count (`{`) of the 4 files equals the original file's count (compare against `git show HEAD:site/style.css`), no rule text altered
- [x] T022 [US3] Move the inline `<script>` from `site/index.html` to `site/assets/js/main.js` verbatim and load it with `defer`; remove the inline block
- [x] T023 [US3] Update `site/index.html` `<head>` stylesheet links to the 4 css files (order: base → layout → components → responsive)
- [x] T024 [US3] Rewrite `site/README.md`: new folder tree, image naming rules, accurate asset inventory tables (diagrams + screenshots, no stale ".png capture needed" rows), robots/sitemap note, draw.io workflow, and report location

**Independent test result**: quickstart §2 render pass (styles + JS work from split files); README table matches `find site/assets -type f` output exactly.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: final spec-kit convergence + audit.

- [x] T025 Run the full quickstart.md audit suite (§1 a–d, §2 note) and fix any failure
- [x] T026 Run `$speckit-converge`-style gap check against spec.md (FR-001..FR-012, SC-001..SC-006) and report the result in the completion summary
- [x] T027 Summarize the diff for the user: files changed/moved/added, before→after image bytes, and how to preview (`python3 -m http.server 8000 --directory site`)

---

## Dependencies

- Phase 1 → Phase 2 → (Phase 3 + Phase 5 css/js can proceed in parallel once Phase 2 done; Phase 4 cleanup requires Phase 3)
- T016 (US1 markup) must precede T020/T022 css/js edits only in final state; both touch `site/index.html`, so execute sequentially: Phase 3 then Phase 5.
- T017 requires T010–T015 (all src refs migrated).

## Implementation strategy

- MVP = Phase 1–3 (US1): SEO-correct page with optimized images in new folders while old images still exist — independently verifiable via quickstart §1/§3.
- Then Phase 4 (US2): cleanup + budgets + integrity.
- Then Phase 5 (US3): modularization + docs.
- Each phase leaves the site renderable; only the final state is pushed.
