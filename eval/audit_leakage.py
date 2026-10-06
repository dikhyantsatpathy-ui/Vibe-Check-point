"""
Audit Leakage Script (SIH26188 Autonomous Work Order v3.1 Task 1d).
Checks:
1. Exact file name overlap between test and train/valid splits.
2. SHA-256 hash overlap between test and train/valid images.
3. Perceptual dHash near-duplicates (Hamming distance <= 6) between test and train/valid.
4. Composite source provenance audit (confirms cutouts and backgrounds came exclusively from train-types).
Saves audit report to eval/runs/<ts>_leakage_audit/report.json.
"""

import os
import sys
import json
import hashlib
import datetime
from pathlib import Path
from PIL import Image
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent

def compute_dhash(img: Image.Image, hash_size: int = 8) -> int:
    """Compute 64-bit difference perceptual hash (dHash)."""
    resized = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
    pixels = np.array(resized, dtype=np.int32)
    diff = pixels[:, 1:] > pixels[:, :-1]
    # Flatten to integer
    bit_string = "".join(["1" if b else "0" for b in diff.flatten()])
    return int(bit_string, 2)


def hamming_distance(h1: int, h2: int) -> int:
    return bin(h1 ^ h2).count("1")


def run_leakage_audit(ts: str = None) -> dict:
    if not ts:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = REPO_ROOT / "eval" / "runs" / f"{ts}_leakage_audit"
    out_dir.mkdir(parents=True, exist_ok=True)

    data_dir = REPO_ROOT / "data" / "coco_card"
    splits = ["train", "valid", "test"]

    split_files = {}
    split_hashes = {}
    split_dhashes = {}

    for s in splits:
        ann_path = data_dir / s / "_annotations.coco.json"
        if not ann_path.exists():
            continue
        with open(ann_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        split_files[s] = []
        split_hashes[s] = {}
        split_dhashes[s] = {}

        img_dir = data_dir / s / "images"
        if not img_dir.exists():
            img_dir = data_dir / s

        for img_info in data.get("images", []):
            fname = img_info["file_name"]
            fpath = img_dir / fname
            if not fpath.exists():
                fpath = data_dir / s / fname
            if not fpath.exists():
                continue

            split_files[s].append(fname)

            with open(fpath, "rb") as f_bytes:
                content = f_bytes.read()
                h_sha = hashlib.sha256(content).hexdigest()
                split_hashes[s][fname] = h_sha

            try:
                with Image.open(fpath) as im:
                    dh = compute_dhash(im)
                    split_dhashes[s][fname] = dh
            except Exception:
                pass

    print(f"[leakage] Loaded: train={len(split_files.get('train', []))}, val={len(split_files.get('valid', []))}, test={len(split_files.get('test', []))}")

    # 1. Exact file name overlap
    test_files = set(split_files.get("test", []))
    train_files = set(split_files.get("train", []))
    val_files = set(split_files.get("valid", []))

    fname_overlap_train = list(test_files.intersection(train_files))
    fname_overlap_val = list(test_files.intersection(val_files))

    # 2. SHA-256 hash overlap
    test_shas = {h: f for f, h in split_hashes.get("test", {}).items()}
    train_shas = {h: f for f, h in split_hashes.get("train", {}).items()}
    val_shas = {h: f for f, h in split_hashes.get("valid", {}).items()}

    sha_overlap_train = []
    for h, f in test_shas.items():
        if h in train_shas:
            sha_overlap_train.append({"test_file": f, "train_file": train_shas[h], "sha256": h})

    sha_overlap_val = []
    for h, f in test_shas.items():
        if h in val_shas:
            sha_overlap_val.append({"test_file": f, "val_file": val_shas[h], "sha256": h})

    # 3. Perceptual hash near duplicates (Hamming <= 6)
    print("[leakage] Scanning perceptual dHash near-duplicates (Hamming <= 6)...")
    dhash_near_duplicates = []
    test_dh = split_dhashes.get("test", {})
    train_dh = split_dhashes.get("train", {})
    val_dh = split_dhashes.get("valid", {})

    for t_name, t_val in test_dh.items():
        for tr_name, tr_val in train_dh.items():
            dist = hamming_distance(t_val, tr_val)
            if dist <= 6:
                dhash_near_duplicates.append({
                    "test_file": t_name,
                    "matched_split": "train",
                    "matched_file": tr_name,
                    "hamming_dist": dist,
                })

        for v_name, v_val in val_dh.items():
            dist = hamming_distance(t_val, v_val)
            if dist <= 6:
                dhash_near_duplicates.append({
                    "test_file": t_name,
                    "matched_split": "valid",
                    "matched_file": v_name,
                    "hamming_dist": dist,
                })

    # 4. Composite source audit
    train_ann_path = data_dir / "train" / "_annotations.coco.json"
    composite_sources_clean = True
    composite_audit_details = []
    if train_ann_path.exists():
        with open(train_ann_path, "r", encoding="utf-8") as f:
            train_coco = json.load(f)
        for img_info in train_coco.get("images", []):
            if img_info.get("source") == "make_composites":
                src_card = img_info.get("source_card", "")
                src_bg = img_info.get("source_bg", "")
                # Check that neither comes from val or test types
                illegal_types = ["alb_id", "srb_passport", "svk_id", "aze_passport", "fin_id"]
                if any(it in src_card or it in src_bg for it in illegal_types):
                    composite_sources_clean = False
                    composite_audit_details.append({"file": img_info["file_name"], "violation": True, "src_card": src_card, "src_bg": src_bg})

    leakage_report = {
        "timestamp": ts,
        "sample_counts": {
            "train": len(split_files.get("train", [])),
            "valid": len(split_files.get("valid", [])),
            "test": len(split_files.get("test", [])),
        },
        "filename_overlap": {
            "test_vs_train_count": len(fname_overlap_train),
            "test_vs_train_files": fname_overlap_train,
            "test_vs_val_count": len(fname_overlap_val),
            "test_vs_val_files": fname_overlap_val,
            "pass": len(fname_overlap_train) == 0 and len(fname_overlap_val) == 0,
        },
        "sha256_overlap": {
            "test_vs_train_count": len(sha_overlap_train),
            "test_vs_train_matches": sha_overlap_train,
            "test_vs_val_count": len(sha_overlap_val),
            "test_vs_val_matches": sha_overlap_val,
            "pass": len(sha_overlap_train) == 0 and len(sha_overlap_val) == 0,
        },
        "perceptual_hash_near_duplicates": {
            "threshold_hamming": 6,
            "near_duplicates_count": len(dhash_near_duplicates),
            "matches": dhash_near_duplicates,
            "pass": len(dhash_near_duplicates) == 0,
        },
        "composite_source_provenance": {
            "composite_sources_clean": composite_sources_clean,
            "violations_count": len(composite_audit_details),
            "violations": composite_audit_details,
            "pass": composite_sources_clean,
        },
        "overall_leakage_audit_pass": (
            len(fname_overlap_train) == 0
            and len(fname_overlap_val) == 0
            and len(sha_overlap_train) == 0
            and len(sha_overlap_val) == 0
            and len(dhash_near_duplicates) == 0
            and composite_sources_clean
        )
    }

    report_path = out_dir / "report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(leakage_report, f, indent=2)

    print(f"\n{'='*70}\n[leakage] AUDIT SUMMARY:")
    print(f"  Filename Overlap:       {len(fname_overlap_train)} train, {len(fname_overlap_val)} val")
    print(f"  SHA-256 Overlap:        {len(sha_overlap_train)} train, {len(sha_overlap_val)} val")
    print(f"  Perceptual Near-Dups:   {len(dhash_near_duplicates)}")
    print(f"  Composite Provenance:   {'PASS' if composite_sources_clean else 'FAIL'}")
    print(f"  OVERALL RESULT:         {'PASS' if leakage_report['overall_leakage_audit_pass'] else 'FAIL'}")
    print(f"Report saved to: {report_path}\n{'='*70}")

    return leakage_report

if __name__ == "__main__":
    run_leakage_audit()
