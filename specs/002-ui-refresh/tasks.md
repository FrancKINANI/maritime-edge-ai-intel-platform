# Tasks: Engaging Mission-Control UI Refresh

**Input**: Design documents from `specs/002-ui-refresh/` (spec.md, plan.md)

**Tests**: No test tasks — static site. Validation tasks run the token-diff and regression audits defined in plan.md.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [x] T001 Snapshot current site files to /tmp as content baseline for token-diff verification (index.html, 4 CSS files, main.js)

## Phase 2: User Story 1 - Engaging mission-control look (Priority: P1)

- [x] T002 [US1] Add design tokens + keyframes to `site/assets/css/base.css`: `--font-mono`, `--accent-cyan`, glass/glow tokens, `:focus-visible` styles, `radar-sweep`/`float-orb` keyframes
- [x] T003 [US1] Add hero mission-control decor to `site/assets/css/layout.css` via `.hero::before` (blueprint grid + gradient mask) and `.hero::after` (radar disc with rings + rotating conic sweep), both `pointer-events: none`
- [x] T004 [US1] Restyle `.section-tag` as telemetry chip (mono, uppercase, letterspaced, accent bar) and `.hero-badge` with pulsing status dot in `site/assets/css/layout.css`
- [x] T005 [US1] Add glass/glow surface treatment (translucent sheen, hairline top highlight, hover lift + cyan glow) for cards/callouts/figures/download panel and button glow in `site/assets/css/components.css`

## Phase 3: User Story 2 - Intuitive navigation & interaction (Priority: P1)

- [x] T006 [US2] Edit `site/index.html`: skip link first in `<body>`, `id="main"` on `<main>`, `.scroll-progress` bar as first child of `#navbar`, back-to-top button before the closing script, `aria-expanded`/`aria-controls` on `#navToggle`
- [x] T007 [US2] Rewrite `site/assets/js/main.js`: existing behaviors + reveal IntersectionObserver (adds `.js` to `<html>`, tags curated blocks), stat count-up, scrollspy active nav, rAF-throttled progress bar + back-to-top, aria-expanded sync; all guarded by `prefers-reduced-motion`
- [x] T008 [US2] Add reveal + stagger CSS (`.js .reveal` hidden → `.is-visible` transition, `.reveal-stagger > *` delays) and skip-link / back-to-top / progress-bar / nav-blur styles to `site/assets/css/components.css`

## Phase 4: User Story 3 - Zero regression (Priority: P2)

- [x] T009 [US3] Append final block to `site/assets/css/responsive.css`: `prefers-reduced-motion: reduce` overrides (kill animations/transitions, force reveal opacity 1) + 375px/480px refinements for new controls
- [x] T010 [US3] Verify: token diff of visible text vs /tmp baseline is empty; previous feature audits (image refs, alt/dims, css order, robots/sitemap) re-pass; `node --check site/assets/js/main.js`; local HTTP serve returns 200 for all references
- [x] T011 [US3] Report summary with before/after CSS bytes and hand off a browser visual pass checklist (desktop, 375px, reduced-motion) to the user

## Dependencies

- Phase 2 CSS tokens (T002) precede layout/component effects (T003–T005)
- T006 (HTML hooks) precedes T008 (styles for those hooks) in final state
- T007 (JS) depends on T006 element ids/classes
- T009 must be last CSS edit (reduced-motion overrides need final cascade position)

## Implementation strategy

- MVP = US1 (look) once tokens exist; US2 (interaction) builds on the same files;
  US3 (regression) is the verification gate. All phases land together before the
  user's visual pass.
