# Landing Site — Maritime Edge AI Intelligence Platform

Static landing page for the KSF Space Foundation internship project, deployed
to **GitHub Pages** with zero build step: plain HTML + CSS + vanilla JavaScript.

## Quick Start

1. Open `index.html` in a browser to preview the site — or serve locally:
   ```bash
   python3 -m http.server 8000 --directory site
   ```
2. Add new images to `assets/img/` following the [naming convention](#image-naming-convention)
3. Replace the report PDF at `assets/doc/rapport_stage.pdf`
4. Push to GitHub — the GitHub Actions workflow deploys automatically

## GitHub Pages Deployment

Automatic deployment via `.github/workflows/deploy-pages.yml`:

1. Push the `site/` folder to your `main` or `master` branch
2. Repo → **Settings → Pages** → Source: **GitHub Actions**
3. The workflow deploys on every push touching `site/**`
4. Live at: `https://franckinani.github.io/maritime-edge-ai-intel-platform/`

### SEO / crawler files

- `robots.txt` allows crawling and points to the sitemap.
- `sitemap.xml` lists the page with `<image:image>` entries for every content
  image. If your GitHub Pages URL differs, update the base URL in
  `sitemap.xml`, `robots.txt`, and the `<link rel="canonical">` / `og:*` /
  JSON-LD block in `index.html` — the same base URL is used everywhere.

## Folder Structure

```text
site/
├── index.html              # Single page (all content + SEO metadata)
├── robots.txt              # Crawl rules + sitemap pointer
├── sitemap.xml             # Page + image sitemap
├── .nojekyll               # Prevents Jekyll processing
├── README.md               # This file
└── assets/
    ├── css/                # Styles split by concern (order matters: base → layout → components → responsive)
    │   ├── base.css        # Reset, design tokens, base element styles
    │   ├── layout.css      # Nav, hero, sections, grids, footer
    │   ├── components.css  # Buttons, cards, callouts, tables, image figures
    │   └── responsive.css  # All media queries (must load last)
    ├── js/
    │   └── main.js         # Nav toggle, smooth scroll, scroll background
    ├── img/
    │   ├── diagrams/       # 6 SVG diagrams + their editable .drawio sources
    │   ├── screenshots/    # SAR + dashboard + docker captures (optimized JPEG)
    │   └── brand/          # KSF Space logo (only naming-convention exception)
    └── doc/
        └── rapport_stage.pdf   # Downloadable internship report
```

Keep the CSS split load order `base → layout → components → responsive`:
all selectors are namespaced per file, and media-query overrides must stay last.

## Editing Diagrams with draw.io

Each published `.svg` has an editable `.drawio` source in `assets/img/diagrams/`.

1. Go to [app.diagrams.net](https://app.diagrams.net) (free, no account needed)
2. **Open Existing Diagram** → pick the `.drawio` file
3. Drag/resize shapes, double-click text to edit, recolor in the Format panel
4. **File → Export as → SVG** and overwrite the matching `.svg` file

### Available diagrams

| Diagram | What it shows |
|---------|---------------|
| `ksf-space-maritime-edge-ai-intel-platform-architecture` | System architecture — 6 services, Redis, APIs |
| `ksf-space-maritime-edge-ai-intel-platform-data-flow` | End-to-end pipeline stages and data products |
| `ksf-space-maritime-edge-ai-intel-platform-zone-classification` | Maritime zones Z1/Z2/Z3 with properties |
| `ksf-space-maritime-edge-ai-intel-platform-tle-fallback` | TLE fallback chain — SatNOGS → Celestrak → Cache |
| `ksf-space-maritime-edge-ai-intel-platform-pipeline-comparison` | 5 preprocessing pipelines (A–E) |
| `ksf-space-maritime-edge-ai-intel-platform-ci-pipeline` | CI/CD pipeline — 4 job stages |

## Image Naming Convention

Every image must follow this exact naming convention for SEO:

```text
ksf-space-maritime-edge-ai-intel-platform-<descriptive-slug>.<ext>
```

The KSF Space logo in `assets/img/brand/` is the only sanctioned exception.

### Current image inventory

Diagrams (`assets/img/diagrams/`, SVG + `.drawio` source pair):

| File | Description |
|------|-------------|
| `…-architecture.svg` / `.drawio` | System architecture — 6 microservices |
| `…-data-flow.svg` / `.drawio` | End-to-end data flow pipeline |
| `…-zone-classification.svg` / `.drawio` | Maritime zones Z1/Z2/Z3 |
| `…-tle-fallback.svg` / `.drawio` | TLE fallback chain |
| `…-pipeline-comparison.svg` / `.drawio` | 5 preprocessing pipelines (A–E) |
| `…-ci-pipeline.svg` / `.drawio` | CI/CD pipeline stages |

Screenshots (`assets/img/screenshots/`, web-optimized JPEG, all raster files
kept under ~250 KB):

| File | Description |
|------|-------------|
| `…-sar-single-vessel.jpg` | Raw Sentinel-1 SAR — single vessel |
| `…-sar-multi-vessel-detection.jpg` | Dark vessel detection — SAR multi-vessel |
| `…-sar-vessel-detection.jpg` | YOLOv8 detection overlay on a SAR tile |
| `…-docker-monitoring.jpg` | Docker container monitoring — 7 services |
| `…-dashboard-upload.jpg` | Dashboard upload mode |
| `…-dashboard-satellite-query.jpg` | Dashboard satellite query |
| `…-dashboard-monitoring-events.jpg` | Dashboard monitoring events |

Branding (`assets/img/brand/`):

| File | Description |
|------|-------------|
| `ksf.space-logo-high.png` | KSF Space Foundation logo (nav bar) |

Report (`assets/doc/`):

| File | Description |
|------|-------------|
| `rapport_stage.pdf` | Downloadable internship report |

## Adding a New Image

1. Take the screenshot or export the diagram
2. Name it using the convention above and place it in the matching folder
3. Reference it in `index.html` as a `<figure class="image-placeholder">` with:
   - descriptive `alt` text stating what the image shows,
   - `width`/`height` matching the file's intrinsic pixels (prevents layout shift),
   - `loading="lazy"` + `decoding="async"` (except above-the-fold images),
   - a `<figcaption>` label under the image
4. Make the image clickable: wrap the `<img>` in
   `<a class="lightbox-link" href="...same src...">` (skip the nav logo) —
   `assets/js/main.js` turns these into the lightbox viewer automatically.
   If the image has an `onerror` fallback, target the figure with
   `this.closest('figure')` so it still works through the wrapper
5. Add it to this README's inventory and, if it is a content image, to
   `sitemap.xml`
6. Verify locally (`python3 -m http.server 8000 --directory site`) before pushing
