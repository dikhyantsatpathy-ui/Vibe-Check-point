"""Script to execute Step 3: MIDV-2020 to COCO conversion, counts logging, leakage check, and contact sheet generation."""

import datetime
import json
import logging
from pathlib import Path
from training.convert_midv_to_coco import convert_midv2020_dataset, generate_contact_sheet, verify_leakage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    raw_dir = Path("data/raw/midv2020")
    coco_dir = Path("data/coco_card")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(f"eval/runs/{ts}_midv_conversion")
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"[step3] Converting MIDV-2020 to COCO in {coco_dir}...")
    counts = convert_midv2020_dataset(raw_dir, coco_dir, max_long_side=1280, seed=42)

    counts_path = run_dir / "counts.json"
    counts_path.write_text(json.dumps(counts, indent=2), encoding="utf-8")
    print(f"[step3] Wrote counts to {counts_path}")

    # Leakage check
    leakage_ok = verify_leakage(counts)
    print(f"[step3] Leakage check passed: {leakage_ok}")
    assert leakage_ok, "Leakage detected!"

    # Visual contact sheet
    contact_path = run_dir / "contact_sheet.jpg"
    generate_contact_sheet(coco_dir, contact_path, num_per_split=8, seed=42)
    print(f"[step3] Generated visual contact sheet at {contact_path}")

    print("\nSUMMARY:")
    for s, data in counts["splits"].items():
        print(f"  Split {s:5s}: {data['images']} images, {data['boxes']} boxes, types: {list(data['types'].keys())}")
    print(f"  Total Images: {counts['total_images']}")
    print(f"  Total Boxes:  {counts['total_boxes']}")

if __name__ == "__main__":
    main()
