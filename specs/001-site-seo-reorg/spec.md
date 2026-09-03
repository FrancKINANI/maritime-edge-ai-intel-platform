# Feature Specification: SEO Image Optimization & Site Reorganization

**Feature Directory**: `specs/001-site-seo-reorg`

**Created**: 2026-09-03

**Status**: Draft

**Input**: User description: "Improve the internship landing site: correct the SEO issues flagged under 'Optimize Image Files for Search Ranking', and reorganize the site very well. Validate the plan before implementing."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Search engines fully understand and rank the page and its images (Priority: P1)

A person searches for terms like "maritime vessel detection SAR Sentinel-1 edge AI" or
"KSF Space maritime AI internship". Search engines must be able to crawl the landing
page, understand what each image depicts, associate each image with the surrounding
content, and present the page (and its images in image search) with correct,
descriptive information.

**Why this priority**: The stated goal of the request is search-ranking
improvement for the site's images. This is the core value of the feature; all
other work supports or preserves it.

**Independent Test**: Review the published page and its underlying files:
every image has a descriptive, plain-language filename; every image is
accompanied by descriptive text describing its content; the page declares its
identity, description, and a representative social image; and crawler-facing
page metadata is present and consistent. Each item can be verified file by file.

**Acceptance Scenarios**:

1. **Given** the published landing page, **When** a crawler or reviewer audits every
   image on the page, **Then** each image has a filename that describes its content
   and a non-empty description of what it shows.
2. **Given** the published landing page, **When** it is shared on a social platform
   or listed in search results, **Then** it displays a correct title, summary, and a
   representative preview image chosen from the site's own visuals.
3. **Given** the site's image files, **When** each file's name, caption, and on-page
   context are checked, **Then** the three always agree and no image is referenced
   under a name that no longer exists.

### User Story 2 - Visitors and internship reviewers experience a fast, tidy, unbroken site (Priority: P1)

An internship supervisor, classmate, or recruiter opens the site on a laptop or a
phone, possibly on a slow connection. The page loads quickly, images appear without
the layout jumping around, and nothing that exists today is missing: all six
diagrams, the SAR screenshots, the dashboard screenshots, every section's content
and statistics, and the downloadable PDF report.

**Why this priority**: The site is the author's internship showcase. If
reorganization breaks any content or the report download, the feature fails
regardless of SEO gains.

**Independent Test**: Open the published page in a desktop and a mobile viewport;
scroll through every section; click the report button; confirm the page weight and
image byte totals before vs. after, and confirm all previously visible content and
the download are present.

**Acceptance Scenarios**:

1. **Given** a first visit on a slow mobile connection, **When** the page loads,
   **Then** the total transferred image weight is substantially lower than before and
   the content visible at the top appears before below-the-fold imagery is fetched.
2. **Given** the reorganized page, **When** every section and every visual from the
   current page is checked, **Then** no content, statistic, diagram, caption, or link
   is missing or altered in meaning.
3. **Given** the report button, **When** clicked, **Then** the internship report PDF
   still downloads successfully.

### User Story 3 - The author can maintain the site without guesswork (Priority: P2)

The author returns weeks later (or a reviewer inspects the repository) to add a new
screenshot or fix a caption. The folder layout is logical, the file organization
groups related assets, the markup is easy to navigate, and one maintenance guide
documents the conventions so no archaeology is needed.

**Why this priority**: Valuable for an internship deliverable and for future
maintenance, but secondary to the SEO and integrity outcomes above.

**Independent Test**: Read the maintenance guide alone and, following it, locate
where each type of asset lives and how new images are named and added; verify the
guide matches reality file for file.

**Acceptance Scenarios**:

1. **Given** the maintenance guide, **When** a new screenshot is added following it,
   **Then** the guide's instructions match the actual folder layout and naming rules.
2. **Given** the reorganized site, **When** the files are browsed, **Then** assets of
   the same kind are grouped together and files belonging to the same deliverable
   (diagram + editable source) travel together.

### Edge Cases

- An image file is referenced by the page but missing from the published site → the
  page must never silently depend on a file that does not exist; the audit in US1
  catches any reference/file mismatch.
- A renamed image was previously shared or bookmarked → reorganization must keep the
  site's internal consistency (US1.S3); the site is early-stage, so no external link
  permanence promise exists.
- Image formats stay standard (.png/.jpg/.svg) after optimization, so every
  browser and every offline tool (report editors, viewers) renders the images
  without compatibility risk.
- A diagram image fails to load → the page must degrade gracefully with a visible
  placeholder naming the expected file (existing behavior preserved).
- Very large screenshots (terminal captures) → they must be cropped/compressed so a
  mobile visitor is not charged megabytes for one image.
- Accessibility tools reading the page → every image keeps meaningful descriptive
  text; purely decorative elements are not announced as content.
- The layout must not jump while images load → every image declares its display size.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every image displayed on the page MUST have a filename that describes
  its content in plain, hyphen-separated words and follows the project's documented
  naming convention; the KSF logo is the only sanctioned exception.
- **FR-002**: Every image displayed on the page MUST carry descriptive text stating
  what the image shows (content, not just "image of X"), written to read naturally
  both to sighted visitors and to screen readers.
- **FR-003**: Every image MUST be presented near a human-readable caption or
  surrounding text that names and contextualizes it.
- **FR-004**: The page MUST declare, in machine-readable form: its unique title, its
  summary description, its language, and one representative image of the site's own
  visuals for social sharing and search previews.
- **FR-005**: The page MUST provide structured metadata describing the project as a
  software project and its key images, so engines can interpret the content without
  guessing, AND crawler helper files (a robots directive file and a sitemap listing
  the page with its images) MUST be published alongside the site.
- **FR-006**: Images below the first screenful MUST NOT be requested until the
  visitor scrolls near them; the image visible at page open MUST load immediately.
- **FR-007**: Every image MUST declare its display dimensions so the page does not
  shift layout while loading.
- **FR-008**: Raster image files MUST be compressed and sized for the web, keeping
  their original .png/.jpg formats, so that no single raster image exceeds roughly
  250 KB and the total page image weight drops by at least 60% from today's 2.2 MB.
- **FR-009**: The site's files MUST be fully modularized: image assets grouped into
  purpose-based subfolders, the single stylesheet split into multiple files by
  concern, and the page markup restructured semantically — while the single-page
  experience, the entry point, and zero-config GitHub Pages deployment are preserved.
- **FR-010**: The maintenance guide (site README) MUST document the folder structure,
  naming rules, and diagram-editing workflow so that it matches reality exactly —
  including the removal of stale entries and the correction of every outdated
  filename list.
- **FR-011**: After reorganization, ALL current page content MUST remain: every
  section, heading, statistic, diagram, screenshot, caption, and the downloadable
  PDF report — with no dead links and no missing visuals.
- **FR-012**: The reorganization MUST NOT change the site's visual identity or
  require any change outside the site folder to function.

### Key Entities *(include if feature involves data)*

- **Page asset**: any file displayed or linked by the page (SVG diagrams, raster
  screenshots, logo, PDF report). Key attributes: filename, format, byte size,
  display dimensions, caption/context, on-page role.
- **Editable diagram source**: the `.drawio` file paired with each published `.svg`
  diagram; must stay alongside its published twin through any reorganization.
- **Maintenance guide**: the site README; the single documented source of truth for
  structure, naming, and workflows.
- **Crawler metadata**: page-level declarations (title, description, language,
  preview image, structured project/image descriptions) that engines consume.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of images on the page have descriptive filenames following the
  documented convention and non-empty descriptive text (verified by audit).
- **SC-002**: Total image bytes transferred on a fresh load drop by at least 60%
  from the current 2.2 MB baseline; no single raster image exceeds ~250 KB.
- **SC-003**: Zero broken image references: the set of image files referenced by the
  page exactly matches files present on disk.
- **SC-004**: 100% of current page content (sections, statistics, diagrams,
  screenshots, captions, PDF download) is present after reorganization.
- **SC-005**: The page earns no "image missing dimension", "next-gen format",
  "properly size images", or "lazy-load below-the-fold" audit failures in a standard
  web performance/SEO audit tool.
- **SC-006**: The maintenance guide's inventory tables match on-disk files exactly
  (no stale rows, no undocumented files).

## Clarifications

### Session 2026-09-03

- Q: How far should the reorganization go? → A: Full modular split — group image assets into purpose subfolders, split the stylesheet into separate files by concern, and restructure the markup semantically.
- Q: How should raster images be optimized for search ranking? → A: Delegated to best judgment. Chosen: keep original .png/.jpg formats and compress/downsize hard (no WebP conversion) so originals stay reusable in the internship report.
- Q: How much crawler-facing SEO infrastructure should be included? → A: Full package — social preview tags, structured data, robots.txt, and a sitemap listing the page and its images.

## Assumptions

- The site remains a single-page, static landing site deployed from the `site/`
  folder; no backend or build step is introduced.
- The site's visual identity (colors, section rhythm, typography) is preserved;
  this feature improves structure and assets, not the design language.
- English remains the page language; the PDF report file name and location stay
  stable so the download button keeps working.
- All statistics and technical claims on the page are truthful and remain
  unchanged by this work.
- The KSF Space logo keeps its existing filename as the one named exception to the
  image naming convention (its name is a brand asset, not a content description).
- Search-ranking work targets on-page and file-level optimization that the author
  can verify and control; no external search-console or analytics account is
  assumed to exist.
- Images marked "capture needed" in the current README are either already provided
  under equivalent descriptive names (the SAR and dashboard screenshots exist) or
  remain documented as future captures; no new screenshots are fabricated.
