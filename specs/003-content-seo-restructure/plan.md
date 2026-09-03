# Implementation Plan: Content Restructure & SEO Copy

**Branch**: `003-content-seo-restructure` | **Date**: 2026-09-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-content-seo-restructure/spec.md`

## Summary

Rewrite the visible copy and structure of all 8 content sections (plus title/meta
description) into one flowing, search-friendly case study. Current visible text:
**1,276 word tokens**. Section order stays largely intact (it already follows
problem → sensor → edge paradigm → system → model → console → quality →
outlook) but *internal* structure is rebalanced and sections get single-purpose
jobs: duplicated explanations are moved to their most relevant home, thin
sections are enriched with moved figures + short copy, verbose paragraphs are
condensed, and every H2/H3 + opening sentence is rewritten to carry the section's
real search topic naturally. Result target: ~1,050–1,150 word tokens (no growth,
≥10% leaner), zero lost facts, zero broken references.

## Technical Context

**Language/Version**: HTML5 copy + markup restructure; CSS/JS from feature 002
are untouched except where section ids/nav labels change (scrollspy list,
possible nav re-label).

**Primary Dependencies**: none. Pure content editing of `site/index.html`
(+ `assets/js/main.js` id list if section ids change) (+ optional nav label
tweaks).

**Storage / Hosting**: static GitHub Pages (unchanged).

**Testing**: no automated suite. Validation = fact-anchor checklist (spec US3),
keyword coverage scan (US2), duplication audit (SC-003), token/word-count
measurement (SC-004), and re-run of the 001/002 audits (image refs, alt+dims,
CSS order, robots/sitemap, brace balance). Human read-through by the owner.

**Constraints**: truthful facts only; no new assets/dependencies; single H1;
correct h2→h3 hierarchy; ids/anchors/scrollspy/JSON-LD/sitemap stay consistent;
figures keep their descriptive alts; report PDF reachable; design/UI untouched.

**Scale/Scope**: `site/index.html` (full content rewrite), `site/assets/js/main.js`
(scrollspy id list — only if ids change), maybe `site/README.md` section mentions.
No other files.

### Current composition & duplication audit (evidence for the restructure)

| # | Section (id) | Today | Problems found |
|---|---|---|---|
| 1 | challenge | Intro + "why legacy AIS fails" + dark-vessel callout + **bandwidth bottleneck** subsection + dark-vessel figure | Bandwidth story belongs with edge AI motivation (it appears again in edge-ai + hero subtitle + constraints card) |
| 2 | sar | 3 H3s (physics / polarization / Copernicus) + 2 figures (single-vessel, 5 pipelines) + 5 pills | Copernicus paragraph sits after physics though it's the *data source*; long |
| 3 | edge-ai | Architecture SVG + constraints grid + 2 H3s + onboard-reasoning callout | Architecture SVG duplicates the hero diagram → repetition; paradigm-shift text re-explains bandwidth (see #1) |
| 4 | architecture | Data-flow SVG + 6 service cards + zone figure + docker figure | 2 figures + 6 dense cards = overload; docker proof is an *ops* artifact (belongs with CI/CD/testing); TLE figure (in #5) belongs beside the Satellite Monitor card |
| 5 | detection | YOLOv8n + INT8 table + result callout + overlay figure + **TLE fallback figure** | TLE is satellite-monitor service detail, not the neural engine → move to #4 |
| 6 | dashboard | 3 mode cards + latency callout | Thin intro copy; fine otherwise |
| 7 | testing | CI/CD SVG + 4 stat numbers | Thinnest section (no sentences at all) → adopt docker figure from #4 + 2–3 sentence ops copy |
| 8 | conclusion | 2 long paragraphs + 4 takeaways + final line | Recaps every earlier section at length; tighten |

Known repeated ideas to de-duplicate (SC-003): bandwidth bottleneck (×3), high-level architecture SVG (hero + edge-ai), docker runtime proof, microservices description (edge-ai H3 vs architecture), INT8 compression (hero stat vs conclusion card vs detection table — keep stat/card as reinforcement, cut *prose* duplication only).

## Constitution Check

*GATE: Must pass before implementation.*

| Principle | Status | How the plan satisfies it |
|---|---|---|
| IV. Content (amended v1.1.0) | ✅ | Owner-approved restructure (this plan is the approval gate); facts/stats stay accurate; anchors & references kept consistent; PDF reachable |
| I. Static, dependency-free | ✅ | Copy/markup only |
| II. SEO image discipline | ✅ | Alt/captions preserved & refreshed with new headings; no asset renames |
| III. Diagrams stay editable | ✅ | Figures move, not rename; SVG/drawio pairs untouched |
| V. Accessibility & performance | ✅ | Single H1, heading hierarchy, no new bytes |
| VI. Simplicity | ✅ | One HTML rewrite + id list; no new architecture |

No violations → Complexity Tracking table empty.

## Project Structure

### Documentation (this feature)

```text
specs/003-content-seo-restructure/
├── spec.md               # Feature specification (clarifications resolved)
├── plan.md               # This file
├── checklists/
│   └── requirements.md   # Spec quality checklist (passing)
└── tasks.md              # Created by $speckit-tasks after plan approval
```

research.md/quickstart.md not generated: no technical unknowns; the regression
suites live in features 001/002 and are re-run verbatim.

### Source Code (only `site/` touched)

```text
site/index.html            # full content/structure rewrite (copy, H2/H3, figure placement)
site/assets/js/main.js     # scrollspy id list only if section ids change
site/README.md             # one-line mention if nav/section naming changes
```

### Proposed narrative & per-section plan (old → new)

**Arc**: *The threat → the sensor → why the brain must be in orbit → the system → the model → the console → the engineering → the outlook.*

**1. Challenge** → H2: *"Maritime Domain Awareness and the Dark Vessel Problem"*
- Keep: MDA definition intro; cooperative-AIS limitation (dark vessels = disabled/spoofed AIS → illegal fishing, smuggling, sanctions evasion); dark-vessel figure; add one closing handoff sentence pointing to SAR (sensors that don't depend on cooperation).
- Move out: the whole "Bandwidth Bottleneck" subsection → becomes the opening hook of edge-ai (#3).
- Tighten: merge 2 intro paragraphs into one topic-first opening containing "maritime domain awareness" and "dark vessel detection" early.

**2. SAR Data** → H2: *"Sentinel-1 SAR Satellite Imagery for Vessel Detection"*
- New internal order: opening sentence (SAR = active sensor; all-weather, night) → **Copernicus Data Space Ecosystem as the data source** → physics of SAR (corner-reflector effect) → VH cross-polarization for contrast → pills → figures (single-vessel SAR + the 5 preprocessing pipelines).
- Tighten: fold the three H3s into tighter paragraphs; keep "5 preprocessing pipelines (A–E)" mention next to its figure.

**3. Edge AI** → H2: *"Orbital Edge AI: Running Vessel Detection in Space"*
- New opening: the *moved* bandwidth bottleneck (hours-to-days latency → tactical intervention impossible) as the motivation for computing in orbit.
- Keep: constraints grid (thermal/power/compute/bandwidth); "instead of downloading data, upload the intelligence" idea; microservices + Redis pub/sub (short, pointing to #4 for detail); onboard-reasoning callout (metadata ping vs secondary segmentation of dark vessels in protected zones).
- Remove: the duplicate architecture SVG (hero already shows it; #4 is the deep dive). Its JSON-LD anchor moves to the hero figure (single occurrence of the id).

**4. Architecture** → H2: *"Microservices Architecture for Maritime Surveillance"*
- Keep: data-flow SVG; 6 service cards in pipeline order (ingestor :8001 → preprocessor :8000 → detector :8003 → satellite monitor :8004 → aggregator :8002 → dashboard :8501).
- Move in: **TLE fallback figure** (SatNOGS → Celestrak → stale cache) beside the Satellite Monitor card — it illustrates graceful degradation for that service.
- Keep: zone-classification figure (Z1 territorial / Z2 EEZ / Z3 high seas) as the aggregator's zone context.
- Move out: docker-monitoring figure → #7 (ops proof).
- Add: 1–2 sentence handoff into the neural engine (#5).

**5. Detection** → H2: *"YOLOv8 INT8 ONNX Inference for SAR Ship Detection"*
- Keep: YOLOv8n (anchor-free) explanation; INT8-vs-FP32 comparison table; result callout (mAP retained); detection-overlay figure.
- Move out: TLE fallback figure → #4. Add opening sentence with "vessel detection", "INT8 quantization", "ONNX" naturally.

**6. Dashboard** → H2: *"Ground Station Dashboard for Maritime Vessel Monitoring"*
- Keep: 3 mode cards (upload / satellite query NORAD 39634 SGP4 / monitoring) + latency callout (days → minutes); tighten intro paragraph to front-load "real-time vessel monitoring".

**7. Testing** → H2: *"Testing, CI/CD, and Containerized Operations"*
- Move in: docker-monitoring figure (7 services healthy) from #4.
- Add: 2–3 sentence ops copy ("122 tests across 9 suites… linting, SAST… 60% coverage threshold") so the section is no longer numbers-only; keep CI/CD SVG + 4 stat cards (115 / 7 / 0 / 60%).

**8. Conclusion** → H2: *"The Future of Maritime Edge AI"*
- Tighten lead paragraphs to one short recap (SAR bypasses weather, microservices for resilience, INT8 for CPU-bound orbit inference → dark vessel detection + AIS correlation); keep the 4-takeaway grid; shorten the closing line; keep the "data → intelligence in orbit" idea as the memorable ending.

**9. Title & meta description** (head, no visual change):
- Title (~60 chars): *"Dark Vessel Detection from Sentinel-1 SAR with Edge AI — KSF Space"*
- Meta description (~155 chars): *"How the KSF Space Foundation detects dark vessels from Sentinel-1 SAR imagery using orbital edge AI — YOLOv8 INT8 ONNX inference across a 6-microservice pipeline."*

**Sample rewrites (tone of the pass; final wording during implementation):**
- Before (challenge): *"Traditional real-time vessel monitoring relies heavily on the Automatic Identification System (AIS). AIS requires vessels to broadcast their GPS coordinates, identity, and heading. However, AIS is a cooperative technology — it relies on the compliance of the vessel's crew."*
- After: *"Real-time vessel monitoring leans on AIS — but AIS is cooperative: it only works when a vessel chooses to broadcast its GPS position, identity, and heading."* (same claim, one sentence)
- Before (conclusion): *"The collaboration of the KSF Space Foundation and the architectural vision of the Maritime Edge AI Intelligence Platform demonstrates a profound leap in space-based surveillance."*
- After (rewritten as plain recap, no puffery): *"Together, SAR all-weather sensing, a resilient microservices platform, and INT8-quantized onboard inference turn hours-to-days latency into near-real-time dark vessel alerts."*

### SEO target keyword placements (intent; verified after implementation)
dark vessel detection (H2 #1 + meta), maritime domain awareness (first ¶ #1),
Sentinel-1 SAR / SAR vessel detection (H2 #2), Copernicus Data Space (¶ #2),
orbital edge computing / edge AI (H2 #3), microservices architecture (H2 #4),
YOLOv8 + INT8 quantization + ONNX (H2 #5 + table), real-time vessel monitoring
(H2 #6), CI/CD (H2 #7), satellite surveillance (¶ #8/meta). No phrase repeated
in adjacent sentences.

### Verification checklist (post-implementation)
1. Fact anchors from spec US3/1 — all present & accurate.
2. Keyword scan vs target list (≥90% found; ≥half in headings/first ¶s).
3. Duplication audit of the 5 known repeated topics — each addressed once.
4. Word count ≤ 1,276 (target ≤ ~1,150); single H1; hierarchy h1→h2→h3 valid.
5. Anchor audit: nav ↔ section ids ↔ scrollspy list ↔ JSON-LD ids consistent;
   zero broken image/href refs; audits of 001 (refs/alts/robots/sitemap/CSS
   order) and 002 (tokens-vs-baseline for UI files) re-pass.
6. Owner read-through of the full new copy before commit.

## Complexity Tracking

No constitution violations — table intentionally empty.
