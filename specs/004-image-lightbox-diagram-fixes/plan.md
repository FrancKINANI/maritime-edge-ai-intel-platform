# Plan — Image Lightbox & Diagram Text Fixes

## Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | `<a class="lightbox-link">` wrapper in HTML, JS opens lightbox | Progressive enhancement: no-JS users still reach the raw file; semantics stay in markup |
| D2 | Single shared overlay built once by JS | No per-image DOM; one dialog with `role="dialog"` |
| D3 | Prev/next + keyboard nav across all 13 content images | Standard lightbox UX, trivial over a shared overlay |
| D4 | Caption from `figcaption.placeholder-label`, fallback to `alt` | Reuses existing captions, no duplicate text |
| D5 | SVG fixes done by hand-editing coordinates/widths, not re-exporting | SVGs are hand-crafted text SVG; precise surgical edits, `.drawio` mirrored manually |
| D6 | `onerror` handlers switch to `this.closest('figure')` | Img is now wrapped in `<a>`; parentElement would be the anchor, breaking the fallback |
| D7 | Lightbox CSS lives in components.css; mobile tweaks in responsive.css | Follows the existing 4-file CSS split by concern |

## Files Touched

- `site/index.html` — wrap 13 imgs, fix 4 onerror handlers (no visible text changes)
- `site/assets/css/components.css` — `.lightbox-link`, `.lightbox`, `.lightbox-*`, keyframes
- `site/assets/css/responsive.css` — small-screen lightbox nav/close positions
- `site/assets/js/main.js` — lightbox module
- `site/assets/img/diagrams/…-tle-fallback.{svg,drawio}` — bottom band rebuilt: NORAD IDs · Legend · SGP4 output as three side-by-side panels (was overlapping + clipped)
- `site/assets/img/diagrams/…-data-flow.svg` — 3 arrow labels shrunk/recentered
- `site/assets/img/diagrams/…-ci-pipeline.svg` — small label poke fixed
- `site/README.md` — image guide documents the lightbox wrapper

## Verification

1. `node --check` on main.js; CSS brace balance across the 4 files
2. HTML structure: 13 `<a class="lightbox-link">`, 14 imgs, balanced tags
3. Anchor-aware SVG text-collision scan: 0 real collisions, 0 canvas-clipped
4. Visible-token diff vs pre-change: identical
5. Local HTTP serve: all 22 asset URLs return 200
6. Manual browser pass (desktop + 375px + reduced-motion)