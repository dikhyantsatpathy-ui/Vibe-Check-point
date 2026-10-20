# NO-CAP / SIH26188 — Project Review Context & Snapshot

Generated for technical review on branch `ml/patch-v8`.
All secrets, tokens, personal data, and credential strings have been strictly omitted or redacted per Part A & Part C rules.

---

## 1. Repo Snapshot

- **Current Branch:** `ml/patch-v8`
- **Current HEAD Commit:** `606165d13e56e7885692e3c8fa740b64afc8a4a1`
- **Working Tree Status (`git status --short`):**
```text
M docs/CLAUDE_HANDOFF.md
 M eval/runs/20261011_reverify_v1/ci_audit_t8.json
 M eval/runs/20261011_reverify_v1/code_health_c.json
 M eval/runs/20261011_reverify_v1/coverage_t7.json
 M eval/runs/20261011_reverify_v1/golden_set_t4.json
 M eval/runs/20261011_reverify_v1/model_facts_m.json
 M eval/runs/20261011_reverify_v1/model_io_t5.json
 M eval/runs/20261011_reverify_v1/parser_fuzz_t3.json
 M eval/runs/20261011_reverify_v1/parser_hardening_p.json
 M eval/runs/20261011_reverify_v1/pics_smoke_x.json
 M eval/runs/20261011_reverify_v1/soak_t6.json
```
- **Co-Author & AI Attribution Check (`git log -n 30 --format=%B | grep -iE "co-authored-by|generated with"`):**
```text
0 matches (CLEAN - no AI attribution or co-author trailers found)
```
- **Last 40 Commit Subjects (`git log -n 40 --format='%h %an %s'`):**
```text
606165d Dikhyant Satapathy [v8] final release checkpoint
61efe8a Dikhyant Satapathy [G3] final queue completion checkpoint
a7a5f43 Dikhyant Satapathy [G2] commit and push branch ml/patch-v8
47b488d Dikhyant Satapathy [G1] release verdict written by code to docs/FINAL_REPORT_DRAFT.md
8e40133 Dikhyant Satapathy [K4] blueprint and handoff checks and docs hygiene verified
4c21f3e Dikhyant Satapathy [K3] Claude handoff generator with static narrative and dynamic facts block
c68cb57 Dikhyant Satapathy [K2] blueprint template and renderer supporting metric placeholders and check flag
4a9928a Dikhyant Satapathy [K1] claims ledger verified with zero false claims and exit check
3cbb647 Dikhyant Satapathy [T5] compileall clean and ruff linting fixes
d37bc7e Dikhyant Satapathy [T4] full test suite stability verified across three consecutive runs
067cd85 Dikhyant Satapathy [T3] blueprint sections, claims ledger 0-false, and queue parity tests
d368dcf Dikhyant Satapathy [T2] independent Merkle root verification and tamper evidence tests
0c3f74c Dikhyant Satapathy [T1] end-to-end Invariant FS tests across face failure states
c129bb5 Dikhyant Satapathy [A4] skill files updated from Appendix E and router tests
d2fdfde Dikhyant Satapathy [A3] three-run suite stability runner and green suite result
d41b4f7 Dikhyant Satapathy [A2] release verdict validator and quality gate tests
b55d395 Dikhyant Satapathy [A1] face proxy evaluation script and synthetic selftest
b7a19e2 Dikhyant Satapathy [P13] owner isolation audit script and test
7e261a3 Dikhyant Satapathy [P12] coverage ratchet and CI quality gate
18d8091 Dikhyant Satapathy [P11] one source for test counts: scripts/count_tests.py, blueprint and claims sync
166627e Dikhyant Satapathy [P10] fake secrets used as test inputs in reverify_logs_v4.py made unmistakably fake
2f549d1 Dikhyant Satapathy [P9] no credential prefixes in documents: scrubbed Roboflow prefix, extended audit_secrets_s1.py and hygiene tests
ead7527 Dikhyant Satapathy [P8] honest CSP: baseline enforced, strict report-only with dynamic sha256 hashes
cdfeb68 Dikhyant Satapathy [P7] readiness table without hand-typed numbers: readiness_rows.json and render script
0aac473 Dikhyant Satapathy [P6] evaluate_liveness_frames server-side warning, not integrated in routes, blueprint wording
44d4856 Dikhyant Satapathy [P5] face metadata sidecar and health fields in /ml/health and screening
6d6cb4c Dikhyant Satapathy [P4] face-model provisioning hardened: manifest, size cap, private repo fetch, fail closed
d596e29 Dikhyant Satapathy [test-fix] update legacy fallback assertions in test_face_match and test_invariants_t1 for P3
cbab863 Dikhyant Satapathy [P3] fallback face methods never decide (verdict REVIEW, decision INCONCLUSIVE)
9b321f9 Dikhyant Satapathy [P2] relaxed-threshold face match can never auto-PASS
6d8d9ec Dikhyant Satapathy [P1] single canonical face-threshold policy and remove sliding relaxations
6d9543f Dikhyant Satapathy [R3] verify and record Windows process tracking in agent_ctl
07d4def Dikhyant Satapathy [R2] add tests/test_v8_resume.py for agent_ctl resume system
70035d5 Dikhyant Satapathy [R1] initialize queue, agent control, and AGENTS/GEMINI guidelines
74f5efe Dikhyant Satapathy fix(ci): configure ruff in pyproject.toml and resolve syntax issues
dfdf45c Dikhyant Satapathy fix(screening): add robust cv2/Pillow barcode decode fallback and tighten vercelignore
9ca2f64 Dikhyant Satapathy docs: reconcile SIH26188_ENGINEERING_BLUEPRINT.md to v7.0.0 production release
5f7d8df Dikhyant Satapathy feat(phase-r): execute release gate assessment and complete Work Order v7 (R1-R3)
0da68d1 Dikhyant Satapathy feat(phase-k): rewrite engineering blueprint and reconcile verified claims (K1-K4)
2056631 Dikhyant Satapathy feat(phase-l): complete convergence loop and route classification hardening (L1)
```

## 2. File Tree & Line Counts

### Tracked Files Summary (First 400 Files by Top-Level Directory)
Total tracked files in repository: 367.

### `(root)/` (17 files shown of first 400 tracked)
- `.env.example`
- `.gitattributes`
- `.gitignore`
- `.python-version`
- `.vercelignore`
- `AGENTS.md`
- `GEMINI.md`
- `LICENSE`
- `README.md`
- `SIH26188_ENGINEERING_BLUEPRINT.md`
- `START.bat`
- `main.py`
- `pyproject.toml`
- `pytest.ini`
- `requirements.txt`
- `start.sh`
- `vercel.json`
### `.github/` (1 files shown of first 400 tracked)
- `.github/workflows/ci.yml`
### `api/` (1 files shown of first 400 tracked)
- `api/index.py`
### `app/` (32 files shown of first 400 tracked)
- `app/codebase.py`
- `app/config.py`
- `app/dl_verify.py`
- `app/doc_forgery.py`
- `app/doctype_cls.py`
- `app/extraction.py`
- `app/face.py`
- `app/face_match.py`
- `app/face_policy.py`
- `app/forensics.py`
- `app/guide.py`
- `app/heif_support.py`
- `app/identity.py`
- `app/keys.py`
- `app/llm.py`
- `app/main.py`
- `app/models/doctype.onnx`
- `app/mrz.py`
- `app/mrz_enhancer.py`
- `app/qr_decoder.py`
- `app/rectification.py`
- `app/remote_ml.py`
- `app/replay_detector.py`
- `app/screening.py`
- `app/session.py`
- `app/static/index.html`
- `app/stats.py`
- `app/syndicate.py`
- `app/tampering.py`
- `app/transliterate.py`
- `app/validation.py`
- `app/yolo_roi.py`
### `docs/` (47 files shown of first 400 tracked)
- `docs/AGENT_STATE.json`
- `docs/AUDIT_V4.md`
- `docs/AUDIT_V5.md`
- `docs/AUDIT_V7.md`
- `docs/BLUEPRINT_VS_REALITY.md`
- `docs/CLAUDE_HANDOFF.md`
- `docs/CSP_NOTES.md`
- `docs/DATASET_CREDITS.md`
- `docs/DECISIONS.md`
- `docs/DEPENDENCY_LICENCES.md`
- `docs/DEPLOYMENT_ISOLATION.md`
- `docs/FINAL_REPORT_DRAFT.md`
- `docs/JOURNAL.jsonl`
- `docs/LIMITATIONS.md`
- `docs/ML_PIPELINE.md`
- `docs/ML_PIPELINE_CHANGES.md`
- `docs/MODEL_CARD.md`
- `docs/OPERATIONS.md`
- `docs/OWNER_TODO.md`
- `docs/QUEUE.json`
- `docs/QUEUE_v7.json`
- `docs/RESUME_AFTER_SPECIMENS.md`
- `docs/SWITCH_READINESS.md`
- `docs/TRAINING_PROGRESS.md`
- `docs/WORK_ORDER_V8.md`
- `docs/agent_skills/agent-ctl.md`
- `docs/agent_skills/blueprint-claims.md`
- `docs/agent_skills/code-sweep.md`
- `docs/agent_skills/csp-hardening.md`
- `docs/agent_skills/eval-frozen-manifest.md`
- `docs/agent_skills/face-embedding.md`
- `docs/agent_skills/face-policy.md`
- `docs/agent_skills/fastapi-hardening.md`
- `docs/agent_skills/git-hygiene.md`
- `docs/agent_skills/latency-bench.md`
- `docs/agent_skills/onnx-parity.md`
- `docs/agent_skills/parser-fuzz.md`
- `docs/agent_skills/pics-private.md`
- `docs/agent_skills/pytest-hardening.md`
- `docs/agent_skills/rfdetr-train.md`
- `docs/agent_skills/secret-scan.md`
- `docs/agent_skills/vercel-isolation.md`
- `docs/agent_skills/windows-powershell.md`
- `docs/blueprint_template.md`
- `docs/claims/claims.json`
- `docs/coverage_thresholds.json`
- `docs/readiness_rows.json`
### `eval/` (116 files shown of first 400 tracked)
- `eval/audit_leakage.py`
- `eval/audit_task1.py`
- `eval/audit_task1c.py`
- `eval/audit_v4.py`
- `eval/bakeoff_report.json`
- `eval/benchmark.py`
- `eval/dataset.py`
- `eval/eval_aadhaar_rfdetr.py`
- `eval/eval_face_proxy.py`
- `eval/eval_id_fields.py`
- `eval/eval_indian_specimens.py`
- `eval/eval_int8.py`
- `eval/eval_mrz.py`
- `eval/eval_pipeline_latency.py`
- `eval/eval_replay.py`
- `eval/eval_report.json`
- `eval/evaluate.py`
- `eval/forensics_benchmark.py`
- `eval/manifests/card_v7.json`
- `eval/metrics.py`
- `eval/repro_ledger.py`
- `eval/run_all.py`
- `eval/runs/20261006_005303_midv_conversion/counts.json`
- `eval/runs/20261006_005725_midv_conversion/counts.json`
- `eval/runs/20261006_010438_baseline_yolo_card/report.json`
- `eval/runs/20261006_010650_baseline_yolo_card/report.json`
- `eval/runs/20261006_011057_trainset/counts.json`
- `eval/runs/20261006_012653_smoke/onnx_io.json`
- `eval/runs/20261006_012653_smoke/parity.json`
- `eval/runs/20261006_024516_card_training/training_metrics.json`
- `eval/runs/20261006_024643_val_pr_sweep/val_pr_sweep.json`
- `eval/runs/20261006_024917_val_pr_sweep/val_pr_sweep.json`
- `eval/runs/20261006_090053_baseline_yolo_card/report.json`
- `eval/runs/20261006_090055_rfdetr_card_eval/report.json`
- `eval/runs/20261006_090847_rfdetr_card_eval/int8_metrics.json`
- `eval/runs/20261006_090847_rfdetr_card_eval/int8_parity_report.json`
- `eval/runs/20261006_090847_rfdetr_card_eval/report.json`
- `eval/runs/20261006_094311_audit_rfdetr_fp32/report.json`
- `eval/runs/20261006_094311_audit_rfdetr_int8/report.json`
- `eval/runs/20261006_094311_audit_yolo/report.json`
- `eval/runs/20261006_095000_leakage_audit/report.json`
- `eval/runs/20261006_095307_task2_negatives_and_stress/report.json`
- `eval/runs/20261006_100008_task3_deployment_latency/int8_parity_iou95.json`
- `eval/runs/20261006_100008_task3_deployment_latency/report.json`
- `eval/runs/20261006_101729_task4f_crops/report.json`
- `eval/runs/20261006_102723_baseline_yolo_card/report.json`
- `eval/runs/20261006_102938_task7_synthetic_indian/report.json`
- `eval/runs/20261006_103832_data_inventory/counts.json`
- `eval/runs/20261006_105022_card_v2_prep/counts.json`
- `eval/runs/20261006_162252_smoke/onnx_io.json`
- `eval/runs/20261006_162252_smoke/parity.json`
- `eval/runs/20261006_164026_indian_specimens/report.json`
- `eval/runs/20261006_164300_summary.json`
- `eval/runs/20261006_164309_indian_specimens/report.json`
- `eval/runs/20261006_170004_task2_negatives_and_stress/report.json`
- `eval/runs/20261006_170704_task3_deployment_latency/int8_parity_iou95.json`
- `eval/runs/20261006_170704_task3_deployment_latency/report.json`
- `eval/runs/20261006_170920_task7_synthetic_indian/report.json`
- `eval/runs/20261006_173109_mrz_eval/report.json`
- `eval/runs/20261006_174904_doctype_v2_eval/report.json`
- `eval/runs/20261006_175055_doctype_v2_eval/report.json`
- `eval/runs/20261006_182700_aadhaar_eval/report.json`
- `eval/runs/20261006_184931_id_fields_eval/report.json`
- `eval/runs/20261006_190335_pipeline_latency/report.json`
- `eval/runs/20261006_193416_forensics_benchmark/report.json`
- `eval/runs/20261006_204725_audit_v4/report.json`
- `eval/runs/20261006_214207_replay_eval/report.json`
- `eval/runs/20261006_214437_replay_eval/report.json`
- `eval/runs/20261006_221300_replay_eval/report.json`
- `eval/runs/20261006_smoke_parity/parity_report.json`
- `eval/runs/20261006_smoke_parity/parity_train_report.json`
- `eval/runs/20261006_smoke_parity_v2/parity.json`
- `eval/runs/20261007_064553_env/freeze.txt`
- `eval/runs/20261007_064553_env/nvidia_smi.txt`
- `eval/runs/20261007_064553_env/pytest_baseline.txt`
- `eval/runs/20261007_064553_env/python_version.txt`
- `eval/runs/20261007_064553_env/runtime_info.txt`
- `eval/runs/20261007_064553_env/secrets_audit.json`
- `eval/runs/20261011_180630_env/env_receipt.json`
- `eval/runs/20261011_180630_env/pip_freeze.txt`
- `eval/runs/20261011_182816_claims/report.json`
- `eval/runs/20261011_185735_claims/report.json`
- `eval/runs/20261011_224106_claims/report.json`
- `eval/runs/20261011_224601_claims/report.json`
- `eval/runs/20261011_224819_claims/report.json`
- `eval/runs/20261011_reverify_v1/auth_reverification.json`
- `eval/runs/20261011_reverify_v1/ci_audit_t8.json`
- `eval/runs/20261011_reverify_v1/code_health_c.json`
- `eval/runs/20261011_reverify_v1/convergence_l.json`
- `eval/runs/20261011_reverify_v1/coverage_t7.json`
- `eval/runs/20261011_reverify_v1/dependency_audit.json`
- `eval/runs/20261011_reverify_v1/golden_set_t4.json`
- `eval/runs/20261011_reverify_v1/log_redaction_test.json`
- `eval/runs/20261011_reverify_v1/model_facts_m.json`
- `eval/runs/20261011_reverify_v1/model_io_t5.json`
- `eval/runs/20261011_reverify_v1/parser_fuzz_t3.json`
- `eval/runs/20261011_reverify_v1/parser_hardening_p.json`
- `eval/runs/20261011_reverify_v1/phase_s_reverification.json`
- `eval/runs/20261011_reverify_v1/pics_smoke_x.json`
- `eval/runs/20261011_reverify_v1/release_readiness_r.json`
- `eval/runs/20261011_reverify_v1/secrets_scan.json`
- `eval/runs/20261011_reverify_v1/soak_t6.json`
- `eval/runs/20261012_195100_tests/count.json`
- `eval/runs/20261012_195123_tests/count.json`
- `eval/runs/20261012_203519_suite/result.json`
- `eval/runs/20261012_210432_claims/report.json`
- `eval/runs/20261012_210727_suite/result.json`
- `eval/runs/20261012_220510_claims/report.json`
- `eval/runs/20261012_220929_tests/count.json`
- `eval/runs/20261012_221411_claims/report.json`
- `eval/runs/benchmark_evidence/postprocess_latency.json`
- `eval/runs/test_markers/DONE.json`
- `eval/task2_negatives_and_stress.py`
- `eval/task3_deployment_latency.py`
- `eval/task4f_crop_contact_sheet.py`
- `eval/task7_synthetic_indian_diagnostic.py`
### `frontend/` (24 files shown of first 400 tracked)
- `frontend/.env.example`
- `frontend/index.html`
- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/src/App.tsx`
- `frontend/src/api.ts`
- `frontend/src/app/english.ts`
- `frontend/src/app/preloader.ts`
- `frontend/src/app/specimens.ts`
- `frontend/src/app/state.tsx`
- `frontend/src/app/util.ts`
- `frontend/src/global.d.ts`
- `frontend/src/knowledge.ts`
- `frontend/src/main.tsx`
- `frontend/src/styles.css`
- `frontend/src/views/ChatModal.tsx`
- `frontend/src/views/DeskView.tsx`
- `frontend/src/views/GoogleSignIn.tsx`
- `frontend/src/views/LedgerView.tsx`
- `frontend/src/views/ReviewQueueView.tsx`
- `frontend/src/views/StaffView.tsx`
- `frontend/src/views/WatchlistView.tsx`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
### `ml_service/` (30 files shown of first 400 tracked)
- `ml_service/Dockerfile`
- `ml_service/README.md`
- `ml_service/app.py`
- `ml_service/doc_forgery.py`
- `ml_service/doctype_cls.py`
- `ml_service/face_match.py`
- `ml_service/face_policy.py`
- `ml_service/main.py`
- `ml_service/media_processor.py`
- `ml_service/model_fetch.py`
- `ml_service/models/MODEL_MANIFEST.json`
- `ml_service/models/aadhaar_fields.onnx`
- `ml_service/models/card.onnx`
- `ml_service/models/doctype_v2.meta.json`
- `ml_service/models/doctype_v2_int8.meta.json`
- `ml_service/models/face_embed.meta.json`
- `ml_service/models/rfdetr_aadhaar.meta.json`
- `ml_service/models/rfdetr_aadhaar_int8.meta.json`
- `ml_service/models/rfdetr_card.meta.json`
- `ml_service/models/rfdetr_card.onnx.meta.json`
- `ml_service/models/rfdetr_card_int8.meta.json`
- `ml_service/models/rfdetr_card_int8.onnx.meta.json`
- `ml_service/models/rfdetr_id_fields.meta.json`
- `ml_service/models/rfdetr_id_fields_int8.meta.json`
- `ml_service/models/rfdetr_mrz.meta.json`
- `ml_service/models/rfdetr_mrz_int8.meta.json`
- `ml_service/models/thresholds.json`
- `ml_service/rectification.py`
- `ml_service/requirements.txt`
- `ml_service/yolo_roi.py`
### `scripts/` (16 files shown of first 400 tracked)
- `scripts/anchor_ledger.py`
- `scripts/audit_independent_secrets.py`
- `scripts/audit_secrets_s1.py`
- `scripts/check_coverage.py`
- `scripts/check_repo_hygiene.py`
- `scripts/count_tests.py`
- `scripts/owner_check_isolation.ps1`
- `scripts/release_verdict.py`
- `scripts/render_blueprint.py`
- `scripts/render_handoff.py`
- `scripts/render_switch_readiness.py`
- `scripts/reverify_auth_v3.py`
- `scripts/reverify_logs_v4.py`
- `scripts/run_suite_n.py`
- `scripts/skill_router.py`
- `scripts/verify_blueprint_claims.py`
### `tests/` (55 files shown of first 400 tracked)
- `tests/conftest.py`
- `tests/test_auth.py`
- `tests/test_authz.py`
- `tests/test_ci_workflow_t8.py`
- `tests/test_code_health_sweep_c.py`
- `tests/test_codebase.py`
- `tests/test_composites.py`
- `tests/test_contract_snapshots_t2.py`
- `tests/test_converters.py`
- `tests/test_coverage_stability_t7.py`
- `tests/test_csp_headers.py`
- `tests/test_csv_injection.py`
- `tests/test_detection_flags.py`
- `tests/test_detector_backend.py`
- `tests/test_detectors.py`
- `tests/test_e2e_screening.py`
- `tests/test_eval_metrics.py`
- `tests/test_face_match.py`
- `tests/test_forensics.py`
- `tests/test_golden_set_t4.py`
- `tests/test_identity.py`
- `tests/test_indian_specimens.py`
- `tests/test_invariants_t1.py`
- `tests/test_ledger_chain.py`
- `tests/test_load_soak_t6.py`
- `tests/test_media_processor_tempfile.py`
- `tests/test_mixed_media.py`
- `tests/test_ml_service_contract.py`
- `tests/test_model_io_t5.py`
- `tests/test_mrz.py`
- `tests/test_parser_fuzz_t3.py`
- `tests/test_phase_m_model_facts.py`
- `tests/test_phase_p_parser_hardening.py`
- `tests/test_phase_x_pics_smoke.py`
- `tests/test_privacy.py`
- `tests/test_qr_and_verification.py`
- `tests/test_rate_limit_proxy.py`
- `tests/test_rectification.py`
- `tests/test_repo_hygiene.py`
- `tests/test_revamp.py`
- `tests/test_rfdetr_inference.py`
- `tests/test_screening.py`
- `tests/test_sessions.py`
- `tests/test_syndicate.py`
- `tests/test_synth_fields.py`
- `tests/test_synth_mrz.py`
- `tests/test_upload_limits.py`
- `tests/test_v8_csp.py`
- `tests/test_v8_docs_hygiene.py`
- `tests/test_v8_face_policy.py`
- `tests/test_v8_invariants.py`
- `tests/test_v8_merkle.py`
- `tests/test_v8_release_verdict.py`
- `tests/test_v8_resume.py`
- `tests/test_yolo_roi.py`
### `training/` (28 files shown of first 400 tracked)
- `training/build_aadhaar_coco.py`
- `training/build_card_trainset.py`
- `training/build_card_trainset_v2.py`
- `training/build_doctype_dataset_v2.py`
- `training/build_id_fields_dataset.py`
- `training/build_mrz_dataset.py`
- `training/convert_midv_to_coco.py`
- `training/convert_yolo_to_coco.py`
- `training/download_midv_subset.py`
- `training/export_card_v2.py`
- `training/indian_specimens/CAPTURE_PROTOCOL.md`
- `training/indian_specimens/import_indian_specimens.py`
- `training/indian_specimens/make_specimen_sheets.py`
- `training/job_markers.py`
- `training/label_cards.py`
- `training/make_composites.py`
- `training/requirements-train.txt`
- `training/run_data_inventory.py`
- `training/run_midv_conversion.py`
- `training/synth_fields.py`
- `training/synth_mrz.py`
- `training/train_aadhaar_rfdetr.py`
- `training/train_card_rfdetr.py`
- `training/train_doctype_mobilenet.py`
- `training/train_id_fields_rfdetr.py`
- `training/train_mrz_rfdetr.py`
- `training/upload_models_hf.py`
- `training/write_meta.py`

### Python Line Counts (`wc -l` across core folders)
Total `.py` files counted: 173 (Total lines of Python: 44948).

| Lines | File Path |
|:---:|:---|
| 331 | `app/codebase.py` |
| 304 | `app/config.py` |
| 103 | `app/dl_verify.py` |
| 271 | `app/doc_forgery.py` |
| 225 | `app/doctype_cls.py` |
| 497 | `app/extraction.py` |
| 197 | `app/face.py` |
| 551 | `app/face_match.py` |
| 71 | `app/face_policy.py` |
| 973 | `app/forensics.py` |
| 172 | `app/guide.py` |
| 22 | `app/heif_support.py` |
| 644 | `app/identity.py` |
| 168 | `app/keys.py` |
| 199 | `app/llm.py` |
| 5261 | `app/main.py` |
| 589 | `app/mrz.py` |
| 161 | `app/mrz_enhancer.py` |
| 471 | `app/qr_decoder.py` |
| 164 | `app/rectification.py` |
| 133 | `app/remote_ml.py` |
| 150 | `app/replay_detector.py` |
| 1750 | `app/screening.py` |
| 599 | `app/session.py` |
| 233 | `app/stats.py` |
| 151 | `app/syndicate.py` |
| 411 | `app/tampering.py` |
| 92 | `app/transliterate.py` |
| 271 | `app/validation.py` |
| 1319 | `app/yolo_roi.py` |
| 214 | `eval/audit_leakage.py` |
| 151 | `eval/audit_task1.py` |
| 121 | `eval/audit_task1c.py` |
| 435 | `eval/audit_v4.py` |
| 134 | `eval/benchmark.py` |
| 217 | `eval/dataset.py` |
| 156 | `eval/eval_aadhaar_rfdetr.py` |
| 383 | `eval/eval_face_proxy.py` |
| 169 | `eval/eval_id_fields.py` |
| 149 | `eval/eval_indian_specimens.py` |
| 78 | `eval/eval_int8.py` |
| 217 | `eval/eval_mrz.py` |
| 208 | `eval/eval_pipeline_latency.py` |
| 111 | `eval/eval_replay.py` |
| 551 | `eval/evaluate.py` |
| 311 | `eval/forensics_benchmark.py` |
| 192 | `eval/metrics.py` |
| 88 | `eval/repro_ledger.py` |
| 129 | `eval/run_all.py` |
| 306 | `eval/task2_negatives_and_stress.py` |
| 208 | `eval/task3_deployment_latency.py` |
| 131 | `eval/task4f_crop_contact_sheet.py` |
| 329 | `eval/task7_synthetic_indian_diagnostic.py` |
| 101 | `ml_service/app.py` |
| 170 | `ml_service/doc_forgery.py` |
| 169 | `ml_service/doctype_cls.py` |
| 494 | `ml_service/face_match.py` |
| 71 | `ml_service/face_policy.py` |
| 523 | `ml_service/main.py` |
| 426 | `ml_service/media_processor.py` |
| 237 | `ml_service/model_fetch.py` |
| 148 | `ml_service/rectification.py` |
| 1144 | `ml_service/yolo_roi.py` |
| 407 | `scripts/agent_ctl.py` |
| 177 | `scripts/anchor_ledger.py` |
| 128 | `scripts/audit_independent_secrets.py` |
| 179 | `scripts/audit_secrets_s1.py` |
| 218 | `scripts/build_doctype.py` |
| 223 | `scripts/build_doctype_dataset.py` |
| 151 | `scripts/check_coverage.py` |
| 98 | `scripts/check_repo_hygiene.py` |
| 91 | `scripts/collect_features.py` |
| 130 | `scripts/count_tests.py` |
| 103 | `scripts/generate_face_meta.py` |
| 167 | `scripts/make_card_scenes.py` |
| 66 | `scripts/normalize_idcard.py` |
| 82 | `scripts/prep_yolo.py` |
| 263 | `scripts/release_verdict.py` |
| 159 | `scripts/render_blueprint.py` |
| 330 | `scripts/render_handoff.py` |
| 162 | `scripts/render_switch_readiness.py` |
| 118 | `scripts/reverify_auth_v3.py` |
| 84 | `scripts/reverify_logs_v4.py` |
| 132 | `scripts/run_suite_n.py` |
| 16 | `scripts/show_secrets_summary.py` |
| 66 | `scripts/skill_router.py` |
| 186 | `scripts/synthetic_test_images.py` |
| 67 | `scripts/train_classifier.py` |
| 257 | `scripts/train_vit_onnx.py` |
| 108 | `scripts/train_yolo.py` |
| 20 | `scripts/update_audit_from_claims.py` |
| 400 | `scripts/verify_blueprint_claims.py` |
| 41 | `tests/conftest.py` |
| 228 | `tests/test_auth.py` |
| 303 | `tests/test_authz.py` |
| 55 | `tests/test_ci_workflow_t8.py` |
| 168 | `tests/test_code_health_sweep_c.py` |
| 175 | `tests/test_codebase.py` |
| 28 | `tests/test_composites.py` |
| 187 | `tests/test_contract_snapshots_t2.py` |
| 158 | `tests/test_converters.py` |
| 133 | `tests/test_coverage_stability_t7.py` |
| 43 | `tests/test_csp_headers.py` |
| 97 | `tests/test_csv_injection.py` |
| 167 | `tests/test_detection_flags.py` |
| 181 | `tests/test_detector_backend.py` |
| 118 | `tests/test_detectors.py` |
| 125 | `tests/test_e2e_screening.py` |
| 56 | `tests/test_eval_metrics.py` |
| 262 | `tests/test_face_match.py` |
| 144 | `tests/test_forensics.py` |
| 175 | `tests/test_golden_set_t4.py` |
| 138 | `tests/test_identity.py` |
| 115 | `tests/test_indian_specimens.py` |
| 247 | `tests/test_invariants_t1.py` |
| 281 | `tests/test_ledger_chain.py` |
| 196 | `tests/test_load_soak_t6.py` |
| 44 | `tests/test_media_processor_tempfile.py` |
| 194 | `tests/test_mixed_media.py` |
| 208 | `tests/test_ml_service_contract.py` |
| 129 | `tests/test_model_io_t5.py` |
| 92 | `tests/test_mrz.py` |
| 176 | `tests/test_parser_fuzz_t3.py` |
| 248 | `tests/test_phase_m_model_facts.py` |
| 337 | `tests/test_phase_p_parser_hardening.py` |
| 249 | `tests/test_phase_x_pics_smoke.py` |
| 235 | `tests/test_privacy.py` |
| 58 | `tests/test_qr_and_verification.py` |
| 58 | `tests/test_rate_limit_proxy.py` |
| 139 | `tests/test_rectification.py` |
| 11 | `tests/test_repo_hygiene.py` |
| 288 | `tests/test_revamp.py` |
| 149 | `tests/test_rfdetr_inference.py` |
| 496 | `tests/test_screening.py` |
| 454 | `tests/test_sessions.py` |
| 223 | `tests/test_syndicate.py` |
| 71 | `tests/test_synth_fields.py` |
| 43 | `tests/test_synth_mrz.py` |
| 152 | `tests/test_upload_limits.py` |
| 129 | `tests/test_v8_csp.py` |
| 448 | `tests/test_v8_docs_hygiene.py` |
| 530 | `tests/test_v8_face_policy.py` |
| 186 | `tests/test_v8_invariants.py` |
| 123 | `tests/test_v8_merkle.py` |
| 197 | `tests/test_v8_release_verdict.py` |
| 213 | `tests/test_v8_resume.py` |
| 246 | `tests/test_yolo_roi.py` |
| 124 | `training/build_aadhaar_coco.py` |
| 395 | `training/build_card_trainset.py` |
| 407 | `training/build_card_trainset_v2.py` |
| 118 | `training/build_doctype_dataset_v2.py` |
| 142 | `training/build_id_fields_dataset.py` |
| 156 | `training/build_mrz_dataset.py` |
| 355 | `training/convert_midv_to_coco.py` |
| 148 | `training/convert_yolo_to_coco.py` |
| 114 | `training/download_midv_subset.py` |
| 88 | `training/export_card_v2.py` |
| 210 | `training/indian_specimens/import_indian_specimens.py` |
| 437 | `training/indian_specimens/make_specimen_sheets.py` |
| 92 | `training/job_markers.py` |
| 161 | `training/label_cards.py` |
| 219 | `training/make_composites.py` |
| 127 | `training/run_data_inventory.py` |
| 42 | `training/run_midv_conversion.py` |
| 441 | `training/synth_fields.py` |
| 127 | `training/synth_mrz.py` |
| 141 | `training/train_aadhaar_rfdetr.py` |
| 375 | `training/train_card_rfdetr.py` |
| 305 | `training/train_doctype_mobilenet.py` |
| 144 | `training/train_id_fields_rfdetr.py` |
| 135 | `training/train_mrz_rfdetr.py` |
| 265 | `training/upload_models_hf.py` |
| 191 | `training/write_meta.py` |

## 3. Deployment Topology

### Deployment Targets & Branches
- **Vercel Production Project:** Deploys branch `main` to `https://vibe-check-point.vercel.app` (FastAPI backend serverless functions via `api/index.py`, pure static frontend assets served via `/app/static`).
- **Vercel Test/Staging Project:** `vibe-check-point-test` project deploys preview/test branches (`stage_test`, `ml/patch-v8`) to `https://vibe-check-point-test.vercel.app`.
- **Hugging Face Space (`ml_service`):** Space repository `koropanda/no-cap-detectors` (Docker container on port 7860).
  - **Hardware Tier:** CPU Basic (2 vCPU, 16 GB RAM, free tier).
  - **Sleep Policy:** Standard free HF Spaces sleep after 48 hours of inactivity (cold-start spin-up takes 45–90s when waking from sleep).

### Runtime Python Versions Across Environments
- Local development (`.python-version`): `3.12`
- Dockerfile (`ml_service/Dockerfile`): `python:3.11-slim`
- GitHub Actions CI (`.github/workflows/ci.yml`): `python-version: "3.11"`
- `pyproject.toml`: `requires-python = ">=3.11"`

### `vercel.json` (Full Contents)
```json
{
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "api/index.py"
    }
  ]
}
```

### `.vercelignore` (Full Contents)
```text
.venv
new
_backup
scripts
tests
data
__pycache__
*.py[cod]
.env
.env.local
.env.*.local
.vercel
.git
*.md
HOW_TO_HOST.md
SIH_PRESENTATION.md
LICENSE
ml_service
runs
weights
pics
frontend
node_modules
**/node_modules
*.pt
app/models/card.onnx
app/models/aadhaar_fields.onnx
app/models/*.onnx
eval/
training/
*.zip
*.tar.gz
```

### `ml_service/Dockerfile` (Full Contents)
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for OpenCV and network tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and models
COPY . .

# Expose standard port for documentation
EXPOSE 7860

# Universal runner: binds to $PORT if provided (Render, Railway, Cloud Run),
# or defaults to 7860 (Hugging Face Spaces, local Docker)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860}"]

```

## 4. Environment Variable Inventory

All values are strictly omitted. Only names, defaults, references, and service bindings are recorded.

| Environment Variable Name | First Code Reference | Code Default | Required? | Service | Secret? |
|:---|:---|:---|:---:|:---:|:---:|
| `AADHAAR_FIELDS_ONNX_PATH` | `app/yolo_roi.py:304` (+1) | `None` | no | ML/Vercel | no |
| `AI_DETECTOR_ENDPOINT` | `app/main.py:539` | `None` | no | Vercel | no |
| `AI_DETECTOR_KEY` | `app/main.py:549` (+1) | `None` | no | Vercel | yes |
| `AI_DETECTOR_MODELS` | `app/main.py:544` | `genai` | no | Vercel | no |
| `AI_DETECTOR_MODEL_DIR` | `app/main.py:704` (+1) | `None` | no | ML/Vercel | no |
| `AI_DETECTOR_MODEL_SHA256` | `ml_service/main.py:114` | `DEFAULT_AI_DETECTOR_SHA256` | no | ML | no |
| `AI_DETECTOR_MODEL_URL` | `app/main.py:710` (+3) | `None` | no | ML/Vercel | no |
| `AI_DETECTOR_PROVIDER` | `app/main.py:930` | `None` | no | Vercel | no |
| `AI_DETECTOR_SECRET` | `app/main.py:550` | `None` | no | Vercel | yes |
| `AI_DETECTOR_TIMEOUT_MS` | `app/main.py:541` | `2500` | no | Vercel | no |
| `ALLOWED_DOMAINS` | `app/main.py:1232` | `` | no | Vercel | no |
| `ALLOWED_EMAILS` | `app/main.py:1235` | `` | no | Vercel | no |
| `ALLOWED_ORIGINS` | `ml_service/app.py:78` (+1) | `` | no | ML | no |
| `ALLOW_DEV_CORS` | `app/main.py:2327` | `` | no | Vercel | no |
| `ANCHOR_SESSION_COOKIE` | `scripts/anchor_ledger.py:163` | `` | no | both | no |
| `APP_MODELS_DIR` | `app/config.py:276` | `None` | no | Vercel | no |
| `AUTO_DOWNLOAD_MODELS` | `app/face_match.py:117` (+4) | `false` | no | ML/Vercel | no |
| `CARD_DETECTOR_BACKEND` | `app/yolo_roi.py:103` (+2) | `None, os.getenv("DETECTOR_BACKEND", "yol` | no | ML/Vercel | no |
| `CONF_THRES_AADHAAR_NO` | `app/yolo_roi.py:81` (+1) | `0.35` | no | ML/Vercel | no |
| `CONF_THRES_DOB` | `app/yolo_roi.py:82` (+1) | `0.35` | no | ML/Vercel | no |
| `CONF_THRES_DOCUMENT` | `app/yolo_roi.py:79` (+3) | `0.35` | no | ML/Vercel | no |
| `CONF_THRES_GENDER` | `app/yolo_roi.py:83` (+1) | `0.35` | no | ML/Vercel | no |
| `CONF_THRES_NAME` | `app/yolo_roi.py:84` (+1) | `0.35` | no | ML/Vercel | no |
| `CONF_THRES_PHOTO` | `app/yolo_roi.py:85` (+1) | `0.35` | no | ML/Vercel | no |
| `CORS_ORIGINS` | `app/main.py:2326` | `` | no | Vercel | no |
| `CSP_STRICT_ENFORCE` | `app/main.py:2286` | `0` | no | Vercel | no |
| `DATABASE_URL` | `app/main.py:1118` | `` | no | Vercel | yes |
| `DATA_MODELS_DIR` | `app/config.py:278` | `None` | no | Vercel | no |
| `DEMO_PASS_ENABLED` | `app/main.py:1266` | `` | no | Vercel | yes |
| `DETECTOR_BACKEND` | `app/yolo_roi.py:91` (+2) | `yolov8` | no | ML/Vercel | no |
| `DOCTYPE_BACKEND` | `app/doctype_cls.py:45` (+2) | `None, v1` | no | ML/Vercel | no |
| `DOCTYPE_CONFIDENCE_REVIEW` | `app/config.py:296` | `0.75` | no | Vercel | no |
| `DOCTYPE_ONNX_PATH` | `app/doctype_cls.py:57` (+1) | `None` | no | ML/Vercel | no |
| `DOCTYPE_REVIEW_THRESHOLD` | `app/doctype_cls.py:192` (+1) | `0.75` | no | ML/Vercel | no |
| `DOCTYPE_TEMPERATURE` | `app/doctype_cls.py:191` (+1) | `1.35` | no | ML/Vercel | no |
| `ENABLE_CARD_RECTIFICATION` | `app/rectification.py:138` (+1) | `false` | no | ML/Vercel | no |
| `ENABLE_GEMINI_FALLBACK` | `app/llm.py:115` | `false` | no | Vercel | no |
| `ENVIRONMENT` | `app/main.py:2550` (+1) | `None` | no | Vercel | no |
| `FACE_EMBED_MODEL` | `app/face_match.py:115` (+7) | `, None` | no | ML/Vercel | no |
| `FACE_EMBED_SAME` | `app/face_policy.py:34` (+1) | `` | no | ML/Vercel | no |
| `FACE_EMBED_SAME_AGED` | `app/face_policy.py:35` (+1) | `` | no | ML/Vercel | no |
| `FACE_MODEL_SHA256` | `ml_service/face_match.py:135` | `None` | no | ML | no |
| `FACE_SIMILARITY_MIN` | `app/config.py:303` | `0.60` | no | Vercel | no |
| `FAIL_CLOSED_ON_DEGRADED` | `ml_service/main.py:376` | `false` | no | ML | no |
| `FIELD_DETECTOR_BACKEND` | `app/yolo_roi.py:120` (+2) | `None, yolov8` | no | ML/Vercel | no |
| `GEMINI_API_KEY` | `app/llm.py:116` (+3) | `None` | no | Vercel | yes |
| `GEMINI_KEY` | `app/llm.py:116` (+3) | `None` | no | Vercel | yes |
| `GEMINI_MODEL` | `app/main.py:5056` (+1) | `None` | no | Vercel | no |
| `GITHUB_TOKEN` | `app/main.py:4470` | `` | no | Vercel | yes |
| `GOOGLE_CLIENT_ID` | `app/main.py:1200` | `` | no | Vercel | no |
| `HF_MODEL_REPO` | `ml_service/face_match.py:177` (+2) | `DEFAULT_REPO, koropanda/no-cap-detectors` | no | ML | no |
| `HF_MODEL_REVISION` | `ml_service/main.py:371` (+1) | `None, main` | no | ML | no |
| `HF_TOKEN` | `ml_service/model_fetch.py:126` | `None` | no | ML | yes |
| `ID_FIELD_DETECTOR_BACKEND` | `app/yolo_roi.py:150` (+1) | `None` | no | ML/Vercel | no |
| `KEEPALIVE_INTERVAL` | `app/main.py:1577` | `45` | no | Vercel | no |
| `KV_URL` | `app/main.py:2181` | `None` | no | Vercel | no |
| `LEDGER_GIST_ID` | `app/main.py:4471` | `` | no | Vercel | no |
| `LITELLM_API_KEY` | `app/llm.py:33` | `dummy-key` | no | Vercel | yes |
| `LITELLM_EXTRACT_MODEL` | `app/llm.py:88` | `gpt-4o` | no | Vercel | no |
| `LITELLM_REASONING_MODEL` | `app/llm.py:188` | `gpt-4o` | no | Vercel | no |
| `LITELLM_URL` | `app/llm.py:29` | `None` | no | Vercel | no |
| `MASTER_VAULT_KEY` | `app/keys.py:93` | `` | no | Vercel | yes |
| `MASTER_VAULT_KEY_PREV` | `app/keys.py:100` | `` | no | Vercel | yes |
| `ML_ALLOW_NO_AUTH` | `ml_service/main.py:37` | `` | no | ML | yes |
| `ML_BREAKER_BACKOFF` | `app/remote_ml.py:17` | `45.0` | no | Vercel | no |
| `ML_CONNECT_TIMEOUT` | `app/config.py:266` | `2.0` | no | Vercel | no |
| `ML_CONSECUTIVE_FAILURES` | `app/remote_ml.py:16` | `3` | no | Vercel | no |
| `ML_MODELS_DIR` | `app/config.py:280` | `None` | no | Vercel | no |
| `ML_SECRET_KEY` | `app/remote_ml.py:107` (+1) | `None` | no | both | yes |
| `ML_SERVICE_CONNECT_TIMEOUT` | `app/remote_ml.py:100` | `1.0` | no | Vercel | no |
| `ML_SERVICE_SECRET` | `app/remote_ml.py:107` (+1) | `None` | no | ML/Vercel | yes |
| `ML_SERVICE_TIMEOUT` | `app/face_match.py:308` (+1) | `2.0, 6.0` | no | Vercel | no |
| `ML_SERVICE_URL` | `app/doc_forgery.py:80` (+14) | `None` | no | both | no |
| `ML_TIMEOUT` | `app/config.py:265` | `6.0` | no | Vercel | no |
| `MODEL_CACHE_DIR` | `ml_service/main.py:372` (+1) | `str(DEFAULT_MODELS_DIR, str(models_dir` | no | ML | no |
| `MRZ_DETECTOR_BACKEND` | `app/yolo_roi.py:137` (+2) | `None, bottom20` | no | ML/Vercel | no |
| `MRZ_ONNX_PATH` | `app/yolo_roi.py:201` (+1) | `None` | no | ML/Vercel | no |
| `PREWARM_MODELS` | `ml_service/main.py:387` | `true` | no | ML | no |
| `RAW_FIELD_TTL_MINUTES` | `app/main.py:3398` | `240` | no | Vercel | no |
| `REDIS_URL` | `app/main.py:2181` | `None` | no | Vercel | no |
| `RF_DETR_FIELDS_ONNX_PATH` | `app/yolo_roi.py:297` (+1) | `None` | no | ML/Vercel | no |
| `RF_DETR_ONNX_PATH` | `app/yolo_roi.py:175` (+1) | `None` | no | ML/Vercel | no |
| `SCREENING_RISK_MAX_GENUINE` | `app/config.py:298` | `25` | no | Vercel | no |
| `SCREENING_RISK_MIN_REJECT` | `app/config.py:299` | `55` | no | Vercel | no |
| `SETU_API_KEY` | `app/dl_verify.py:82` | `None` | no | Vercel | yes |
| `SETU_CLIENT_ID` | `app/dl_verify.py:82` (+1) | `, None` | no | Vercel | no |
| `SETU_CLIENT_SECRET` | `app/dl_verify.py:88` | `` | no | Vercel | yes |
| `SETU_URL` | `app/dl_verify.py:92` | `https://api.setu.co/api/verify/dl` | no | Vercel | no |
| `SUPER_ADMINS` | `app/main.py:1246` | `` | no | Vercel | no |
| `TAMPER_CLF_ONNX_PATH` | `app/main.py:2426` (+1) | `os.path.join(_model_dir, "tamper_classif` | no | Vercel | no |
| `TAMPER_MODEL_BACKEND` | `ml_service/main.py:315` | `heuristic` | no | ML | no |
| `TAMPER_RISK_FLAG` | `app/config.py:301` | `50.0` | no | Vercel | no |
| `TESTING` | `app/keys.py:58` (+2) | `None` | no | Vercel | no |
| `TRUST_PROXY_HEADERS` | `app/main.py:2171` | `` | no | Vercel | no |
| `VERCEL` | `app/main.py:1575` (+3) | `None` | no | Vercel | no |
| `YOLO_ROI_ONNX_PATH` | `app/yolo_roi.py:189` (+1) | `None` | no | ML/Vercel | no |

### Service Environment Variable Assignments
- **Configured on Vercel:** `DATABASE_URL`, `MASTER_VAULT_KEY`, `SESSION_SECRET`, `ML_SERVICE_URL`, `ML_SECRET_KEY`, `DEMO_PASS_ENABLED`, `ENABLE_CARD_RECTIFICATION`, `OCR_FAST_FALLBACK`, `ALLOWED_ORIGINS`, `STAGE_LABEL`.
- **Configured on HF Space (`ml_service`):** `ML_SECRET_KEY`, `DETECTOR_BACKEND`, `CARD_DETECTOR_BACKEND`, `FIELD_DETECTOR_BACKEND`, `CONF_THRES_DOCUMENT`, `CONF_THRES_AADHAAR_NO`, `CONF_THRES_DOB`, `CONF_THRES_GENDER`, `CONF_THRES_NAME`, `CONF_THRES_PHOTO`, `ALLOWED_ORIGINS`, `MAX_MEDIA_BYTES`.

## 5. Dependencies & Runtime Posture

### `requirements.txt` (Vercel Production Build)
```text
fastapi==0.141.1
uvicorn==0.52.4
sqlalchemy==2.0.52
psycopg2-binary==2.9.12
pypdf==6.16.2
requests==2.34.2
python-multipart==0.0.32
slowapi==0.1.10
google-auth==2.57.0
python-dotenv==1.2.3
numpy==2.3.5
Pillow==12.3.0
openai==2.54.0
pydantic==2.13.4

# Local-only (NOT installed on Vercel): on-device AI pretrained model runtime.
# Only needed if you run AI_DETECTOR_PROVIDER=self-hosted on a laptop/worker.
# onnxruntime
httpx==0.28.1
cryptography==50.0.1
```

### `ml_service/requirements.txt` (Hugging Face Space ML Container)
```text
fastapi==0.141.1
uvicorn==0.52.4
python-multipart==0.0.32
opencv-python-headless==5.0.0.93
onnxruntime==1.29.0
pillow==12.3.0
numpy==2.3.5
pydantic==2.13.4
httpx==0.28.1
requests==2.34.2
gradio==6.28.0
pypdf==6.16.2
huggingface-hub==1.28.0
```

### Optional Runtime Imports & Degradation Behaviors (`try/except ImportError`)
| Package / Import | Where Handled | Runtime Degradation Behavior if Missing |
|:---|:---|:---|
| `onnxruntime` | `app/yolo_roi.py, ml_service/yolo_roi.py` | Neural card & Aadhaar field detection degrades to classical CV heuristic bounding boxes (tagged source: heuristic, forcing REVIEW). |
| `fitz (PyMuPDF)` | `app/extraction.py, ml_service/media_processor.py` | Fast PDF page rendering falls back to pypdf / pypdfium2 in-memory rasterization. |
| `pypdfium2` | `ml_service/media_processor.py` | PDF rendering falls back to pypdf embedded image extraction; vector-only pages without text layer return render_failed. |
| `pillow_heif` | `app/heif_support.py, ml_service/media_processor.py` | Apple iPhone HEIC/HEIF photo decoding is disabled; returns HTTP 415. |
| `av (PyAV)` | `ml_service/media_processor.py` | In-memory burst video decoding for Apple Live Photo motion liveness is skipped (experimental: true). |
| `insightface / cv2` | `ml_service/face_engine.py, app/face_match.py` | 1:1 biometric facial comparison degrades to color/histogram heuristic; forces REVIEW verdict. |
| `psycopg2 / asyncpg` | `app/database.py` | PostgreSQL database client; if missing, app cannot connect to Neon PostgreSQL. |

### Active Environment `pip freeze` (Local Machine Snapshot)
```text
accelerate==1.15.0
aider-install==0.2.0
aiohappyeyeballs==2.7.1
aiohttp==3.14.3
aiosignal==1.4.0
altair==6.2.2
annotated-doc==0.0.5
annotated-types==0.8.0
anyio==4.14.2
APScheduler==3.11.3
attrs==26.1.0
av==18.1.0
azure-core==1.41.0
azure-identity==1.25.3
azure-storage-blob==12.30.1
backoff==2.2.1
bcrypt==5.0.0
beautifulsoup4==4.15.0
bitarray==3.11.0
bleach==6.4.0
blinker==1.9.0
boolean.py==5.0
boto3==1.43.83
botocore==1.43.83
brotli==1.2.0
build==1.5.0
CacheControl==0.14.4
certifi==2026.7.22
cffi==2.1.1
charset-normalizer==3.5.1
chromadb==1.5.9
ckzg==2.1.8
click==8.4.2
cloudpickle==3.1.2
colorama==0.4.6
contourpy==1.3.3
coverage==7.16.2
croniter==6.2.4
cryptography==50.0.1
cycler==0.12.1
cyclonedx-python-lib==11.12.0
cytoolz==1.1.0
defusedxml==0.7.1
Deprecated==1.3.1
distro==1.9.0
dnspython==2.8.0
durationpy==0.10
email-validator==2.3.0
eth-account==0.14.0
eth-hash==0.8.0
eth-keyfile==0.10.0
eth-keys==0.8.0
eth-rlp==3.0.0
eth-typing==6.0.0
eth-utils==6.0.0
eth_abi==6.0.0
Expression==5.7.0
fastapi==0.141.1
fastapi-sso==0.21.1
faster-coco-eval==1.8.0
fastjsonschema==2.22.2
fastuuid==0.14.0
filelock==3.32.4
filetype==1.2.0
flatbuffers==25.12.19
fonttools==4.65.0
frozenlist==1.8.0
fsspec==2026.7.0
geoip2==5.3.0
git-filter-repo==2.47.0
google-auth==2.57.0
googleapis-common-protos==1.75.2
gradio==6.28.0
gradio_client==2.7.1
granian==2.8.2
greenlet==3.5.5
groovy==0.1.2
grpcio==1.83.0
gunicorn==23.0.0
h11==0.16.0
hexbytes==2.0.0
hf-gradio==0.4.1
hf-xet==1.6.0
hiredis==3.4.1
hotcoco==1.0.1
httpcore==1.0.9
httptools==0.8.0
httpx==0.28.1
httpx-sse==0.4.3
huggingface_hub==1.28.0
idna==3.19
importlib_metadata==8.9.0
importlib_resources==7.1.0
iniconfig==2.3.0
inquirerpy==0.3.4
isodate==0.7.2
itsdangerous==2.2.0
Jinja2==3.1.6
jiter==0.16.0
jmespath==1.1.0
joblib==1.5.3
jsonpatch==1.33
jsonpointer==3.1.1
jsonschema==4.26.0
jsonschema-specifications==2025.9.1
jupyter_core==5.9.1
jupytext==1.19.5
kaggle==2.2.4
kagglehub==1.0.2
kagglesdk==0.1.37
kiwisolver==1.5.1
kubernetes==36.0.3
langchain==1.3.17
langchain-chroma==1.1.0
langchain-classic==1.0.8
langchain-community==0.4.2
langchain-core==1.6.0
langchain-huggingface==1.2.2
langchain-protocol==0.0.18
langchain-text-splitters==1.1.2
langgraph==1.2.11
langgraph-checkpoint==4.2.0
langgraph-prebuilt==1.1.0
langgraph-sdk==0.4.3
langsmith==0.11.1
license-expression==30.4.4
lightning-utilities==0.15.3
limits==5.8.0
litellm==1.98.0
litellm-enterprise==0.1.56
litellm-proxy-extras==0.4.86
lxml==6.1.3
markdown-it-py==4.2.0
MarkupSafe==3.0.3
matplotlib==3.11.2
maxminddb==3.2.0
mcp==1.29.1
mdit-py-plugins==0.6.1
mdurl==0.1.2
ml_dtypes==0.6.0
mmh3==5.3.0
MouseInfo==0.1.3
mpmath==1.3.0
msal==1.38.0
msal-extensions==1.3.1
msgpack==1.2.2
mss==10.2.0
multidict==6.7.1
mutagen==1.48.1
narwhals==2.25.0
nbformat==5.11.1
networkx==3.6.1
nodriver==0.50.5
numpy==2.3.5
nvidia-ml-py==13.610.43
oauthlib==3.3.1
onnx==1.23.0
onnxruntime==1.29.0
onnxruntime-gpu==1.30.0
onnxslim==0.1.96
openai==2.54.0
opencv-python==5.0.0.93
opencv-python-headless==5.0.0.93
opentelemetry-api==1.44.0
opentelemetry-exporter-otlp-proto-common==1.44.0
opentelemetry-exporter-otlp-proto-grpc==1.44.0
opentelemetry-proto==1.44.0
opentelemetry-sdk==1.44.0
opentelemetry-semantic-conventions==0.65b0
orjson==3.12.0
ormsgpack==1.12.2
overrides==7.7.0
packageurl-python==0.17.6
packaging==26.3
pandas==3.0.5
parsimonious==0.10.0
peft==0.21.2
pfzy==0.3.4
pillow==12.3.0
pillow-avif-plugin==1.6.0
pip-requirements-parser==32.0.1
pip_api==0.0.35
pip_audit==2.10.1
platformdirs==4.11.8
pluggy==1.6.0
polars==1.44.1
polars-runtime-32==1.44.1
primp==2.0.1
prompt_toolkit==3.0.53
propcache==0.5.2
protobuf==7.36.0
psutil==7.2.2
psycopg2-binary==2.9.12
py-ecc==8.0.0
py-serializable==2.1.0
pyarrow==25.0.1
pyasn1==0.6.4
pyasn1_modules==0.4.2
PyAutoGUI==0.9.54
pybase64==1.5.0
pyclipper==1.4.0
pycocotools==2.0.11
pycparser==3.0
pycryptodome==3.23.0
pydantic==2.13.4
pydantic-settings==2.15.0
pydantic_core==2.46.4
pydeck==0.9.3
pyDeprecate==0.9.0
pydub==0.25.1
pyflakes==3.4.0
PyGetWindow==0.0.9
Pygments==2.21.0
PyJWT==2.13.0
PyMsgBox==2.0.1
PyNaCl==1.6.2
pyparsing==3.3.2
pypdf==6.16.2
pypdfium2==5.14.0
pyperclip==1.11.0
PyPika==0.51.1
pyproject_hooks==1.2.0
PyRect==0.2.0
PyScreeze==1.0.1
pytest==9.1.1
pytest-cov==7.1.0
python-dateutil==2.9.0.post0
python-docx==1.2.0
python-dotenv==1.2.3
python-multipart==0.0.32
python-slugify==9.1.1
pytorch-lightning==2.6.6
pytweening==1.2.0
pytz==2026.3.post1
pyunormalize==17.0.0
pywin32==312
PyYAML==6.0.3
qrcode==8.2
rapidocr-onnxruntime==1.4.4
redis==8.1.0
referencing==0.37.0
regex==2026.7.19
requests==2.34.2
requests-oauthlib==2.0.0
requests-toolbelt==1.0.0
RestrictedPython==8.5
rfdetr==1.11.2
rich==13.9.4
rlp==5.0.0
roboflow==1.7.0
rpds-py==2026.6.3
rq==2.11.0
s3transfer==0.19.2
safehttpx==0.1.7
safetensors==0.8.0
scikit-learn==1.9.0
scipy==1.17.1
semantic-version==2.10.0
sentence-transformers==6.0.0
shapely==2.1.2
shellingham==1.5.4
simplejpeg==1.9.0
six==1.17.0
slowapi==0.1.10
sniffio==1.3.1
sortedcontainers==2.4.0
soundfile==0.14.0
soupsieve==2.10
SQLAlchemy==2.0.52
sse-starlette==3.4.8
starlette==1.6.0
streamlit==1.62.0
supervision==0.30.7
sympy==1.14.0
tenacity==9.1.4
text-unidecode==1.3
threadpoolctl==3.6.0
tiktoken==0.14.0
tokenizers==0.23.1
toml==0.10.2
tomli==2.4.1
tomli_w==1.2.0
tomlkit==0.14.0
toolz==1.1.0
torch==2.11.0+cu128
torch-hungarian==0.1.0rc0
torchmetrics==1.8.2
torchvision==0.26.0+cu128
tqdm==4.70.0
traitlets==5.16.1
transformers==5.16.0
typer==0.25.1
typing-inspection==0.4.4
typing_extensions==4.16.0
tzdata==2026.3
tzlocal==5.4.4
ultrafast-pycocotools==0.1.13
ultralytics==8.4.156
ultralytics-platform==0.1.48
ultralytics-thop==2.1.6
urllib3==2.7.0
uuid_utils==0.17.0
uv==0.12.13
uvicorn==0.52.4
vernier==0.5.4
watchdog==6.0.0
watchfiles==1.2.0
wcwidth==0.8.3
web3==8.0.0
webencodings==0.6.1
websocket-client==1.9.0
websockets==15.0.1
wrapt==2.4.0
xxhash==4.0.1
yarl==1.24.5
zipp==4.1.0
zstandard==0.25.0
zxing-cpp==3.1.1
```

## 6. API Surface & Inter-Service Utilization

### ML Service Route Utilization from Vercel App
| ML Endpoint Path | Vercel App Utilization |
|:---|:---|
| `/api/ml/yolo_roi` | CALLED by `app/yolo_roi.py` (primary card & Aadhaar field inference) |
| `/api/ml/aadhaar_fields` | CALLED by `app/yolo_roi.py` (semantic Aadhaar field segmentation) |
| `/api/ml/face_match` | CALLED by `app/face_match.py` (1:1 portrait verification) |
| `/api/ml/detect_image` | CALLED by `app/main.py` (AI-generated document / deepfake detection) |
| `/api/ml/doctype` | CALLED by `app/doctype_cls.py` (neural document type classification) |
| `/api/ml/doc_forgery` | CALLED by `app/doc_forgery.py` (spectral / ELA forgery detection) |
| `/api/ml/media/process_pdf` | NEVER CALLED by `app/` (Fix 3 targets this) |
| `/api/ml/media/process_live_photo` | NEVER CALLED by `app/` (Fix 3 targets this) |
| `/detect/card` | NEVER CALLED (legacy route alias in `ml_service/main.py`) |
| `/detect/fields` | NEVER CALLED (legacy route alias in `ml_service/main.py`) |
| `/classify/doctype` | NEVER CALLED (legacy route alias in `ml_service/main.py`) |
| `/health` | CALLED by keepalive and health checks |
| `/ml/health` | NEVER CALLED directly by `app/` |

### Vercel App Routes (`app/main.py` OpenAPI Routes: 62)
| Method | Route Path | Summary / Tag | Auth Required? |
|:---:|:---|:---|:---:|
| GET | `/` | Index | no |
| POST | `/api/admin/assign_role` | Assign Role | yes |
| POST | `/api/admin/demo_login` | Admin Demo Login | no |
| POST | `/api/admin/login` | Admin Login | no |
| POST | `/api/admin/logout` | Admin Logout | yes |
| GET | `/api/admin/me` | Check Auth Status | yes |
| POST | `/api/admin/remove_officer` | Remove Officer | yes |
| POST | `/api/admin/revoke_officer` | Revoke Officer | yes |
| GET | `/api/admin/signers` | List Signers | yes |
| POST | `/api/admin/unrevoke_officer` | Unrevoke Officer | yes |
| GET | `/api/analytics` | Public Analytics | no |
| GET | `/api/analytics/summary` | Public Analytics Summary | no |
| GET | `/api/border/threat_matrix` | Border Threat Matrix | no |
| GET | `/api/broadcasts` | List Broadcasts | no |
| POST | `/api/broadcasts/create` | Create Broadcast | no |
| POST | `/api/broadcasts/delete` | Retract Broadcast | no |
| POST | `/api/chat` | Ai Chat | no |
| GET | `/api/checkpoints` | Catalog Endpoint | no |
| POST | `/api/extract` | Extract Live Image | no |
| GET | `/api/guide` | Guide Endpoint | no |
| GET | `/api/health` | Health Check | no |
| POST | `/api/ledger/anchor` | Blueprint Ledger Anchor | no |
| GET | `/api/ledger/blocks` | Blueprint Ledger Blocks | no |
| GET | `/api/ledger/cert/65b/{session_id}` | Blueprint Ledger Cert 65B | no |
| GET | `/api/ledger/verify` | Blueprint Ledger Verify | yes |
| POST | `/api/ml/keepalive/ping` | Ping Ml Service | no |
| GET | `/api/ml/status` | Ping Ml Service | no |
| GET | `/api/reports/{report_id}` | Blueprint Report Detail | no |
| POST | `/api/screen` | Screen Document | yes |
| POST | `/api/screen/aadhaar-fields` | Screen Aadhaar Fields | yes |
| GET | `/api/screen/bsa65b/{session_id}` | Screening Bsa65B Certificate | yes |
| GET | `/api/screen/dossier/{report_id}` | Screening Evidentiary Dossier | yes |
| GET | `/api/screen/handover/{session_id}` | Screening Shift Handover Token | yes |
| GET | `/api/screen/ledger/anchor` | Get Ledger Anchor | yes |
| POST | `/api/screen/ledger/anchor` | Anchor Ledger Chain | yes |
| GET | `/api/screen/ledger/verify` | Verify Ledger Chain | yes |
| POST | `/api/screen/liveness` | Verify Liveness | yes |
| GET | `/api/screen/queue` | Screening Queue | yes |
| GET | `/api/screen/reports/{report_id}` | Screening Report Detail | yes |
| POST | `/api/screen/reports/{report_id}/adjudicate` | Screen Adjudicate | yes |
| GET | `/api/screen/shift-export` | Screening Shift Export | yes |
| GET | `/api/screen/syndicate-alerts` | Screening Syndicate Alerts | yes |
| GET | `/api/screen/watchlist` | Screening Watchlist | yes |
| POST | `/api/screen/watchlist/add` | Screening Watchlist Add | yes |
| POST | `/api/screen/watchlist/remove` | Screening Watchlist Remove | yes |
| POST | `/api/sessions` | Create Session | yes |
| GET | `/api/sessions` | List Sessions | yes |
| POST | `/api/sessions/close-unused` | Close Unused Sessions | yes |
| GET | `/api/sessions/ledger/blocks` | Session Ledger | yes |
| GET | `/api/sessions/ledger/verify` | Session Ledger Verify | yes |
| GET | `/api/sessions/open` | Blueprint Sessions Open | yes |
| POST | `/api/sessions/sweep-raw-fields` | Sweep Stale Raw Fields | yes |
| GET | `/api/sessions/{session_id}` | Session Detail | yes |
| POST | `/api/sessions/{session_id}/adjudicate` | Adjudicate Session | yes |
| POST | `/api/sessions/{session_id}/close` | Close Session | yes |
| POST | `/api/sessions/{session_id}/documents/{report_id}/remove` | Remove Session Document | yes |
| POST | `/api/sessions/{session_id}/documents/{report_id}/restore` | Restore Session Document | yes |
| GET | `/api/stats/overview` | Stats Overview | no |
| POST | `/api/verify` | Verify Digest | yes |
| POST | `/api/verify/aadhaar-qr` | Verify Aadhaar Qr Endpoint | yes |
| POST | `/api/verify/dl` | Verify Dl Endpoint | yes |
| GET | `/health` | Health Check | no |

### ML Service Routes (`ml_service/main.py` OpenAPI Routes: 14)
| Method | Route Path | Summary / Operation | Auth Required? |
|:---:|:---|:---|:---:|
| GET | `/` | Ml Health Check | no |
| POST | `/api/ml/aadhaar_fields` | Api Aadhaar Fields | yes |
| POST | `/api/ml/detect_image` | Api Detect Image | yes |
| POST | `/api/ml/doc_forgery` | Api Doc Forgery | yes |
| POST | `/api/ml/doctype` | Api Doctype | yes |
| POST | `/api/ml/face_match` | Api Face Match | yes |
| POST | `/api/ml/media/process_live_photo` | Api Process Live Photo | yes |
| POST | `/api/ml/media/process_pdf` | Api Process Pdf | yes |
| POST | `/api/ml/yolo_roi` | Api Yolo Roi | yes |
| POST | `/classify/doctype` | Api Doctype | no |
| POST | `/detect/card` | Api Yolo Roi | no |
| POST | `/detect/fields` | Api Aadhaar Fields | no |
| GET | `/health` | Ml Health Check | no |
| GET | `/ml/health` | Ml Health Check | no |

## 7. Models Table & Verified Metrics

All facts gathered from `ml_service/models/MODEL_MANIFEST.json`, `docs/ML_PIPELINE_CHANGES.md`, and `eval/runs/`.

| Model File | Location | Size | SHA256 (first 16) | Task | Input Size | Dataset & Samples | Eval Metrics | Status |
|:---|:---|:---:|:---:|:---|:---:|:---|:---|:---:|
| `card.onnx` | app/models & ml_service/models | 5.94 MB | `8ebbbd4ebf04b281...` | Document Card Boundary Detection | 640x640x3 | Roboflow IDcard (58 images) + Synthetic (1557 images) | mAP50: 0.992 (Card v7 frozen eval on 300 MIDV-2020: precision 1.0, recall 0.99) | Production Default |
| `rfdetr_card_int8.onnx` | ml_service/models | 37.16 MB | `ccab01630e533893...` | Document Card Boundary Detection | 640x640x3 | MIDV-2020 (500 train, 200 val, 300 test photos) | mAP50: 0.992, mAP50-95: 0.884, Latency p50: 332ms (2 threads) | Production Default when DETECTOR_BACKEND=rf_detr |
| `aadhaar_fields.onnx` | app/models & ml_service/models | 5.96 MB | `4b68407eeefae95a...` | Semantic Aadhaar Zone Segmentation | 640x640x3 | Roboflow AADHAR (2,645 images: 2,381 train, 185 val, 79 test) | mAP50: 0.923 (Aadhaar_No: 0.94, DOB: 0.93, Gender: 0.92, Name: 0.91, Photo: 0.89) | Production Default |
| `rfdetr_aadhaar_int8.onnx` | ml_service/models | 37.28 MB | `c4900ff2fcff0b50...` | Semantic Aadhaar Zone Segmentation | 640x640x3 | Roboflow AADHAR + Mendeley Synthetic (2,645 images) | mAP50: 0.938, mAP50-95: 0.812, Latency p50: 503ms | Production Default when FIELD_DETECTOR_BACKEND=rf_detr |
| `doctype_v2.onnx` | app/models & ml_service/models | 5.83 MB | `548faa0fd6cf98ca...` | Document Type Classifier | 224x224x3 | Internal balanced specimen corpus (1,629 images) | Top-1 Accuracy: 98.4%, Macro F1: 0.981 | Production Default |
| `rfdetr_mrz_int8.onnx` | ml_service/models | 37.23 MB | `a208402229d99023...` | MRZ Zone Detection (TD1, TD2, TD3) | 640x640x3 | MIDV-2020 + Synthetic Travel Documents (1,503 images) | mAP50: 0.991, Latency p50: 657ms (pipeline total) | Production Default |
| `rfdetr_id_fields_int8.onnx` | ml_service/models | 37.26 MB | `85c342e33f2b116d...` | Generic ID Card Field Segmentation | 640x640x3 | MIDV-500 / MIDV-2020 ID specimens (1,924 images) | mAP50: 0.918, Latency p50: 321ms | Production Default |
| `w600k_r50.onnx` | Hugging Face Space (`koropanda/no-cap-detectors`) | 166.31 MB | `4c06341c33c2a6f3...` | 1:1 Biometric Face Embedding / Verification | 112x112x3 | Glint360K / WebFace600K | LFW Accuracy: 99.82%, Verification threshold: cosine 0.38 | Production Default on HF Space |

## 8. Thresholds Actually in Effect

### Detector Confidence & NMS Thresholds
| Parameter / Class | Code Default | Env Override Variable | Source / Origin of Threshold |
|:---|:---:|:---|:---|
| `document` | `0.35` | `CONF_THRES_DOCUMENT` | Untuned default (heuristic baseline) |
| `card` | `0.35` | `CONF_THRES_DOCUMENT` (Fix 7 adds `CONF_THRES_CARD`) | Precision-Recall sweep on 200 validation images (`ml_service/models/thresholds.json` calibrated to 0.40 for F1 max) |
| `Aadhaar_No` | `0.35` | `CONF_THRES_AADHAAR_NO` | Untuned default from YOLO training export |
| `DOB` | `0.35` | `CONF_THRES_DOB` | Untuned default from YOLO training export |
| `Gender` | `0.35` | `CONF_THRES_GENDER` | Untuned default from YOLO training export |
| `Name` | `0.35` | `CONF_THRES_NAME` | Untuned default from YOLO training export |
| `Photo` | `0.35` | `CONF_THRES_PHOTO` | Untuned default from YOLO training export |
| NMS IoU Threshold | `0.45` | Hardcoded in `nms_numpy` | Standard YOLO non-maximum suppression overlap limit |
| Max Detections per Class | `1` (for `card`, `Photo`, `Aadhaar_No`) | Hardcoded in post-processor | Structural constraint of single-document presentation |

### Face Verification & Forensic Thresholds
| Threshold Name | Value | Enforcement Location | Consequence of Failure |
|:---|:---:|:---|:---|
| `FACE_MATCH_THRESHOLD` | `0.38` (cosine) | `app/face_match.py:28` | Score < 0.38 triggers MISMATCH (`hard_flag=True`, risk +55, FLAGGED) |
| `FACE_RELAXED_THRESHOLD` | `0.32` (cosine) | `app/face_match.py:32` | 0.32–0.38 requires supervisory officer confirmation (forces REVIEW) |
| `ELA_HIGH_THRESHOLD` | `45.0` | `app/forensics.py` | ELA anomaly score > 45.0 triggers CRITICAL FORENSIC ALERT (FLAGGED) |
| `LAPLACIAN_BLUR_MIN` | `100.0` | `app/forensics.py` | Variance < 100 flags blurred/illegible document (forces REVIEW) |

## 9. Test & CI Status

### Test Suite Execution Output (`pytest -q -m "not slow" -rs`)
```text
=========================== short test summary info ===========================
SKIPPED [2] tests\test_authz.py:162: route not registered for this method
SKIPPED [1] tests\test_codebase.py:94: local scripts/ study guides not present (gitignored)
466 passed, 3 skipped, 1 deselected, 12 warnings in 1024.77s (0:17:04)
```

### Skipped Tests & Verified Reasons
1. `tests/test_authz.py:162`: Route not registered for tested HTTP verb in test matrix (expected behavior for unmapped HTTP methods).
2. `tests/test_codebase.py:94`: Local study guides in `scripts/` are excluded by `.gitignore` in clean checkout (expected behavior).
3. 1 test deselected: Marked with `@pytest.mark.slow` (deselected by `-m "not slow"` filter).

### Ruff Linter Output (`ruff check app/ ml_service/ tests/`)
```text
All checks passed!
```

### `.github/workflows/ci.yml` (Full Contents)
```yaml
name: CI

on:
  push:
    branches: [ main, ml/detector-v3, "ml/**" ]
  pull_request:
    branches: [ main, "ml/**" ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install ruff pytest pytest-asyncio coverage pytest-cov
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

      - name: Repo Hygiene Check
        run: |
          python scripts/check_repo_hygiene.py

      - name: Lint with Ruff
        run: |
          ruff check app/ ml_service/ tests/ --exclude=Vibe-Check-point-main,.venv

      - name: Security Invariants Suite (Invariant FS & AUTH)
        run: |
          pytest tests/test_invariants_t1.py -v

      - name: Contract Snapshots & Model I/O Audit
        run: |
          pytest tests/test_contract_snapshots_t2.py tests/test_model_io_t5.py -v

      - name: Drift Test (Dual yolo_roi Alignment)
        run: |
          pytest tests/test_yolo_roi.py -k "test_yolo_roi_dual_implementation_drift"

      - name: Run Test Suite
        run: |
          pytest -v -m "not slow"

      - name: Code Coverage Ratchet Gate
        run: |
          pytest --cov=app --cov=ml_service --cov-report=json
          python scripts/check_coverage.py

      - name: Model Card Validation
        run: |
          python -c "import os; assert os.path.exists('docs/MODEL_CARD.md'), 'docs/MODEL_CARD.md must exist'"
```

**CI Requirements Posture:** CI installs only `requirements.txt` via `if [ -f requirements.txt ]; then pip install -r requirements.txt; fi`. `ml_service/requirements.txt` is NOT installed in CI (targeted by Fix 6).

## 10. Input-Handling Matrix (Synthetic Test Verification)

Every format was tested with a synthetic fixture against the live codebase:

| Input Format / Media Type | Accepted by `validate_upload_bytes`? | Decoded Where? | Handling Function (file:line) | Failure / Error Behavior |
|:---|:---:|:---:|:---|:---|
| JPEG (`image/jpeg`) | YES (`jpg`) | Vercel & ML | `app/main.py:1080` / `app/screening.py:1260` | HTTP 400 on malformed SOI/EOI, decompression bomb check (>50MP) |
| PNG (`image/png`) | YES (`png`) | Vercel & ML | `app/main.py:1080` / `app/screening.py:1260` | HTTP 400 on bad chunk CRC, decompression bomb check |
| WEBP (`image/webp`) | YES (`webp`) | Vercel & ML | `app/main.py:1080` / `app/screening.py:1260` | HTTP 400 on header truncation |
| BMP (`image/bmp`) | YES (`bmp`) | Vercel & ML | `app/main.py:1080` / `app/screening.py:1260` | HTTP 400 on invalid DIB header |
| TIFF (`image/tiff`) | YES (`bmp`) | Vercel & ML | `app/main.py:1080` / `app/screening.py:1260` | HTTP 400 on malformed IFD directory |
| HEIC/HEIF (`image/heic`) | NO (HTTP 415) | Blocked at gate | `app/main.py:1088` (`validate_upload_bytes`) | HTTP 415: 'Unsupported type — send a PDF or a jpg/png/webp/bmp image.' (Fix 2/3 target) |
| PDF (with text layer) | YES (`pdf`) | Vercel (`pypdf`) | `app/extraction.py:340` (`extract_pdf_pages_in_memory`) | HTTP 400 on corrupt trailer/xref; extracted text layer parsed for identifiers |
| PDF scan (embedded image) | YES (`pdf`) | Vercel (`pypdf`) | `app/extraction.py:318` (`_pdf_text_or_image`) | If no images and no text, returns ('', None) -> sets pdf_no_text=True -> forces REVIEW |
| PDF vector-only (no text) | YES (`pdf`) | Vercel (currently) | `app/extraction.py:318` (`_pdf_text_or_image`) | Returns ('', None) as ML media endpoint is uncalled -> sets pdf_no_text=True -> forces REVIEW |
| Motion Photo (JPEG+MP4) | YES (`jpg`) | Vercel & ML | `app/main.py:1080` / `ml_service/media_processor.py:160` | Pillow parses JPEG still; ML parser currently treats files with ftyp as empty still (Fix 1 target) |
| Apple Live Photo (HEIC+MOV) | NO (HTTP 415) | Blocked at gate | `app/main.py:1088` (`validate_upload_bytes`) | HTTP 415 because HEIC is rejected at entry gate; ML burst video wrote to tempfile (Fix 5 target) |
| Live camera frame | YES (`jpg`/`png`) | Vercel | `app/main.py:1080` (`validate_upload_bytes`) | HTTP 400 on truncated stream; processed in RAM for 1:1 face matching against document |

## 11. Latency Measurements

All latencies measured on CPU (2 vCPU threads allocated per screening budget). Data extracted from `eval/runs/20261006_190335_pipeline_latency/report.json` and `eval/runs/20261006_170704_task3_deployment_latency/report.json`:

### Full Document Screening Chains (30 Iterations per Chain, 2 Threads)
| Screening Pipeline Chain | Samples | p50 Latency | p95 Latency | Mean Latency | Gate Budget | Gate Verdict |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| `passport_mrz_chain` | 30 | **657.53 ms** | **707.23 ms** | 657.09 ms | 900.0 ms | **PASS** |
| `aadhaar_field_chain` | 30 | **503.25 ms** | **554.63 ms** | 510.51 ms | 900.0 ms | **PASS** |
| `generic_id_chain` | 30 | **321.85 ms** | **353.17 ms** | 325.21 ms | 900.0 ms | **PASS** |

### Individual Detector Component Latencies (Small CPU Spec, 2 Threads)
| Model Component | Backend / Mode | Samples | p50 Total Latency | p95 Total Latency | Preprocess Mean | Inference Mean | Postprocess Mean |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| `card.onnx` | YOLOv8n (FP32) | 30 | 191.49 ms | 229.86 ms | 12.88 ms | 180.23 ms | 1.09 ms |
| `rfdetr_card.onnx` | RF-DETR (FP32) | 30 | 449.83 ms | 508.13 ms | 17.61 ms | 435.10 ms | 1.39 ms |
| `rfdetr_card_int8.onnx` | RF-DETR (INT8) | 30 | 332.96 ms | 383.09 ms | 16.56 ms | 320.40 ms | 1.47 ms |

### Live Measurement Command
To re-run latency profiling on live deployment:
```bash
python eval/benchmark.py --models ml_service/models --runs 30 --threads 2
```

## 12. Zero-Storage Audit

Audit grepped for `tempfile`, `NamedTemporaryFile`, `open(`, `.write(`, `to_file`, `/tmp`, `cv2.imwrite`, `.save(` across the repository.

### Key Finding on Upload Bytes Persistence:
- **`ml_service/media_processor.py:306-307`:**
  ```python
  with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
      f.write(video_bytes)
  ```
  **Vulnerability:** This was the **ONLY** location in the entire codebase where user-uploaded payload bytes touched the physical disk filesystem (unlinking in `finally`). Addressed by Fix 5 (migrates to in-memory PyAV decoding via `io.BytesIO(video_bytes)`).

### Repository-Wide Disk I/O Classification:
1. `app/`: All `.save(` calls target in-memory `io.BytesIO()` buffers (Zero-Raw-Storage fully preserved).
2. `ml_service/`: All image operations (`pil_image.save(out_buf, format="PNG")`) target `io.BytesIO()` except the tempfile MP4 video slice noted above.
3. `scripts/` and `eval/`: Read local dataset images (`data/`) and write JSON evaluation metrics (`eval/runs/`). User upload data is never touched.
4. `tests/`: Generate synthetic specimen fixtures in RAM (`io.BytesIO()`) and verify unlinking behavior.

## 13. Known Issues & Open Work

### Secrets Scan Summary (`eval/runs/20261011_reverify_v1/secrets_scan.json`)
- **Working Tree Findings (59 total):**
  - **50 Findings:** False positives inside binary `.onnx` files (`ml_service/models/rfdetr_*.onnx`) where binary float weights match regex `hf_[A-Za-z0-9]{20,}`.
  - **8 Findings:** False positives inside `.ruff_cache/` indexing regex strings from `app/main.py`.
  - **1 Finding:** False positive in `app/main.py:1026` inside docstring / sanitization regex `(postgres(?:ql)?://[^\s:]+:)([^@\s]+)(@[^\s"'`]+)`.
  - **Verdict on Working Tree:** **100% FALSE POSITIVES (CLEAN)**. No active secret keys or credentials exist in working tree.
- **Git History Findings (19 total across ~9 commits):**
  - **Historical Commit `3724e9e3`:** Hardcoded Neon connection string embedded in old commit. Flagged as **S1-01** in `docs/AUDIT_V7.md` and **Item 8** in `docs/OWNER_TODO.md`. Requires human owner rotation of Neon database password via web console (cannot be done by agent).
  - **Other 18 History Findings:** Short dummy placeholders (`sk-...`, test URIs in unit test commits).

### Active Items in `docs/OWNER_TODO.md` Requiring Human Owner Action
1. **Item 8 (S1-01):** Rotate Neon database password in Neon console.
2. **Item 1:** Roboflow API key returned 401 Unauthorized (owner to refresh key in Roboflow dashboard).
3. **Item 6:** Vercel environment variable audit (`vercel env ls`) to confirm production vs preview isolation.
4. **Item 2:** Physical specimen field capture (Phase 9: 150 camera photos across smartphones).

## 14. Decision Logic Summary (`app/screening.py`)

### Risk Score Calculation & Verdict Thresholds (`_grade`)
The final screening verdict is determined by `_grade(score, hard_flag=hard_flag, can_clear=can_clear)`:
- **`FLAGGED`:** Triggered if `hard_flag == True` OR `risk_score > 55`.
- **`REVIEW`:** Triggered if `can_clear == False` OR `risk_score > 25`.
- **`CLEAR`:** Triggered ONLY if `can_clear == True` AND `hard_flag == False` AND `risk_score <= 25`.

### Conditions Forcing `can_clear = False` (Mandatory Supervisory Review)
There are 38 distinct code paths in `app/screening.py` that force `can_clear = False`, including:
1. `line 1038`: Unidentified document (no valid document number or holder).
2. `line 1062`: Passport bio-page fields missing or MRZ unparsed.
3. `line 1070`: Expired document.
4. `line 1091`: ICAO 9303 MRZ checksum validation failure.
5. `line 1096`: Discrepancy between MRZ and Visual Inspection Zone (VIZ).
6. `line 1104`: Aadhaar Verhoeff algorithm checksum mismatch.
7. `line 1113`: Income Tax PAN structural checksum / category invalid.
8. `line 1121`: Driving Licence state code or sequence invalid.
9. `line 1129`: Voter ID (EPIC) structural format invalid.
10. `line 1146`: Nepali Citizenship number / district invalid.
11. `line 1152`: Bhutan Citizenship card invalid.
12. `line 1161`: QR code content mismatch with visual document text.
13. `line 1249`: JPEG Error Level Analysis (ELA) paste anomaly detected.
14. `line 1260`: PRNU sensor noise correlation mismatch.
15. `line 1271`: 2D-FFT spectral PAPR resampling peak detected.
16. `line 1283`: Copy-move cloning forgery detected.
17. `line 1302`: Laplacian blur below legibility threshold.
18. `line 1341`: Synthetic / deepfake document generator detected.
19. `line 1369`: `pdf_no_text` (scanned PDF without extractable text layer).
20. `line 1382`: Module 2 (validation) deterministic check failure.
21. `line 1386`: Module 2 (validation) UNVERIFIED status.
22. `line 1400`: Module 3 (tampering) visual forgery detected.
23. `line 1412`: Module 4 (face match) portrait mismatch.
24. `line 1418`: Crop meta degraded to fallback heuristic (`source: "heuristic"`).
25. `line 1428`: Face mode running in non-ArcFace degraded mode.
26. `line 1432`: Inconclusive facial biometric match.
27. `line 1441`: Watchlist / law enforcement lookout hit.
28. `line 1472`: Devanagari ↔ Latin transliteration divergence.
29. `line 1533`: Syndicate recidivism / identity clash alert.

### Invariant FS (Fail-Safe Invariant)
No fallback, model degradation, heuristic mode, or missing signal may ever produce an autonomous `CLEAR`. All such instances route to `REVIEW` with an explicit diagnostic reason.

## 15. Data Inventory (Counts Only, Strictly Git-Ignored)

All raw datasets reside exclusively on local disk under `data/` and are strictly excluded from git tracking via `.gitignore`.

| Dataset Name | Image Count | Classes & Label Counts | Real vs Synthetic | Local Path | Git-Ignored? |
|:---|:---:|:---|:---:|:---|:---:|
| `AADHAR` | 2,645 | `['Aadhaar_No': 2344, 'DOB': 2282, 'Gender': 2297, 'Name': 2274, 'Photo': 79]` | Real specimen photos (Roboflow Universe) | `data/AADHAR` | YES |
| `IDcard` | 58 | `['Card': 96 total labels]` | Real generic ID photos (Roboflow Universe) | `data/IDcard` | YES |
| `card_synth` | 1,557 | `['Card': 1,596 labels]` | Synthetic card composites | `data/card_synth` | YES |
| `coco_card_v2` | 3,542 | `['Card']` | Augmented & composite card photos | `data/coco_card_v2` | YES |
| `coco_aadhaar` | 2,648 | 5 semantic fields | Converted COCO format from AADHAR | `data/coco_aadhaar` | YES |
| `coco_mrz` | 1,503 | `['MRZ']` | MIDV-2020 + Synthetic Travel Documents | `data/coco_mrz` | YES |
| `coco_id_fields` | 1,924 | 5 semantic fields | MIDV-500 / MIDV-2020 ID specimens | `data/coco_id_fields` | YES |
| `doctype_v2` | 1,629 | 6 document classes | Balanced specimen corpus | `data/doctype_v2` | YES |
| `raw/midv2020` | 1,000 | 10 document types (300 test, 200 val, 500 train) | Real smartphone photos (MIDV-2020 benchmark) | `data/raw/midv2020` | YES |

## 16. Open Questions for Owner Review

1. **Python Runtime Alignment (Fix 6):**
   `.python-version` specifies `3.12`, while `ml_service/Dockerfile` and `.github/workflows/ci.yml` specify Python `3.11`. Should we standardize all environments on Python `3.11` (recommended for onnxruntime/PyAV stability) or `3.12`?
2. **Vercel Free Tier maxDuration (Fix 11):**
   The modernized `vercel.json` configures `"maxDuration": 30`. On the Vercel Hobby (free) tier, serverless function maxDuration is capped at 10 seconds (or up to 60s depending on project creation date/Fluid Compute). Can you confirm if your Vercel project plan supports 30s?
3. **MIDV-2020 Licence Text (OWNER_TODO Item 3):**
   Please paste the final licence text from the L3I registration form into `data/DATASET_MANIFEST.md` when convenient.
4. **Historical Neon Credential Rotation (OWNER_TODO Item 8 / S1-01):**
   Please confirm once the Neon database password for the historical connection string in commit `3724e9e3` has been rotated via the Neon web console.
