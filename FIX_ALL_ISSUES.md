# FIX_ALL_ISSUES.md — SIH26188 Master Fix & Hardening Spec

## Read this whole document before touching any file

This is the **NO-CAP SIH26188** codebase — "AI-Based Fake Identity & Document
Screening System" for Ministry of Home Affairs / SSB border checkpoints. It
has three distinct, verified problems:

1. **Genuine documents get falsely flagged** (real passports/PAN/Aadhaar
   photographed on ordinary phone or webcam cameras get REVIEW/FAIL).
2. **The pipeline can't handle concurrent load** (multiple officers/desks
   screening documents at once will hit resource exhaustion).
3. **The core "is this genuine" question is answered with hand-tuned pixel
   thresholds**, which is structurally weaker than the alternatives below.

**Deployment constraint that changes how you fix #2 and #3 — read this first:**
this app is deployed on **Vercel** as the demo target (`vercel.json`: rewrite
all → `/api/index.py`, `maxDuration: 60`), with a **Neon Postgres** primary DB
and a **SQLite fallback**. Vercel functions are:
- **Serverless and ephemeral** — no long-running background workers, no
  in-memory state that survives between invocations, no assumption that a
  process stays warm. `onnxruntime` is deliberately excluded from the Vercel
  requirements path (heavier native binary, cold-start cost) — the heuristic
  Pillow/NumPy path must always work standalone; ONNX is an optional local-only
  enhancement. **Do not break this graceful-degradation contract while fixing
  anything below.**
- **Hard-capped at `maxDuration` seconds per invocation** (60s here). Anything
  you add must fit inside that, including cold-start cost.
- **Horizontally scaled by spinning up multiple concurrent isolated function
  instances**, not by adding threads/workers to one long-lived process. This
  changes what "connection pooling" and "rate limiting" even mean here — see
  Section 2.
- Any fix that assumes a persistent Redis/queue/worker you have to run
  yourself adds infra Vercel doesn't give you for free. Where a fix needs
  shared state across instances, prefer **serverless-native** options
  (Neon's own pooler, Upstash Redis) over self-hosted ones, or fall back to a
  documented soft-limitation if no serverless-friendly option exists.

Fix things in the order given in each section — later fixes assume earlier
ones are done, and testing a later fix while an earlier bug is still live will
give you misleading results.

---

# SECTION 1 — Genuine documents falsely flagged

## Problem 1 (root cause, fix first): boolean AND-gate verdicts compound independent noise

Three separate places turn "any single check returned `ok: False`" into an
automatic failure, even though each check is independently probabilistic:

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

**Why this causes mass false positives:** `tamper_analysis()` runs 7-8
independent checks per document (ela, focus, liveness, ai-generated-or-edited,
spectral-analysis, sensor-noise, copy-move-cloning, dual-stream-forgery). If
each check only misfires on a genuine photo ~8% of the time (realistic given
Problems 2-4 below), the probability that *at least one* misfires is
`1 - (0.92)^8 ≈ 49%`. Roughly half of all genuine documents get an incorrect
`False` on *some* check purely by chance, and that one `False` currently
vetoes the whole document at three different layers.

Note `screening.py` (~line 1185-1198, `has_real_tamper`) already shows the
right instinct — it tries to only hard-fail on *meaningful* tamper signals
(ELA HIGH, confirmed AI/edited, liveness failure) rather than any `False`. But
the blanket loop at ~line 1228-1231 (`for m in (val_res, tamper_res,
face_res): if any(...) is False: can_clear = False`) undoes that nuance — a
noisy `sensor-noise` or `copy-move-cloning` false flag still silently kills
`can_clear` even when it wasn't counted as "real tamper" a few lines above.
**This inconsistency is itself a bug to fix.**

### What to do

Replace the boolean AND/OR-gate pattern with a **weighted-evidence** model.
Each check gets a reliability weight; sum weighted evidence for FAIL and PASS
instead of letting one shaky signal veto everything.

1. In `app/tampering.py`, add a module-level weight table and scoring
   function, used in place of the current `decided/failed/passed` block:

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

       def _w(label: str) -> float:
           key = label.split("-", 1)[0] if label.startswith("liveness-") else label
           return CHECK_WEIGHTS.get(key, 0.5)

       fail_weight = sum(_w(c["label"]) for c in decided if c.get("ok") is False)
       pass_weight = sum(_w(c["label"]) for c in decided if c.get("ok") is True)

       if fail_weight >= 1.3:       # one strong signal, or two+ weak ones corroborating
           return "FAIL"
       if fail_weight > 0 or pass_weight < 1.0:
           return "REVIEW"
       return "PASS"
   ```

   Replace the final `verdict = ...` line with `verdict =
   _weighted_verdict(checks)`. Keep the returned dict's key name as
   `"verdict"` — `screening.py` reads `tamper_res.get("verdict")`.

2. In `app/forensics.py`'s liveness function, replace `all_ok = all(...)` with
   the same weighted approach: `challenge_response`/`challenge_blink` = weight
   1.0 (actual proof-of-life), `anti_screen_replay` = 0.6, posture/motion
   checks = 0.3. A single soft signal misfiring (e.g. `anti_screen_replay`
   false-triggering on unusual but legitimate lighting) should downgrade to
   `SUSPECT`, not force `SPOOF`.

3. In `app/screening.py`, delete the blanket loop:
   ```python
   for m in (val_res, tamper_res, face_res):
       if any(c.get("ok") is False for c in m.get("checks", [])):
           can_clear = False
   ```
   Rely instead on the `mod_fail` handling already above it — update that to
   read `mod_res.get("verdict")` from the new weighted verdict rather than
   re-deriving its own `any(...)`. Don't compute the same thing two different
   ways in two different places in the same file.

---

## Problem 2: AI-detector noise heuristic flags denoised phone photos as "AI-generated"

`app/main.py`, `_pixel_scan()` (~line 286):
```python
suspicious_noise = content and (ratio < 0.04 and fine_noise < 1.5)
```

**Why this misfires:** modern phone cameras apply heavy computational
denoising, especially on close-up, well-lit shots — exactly the conditions of
someone photographing an ID card. The result is a genuinely smooth, low-noise
JPEG straight out of the camera, indistinguishable from this heuristic's
definition of "AI-generated."

### What to do

1. Tighten the raw threshold so it only fires on images that are
   *unnaturally* smooth, not just smooth:
   ```python
   suspicious_noise = content and (ratio < 0.018 and fine_noise < 0.8)
   ```
2. Add EXIF camera provenance as a corroborating signal. Real phone photos
   carry `Make`, `Model`, `DateTimeOriginal` EXIF tags; AI generator output
   and screenshots/screen-recaptures almost never do.
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
   when there's no camera EXIF; when camera EXIF *is* present, downgrade to a
   soft/advisory finding (`ai_score` capped ~35, `ai_suspected = False`) —
   corroborating evidence only, consistent with Problem 1's weighting.
3. Apply the same EXIF-gated downgrade to `uniform_reencode` in the same
   function — it's a second absolute-threshold trap (`np.std(flat) < 0.02 and
   np.mean(flat) > 0.01`) with the same "real photos can be very uniform"
   issue.

---

## Problem 3: dual-stream forgery detector flags denoised flat regions as "digital erasure"

`app/doc_forgery.py`, `analyze_doc_forgery()` (~line 154):
```python
dead_blocks = int(np.sum(non_margin & (block_vars < 0.05)))
inpaint_void = bool(dead_blocks > (non_margin_count * 0.15) and non_margin_count > 40)
```

**Why this misfires:** any 16×16 SRM-residual patch with variance under 0.05
is treated as evidence of digital erasure/inpainting. A denoised card
background, a passport photo page's blank margin, or a plain-colored PAN card
face can easily produce >15% of blocks under that floor on a genuinely smooth
phone photo — nothing tampered at all. There's currently no way to
distinguish "one contiguous rectangular patch was erased" (real tamper
signature) from "the whole image is uniformly smooth because the phone
denoised it" (normal capture).

### What to do

1. Tighten the raw variance floor:
   ```python
   dead_blocks = int(np.sum(non_margin & (block_vars < 0.015)))
   ```
2. **Add spatial contiguity as a requirement.** Real erasure/inpainting
   produces a compact, connected blob of dead blocks; denoising scatters dead
   blocks broadly across the whole card.
   ```python
   from scipy import ndimage  # add scipy as a dependency, or implement a
                               # pure-NumPy/Python flood-fill/union-find over
                               # the small boolean block grid if you'd rather
                               # not add the dependency

   dead_mask = non_margin & (block_vars < 0.015)
   labeled, num_features = ndimage.label(dead_mask)
   if num_features > 0:
       component_sizes = ndimage.sum(dead_mask, labeled, range(1, num_features + 1))
       largest_component = int(component_sizes.max())
   else:
       largest_component = 0

   inpaint_void = bool(
       largest_component > (non_margin_count * 0.12)
       and largest_component > 20
   )
   ```
3. Keep `seam_anomaly` (max pixel step > 250 AND `inpaint_void`) as-is — it
   already requires `inpaint_void` first, so fixing #2 tightens it too.
4. Gate this detector by resolution (Problem 5) — it needs real pixel-level
   texture to say anything meaningful.

---

## Problem 4: ELA uses a fixed re-compression quality regardless of the photo's real compression history

`app/forensics.py`, `ela()` (~line 94):
```python
def ela(data: bytes, quality: int = 92, preview: int = 128):
    ...
    Image.fromarray(rgb).save(first, "JPEG", quality=quality)
```

**Why this misfires:** ELA only works reliably when the re-compression
quality (hardcoded `92`) is close to the *original* photo's actual JPEG
quality. Real document photos frequently arrive already compressed lower than
92 — a phone's own JPEG encoder (commonly 80-90), or a photo re-saved by
WhatsApp/Telegram/an upload resizer (typically ~70-80). Re-encoding an
already-lower-quality image at 92 produces a **globally elevated** diff (the
whole image loses/gains detail relative to a higher target, not just a pasted
region), which can push `damaged_blocks` past the `0.15`/`0.30` thresholds and
produce a false `MEDIUM`/`HIGH` status on a completely untampered image.

### What to do

1. Estimate the image's actual JPEG quality before choosing the ELA
   re-compression quality, so the two are close together:
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
   Run this on a downscaled copy (e.g. 256px) to keep it cheap — it only
   needs to run before the real full-resolution ELA pass, which then uses the
   estimated quality instead of the fixed `92`.
2. If the input isn't a JPEG in the first place (came in as PNG/HEIC before
   conversion), keep the default `92` — quality-matching only matters when
   there's real prior JPEG compression history to match.
3. Keep the existing localized-cluster logic (`peak_cluster_damage`) as-is —
   fixing the quality mismatch will make diffuse false-positive diff mostly
   disappear, sharpening the distinction it already draws.

---

## Problem 5: no resolution/device-adaptive gating

Every check (ELA, spectral-analysis, dual-stream-forgery, sensor-noise,
copy-move) runs unconditionally regardless of source resolution. A 2.1MP
laptop webcam frame doesn't carry enough signal for FFT spectral analysis or
16×16-block SRM residual analysis to say anything meaningful — these checks
are closer to analyzing noise-on-noise than real signal at that resolution,
and are likely to produce spurious REVIEW/FAIL rows.

### What to do

In `app/tampering.py`, before running the per-check block, compute the
resolution once and skip/soften checks that need real detail below a floor —
following the same "honest not-applicable, never a silent pass" pattern the
module already uses for PDFs:

```python
MIN_PIXELS_FOR_TEXTURE_CHECKS = 400_000  # ~640x625, roughly a low-end webcam frame

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
    # skip calling analyze_doc_forgery()/spectral_analysis() entirely at low res
else:
    # existing calls as today
```

This removes a whole category of false flags on cheap cameras instead of
chasing one threshold that works for both a 12MP phone sensor and a 2.1MP
webcam sensor — there isn't one; their noise/detail characteristics are
fundamentally different, not scaled versions of each other.

---

## Section 1 implementation order

1. **Problem 1** (weighted verdict) first — visibly reduces over-flagging
   before touching any individual detector, and prevents one stray `False`
   from masking whether Problems 2-4's fixes actually worked.
2. **Problem 2** (AI-detector noise heuristic + EXIF gating).
3. **Problem 3** (dual-stream forgery contiguity check).
4. **Problem 4** (ELA quality-matching).
5. **Problem 5** (resolution gating) — additive, do last.

## Section 1 verification

- Collect ~10 genuine phone photos of real/dummy PAN, Aadhaar, and passport
  documents on at least two different phones (one flagship, one budget) and,
  if available, one low-res webcam capture. Keep 2-3 known-tampered/AI-
  generated samples as negative controls.
- Before any change, run all samples through `tamper_analysis()` and record
  each check's `ok` value and the final `verdict` — this is your baseline.
- After each fix, re-run the same set and confirm genuine photos trend toward
  `PASS`/`REVIEW`, **and** the known-tampered samples still correctly produce
  `FAIL` — if any flip to `PASS`, that fix's threshold was loosened too far
  and needs tightening back up.
- Never tune thresholds against only genuine samples — always check both
  directions after every change.

---

# SECTION 2 — Load handling (Vercel + Neon aware)

## Problem 6: DB connections held open for the full CPU-heavy screening duration

`app/main.py` (~line 2644-2696), `/api/screen`:
```python
with _get_db_for_session(session_owner) as db:
    ... # session/permission checks
    report = await run_in_threadpool(
        run_screening, db, data, file.filename or "upload", ...
    )
```

`run_screening` (OCR + ELA/FFT + ONNX inference where present) can take
1-5+ seconds. The DB session — and its checked-out connection — is held for
that **entire** duration, even though the DB is only actually touched at the
start (watchlist hash lookup) and the end (persisting the report).

**Why this matters more on Vercel than on a normal server:** each concurrent
Vercel invocation is its own isolated function instance, each creating its own
engine/pool from `DATABASE_URL`. The current pool settings
(`pool_size=2, max_overflow=4`, ~line 1057-1062) are **per-instance**, but the
real limit that matters is **Neon's total concurrent-connection cap for your
plan**, summed across every concurrently running Vercel instance. Under a
demo burst (a judge or officer hammering the endpoint, or your own load test),
you can have many Vercel instances alive at once, each holding a connection
open for seconds at a time purely to babysit CPU work that doesn't need it —
that's what will actually exhaust Neon's connection ceiling, not any single
instance's local pool number.

### What to do

1. **Confirm you're using Neon's pooled connection string, not the direct
   one.** Neon gives you two hostnames — a direct one and a `-pooler` one
   (PgBouncer in transaction-pooling mode) — make sure `DATABASE_URL` uses the
   `-pooler` host. This is the serverless-correct way to handle many short-
   lived Vercel-instance connections; it's not optional infra to add, it's a
   config you should already have and must verify.
2. **Split the DB session's lifetime from the CPU-work lifetime** so the
   connection is only held for the brief moments that actually touch the DB:
   ```python
   # Short-lived session: permission checks + watchlist lookup only.
   with _get_db_for_session(session_owner) as db:
       # ...existing session/permission checks...
       watchlist_hits = _query_watchlist(db, ...)   # extract this as its own helper

   # CPU-heavy work runs with NO db handle held open.
   report_data = await run_in_threadpool(
       run_screening_pure, data, file.filename or "upload", ...,
       watchlist_hits=watchlist_hits,
   )

   # Short-lived session: persist result only.
   with _get_db_for_session(session_owner) as db:
       _persist_report(db, report_data)
   ```
   This requires splitting `run_screening` in `app/screening.py` into a pure-
   compute function and a thin DB-touching wrapper. This is the single
   highest-impact change in this section — it turns "6-ish documents can be
   mid-flight system-wide" into "hundreds can be mid-flight, only the brief
   read/write is ever serialized on a DB connection."
3. With per-instance pools now held for milliseconds instead of seconds, you
   can keep `pool_size` conservative (1-2) per instance — you don't need to
   raise it once the connection isn't sitting idle-but-checked-out during
   inference. Raising `max_overflow` further without doing step 2 first would
   just let you exhaust Neon's plan-wide connection cap faster, not fix the
   underlying problem.

## Problem 7: rate limiting is per-instance, not global — misleading on Vercel specifically

`slowapi`'s default limiter stores counters in local process memory. On
Vercel, each concurrent function invocation can be a **separate instance**
with its own memory — so `"60/minute"` on `/api/screen` is enforced per
instance, not globally. Under a demo burst that spins up several concurrent
instances, the *effective* limit is `60 × (number of live instances)`, which
gives a false sense that backpressure is handled when it isn't.

### What to do

- **Serverless-appropriate fix:** point slowapi at a serverless-friendly
  shared store — **Upstash Redis** is the standard pairing with Vercel (REST-
  based, no persistent connection needed, has a generous free tier, and
  Vercel has a first-party Upstash integration in its dashboard):
  ```python
  limiter = Limiter(key_func=get_remote_address, storage_uri="redis://<upstash-url>")
  ```
- If you don't want to add Upstash before the deadline, **do not silently
  leave this as-is** — document it explicitly as a known limitation in your
  pitch/README ("rate limiting is best-effort per-instance in the current
  Vercel deployment; a shared store is the documented next step"), so a judge
  reading your code doesn't mistake the current number for a real global cap.

## Problem 8: cold-start cost stacking against the 60s `maxDuration` ceiling

On a cold Vercel invocation you can stack: Neon connection cold-start (can be
1-2s if the compute was suspended), any ONNX model load from disk if
`onnxruntime` happens to be present in your test environment, then the actual
OCR/forensics/ArcFace inference. Individually each is fine; stacked on an
unlucky cold invocation under load, they can approach the 60s ceiling — a
killed function looks like a silent hang to the officer/judge, with no
graceful message.

### What to do

1. Confirm models are loaded **once per container lifetime at module import
   time**, not per-request — check `yolo_roi.py`/`face_match.py` cache the
   loaded ONNX session at module scope rather than reloading weights inside
   the request-handling function.
2. Add an explicit **internal soft timeout inside `run_screening`** (e.g. 45s,
   safely under the 60s hard cap) that, if hit, degrades to whatever partial
   result is available (heuristic-only path) and returns it with a clear
   `"degraded": true` / reason field, rather than letting Vercel's hard kill
   be the first thing that happens. A partial, explained result is always
   better for an officer than a dead request.
3. Since `onnxruntime` is intentionally excluded from the Vercel
   `requirements.txt` per the existing architecture, the Vercel-deployed demo
   path is **already** running the lighter heuristic-only path with no ONNX
   cold-start cost — good, keep it that way. Just make sure nothing you add
   in Sections 1 or 3 accidentally imports `onnxruntime` unconditionally at
   module level in a file that's on the Vercel import path (guard any new
   ONNX import with the same `try/except ImportError` pattern the existing
   YOLO/face code already uses).

## Problem 9: SQLite fallback is single-writer — a real risk given your stated offline scenario

WAL mode helps concurrent *reads*, but SQLite still serializes all writes.
This mostly matters for your **actual target scenario** — "border posts have
low-to-zero connectivity" per the blueprint — meaning the SQLite fallback
isn't a rare edge case for you, it may be the **primary** path in a real
deployment. Simultaneous officer submissions writing `ScreeningReport` rows
during a burst will queue behind each other on the SQLite writer lock.

### What to do

- This is lower urgency for the Vercel demo itself (Neon will be reachable
  there), but real for any future offline/edge deployment. At minimum,
  document the expected write latency under burst for the SQLite path in your
  README, and consider batching/short retry-with-backoff around SQLite writes
  in `_get_db_for_session`'s fallback branch so a burst produces brief queuing
  rather than an outright write-lock exception surfaced to the officer.

## Section 2 priority order

1. **Problem 6** (DB session/CPU-work split) — the one most likely to
   actually break a live demo under simulated concurrent submissions.
2. **Problem 8** (cold-start/timeout handling) — matters specifically because
   you're staying on Vercel for the demo.
3. **Problem 7** (rate-limiter backend) — do if time allows; otherwise
   document as a known limitation, don't leave it silently misleading.
4. **Problem 9** (SQLite write queuing) — lowest urgency for the Vercel demo,
   but call it out explicitly in your pitch as a known, understood item.

---

# SECTION 3 — Better alternatives to hand-tuned pixel thresholds

Nothing here is "permanent and will never misfire" — no detector, model, or
library can promise that, and you should say so plainly if asked. What
follows are approaches that are **structurally more reliable** than comparing
a number to a hardcoded constant, ranked by fit for this specific
architecture (offline-first, graceful ONNX-optional degradation, staying on
Vercel for the demo).

## 3.1 Replace hand-tuned thresholds with a small trained classifier (highest-leverage, do this first)

Every detector in Section 1 already computes a meaningful numeric feature
(ELA damage ratio, PAPR, block variance, noise ratio, copy-move score). The
actual disease isn't any single threshold value — it's that a human guessed
all of them independently instead of learning where the real decision
boundary sits across all features jointly (e.g. "low noise is fine if ELA is
also clean, but suspicious if ELA is also elevated" — a relationship no fixed
threshold can express).

**Fits this architecture perfectly** because it slots into the exact
graceful-degradation pattern already used for YOLO/ArcFace: a small optional
ONNX model, loaded if present, heuristic path as fallback if absent (i.e.
still works with zero extra infra on Vercel where `onnxruntime` is excluded).

### Exact steps for the builder agent

1. **Feature extraction script** — `scripts/collect_features.py`:
   - Walk a labeled dataset directory: `dataset/genuine/*.jpg` and
     `dataset/tampered/*.jpg` (you'll need to assemble ~200-500 images per
     class; mix phone models, lighting, and a few AI-generated/screen-
     recaptured negatives).
   - For each image, call the *existing* extractor functions directly
     (`ela`, `spectral_analysis`, `noise_consistency`, `copy_move_detection`
     from `app/forensics.py`; `analyze_doc_forgery` from `app/doc_forgery.py`;
     the noise-ratio/fine-noise values from `_pixel_scan` in `app/main.py`) —
     don't reimplement feature extraction, reuse what's already there.
   - Flatten each result into a fixed-order numeric feature vector (e.g.
     `[ela_damaged_blocks, ela_peak_cluster, papr, high_freq_ratio,
     noise_var_ratio, copy_move_score, dead_block_ratio, largest_component,
     fine_noise, pixel_ratio, has_camera_exif]`), append the label
     (`0`=genuine, `1`=tampered), write to `dataset/features.csv`.

2. **Training script** — `scripts/train_classifier.py`:
   - Load `features.csv` with pandas.
   - Train a **logistic regression** or **gradient-boosted tree**
     (scikit-learn `LogisticRegression` or `GradientBoostingClassifier` —
     no deep learning needed for ~11 numeric features and a few hundred
     samples; keep it small and fast to keep cold-start cost low if ever
     loaded on Vercel).
   - Evaluate with k-fold cross-validation, print precision/recall per class
     (recall on the tampered class matters most — don't just optimize
     accuracy, a model that never flags tampering scores high accuracy on an
     imbalanced set and is useless).
   - **Export to ONNX** with `skl2onnx` (`pip install skl2onnx`), save as
     `app/models/tamper_classifier.onnx`. Exporting to ONNX — rather than
     pickling the sklearn model directly — keeps this consistent with the
     existing `onnxruntime`-optional pattern already used for YOLO/ArcFace:
     same loader pattern, same graceful fallback, same "absent on Vercel,
     present locally" story.

3. **Integration point** — `app/tampering.py`:
   - Add a loader guarded exactly like the existing YOLO ROI loader (check
     `app/yolo_roi.py` for the established pattern in this codebase — reuse
     it, don't invent a new one):
     ```python
     _TAMPER_CLF_SESSION = None
     def _load_tamper_classifier():
         global _TAMPER_CLF_SESSION
         if _TAMPER_CLF_SESSION is not None:
             return _TAMPER_CLF_SESSION
         try:
             import onnxruntime as ort
             path = os.getenv("TAMPER_CLF_ONNX_PATH", "app/models/tamper_classifier.onnx")
             if os.path.exists(path):
                 _TAMPER_CLF_SESSION = ort.InferenceSession(path)
         except Exception:
             _TAMPER_CLF_SESSION = False  # tried and unavailable; don't retry every call
         return _TAMPER_CLF_SESSION or None
     ```
   - When the session is available, run the same feature vector through it
     and use its output probability as an **additional weighted check** in
     the `_weighted_verdict` scheme from Problem 1 (e.g. weight 1.2 — it's the
     most informed signal once trained, since it's the only one that
     considers all features jointly). When unavailable (Vercel demo path,
     `onnxruntime` absent), fall through to the existing weighted-heuristic
     verdict untouched — **the heuristic path must remain fully functional on
     its own**, this is additive, not a replacement.

4. This does not change your Vercel demo at all unless you choose to bundle
   the (small — a logistic regression/GBM ONNX export is typically tens to a
   few hundred KB) model file and add `onnxruntime` back for Vercel
   specifically. Given the "stay on Vercel" constraint, the practical default
   is: **train and use this locally / for any non-Vercel deployment target**,
   keep the Vercel demo path on the heuristic-only fixes from Section 1. Note
   this explicitly in your pitch as "the same offline-first, ONNX-optional
   pattern already used for YOLO/ArcFace, applied to tamper scoring."

## 3.2 Pretrained forgery-localization models (research-and-evaluate, don't assume)

Your ELA and dual-stream SRM code are reimplementations of ideas from
published forensics research. There are pretrained, open-source models built
specifically for this:
- **TruFor**, **CAT-Net**, **Noiseprint/Noiseprint++** — image-forgery-
  localization models trained on large forged/authentic datasets, output a
  per-pixel tamper-probability map instead of a hand-tuned block-variance
  rule, and generalize across camera types far better because they were
  trained across thousands of devices, not tuned against your own test phone.

**Per the blueprint's own research mandate:** before integrating any of
these, autonomously search for their current GitHub repos, check license
terms, confirm whether an ONNX-exportable checkpoint exists or whether you'd
need to export one yourself (`torch.onnx.export`), and check inference-time
model size against what's reasonable to bundle for an optional local-only
enhancement (same "present locally, absent on Vercel" pattern as 3.1). Do not
guess model input shapes or preprocessing steps — read the actual repo's
inference script before writing integration code.

## 3.3 Strengthen your *existing* multi-frame liveness capture instead of adding new infra

You already capture multiple frames for challenge-response liveness
(blink/nod). Two additions reuse that capture you already have, rather than
adding new capture flows:
- **Cross-frame noise-consistency check**: extract the sensor-noise residual
  from each frame in the same liveness session and check they're
  consistent with each other (same physical sensor across the session). A
  screen-replay attack (holding up a video on a second screen) tends to
  introduce a *different*, more uniform noise signature than a live sensor
  feed, and this is harder to spoof than passing a single-frame noise check
  once.
- **EXIF/session device-consistency check**: if multiple documents are
  screened in one officer session, an abrupt change in camera EXIF Make/Model
  mid-session (where the officer's setup didn't physically change) is itself
  a soft corroborating signal worth surfacing as an advisory note, not a hard
  fail.

Both of these are refinements of code you already have, not new
infrastructure — cheapest path to a real improvement.

## 3.4 Things that don't fit this architecture — mentioned for completeness, not recommended here

- **Cloud ID-verification vendor APIs** (HyperVerge, IDfy, Digio, Onfido):
  these have the strongest real-world accuracy (trained on millions of real
  Indian ID documents across every phone in the market) but require internet
  connectivity per-request — this **directly conflicts** with your stated
  "border posts have low-to-zero connectivity, offline-first" requirement and
  your own blueprint's explicit prioritization of offline-first capability.
  Only worth mentioning in your pitch as an *optional* enhancement path when
  connectivity is available, never as the primary path.
- **Mobile device attestation** (Android Play Integrity API, iOS
  DeviceCheck/App Attest): these prove "this photo was captured just now by
  an unmodified app on real hardware" — genuinely strong, but they require a
  **native mobile app** context to call the OS attestation API. Your capture
  path here is a browser-based webcam capture (React frontend), not a native
  app, so these APIs aren't reachable from this architecture as it stands.
  Worth noting as a future-hardening idea *if* SSB ever wants a dedicated
  officer mobile app, not something to bolt onto the current web flow.
- **PRNU sensor-fingerprint matching** across *separate* documents/sessions
  (proving two photos came from the same physical sensor over time, useful
  for repeat-traveler/device-reuse detection): genuinely powerful, but it's a
  different question ("is this the same device as last time") than "is this
  photo genuine right now," and needs a fingerprint database/matching
  infrastructure to be useful — bigger scope than this fix pass. Flag as a
  roadmap item, not something to implement under this deadline.

## Section 3 priority order

1. Do **3.3 first** — it's free (reuses capture you already have), no new
   dependencies, works identically on Vercel and locally.
2. Do **3.1 next**, scoped as a local/non-Vercel enhancement per the note
   above — highest genuine accuracy improvement, fits the existing
   ONNX-optional pattern exactly.
3. Treat **3.2** as a research spike with a time-box — evaluate feasibility,
   don't commit to full integration unless research confirms an ONNX-
   exportable checkpoint is genuinely available and small enough.
4. Mention **3.4** in your pitch/report as understood-but-descoped roadmap
   items — this shows judges you evaluated the full solution space and made
   a deliberate architecture-fit decision, not that you missed them.

---

# Master verification checklist (run after all sections)

- [ ] Genuine phone/webcam photos of real/dummy documents produce
      `PASS`/`REVIEW`, not `FAIL`, across at least 2 phone models + 1 low-res
      webcam.
- [ ] Known-tampered/AI-generated negative-control samples still correctly
      produce `FAIL` — no regression from loosening thresholds.
- [ ] Simulate 10-20 concurrent `/api/screen` submissions (a simple script
      with `asyncio`/`httpx` firing concurrent requests works) against the
      Vercel-deployed demo URL and confirm no connection-pool timeout errors
      surface to the caller.
- [ ] Confirm `DATABASE_URL` uses Neon's `-pooler` host.
- [ ] Confirm the Vercel deployment still runs with `onnxruntime` absent from
      `requirements.txt` and the heuristic-only path still fully functions
      end-to-end (this is your safety net — never let it silently break while
      adding the Section 3 enhancements).
- [ ] Document, in your README or pitch deck, which items were fully fixed
      vs. scoped-out-with-reason (rate-limiter backend, SQLite write
      queuing, PRNU roadmap, vendor API/device-attestation trade-offs) —
      judges reward explicit, reasoned scope decisions over silent gaps.
