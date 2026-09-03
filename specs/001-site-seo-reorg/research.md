# Research & Design Decisions — SEO Image Optimization & Site Reorganization

Each entry records a decision, its rationale, and the alternatives considered.

## D-1: What "optimize images for search ranking" means here

**Decision**: Treat it as the standard image-SEO checklist, applied to a static
GitHub Pages site, verified by an audit instead of by an analytics account:

1. Descriptive, keyword-relevant **filenames** (crawlers read them; so do image
   search and users hovering links).
2. Unique, descriptive **alt text** and a visible **caption/context** per image.
3. Fast-loading, properly sized **files** (compression reduces bytes; page speed
   is a ranking factor and image search favors it).
4. **Dimensions + lazy loading** so nothing shifts layout and below-fold bytes
   are deferred.
5. **Page metadata**: canonical URL, social preview tags (og:image, twitter),
   and JSON-LD structured data so engines understand the page without guessing.
6. **robots.txt + sitemap.xml with image entries** so every image URL is
   discoverable and can appear in image search.

**Rationale**: These are Google's documented image best practices (descriptive
filenames/alt, context, quality, sitemaps, page speed) and are fully
controllable from the repository — ideal for an internship deliverable that must
be verifiable without a search console account.

**Alternatives considered**: registering Search Console / submitting URLs
(needs the author's Google account and the site already deployed — out of scope
and external); buying SEO tooling (unnecessary).

## D-2: Image formats — keep .png/.jpg, no WebP

**Decision**: All web raster images stay in standard .png/.jpg; the four
1902×1062 PNG screenshots become optimized JPEGs; the logo stays PNG.

**Rationale**: (a) JPEG at 1600px/q80–85 compresses photo-like UI screenshots
far better than PNG while keeping sharp text legible at display size ≤1000px;
(b) .jpg/.png embed directly in the author's Word/PDF internship report;
(c) zero compatibility risk on GitHub Pages or in offline tools; (d) the target
(≤250 KB each, total ≥60% lighter) is reached without any modern-only format.

**Alternatives considered**: WebP (~30–50% smaller still) — rejected because the
user prioritized keeping files reusable elsewhere and delegated the choice to
best judgment; AVIF — same rejection plus narrower support.

## D-3: Compression tooling — isolated Pillow, no project dependency

**Decision**: Re-encode images with a throwaway Python Pillow script executed as
`uv run --with pillow python tools_/…` (or an equivalent isolated env). No
package is added to pyproject.toml or uv.lock, and no committed script is
required beyond the repo if a one-shot inline script is used.

**Rationale**: The repo's Python ecosystem is uv-based; Pillow is the standard
image library; running it isolated respects constitution principle I (no new
dependencies) and keeps the diff clean.

**Alternatives considered**: ImageMagick CLI (may not be installed); adding
pillow to a project requirements file (touches the Python service environment —
rejected).

## D-4: Target geometry for re-encoding

**Decision**:
- Screenshots: max width 1600 px (container ≤1000 px → ~1.6× for crisp
  high-DPI rendering), JPEG quality tuned per file to land ≤250 KB (start q82;
  drop to q78 or 1400 px if a busy frame overshoots; raise q85 if text looks
  soft at 100%).
- SAR JPEGs (640×640, display ≤~560 px): keep 640 px, recompress q78–82.
- Logo (display ~44 px in nav): keep PNG RGBA, resize to 220 px, reduce colors
  to 256 with alpha; target ≤25 KB (from 140 KB).

**Rationale**: dimension attributes in HTML must match the final file's
intrinsic pixels so the browser reserves the correct aspect box; sizes above
are the smallest that still look sharp at their CSS display sizes on 2× screens.

**Alternatives considered**: keeping 1902 px (wastes ~3× bytes for pixels never
shown at full size); serving srcset sizes (overkill for one image per slot on a
no-build static page).

## D-5: Folder structure — assets/ with purpose subfolders

**Decision**: `site/assets/{css,js,img,doc}`; `img/` split into `diagrams/`
(6 svg + 6 drawio), `screenshots/` (7 jpg), `brand/` (logo); report PDF to
`assets/doc/`.

**Rationale**: separates deploy root (index.html, robots, sitemap, README,
.nojekyll) from reusable assets; pairs editable sources with published
diagrams; matches the standard static-site convention; keeps every filename SEO
descriptive.

**Alternatives considered**: flat `images/` with prefixes only (today's state —
the thing being fixed); `src/` + build output (introduces a build step —
forbidden).

## D-6: CSS split — four files by concern

**Decision**: `base.css` (reset, tokens, base elements), `layout.css` (nav,
hero, sections, grids, footer), `components.css` (buttons, cards, callouts,
tables, pills, image figures, stat grids), `responsive.css` (all @media blocks,
loaded last). Split follows the existing `/* ===== X ===== */` block headers;
styles are moved verbatim, not rewritten.

**Rationale**: 1,050 lines in one file makes maintenance archaeology harder;
four concern files with the media queries isolated last preserve the exact
cascade order. Zero rule changes → zero visual risk.

**Alternatives considered**: single file with more comments (doesn't meet the
user's "full modular split" choice); CSS custom-property-driven theming restyle
(visual change — out of scope).

## D-7: Crawler-facing files and structured data

**Decision**: Add robots.txt (allow all + Sitemap line) and sitemap.xml listing
the page plus `<image:image>` entries for the 13 content images. Add canonical,
og:url/og:locale/og:image, twitter summary_large_image, and JSON-LD @graph with
WebSite, Organization (KSF Space Foundation), and ImageObject entries for the
key visuals. The absolute base URL is centralized in one constant
(`https://franckinani.github.io/maritime-edge-ai-intel-platform/`) reused by
canonical/og/sitemap, and confirmed against the live Pages URL before
finalizing.

**Rationale**: complete the standard package (spec FR-005, user choice "full
metadata + robots/sitemap"); image sitemaps are the only direct way to feed
image URLs to Google; JSON-LD removes guesswork about what the page is.

**Alternatives considered**: on-page tags only (user rejected); including
analytics/tracking scripts (not needed, and adds third-party requests).

## D-8: Markup restructure — semantics without behaviour change

**Decision**: introduce `<main>`, wrap figures in `<figure>`/`<figcaption>`,
keep the placeholder-fallback pattern (JS `onerror` toggles the `.missing`
class), move the inline script to `assets/js/main.js` (`defer`), add
width/height + loading/decoding/fetchpriority attributes. Section ids, nav
anchors, heading order, copy, and stats stay byte-identical in content.

**Rationale**: satisfies FR-009/FR-011/FR-012 and constitution IV/V while
keeping the rendered experience identical and the diff reviewable.

**Alternatives considered**: multi-page split per section (single-page design is
a feature; nav relies on anchors — rejected); client-side templating (breaks
no-build constraint).
