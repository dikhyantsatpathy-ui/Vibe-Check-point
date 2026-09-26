# Fix: Genuine Documents (Passport / PAN / Aadhaar) Getting Falsely Flagged

## Context for the AI agent working on this

This is the **NO-CAP SIH document-fraud-screening** codebase. The forensics/tampering
pipeline (`app/forensics.py`, `app/tampering.py`, `app/doc_forgery.py`,
`app/screening.py`, `app/main.py`) is meant to catch forged/AI-generated/tampered
identity documents. Right now it is **over-flagging genuine documents** — real
photos of real passports, PAN cards, and Aadhaar cards taken on ordinary phone
cameras (and low-quality laptop/webcam cameras) are being marked REVIEW/FAIL.

Your job is to fix this **without weakening real fraud detection**. Read the
whole document before editing anything — the five problems below compound each
other, so fixing only one will just move the false positive somewhere else.

---

## Problem 1 (root cause, fix first): boolean AND-gate verdicts compound independent noise

There are **three separate places** in the codebase that turn "any single check
returned `ok: False`" into an automatic failure, even though each individual
check is independently probabilistic and none of them is 100% reliable on its
own:

1. `app/tampering.py`, `tamper_analysis()`, bottom of the function:
   ```python
   decided = [c for c in checks if c.get("ok") is not None]
   failed = any(c.get("ok") is False for c in decided)
   passed = decided and all(c.get("ok") is True for c in decided)
   verdict = "PASS" if passed else ("FAIL" if failed else "REVIEW")
   ```
2. `app/forensics.py`, end of the liveness check function:
   ```python
   all_ok = all(c["ok"] is True for c in checks)
   ```
3. `app/screening.py`, final aggregation (two spots):
   ```python
   mod_fail = any(c.get("ok") is False for c in mod_res.get("checks", []))
   ...
   for m in (val_res, tamper_res, face_res):
       if any(c.get("ok") is False for c in m.get("checks", [])):
           can_clear = False
   ```

**Why this causes mass false positives:** `tamper_analysis()` alone runs 7-8
independent checks per document (ela, focus, liveness, ai-generated-or-edited,
spectral-analysis, sensor-noise, copy-move-cloning, dual-stream-forgery). If
each check only misfires on a genuine photo ~8% of the time (realistic, given
Problems 2-4 below), the probability that *at least one* misfires is
`1 - (0.92)^8 ≈ 49%`. Roughly half of all genuine documents get an incorrect
`False` on *some* check purely by chance, and that one `False` currently vetoes
the whole document at three different layers.

Note that `screening.py` around line 1185-1198 (`has_real_tamper`) already
shows the right instinct — it tries to only hard-fail on *meaningful* tamper
signals (ELA HIGH, confirmed AI/edited, liveness failure) rather than any
`False`. But the blanket loop at line ~1228-1231 (`for m in (val_res,
tamper_res, face_res): if any(...) is False: can_clear = False`) undoes that
nuance — a single noisy `sensor-noise` or `copy-move-cloning` false flag still
silently kills `can_clear` even when it wasn't counted as "real tamper" a few
lines above. **This inconsistency is itself a bug to fix.**

### What to do

Replace the boolean AND/OR-gate pattern with a **weighted-evidence** model.
Each check gets a reliability weight; you sum weighted evidence for FAIL and
PASS instead of letting one shaky signal veto everything.

1. In `app/tampering.py`, add a module-level weight table and a scoring
   function, and use it in place of the current `decided/failed/passed` block:

   ```python
   CHECK_WEIGHTS = {
       "dual-stream-forgery": 1.0,
       "ela": 1.0,
       "sensor-noise": 0.8,
       "copy-move-cloning": 0.9,
       "ai-generated-or-edited": 0.5,   # noisiest signal — corroborating, not decisive alone
       "spectral-analysis": 0.4,        # corroborating only
       "focus": 0.2,
       "liveness": 0.2,
       "card-localization": 0.1,
       "medium": 0.1,
   }

   def _weighted_verdict(checks: list[dict]) -> str:
       decided = [c for c in checks if c.get("ok") is not None]
       fail_weight = sum(CHECK_WEIGHTS.get(c["label"].split("-", 1)[0] if c["label"].startswith("liveness-") else c["label"], 0.5)
                          for c in decided if c.get("ok") is False)
       pass_weight = sum(CHECK_WEIGHTS.get(c["label"].split("-", 1)[0] if c["label"].startswith("liveness-") else c["label"], 0.5)
                          for c in decided if c.get("ok") is True)
       if fail_weight >= 1.3:       # needs one strong signal, or two+ weak ones corroborating
           return "FAIL"
       if fail_weight > 0 or pass_weight < 1.0:
           return "REVIEW"
       return "PASS"
   ```

   Then replace the final `verdict = ...` line with `verdict =
   _weighted_verdict(checks)`. Keep `decided`/`failed`/`passed` out of the
   return dict if nothing else in the codebase reads those exact keys (grep
   for `tamper_res.get("verdict")` usage — `screening.py` does read
   `.get("verdict")`, so the returned key name must stay `"verdict"`).

2. In `app/forensics.py`'s liveness function, replace the hard `all_ok = all(...)`
   with the same weighted approach (liveness checks: `challenge_response` /
   `challenge_blink` should be weight 1.0 since they're the actual proof-of-life;
   `anti_screen_replay` 0.6; posture/motion checks 0.3). A single soft signal
   (e.g. `anti_screen_replay` false-triggering on unusual but legitimate
   lighting) should downgrade to `SUSPECT`, not force `SPOOF`.

3. In `app/screening.py`, delete the blanket loop:
   ```python
   for m in (val_res, tamper_res, face_res):
       if any(c.get("ok") is False for c in m.get("checks", [])):
           can_clear = False
   ```
   and instead rely on the `mod_fail` handling already above it (which you'll
   also update to read `mod_res.get("verdict")` from the new weighted verdict
   rather than re-deriving its own `any(...)` — don't compute the same thing
   two different ways in two different places).

---

## Problem 2: AI-detector noise heuristic flags denoised phone photos as "AI-generated"

`app/main.py`, `_pixel_scan()` (~line 286):

```python
suspicious_noise = content and (ratio < 0.04 and fine_noise < 1.5)
```

**Why this misfires:** modern phone cameras (iPhone/Pixel/Samsung) apply heavy
computational-photography noise reduction, especially on close-up, well-lit
shots — exactly the conditions of someone photographing an ID card. The result
is a genuinely smooth, low-noise JPEG straight out of the camera, which is
indistinguishable from this heuristic's definition of "AI-generated."

### What to do

1. Tighten the raw threshold so it only fires on images that are *unnaturally*
   smooth, not just "smooth":
   ```python
   suspicious_noise = content and (ratio < 0.018 and fine_noise < 0.8)
   ```
2. Add EXIF camera provenance as a corroborating signal that raises the bar
   before this heuristic can flag an image. Real phone photos carry `Make`,
   `Model`, `DateTimeOriginal` EXIF tags; AI generator output and
   screenshots/screen-recaptures almost never do. Add a helper:
   ```python
   def _has_camera_exif(image_bytes: bytes) -> bool:
       try:
           from PIL import Image
           img = Image.open(io.BytesIO(image_bytes))
           exif = img.getexif()
           if not exif:
               return False
           # 0x010F = Make, 0x0110 = Model, 0x9003 = DateTimeOriginal
           return any(tag in exif for tag in (0x010F, 0x0110, 0x9003))
       except Exception:
           return False
   ```
   In `_pixel_scan`, only let `suspicious_noise` set `is_ai = True` outright
   when there's no camera EXIF; when camera EXIF *is* present, downgrade the
   result to a soft/advisory finding (`ai_score` capped around 35, `ai_suspected
   = False`) so it can't unilaterally fail a document — it becomes corroborating
   evidence only, consistent with Problem 1's weighting (`ai-generated-or-edited`
   is already weight 0.5, not decisive alone, once Problem 1 is fixed).

3. Do the equivalent for `uniform_reencode` in the same function — it's a
   second, separate absolute-threshold trap (`np.std(flat) < 0.02 and
   np.mean(flat) > 0.01`) with the same "real photos can be very uniform" issue.
   Same EXIF-gated downgrade applies.

---

## Problem 3: dual-stream forgery detector flags denoised flat regions as "digital erasure"

`app/doc_forgery.py`, `analyze_doc_forgery()` (~line 154):

```python
dead_blocks = int(np.sum(non_margin & (block_vars < 0.05)))
inpaint_void = bool(dead_blocks > (non_margin_count * 0.15) and non_margin_count > 40)
```

**Why this misfires:** any 16×16 SRM-residual patch with variance under 0.05 is
treated as evidence of digital erasure/inpainting. A denoised card background,
the blank margin of a passport photo page, or a plain-colored PAN card face
can easily produce >15% of blocks under that variance floor on a genuinely
smooth phone photo — with nothing tampered at all. The detector currently has
no way to distinguish "one contiguous rectangular patch was erased" (real
tamper signature) from "the whole image is uniformly smooth because the phone
denoised it" (normal capture).

### What to do

1. Tighten the raw variance floor (still not sufficient alone, but reduces raw
   sensitivity):
   ```python
   dead_blocks = int(np.sum(non_margin & (block_vars < 0.015)))
   ```
2. **Add spatial contiguity as a requirement.** Real digital erasure/inpainting
   produces a compact, connected blob of dead blocks (a rectangle or blob where
   something was cut/painted out). Denoising produces dead blocks scattered
   broadly across the whole card. Add a connected-component check using the
   block grid you already have (`block_vars` is a 2D grid, `bh × bw`):
   ```python
   from scipy import ndimage  # add scipy if not already a dependency; otherwise
                               # implement a simple flood-fill over the boolean grid

   dead_mask = non_margin & (block_vars < 0.015)
   labeled, num_features = ndimage.label(dead_mask)
   if num_features > 0:
       component_sizes = ndimage.sum(dead_mask, labeled, range(1, num_features + 1))
       largest_component = int(component_sizes.max())
   else:
       largest_component = 0

   # Require the dead area to be concentrated in ONE contiguous region,
   # not scattered noise-reduction artifacts across the whole card.
   inpaint_void = bool(
       largest_component > (non_margin_count * 0.12)
       and largest_component > 20
   )
   ```
   If you'd rather not add a `scipy` dependency, implement a basic
   iterative flood-fill/union-find over the `bool` 2D grid — the grid is small
   (typically well under 100×100 blocks), so a pure-NumPy/Python BFS is fast
   enough at this scale.
3. Keep the existing `seam_anomaly` (max pixel step > 250 AND inpaint_void) as
   an additional corroborating condition — it already requires `inpaint_void`
   to be true first, so fixing #2 automatically tightens this too.
4. Gate this detector by resolution (see Problem 5) since it needs real
   pixel-level texture to say anything meaningful.

---

## Problem 4: ELA uses a fixed re-compression quality regardless of the photo's real compression history

`app/forensics.py`, `ela()` (~line 94):

```python
def ela(data: bytes, quality: int = 92, preview: int = 128):
    ...
    Image.fromarray(rgb).save(first, "JPEG", quality=quality)
```

**Why this misfires:** Error Level Analysis only works reliably when the
re-compression quality (`92` here, hardcoded) is close to the *original*
photo's actual JPEG quality. Real-world document photos frequently arrive
already compressed at a lower quality than 92 — a phone camera's own JPEG
encoder (commonly 80-90 for storage-saving modes), or a photo that passed
through WhatsApp/Telegram/an upload resizer (these typically re-save around
quality 70-80). When the analysis re-encodes an already-lower-quality image at
quality 92, the diff between the two passes is **globally elevated** (because
the whole image is losing/gaining detail relative to a higher target quality,
not just a pasted region), which can push `damaged_blocks` over the `0.15`/`0.30`
thresholds and produce a false `MEDIUM`/`HIGH` ELA status on a completely
untampered image.

### What to do

1. Estimate the image's actual JPEG quality before choosing the ELA
   re-compression quality, so the two are close together (this is what makes
   ELA discriminate localized edits instead of lighting up everywhere). A
   simple approach: try re-encoding at a handful of candidate qualities (e.g.
   `[70, 80, 85, 90, 95]`), and pick whichever produces the lowest mean diff
   against the original — that's the closest match to the image's real
   compression history:
   ```python
   def _estimate_jpeg_quality(rgb: np.ndarray) -> int:
       candidates = [70, 75, 80, 85, 90, 95]
       orig = _to_gray(rgb)
       best_q, best_diff = 92, float("inf")
       for q in candidates:
           buf = io.BytesIO()
           Image.fromarray(rgb).save(buf, "JPEG", quality=q)
           buf.seek(0)
           re_enc = _to_gray(np.asarray(Image.open(buf).convert("RGB")))
           d = float(np.abs(orig - re_enc).mean())
           if d < best_diff:
               best_diff, best_q = d, q
       return best_q
   ```
   Only run this on a downscaled copy (e.g. 256px) to keep it cheap — it does
   not need full resolution to estimate quality, it just needs to run before
   the real ELA pass, which still runs at full resolution using the estimated
   quality instead of the fixed `92`.
2. If the input isn't a JPEG in the first place (came in as PNG/HEIC before
   conversion), keep the current default of `92` — quality-matching only
   matters for images with real JPEG compression history to match.
3. Keep the existing localized-cluster logic (`peak_cluster_damage`) as-is —
   it's already good at distinguishing "small hot region" (real tamper
   signature) from "diffuse elevated diff" (quality-mismatch artifact from this
   bug). Fixing the quality match will make that distinction much cleaner
   because diffuse false-positive diff will mostly disappear.

---

## Problem 5: no resolution/device-adaptive gating

Right now every check (ELA, spectral-analysis, dual-stream-forgery,
sensor-noise, copy-move) runs unconditionally, regardless of how much real
pixel detail the source image actually has. A 2.1MP laptop webcam frame simply
does not carry enough signal for FFT spectral analysis or 16×16-block SRM
residual analysis to say anything meaningful — on such an image these checks
are closer to analyzing noise-on-noise than a real signal, and are likely to
produce spurious REVIEW/FAIL rows.

### What to do

In `app/tampering.py`, before running the per-check block, compute the
resolution of `active_bytes` (width × height) once, and skip/soften checks
that need real detail below a resolution floor — following the same "honest
not-applicable, never a silent pass" pattern the module docstring already
promises for PDFs:

```python
MIN_PIXELS_FOR_TEXTURE_CHECKS = 400_000  # ~640x625, roughly a low-end webcam frame

...
w, h = <decode active_bytes dimensions>
low_res = (w * h) < MIN_PIXELS_FOR_TEXTURE_CHECKS

if low_res:
    checks.append({
        "label": "spectral-analysis", "ok": None,
        "detail": "Resolution too low for reliable spectral/SRM texture analysis — not applicable, verify by other modules.",
    })
    checks.append({
        "label": "dual-stream-forgery", "ok": None,
        "detail": "Resolution too low for reliable dual-stream forgery analysis — not applicable, verify by other modules.",
    })
    # skip calling analyze_doc_forgery() and spectral_analysis() entirely at low res,
    # or call them but discard/override their ok value as above
else:
    # existing calls as today
```

This removes a whole category of false flags on cheap cameras instead of
trying to find one threshold that works for both a 12MP phone sensor and a
2.1MP webcam sensor (there isn't one — their noise/detail characteristics are
fundamentally different, not just scaled versions of each other).

---

## Implementation order

Do these in order — each one reduces noise that the next one's testing depends
on:

1. **Problem 1** (weighted verdict) first. This alone should visibly reduce
   over-flagging even before touching any individual detector, and makes it
   possible to test Problems 2-4 without a single stray `False` masking
   whether your threshold fix actually worked.
2. **Problem 2** (AI-detector noise heuristic + EXIF gating).
3. **Problem 3** (dual-stream forgery contiguity check).
4. **Problem 4** (ELA quality-matching).
5. **Problem 5** (resolution gating) — do last since it's additive and doesn't
   depend on the others.

## How to verify the fix

- Collect a small test set: ~10 genuine phone photos of real/dummy PAN,
  Aadhaar, and passport documents, taken on at least two different phones
  (ideally one flagship, one budget) and, if available, one low-res webcam
  capture. Also keep 2-3 known-tampered/AI-generated samples as negative
  controls.
- Before making any change, run all samples through `tamper_analysis()` and
  record each check's `ok` value and the final `verdict` — this is your
  baseline.
- After each problem's fix, re-run the same set and confirm:
  - Genuine photos trend toward `PASS`/`REVIEW` instead of `FAIL`.
  - The known-tampered/AI-generated samples still correctly produce `FAIL` —
    if any of them flip to `PASS`, the corresponding threshold in that fix was
    loosened too far and needs to be tightened back up.
- Do not tune thresholds against only genuine samples — always check both
  directions after every change, since the goal is separating real fraud
  from genuine capture noise, not just suppressing all flags.
