# Validation and scoring

The rules live in three modules: `app/validation.py` (photos and body data), `app/fitting.py` (size and garment length) and `app/scoring.py` (reliability score). The thresholds are empirical and deliberately lenient; recalibrate them once real user data has been collected.

## 1. Photo checks (on upload)

Done with the try-on model's own pose detection and human parsing, about 1 second per photo.

| Check | Result | Rule |
|---|---|---|
| Resolution | Block / warn | Short side < 400 px blocks, < 700 px warns |
| Sharpness | Block / warn | Laplacian variance < 15 blocks, < 50 warns |
| Single person | Block | 0 or more than 1 person detected |
| Full body in frame | Block | The silhouette touches the top or bottom edge, or the ankles are not visible |
| Person too small | Warn | The person is less than half the image height |
| View | Block | Front vs. back is told apart by "face pixels / (face + hair)", side by "shoulder span / height"; blocks if it does not match the slot the photo was put in |
| Lower legs covered | Warn | Below the knees, trouser / skirt pixels outnumber skin |
| Arms covered | Warn | Arm skin is less than 1% of the person's area |

If any photo is blocked, nothing from the upload is saved, and the page shows the reason on the photo in question.

## 2. Body data credibility

| Level | Rule | Result |
|---|---|---|
| Single values | Height 120–220, weight 30–200, chest 60–160, waist 45–160, hips 60–170, shoulder width 28–60 (cm / kg) | Out of range: untrusted |
| BMI | Outside 13–50 | Untrusted |
| | Outside 16–40 | Suspicious |
| Circumference relations | Waist more than 15cm larger than both chest and hips; waist / height outside 0.33–0.8; shoulder width / height outside 0.19–0.31 | Suspicious |
| Against the photos | Hip circumference / hip width in the photo outside 2.2–4.2; BMI ≥ 35 but hip width < 36cm (< 31cm when ≥ 30); BMI ≤ 18.5 but hip width > 40cm; measured shoulder width differs from the entered one by more than 20–30% | Suspicious |
| Across the three views | Leg-length ratio differs by > 0.06 between front and back; clothing colour differs a lot between photos | Suspicious |

Final level: any "untrusted" → `untrusted`; a required field missing → `unverified`; any "suspicious" → `suspicious`; otherwise `trusted`. Untrusted data is never used for size selection or length calculation.

## 3. Size and garment length (fitting.py)

**Picking a size**: compare the size chart's garment measurements with the body measurements plus ease (chest +4, waist +0, hips +2cm; high-stretch fabric gets 6cm more, slight stretch 2cm more) and pick the smallest size that fits. Tops and dresses are matched on chest (dresses also on waist), bottoms on waist and hips.

- No circumferences but a usual size: use the usual size.
- Neither: use the middle size and say so.
- No size fits: use the largest size and warn that it may be tight.

**Length**: with a garment length in the size chart and the person's height, the hem position is computed (see [Architecture](architecture.md#2-building-the-repaintable-region-build_agnostic)); if either is missing, the length is not calibrated and the score explains why.

## 4. Reliability score (scoring.py)

Points are deducted from 100, each deduction with its reason, in two parts:

**Visual reliability**: can this image stand for how the garment looks on this person?

| Deduction | Condition |
|---|---|
| -20 | The garment shows the lower legs, but they are covered in the photo (the legs are inferred) |
| -15 | The garment shows the arms, but they are covered in the photo |
| -15 | The photo did not go through the quality checks |
| -10 | Side / back view |
| -10 | The product image is an on-model / generated image |
| -10 | Complex construction such as draping, lace or cut-outs |
| -10 | Turbo mode |
| -10 | Garment length not calibrated against the size chart |
| -5 | Prints, text, stripes and similar details; hanging shot; missing length or sleeve information; blurry or low-resolution photo |
| -3 | Standard mode (compared with quality mode) |
| **QC** | Generated length deviates from the size chart by more than 5cm: minus the number of cm, at most 30 |
| **QC** | Visible legs are more than 10% thinner or thicker than in the original photo: minus the percentage, at most 30 |

**Fit basis**: is there enough data to judge the fit? Body data untrusted -60, suspicious -20, missing -40; no size chart -40; each key circumference for the category that was not entered -10; size chart from mock data or recognition -10; no stretch information -10; no fit information, no model reference -5 each.

**Overall** = visual × 60% + fit × 40%; ≥ 80 is High (高), 60–79 Medium (中), < 60 Low (低).

**QC veto**: if any single QC deduction is ≥ 20 points, the overall score is capped at 59 (Low), and the page shows a red "QC failed (质检未通过): reason".

The score is computed twice: before generation it is an estimate based on the data (shown as "pending QC" (待质检)), after generation it includes the QC results (shown as "QC checked" (已质检)).

## Tuning the rules

- Thresholds and deductions are the constants and functions at the top of the three modules above; run `pytest tests` after changing them.
- Collect user feedback on whether results "look right" and use it to recalibrate the deduction weights.
