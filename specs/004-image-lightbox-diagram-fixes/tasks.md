# Tasks — Image Lightbox & Diagram Text Fixes

| ID | Task | Status |
|----|------|--------|
| T001 | Analyze all 6 SVGs with anchor-aware text-collision scan | ✅ |
| T002 | Rebuild TLE fallback bottom band (NORAD IDs · Legend · SGP4 output, 3 side-by-side panels) | ✅ |
| T003 | Fix data-flow arrow labels (shrink + recenter into gaps) | ✅ |
| T004 | Fix ci-pipeline small label poke | ✅ |
| T005 | Mirror TLE fix into `.drawio` editable source | ✅ |
| T006 | Wrap all 13 content images in `.lightbox-link` anchors (nav logo exempt) | ✅ |
| T007 | Fix 4 `onerror` handlers to `this.closest('figure')` | ✅ |
| T008 | Add lightbox CSS to components.css (overlay, figure, caption, counter, close, nav, keyframes) | ✅ |
| T009 | Add mobile lightbox tweaks to responsive.css | ✅ |
| T010 | Add lightbox module to main.js (open/close, prev/next, keyboard, focus mgmt, scroll lock) | ✅ |
| T011 | Verify: node --check, CSS braces, HTML structure, visible-token diff empty, HTTP 200s | ✅ |
| T012 | Update README image guide; write spec/plan/tasks records | ✅ |

## Verification Results

- `node --check` passes; CSS braces balanced (components 106/106, layout 82/82,
  responsive 53/53, base 24/24)
- 13/13 content imgs wrapped; 14 imgs total; 14 alt + width + height (0 missing)
- Visible-token diff vs pre-change: **identical (1345/1345)**
- All 6 SVGs: 0 text↔text collisions, 0 canvas-clipped texts (anchor-aware scan)
- 22/22 asset URLs serve HTTP 200 locally
- Reduced-motion covered by existing global block