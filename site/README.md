# Landing Site — Maritime Edge AI Intelligence Platform

## Quick Start

1. Open `index.html` in a browser to preview the site
2. Add your images to the `images/` folder (see naming convention below)
3. Add your PDF report as `rapport_stage.pdf` (already included)
4. Push to GitHub — GitHub Pages deploys automatically

## GitHub Pages Deployment

This site is configured for **automatic deployment** via GitHub Actions:

1. Push the `site/` folder to your `main` or `master` branch
2. Go to your repo → **Settings → Pages**
3. Under **Source**, select **GitHub Actions**
4. The workflow (`.github/workflows/deploy-pages.yml`) deploys on every push
5. Your site will be live at: `https://<username>.github.io/<repo-name>/`

### First-time setup
- Enable GitHub Pages in repo Settings → Pages → Source: **GitHub Actions**
- The workflow runs automatically on push to main/master

## Editing Diagrams with draw.io (Recommended)

All 6 diagrams are provided as **`.drawio` files** — fully editable with a free visual editor.

### How to edit

1. Go to **[app.diagrams.net](https://app.diagrams.net)** (free, no account needed)
2. Click **Open Existing Diagram** → select the `.drawio` file
3. **Drag** boxes to reposition them
4. **Double-click** any text to edit it
5. **Resize** boxes by dragging the corners
6. **Change colors** by selecting a shape → Format panel on the right
7. **Add/remove** shapes from the toolbar
8. **Export** as SVG or PNG: File → Export as → SVG/PNG

### Available `.drawio` files

| File | What it diagrams |
|------|------------------|
| `ksf-space-maritime-edge-ai-intel-platform-architecture.drawio` | System architecture — 6 services, Redis, APIs |
| `ksf-space-maritime-edge-ai-intel-platform-data-flow.drawio` | End-to-end pipeline — 6 stages with data products |
| `ksf-space-maritime-edge-ai-intel-platform-zone-classification.drawio` | Maritime zones Z1/Z2/Z3 with properties |
| `ksf-space-maritime-edge-ai-intel-platform-tle-fallback.drawio` | TLE fallback chain — SatNOGS → Celestrak → Cache |
| `ksf-space-maritime-edge-ai-intel-platform-pipeline-comparison.drawio` | 5 preprocessing pipelines (A–E) comparison |
| `ksf-space-maritime-edge-ai-intel-platform-ci-pipeline.drawio` | CI/CD pipeline — 4 job stages |

### Tips
- **Move a box:** click and drag it
- **Resize:** drag the blue handles on the corners/edges
- **Edit text:** double-click the text inside a box
- **Change colors:** select shape → right panel → Fill Color
- **Add arrow:** click a shape edge → drag to another shape
- **Delete:** select → press Delete key
- **Undo:** Ctrl+Z

## Image Naming Convention

All images must follow this exact naming convention for SEO optimization:

```
ksf-space-maritime-edge-ai-intel-platform-<descriptive-slug>.<ext>
```

### Required Images

| File Name | Description | Status |
|-----------|-------------|--------|
| `ksf-space-maritime-edge-ai-intel-platform-architecture.svg` | System architecture diagram | ✅ Included |
| `ksf-space-maritime-edge-ai-intel-platform-data-flow.svg` | End-to-end data flow pipeline | ✅ Included |
| `ksf-space-maritime-edge-ai-intel-platform-zone-classification.svg` | Maritime zones Z1/Z2/Z3 | ✅ Included |
| `ksf-space-maritime-edge-ai-intel-platform-tle-fallback.svg` | TLE fallback chain | ✅ Included |
| `ksf-space-maritime-edge-ai-intel-platform-pipeline-comparison.svg` | 5 preprocessing pipelines | ✅ Included |
| `ksf-space-maritime-edge-ai-intel-platform-ci-pipeline.svg` | CI/CD pipeline stages | ✅ Included |
| `ksf-space-maritime-edge-ai-intel-platform-dark-vessel-detection.png` | Dark vessel detection screenshot | ⬜ Capture needed |
| `ksf-space-maritime-edge-ai-intel-platform-sar-raw-scene.png` | Raw Sentinel-1 scene | ⬜ Capture needed |
| `ksf-space-maritime-edge-ai-intel-platform-detection-overlay.png` | YOLOv8 detection result | ⬜ Capture needed |
| `ksf-space-maritime-edge-ai-intel-platform-satellite-orbit.png` | Satellite ground track | ⬜ Capture needed |
| `ksf-space-maritime-edge-ai-intel-platform-dashboard-upload.png` | Dashboard upload mode | ⬜ Capture needed |
| `ksf-space-maritime-edge-ai-intel-platform-dashboard-satellite-query.png` | Dashboard satellite query | ⬜ Capture needed |
| `ksf-space-maritime-edge-ai-intel-platform-dashboard-monitoring-events.png` | Dashboard monitoring mode | ⬜ Capture needed |
| `ksf-space-maritime-edge-ai-intel-platform-test-results.png` | Test results output | ⬜ Capture needed |

## Adding Images

1. Take screenshots or export diagrams
2. Rename files using the convention above
3. Place them in the `images/` folder
4. The HTML has fallback placeholders that show the expected filename if an image is missing

## PDF Report

Place your final report PDF as:
```
ksf-space-maritime-edge-ai-intel-platform-report.pdf
```

## Google Sites Deployment

If deploying to Google Sites:
1. Upload all images through the Google Sites editor
2. Embed the content using Google Sites' text and image blocks
3. Use the Gemini-generated article text (already structured in the HTML)
4. Add the PDF as a downloadable link

## File Structure

```
site/
├── index.html          # Main page (all content)
├── style.css           # All styles
├── .nojekyll           # Prevents Jekyll processing
├── README.md           # This file
└── images/             # All images and diagrams
    ├── *.svg           # 6 SVG diagrams (included)
    ├── *.png           # Screenshots
    └── rapport_stage.pdf  # Downloadable report
```
