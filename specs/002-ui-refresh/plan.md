# Implementation Plan: Engaging Mission-Control UI Refresh

**Branch**: `002-ui-refresh` | **Date**: 2026-09-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-ui-refresh/spec.md`

## Summary

Presentational + interactional refresh of the static landing site — no content,
id, URL, image, or SEO-file changes. Add a "space mission control" visual layer
(CSS-only radar/scan hero motif, deep-space glow, glassy cards, telemetry-style
section tags) plus tasteful, accessible motion (scroll reveals, stat count-ups,
hover lift) and UX aids (scroll-progress bar, active-nav highlighting via
scrollspy, back-to-top, skip link, focus-visible styles, fluid mobile menu).
Everything animates through progressive enhancement and is disabled under
`prefers-reduced-motion`. Zero new dependencies, images, or font downloads.

## Technical Context

**Language/Version**: HTML5, CSS3 (custom properties, `backdrop-filter`,
`@supports`, keyframes), vanilla JS (IntersectionObserver, rAF throttling) —
no frameworks, no build (constitution principle I).

**Primary Dependencies**: none added. Existing system font stacks reused; a
monospace stack (`ui-monospace, 'Cascadia Code', 'SF Mono', Consolas,
monospace`) is added via CSS only.

**Storage / Hosting**: static GitHub Pages from `site/` (unchanged).

**Testing**: no automated suite (static site). Validation = token-level content
diff, structure/reference audits, local HTTP serve + a JS smoke check, and the
previous feature's quickstart suite re-run (image refs, alt/dimensions,
robots/sitemap). Backend pytest untouched.

**Target Platform**: modern browsers incl. mobile 375px+; reduced-motion OS
setting honored.

**Performance Goals**: no new image/font bytes; added CSS ≤ ~15 KB; animation
durations 200–700 ms; no layout shift; main thread work only on scroll
(throttled via rAF), scrollspy + reveals via IntersectionObserver.

**Constraints**: keep the 4-file CSS split and load order (base → layout →
components → responsive); keep `assets/js/main.js` as the only script; every
decorative element `aria-hidden` + `pointer-events: none`; all new behavior
gracefully degrades with JS disabled (elements visible, nav works via anchors);
visible text stays byte-identical (token diff empty); reduced-motion kills all
animation (radar, count-up, reveals, hover lift) and shows final state.

**Scale/Scope**: `site/index.html` (+~8 attribute/class touch-points),
`site/assets/css/*.css` (4 files extended), `site/assets/js/main.js` (+~90
lines). No other files.

### Design system additions (all CSS custom properties, in `base.css`)

- `--font-mono` system stack (telemetry tags, labels).
- Glass surfaces: `--glass-bg` translucent gradient fill, `--glass-border`
  hairline rgba border, `--surface-highlight` top-edge light line.
- Glow palette: cyan accent (`--accent-cyan: #22d3ee`) for radar/scan + focus;
  existing blues/purples for gradients; `--glow-soft`/`--glow-strong` shadow
  tokens (button/card hover).
- Keyframes: `radar-sweep` (rotate a conic sweep), `ping-dot` (badge pulse),
  `float-orb` (slow hero orb drift) — durations 4–12 s, all disabled under
  reduced motion.

## Constitution Check

*GATE: Must pass before implementation.*

| Principle | Status | How the plan satisfies it |
|---|---|---|
| I. Static, dependency-free | ✅ | CSS + vanilla JS only; still zero-config GH Pages |
| II. SEO image discipline | ✅ | No image files touched; previous audits re-run |
| III. Diagrams stay editable | ✅ | Diagram markup/structure untouched |
| IV. Content is the deliverable | ✅ | Zero text changes; token diff verified empty |
| V. Accessibility & performance | ✅ | reduced-motion support, focus-visible, skip link, no new bytes, no CLS |
| VI. Simplicity & minimal change | ✅ | Extends the existing 4-file CSS + one JS file in style; no new architecture |

No violations → Complexity Tracking table left empty.

## Project Structure

### Documentation (this feature)

```text
specs/002-ui-refresh/
├── spec.md               # Feature specification (clarifications resolved)
├── plan.md               # This file
├── checklists/
│   └── requirements.md   # Spec quality checklist (passing)
└── tasks.md              # Created by $speckit-tasks after plan approval
```

research.md / quickstart.md are intentionally not generated for this feature:
no technical unknowns or new interfaces exist (all techniques are established
browser APIs), and the previous feature's `quickstart.md` already defines the
regression suite this refresh must re-pass. A short "verification" checklist is
included in the completion summary instead.

### Source Code (site folder — only area changed)

```text
site/index.html                # +skip link, +back-to-top button, +scroll-progress bar,
                               #  id="main", .reveal markers, navToggle aria-expanded
                               #  (no text/content changes)
site/assets/css/base.css       # +font-mono, +glass/glow tokens, +focus-visible,
                               #  +keyframes (radar, ping, float)
site/assets/css/layout.css     # +hero decor (grid overlay, orbs, radar disc via
                               #  ::before/::after), +scroll-progress bar,
                               #  +back-to-top placement, +section-tag telemetry
site/assets/css/components.css # +glass surface treatment + hover lift for cards/
                               #  figures/callouts/download panel, +button glow
                               #  +nav blur & reveal states, +skip link styles
site/assets/css/responsive.css # +reduced-motion block (last), +375px refinements,
                               #  +mobile-nav open animation polish
site/assets/js/main.js         # +reveal IO, +stat count-up IO, +scrollspy IO,
                               #  +progress bar & back-to-top (rAF scroll),
                               #  +navToggle aria-expanded sync
```

**Structure Decision**: keep the approved modular layout; new rules go into the
file matching their concern (per the plan above), preserving the documented
load order. No new files.

### Behavior design (progressive enhancement)

1. **Radar/scan hero (CSS only)**: `.hero::before` = faint blueprint grid
   (repeating-linear-gradient, radial mask); `.hero::after` = a radar disc
   (concentric ring borders + conic-gradient sweep) behind the content with a
   slow rotation; two blurred gradient "orbs" via extra decorative divs or
   layered backgrounds drift very slowly. All layers `aria-hidden`,
   `pointer-events: none`, low opacity, `mix-blend` optional. Reduced motion →
   static, non-rotating.
2. **Telemetry chips**: `.section-tag` restyled (mono, uppercase, letterspaced,
   tinted pill + left accent bar) and `.hero-badge` gets a pulsing status dot
   via `::before` (content unchanged).
3. **Stat count-up**: each `.stat-number` gets `data-value` + optional suffix
   read from its existing text; on intersect, JS counts 0 → value over ~800 ms
   with ease-out (rAF), writing the exact original string when done. Skipped
   under reduced motion.
4. **Scroll reveals**: JS adds `js` class to `<html>` and observes
   `.reveal`-tagged blocks (sections' header/grids/cards); CSS
   `.js .reveal { opacity:0; translateY(18px) }` → `.is-visible` transition
   (≤500 ms, ease-out, staggered via `transition-delay` on children where
   cheap). `.js` + reduced-motion media query forces opacity 1; no-JS users
   never see a hidden state.
5. **Scrollspy**: IO with `rootMargin: "-45% 0px -50% 0px"` tracks the 8
   section ids; the matching nav link gets `.active` (CSS underline/glow).
6. **Scroll progress**: 3px gradient bar at the navbar's top edge scaled by
   `scrollY / (docHeight - winHeight)` on rAF-throttled scroll; `aria-hidden`.
7. **Back to top**: fixed circular ghost button (↑), `.show` after
   `scrollY > 600`, smooth scrolls to top; below 480px it docks above the
   footer content without overlap.
8. **Skip link**: `<a class="skip-link" href="#main">Skip to content</a>`
   first element in `<body>`; `id="main"` on the existing `<main>`;
   `.skip-link` visible on focus (offscreen until `:focus-visible`).
9. **Mobile nav**: `.nav-links` opens with fade/slide + slight stagger per
   link (transform/opacity); `#navToggle` keeps `aria-expanded` in sync and is
   labelled "Toggle navigation". Reduced motion → instant open.
10. **Glass & glow**: cards/callouts/figures/download panel get translucent
    fills + `backdrop-filter: blur(10px)` inside `@supports`, hairline borders
    with top highlight; hover = `translateY(-4px)` + cyan border + soft glow
    (motion disabled under reduced motion but color change retained). Buttons
    get gradient sheen + glow on hover/focus.
11. **Focus & reduced motion**: global `:focus-visible` outline (2px cyan,
    3px offset); one `@media (prefers-reduced-motion: reduce)` block at the end
    of `responsive.css` disabling animations/transitions and forcing reveal
    opacity 1.

### Verification checklist (mirrors SC-001..006, run post-implementation)

- `git diff`/token diff of visible text = empty; section ids + copy unchanged.
- Reference audits of `001-site-seo-reorg/quickstart.md` §1 re-pass.
- No new files under `site/assets/img`; CSS total ≤ ~15 KB added; file order
  intact (4 links in base→layout→components→responsive).
- Local serve (`python3 -m http.server 8000 --directory site`): all URLs 200,
  JS parses (node --check), no console errors reported by user's browser pass.
- Manual browser pass by the user (visual + mobile + reduced-motion), since no
  browser is available in this environment.

## Complexity Tracking

No constitution violations to justify — table intentionally empty.
