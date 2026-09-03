<!--
Sync Impact Report v1.1.0
- Version change: 1.0.0 → 1.1.0 (amendment authorized by repository owner 2026-09-03)
- Modified principles: IV. Content Is the Deliverable — now permits narrative reorganization and copy tightening with explicit owner approval, while keeping all factual claims and statistics truthful; anchors/inventories must stay consistent
- Added sections: none | Removed sections: none
- Rationale: owner requested a full content restructure (feature 003-content-restructure): reorder sections, rearrange internal blocks, and condense wording for narrative flow
- Migration note: earlier features' "content word-for-word intact" checks apply to features 001/002; feature 003 supersedes them with a truthfulness-preserving reorganization
- Deferred TODOs: none
-->

<!--
Sync Impact Report (original v1.0.0)
- Version change: n/a (initial adoption) → 1.0.0
- Modified principles: none (new file)
- Added sections: Core Principles (I–VI), Static-Site Deployment Constraints, Change Scope & Quality Gates, Governance
- Removed sections: none
- Deferred TODOs: none
-->
# Maritime Edge AI Platform Constitution

## Core Principles

### I. Static, Dependency-Free Site (NON-NEGOTIABLE)
The landing site under `site/` MUST remain plain HTML + CSS + vanilla JavaScript.
No frameworks, no build step, no package manager, and no runtime CDN
dependencies are allowed. Every change MUST keep `index.html` openable by
double-click and deployable as-is to GitHub Pages via the existing
`.github/workflows/deploy-pages.yml` workflow. Relative asset paths MUST be
preserved so the site works from any sub-path of the GitHub Pages URL.

### II. SEO-Driven Image Discipline
Every image in `site/images/` MUST follow the documented naming convention
`ksf-space-maritime-edge-ai-intel-platform-<descriptive-slug>.<ext>` (the KSF
logo is the only sanctioned exception) and MUST carry a descriptive,
context-rich `alt` attribute in `index.html`. HTML image references, the files
present on disk, and the inventory tables in `site/README.md` MUST agree with
one another — no orphan references, no undocumented files, no stale rows.
Raster screenshots MUST be compressed and sized for the web.

### III. Diagrams Stay Editable
Each published `.svg` diagram in `site/images/` MUST keep its paired
`.drawio` source file so diagrams remain editable in diagrams.net. The HTML
`<img>` references, alt text, and captions MUST describe what the diagram
actually shows and MUST NOT be renamed away from the convention without
renaming the source pair together.

### IV. Content Is the Deliverable (amended v1.1.0)
The site presents the author's internship work for KSF Space Foundation.
All technical claims, statistics (microservices count, test counts, INT8
compression figures), and the downloadable report link MUST remain truthful.
With explicit owner approval, section order, internal structure, headings,
and wording MAY be reorganized and tightened to improve narrative flow. Such
edits MUST NOT change the meaning of any claim, MUST keep every factual
statement accurate, MUST update every id, anchor, and asset reference they
touch (no dead links, no orphan figures), and MUST keep the report PDF
reachable. Structure, SEO, asset, and performance principles (I–III, V–VI)
continue to apply unchanged.

### V. Accessibility & Performance
The site MUST remain keyboard-navigable and readable by assistive
technology: heading hierarchy, landmark elements, focus styles, and
sufficient text contrast MUST be preserved or improved. Performance
budget: the page and its images MUST stay lightweight — lazy-load
below-the-fold images, declare dimensions to prevent layout shift, and
avoid loading more bytes than the design needs.

### VI. Simplicity & Minimal Change
Prefer the fewest, smallest edits that satisfy the request. YAGNI applies:
no speculative abstractions, no new "architecture" for a three-file static
site, no gratuitous churn of working markup or styles. Restructure only
where it clearly improves maintainability, SEO, or readability.

## Static-Site Deployment Constraints

- `site/index.html` and `site/style.css` are the only application files; a
  future split of CSS/JS is permitted only if the result still deploys with
  zero configuration.
- The GitHub Pages workflow deploys the `site/` folder; changes outside
  `site/` MUST NOT be required for the site to function.
- `images/rapport_stage.pdf` is the internship report and MUST remain
  downloadable from the existing button.
- The site README documents structure, image conventions, and draw.io
  workflow; any structural or naming change MUST be reflected there in the
  same change.

## Change Scope & Quality Gates

- Feature work is specified, planned, and task-broken-down under
  `.specify/features/` before implementation, and implementation is
  validated against the spec (converge).
- Before declaring a site change complete: validate the HTML (no broken
  image references, all files named per convention, all alt attributes
  present), confirm the page still renders with no console errors, and
  confirm no content was lost.
- Tests: the site is static and has no automated test suite; manual render
  checks plus a reference audit of image paths vs. on-disk files serve as
  the quality gate. Backend/service tests (122 across 9 suites) remain the
  repo's test gate and MUST NOT be touched by site work.

## Governance

This constitution supersedes ad-hoc site practices. Amendments require
documentation of the change, approval from the repository owner
(FrancKINANI), and a migration note for affected artifacts. Compliance with
the image naming convention, README synchronization, and accessibility
principles is verified during every site change review. Use the repository
READMEs, `.github/workflows/deploy-pages.yml`, and this document as the
runtime guidance sources.

**Version**: 1.1.0 | **Ratified**: 2026-09-03 | **Last Amended**: 2026-09-03
