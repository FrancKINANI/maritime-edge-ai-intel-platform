# Validation Guide — SEO Image Optimization & Site Reorganization

How to prove the feature works after implementation. Checks are runnable from
the repository root; the final visual check needs a human with a browser.

## 1. Reference audit (automated, pass/fail)

From the repo root:

```bash
# a) Every image referenced by index.html exists on disk under that path
python3 - <<'EOF'
import re, pathlib
html = pathlib.Path("site/index.html").read_text()
refs = re.findall(r'(?:src|href)="([^"]+\.(?:png|jpe?g|svg|pdf))"', html)
missing = [r for r in refs if not (pathlib.Path("site") / r.lstrip("./")).exists()]
print("refs:", len(refs), "| missing:", missing)
assert not missing
EOF

# b) Every <img> has alt text and width/height attributes
python3 - <<'EOF'
import re, pathlib
html = pathlib.Path("site/index.html").read_text()
imgs = re.findall(r'<img[^>]*>', html)
bad = [i[:80] for i in imgs if 'alt=' not in i or 'width=' not in i or 'height=' not in i]
print("imgs:", len(imgs), "| missing alt/width/height:", len(bad))
assert not bad
EOF

# c) Total image weight (excluding the PDF) is ≤ ~900 KB and no raster > 250 KB
find site/assets/img -type f \( -name '*.jpg' -o -name '*.png' -o -name '*.svg' \) \
  -exec du -k {} + | sort -rn

# d) CSS split preserved every rule: concatenation rule-count equals the original
#    (run against git show HEAD:site/style.css before finalizing)
```

Expected outcome: zero missing refs, zero images lacking attributes, raster
total well under the 2.2 MB baseline (~0.7 MB), and identical rule count across
the split CSS files.

## 2. Local serve check

```bash
python3 -m http.server 8000 --directory site
# open http://localhost:8000/ in a browser
```

Expected outcome: page renders with all 13 images + logo visible in their
captioned figures; report button downloads `assets/doc/rapport_stage.pdf`;
navigation smooth-scrolls; no console errors; the layout does not jump while
images load.

## 3. SEO spot-checks (in the browser's rendered source)

- Head contains one canonical URL, `og:image` pointing at an absolute
  `…/screenshots/…docker-monitoring.jpg` URL, `twitter:card`, and a JSON-LD
  `@graph` script block.
- `http://localhost:8000/robots.txt` and `/sitemap.xml` return 200; sitemap
  uses the same absolute base URL as the canonical tag and lists image entries.
- Each image filename follows `ksf-space-maritime-edge-ai-intel-platform-<slug>`.
- Alt text reads as a sentence describing content; captions sit under every
  figure.

## 4. Mobile & accessibility pass (manual)

- Resize to ≤375 px: sections stack correctly, no horizontal scroll.
- Keyboard: tab through nav, focus is visible; headings run h1 → h2 → h3
  without skips.
- Lighthouse/PageSpeed on the deployed URL (later, after the site is pushed):
  no failures for "properly size images", "next-gen formats" (n/a — standard
  formats chosen deliberately), "defer offscreen images", or "image elements do
  not have explicit width and height".

## 5. Content integrity checklist (manual diff)

Before/after the push: all 8 sections and their ids, the hero stats (6 / 122 /
5 / 75%), the test-grid numbers (115 / 7 / 0 / 60%), every callout, the footer
links, and the report download are present with identical wording.
