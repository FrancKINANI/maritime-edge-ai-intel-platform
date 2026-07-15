# Traceability Verification Report

**Project:** Maritime Edge AI Intel Platform
**Protocol:** PH0-CORR-002_density_targeted
**Date:** 2026-07-15 19:00:27
**Status:** ✅ PASSED

## 1. Summary
This document verifies the end-to-end traceability from AIS-density targeting to the final processed SAR tiles.

## 2. Evidence
| Field | Expected (target_trace.json) | Actual (metadata.json) | Match |
| :--- | :--- | :--- | :--- |
| **Cell Index** | 413 | 413 | Yes |
| **Bounding Box** | [-6.0, 35.5, -5.5, 36.0] | [-6.0, 35.5, -5.5, 36.0] | Yes |
| **Protocol ID** | PH0-CORR-002_density_targeted | PH0-CORR-002_density_targeted | Yes |

## 3. Scene Details
- **Targeted Scene:** `S1D_IW_GRDH_1SDV_20260711T061903_20260711T061928_003622_00673D_224C`
- **Pipeline Used:** `Pipeline D (VV Polarization)`
- **Tiles Generated:** 6408

## 4. Verification Trace
```json
{
  "target_density_cell_index": 413,
  "target_cell_bbox": [
    -6.0,
    35.5,
    -5.5,
    36.0
  ],
  "protocol": "PH0-CORR-002_density_targeted"
}
```

---
*Generated automatically by Traceability Suite.*