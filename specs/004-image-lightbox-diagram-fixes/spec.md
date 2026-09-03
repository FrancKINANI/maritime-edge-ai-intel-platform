# 004 — Image Lightbox & Diagram Text Fixes

## Goal

Make every content image clickable so visitors can view it large, and rebuild
the diagrams whose text overlaps or is cut off.

## Functional Requirements

- **FR-001** Every content image (13 of 14; the nav logo is exempt) is wrapped
  in an `<a class="lightbox-link">` pointing at the same asset, so the lightbox
  works and degrades to opening the raw file without JS.
- **FR-002** Clicking a content image opens a full-screen lightbox viewer:
  backdrop blur, large image, caption (figcaption, falling back to `alt`),
  image counter (`n / 13`).
- **FR-003** The lightbox supports closing via ✕ button, backdrop click, and
  `Escape`; navigation via ‹ › buttons and `←`/`→` keys; ends disable their
  arrow.
- **FR-004** Accessibility: `role="dialog"` + `aria-modal`, focus moves to
  close on open and returns to the triggering link on close, `aria-label`s on
  all controls, body scroll locked while open.
- **FR-005** All lightbox motion is killed by the existing
  `prefers-reduced-motion` block.
- **FR-006** Diagram rebuilds: no overlapping or canvas-clipped text in any of
  the 6 SVGs (TLE fallback, data flow, CI pipeline, zone classification,
  pipeline comparison, architecture).
- **FR-007** The TLE fallback fix is mirrored in its `.drawio` editable source
  (svg↔drawio pair stays in sync).
- **FR-008** No visible page content changes; no new dependencies; image
  `alt`/`width`/`height` invariants from feature 001 remain intact.

## Scope Exclusions

- No content copy changes (feature 003 owns that).
- No new assets or libraries.
- Diagram **content** unchanged — only layout positions, sizes, and one
  bottom-band restructure.