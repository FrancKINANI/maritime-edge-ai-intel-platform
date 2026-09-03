# Implementation Plan: SEO Image Optimization & Site Reorganization

**Branch**: `001-site-seo-reorg` | **Date**: 2026-09-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-site-seo-reorg/spec.md`

## Summary

Improve the static landing site under `site/` (GitHub Pages, zero-config) in two
moves that must not change any visible content or the visual identity:

1. **Correct image SEO** — every image gets a descriptive filename following the
   documented convention, unique descriptive `alt` text, an HTML caption, declared
   display dimensions (no layout shift), lazy loading below the fold, and a
   compressed web-sized file. Page head gains a canonical URL, social preview tags
   with a real preview image, and JSON-LD structured data; `robots.txt` and
   `sitemap.xml` (with image entries) are published.
2. **Modular reorganization** (user-selected "full split") — assets move into
   purpose-based subfolders, the single 1,050-line stylesheet is split into four
   files by concern, the inline script moves to its own file, and the markup is
   restructured semantically (`<main>`, `<figure>`/`<figcaption>`, header/footer
   landmarks) with identical ids, anchors, content, and statistics.

Raster strategy (Q2 delegated to best judgment): **keep standard .png/.jpg/.svg
formats only** — no WebP — but re-encode aggressively. The four 1902×1062 PNG
screenshots (largest is 1.5 MB) are downscaled to ≤1600px and saved as optimized
JPEG; the PNG logo is kept PNG (alpha) but downsized and palette-optimized; the
three 640×640 SAR JPEGs are recompressed at equal size. Rationale: originals
remain directly usable in the author's PDF/Word internship report, compatibility
is universal, and the 60% weight-reduction target (2.2 MB → ~0.7 MB) is still met.
See [research.md](research.md) for the full decision log.

## Technical Context

**Language/Version**: HTML5, CSS3, vanilla ES5/ES6 JavaScript — no frameworks, no
build step (constitution principle I).

**Primary Dependencies**: none at runtime. Image re-encoding uses Python Pillow
run in an isolated throwaway environment (`uv run --with pillow`), never added to
project dependencies.

**Storage**: static files served by GitHub Pages from the `site/` folder; the
existing `.github/workflows/deploy-pages.yml` uploads the whole folder, so file
moves inside `site/` deploy without workflow changes.

**Testing**: no automated suite for the static site (constitution §Change
Scope). Validation = reference audit scripts (image paths, alt text, dimensions,
bytes) + local HTTP serving + manual visual check in a browser. Backend pytest
suite (122 tests) is untouched.

**Target Platform**: modern browsers (Chrome, Firefox, Safari, Edge) + mobile;
GitHub Pages host. Baseline raster weight measured today: ~2.2 MB across 13
displayed images + logo.

**Performance Goals**: total image weight ≤ ~0.9 MB (≥60% reduction from 2.2 MB);
no single raster > ~250 KB; no layout shift from images (all `<img>` carry
`width`/`height`); below-the-fold images lazy-loaded.

**Constraints**: index.html must remain at `site/index.html`; all paths relative;
no content/statistic/caption changes; PDF report stays downloadable; all 6
`.svg` diagrams keep their `.drawio` partners; site works when opened by
double-click and when deployed (no server-side includes).

**Scale/Scope**: single page, 17 asset files today (6 SVG + 6 drawio + 4 PNG +
3 JPG + 1 PDF + 1 logo PNG → after optimization 6 SVG + 6 drawio + 7 raster
[4 JPG + 3 JPG] + 1 logo PNG + 1 PDF ≈ 24 files including new robots/sitemap).

### Baseline asset inventory (measured 2026-09-03)

| File (today) | Format | Dims | Size | Action |
|---|---|---|---|---|
| docker-monitoring.png | PNG | 1902×1062 | 1.5 MB | → JPEG ≤1600px, target ≤250 KB |
| dashboard-upload.png | PNG | 1902×1062 | 144 KB | → JPEG ≤1600px, ~≤120 KB |
| dashboard-monitoring-events.png | PNG | 1902×1062 | 96 KB | → JPEG ≤1600px, ~≤100 KB |
| dashboard-satellite-query.png | PNG | 1902×1062 | 68 KB | → JPEG ≤1600px, ~≤90 KB |
| ksf.space-logo-high.png | PNG | 435×420 | 140 KB | keep PNG, resize ~220px, ≤25 KB |
| sar-vessel-detection.jpg | JPEG | 640×640 | 100 KB | recompress q80 → ~≤60 KB |
| sar-single-vessel.jpg | JPEG | 640×640 | 56 KB | recompress → ~≤40 KB |
| sar-multi-vessel-detection.jpg | JPEG | 640×640 | 32 KB | recompress → ~≤25 KB |
| 6 × *.svg diagrams | SVG | — | ~80 KB total | unchanged, moved |
| 6 × *.drawio sources | XML | — | ~92 KB total | unchanged, moved |
| rapport_stage.pdf | PDF | — | 580 KB | unchanged, moved |

Target total raster weight ≈ 700 KB (from 2.14 MB) — exceeds the 60% goal.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after design.*

| Constitution principle | Status | How the plan satisfies it |
|---|---|---|
| I. Static, dependency-free site | ✅ | No build step, no framework, no CDN; index.html stays at site root; relative paths only |
| II. SEO image discipline | ✅ | Naming convention + alt + captions kept/strengthened; README/HTML/disk reconciled |
| III. Diagrams stay editable | ✅ | SVG + drawio pairs move together; names unchanged |
| IV. Content is the deliverable | ✅ | No content/statistic/caption changes; reorg is structural only |
| V. Accessibility & performance | ✅ | width/height, lazy loading, semantics, landmark elements, weight budget |
| VI. Simplicity & minimal change | ✅ | Edits are moves/splits/additions with zero behavioural change; no speculative abstraction |

No violations → no complexity justification needed. Re-check after Phase 1
design: still compliant (structure only; identical rendered output intended).

## Project Structure

### Documentation (this feature)

```text
specs/001-site-seo-reorg/
├── spec.md               # Feature specification (approved, clarifications folded in)
├── plan.md               # This file
├── research.md           # Phase 0 — design decisions & rationale
├── quickstart.md         # Phase 1 — validation guide (run before/after implementation)
├── checklists/
│   └── requirements.md   # Spec quality checklist (passing)
└── tasks.md              # Created later by $speckit-tasks
```

**data-model.md and contracts/ are intentionally not generated**: the feature
introduces no stored data or external interface contract — its "entities"
(asset inventory above; key entities in spec.md) are a static file manifest that
lives in this plan and in tasks.md. Documented in quickstart.md instead.

### Source Code (site folder — the only area changed)

```text
site/
├── index.html                # restructured: semantics + SEO head, same ids/anchors/content
├── robots.txt                # NEW — allow all + Sitemap directive
├── sitemap.xml               # NEW — page + image entries (base URL configurable)
├── .nojekyll                 # unchanged
├── README.md                 # rewritten to match the new structure exactly
└── assets/
    ├── css/
    │   ├── base.css          # reset, :root design tokens, base element styles (from style.css 1–74)
    │   ├── layout.css        # nav, hero, sections/headers, content grids, download band, footer
    │   ├── components.css    # buttons, cards, callouts, tables, pills, image figures, stat cards
    │   └── responsive.css    # all three @media blocks (current lines 927–1050)
    ├── js/
    │   └── main.js           # NEW — nav toggle, smooth scroll, scroll nav bg (from inline <script>)
    └── img/
        ├── diagrams/         # 6 .svg + their 6 .drawio partners (names unchanged)
        ├── screenshots/      # sar-single-vessel.jpg, sar-multi-vessel-detection.jpg,
        │                     # sar-vessel-detection.jpg, dashboard-upload.jpg,
        │                     # dashboard-satellite-query.jpg, dashboard-monitoring-events.jpg,
        │                     # docker-monitoring.jpg  (all ksf-…-platform-<slug>.jpg)
        └── brand/
            └── ksf.space-logo-high.png   # sanctioned naming exception, downsized
    └── doc/
        └── rapport_stage.pdf # internship report (download target unchanged)
```

**Structure Decision**: `assets/` with `css|js|img|doc` mirrors standard static
site organization, keeps the deploy root shallow, and groups each deliverable's
files (diagram + source) together. `img/` subfolders (`diagrams`, `screenshots`,
`brand`) make the file's purpose explicit at a glance — replacing today's flat
17-file `images/` dump. All names keep the SEO convention so URLs stay
descriptive after the move.

**HTML restructure plan (behaviour-identical)**:
- Head: add `<link rel="canonical">`, `og:url`, `og:image` (absolute URL of the
  flagship docker-monitoring screenshot JPEG), `og:locale`, `twitter:card`
  `summary_large_image`, `theme-color`, JSON-LD `@graph` (WebSite +
  Organization KSF Space Foundation + ImageObject entries for key images), keep
  existing description/keywords/author/og tags.
- Body: wrap content sections in `<main>`; convert each
  `div.image-placeholder > img + div.placeholder-label` to
  `<figure class="image-placeholder"> <img … width height loading decoding
  alt> <figcaption class="placeholder-label">…</figcaption> </figure>`; fallback
  markup (`placeholder-fallback` + `onerror`) preserved for SVG figures.
- Every `<img>` gains `width`/`height` (intrinsic file pixels after re-encode);
  hero + first SAR figure load eagerly, all others `loading="lazy"`
  `decoding="async"`; hero image gets `fetchpriority="high"`.
- Inline `<script>` moves to `assets/js/main.js` loaded with `defer`.
- Section ids, nav anchors, copy, stats, alt intent, and download link href are
  unchanged (only paths and structure change).

**CSS split**: sections are extracted from the current well-commented style.css
by the `/* ===== X ===== */` block headers into the four files above; the three
`@media` blocks move as-is to responsive.css (loaded last, preserving cascade).
Verification: selector count of the concatenated files equals the original, and
the rendered page looks identical.

## Complexity Tracking

No constitution violations to justify — table intentionally empty.
