name: eval-frozen-manifest
triggers: manifest, recall, precision, gate, frozen, leakage, dhash, test set, baseline, benchmark, negatives, scale-stress
- One manifest = list of image paths + SHA-256 + label source; its own hash is printed in every report.
- Compare models only on the identical manifest, identical preprocessing (state EXIF handling), thresholds chosen on validation.
- Leakage: dHash Hamming <= 6 between every test image and every train image; split by document type/design, never by frame.
- Report per-condition numbers, negatives FP by category, n for every row; n < 30 = INDICATIVE ONLY.
- Gates are fixed in advance and never edited after seeing results. FAIL stays FAIL.
