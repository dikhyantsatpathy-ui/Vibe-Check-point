name: pics-private
triggers: pics, private images, real photos, folder, smoke test, robustness, silver labels, local images, owner images
- The `pics` folder holds UNLABELED images that may show real people or real IDs. They are private.
- Never commit them, never upload them anywhere (no HF, no APIs, no cloud), never copy them into fixtures, training sets or docs, never print or describe personal details, never put file names in tracked reports (names may contain personal data).
- Read-only: never modify, move or delete originals. Work on copies in `eval/local/pics_work/`.
- `pics/` and `eval/local/` must be git-ignored and verified with `git check-ignore -v`.
- Valid uses: crash/robustness smoke, latency, detector hit-rate and score histograms, face-embedding sanity, leakage checks. Invalid uses: accuracy claims, gates, training or test ground truth.
- Tracked reports get aggregates only (counts, histograms, quantiles).
