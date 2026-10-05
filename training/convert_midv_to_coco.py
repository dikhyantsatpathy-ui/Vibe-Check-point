"""MIDV to COCO conversion utility.

Handles:
1. MIDV-500 / MIDV-2019 per-frame {"quad": [[x, y], ...]} JSON
2. MIDV-2020 VIA format JSON with region 'doc_quad'
Converts arbitrary quadrilaterals to clipped axis-aligned bounding boxes.
Handles off-frame document boundaries (negatives).
Supports downscaling to max dimension 1280 px and document-type based leakage-free splitting.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageOps

logger = logging.getLogger(__name__)

# Strict MIDV-2020 document type split (Section 2, 3/2/5 split):
# - TEST: 3 types (300 photos)
# - VAL: 2 types (200 photos)
# - TRAIN: 5 types (500 photos)
MIDV_TYPE_SPLITS = {
    "test": {"alb_id", "srb_passport", "svk_id"},
    "valid": {"fin_id", "aze_passport"},
    "train": {"esp_id", "est_id", "grc_passport", "lva_passport", "rus_internalpassport"},
}

# Capture conditions by image index range (Section 2)
CAPTURE_CONDITIONS = [
    (0, 19, "projective_distortion"),
    (20, 29, "text_document_background"),
    (30, 39, "keyboard"),
    (40, 49, "outdoors"),
    (50, 59, "table"),
    (60, 69, "highlight"),
    (70, 89, "low_light"),
    (90, 99, "cloth"),
]


def get_capture_condition(image_num: int) -> str:
    """Map image index (00-99) to capture condition name."""
    for start, end, name in CAPTURE_CONDITIONS:
        if start <= image_num <= end:
            return name
    return "unknown"


def get_split_for_midv_type(doc_type: str) -> str:
    """Return 'train', 'valid', or 'test' according to strict type split."""
    clean = doc_type.strip().lower()
    for split_name, type_set in MIDV_TYPE_SPLITS.items():
        if clean in type_set:
            return split_name
    return "train"


def quad_to_axis_aligned_box(
    quad: List[List[float]],
    img_width: int,
    img_height: int,
    scale_factor: float = 1.0,
) -> Optional[Tuple[float, float, float, float]]:
    """Convert a 4-point quadrilateral to a clipped axis-aligned COCO bbox [x, y, w, h].

    Returns None if document is completely outside the image frame (negative sample).
    """
    if len(quad) < 4:
        return None

    xs = [pt[0] * scale_factor for pt in quad]
    ys = [pt[1] * scale_factor for pt in quad]

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    target_w = float(img_width)
    target_h = float(img_height)

    # Completely off frame
    if max_x <= 0 or min_x >= target_w or max_y <= 0 or min_y >= target_h:
        return None

    clipped_x1 = max(0.0, min_x)
    clipped_y1 = max(0.0, min_y)
    clipped_x2 = min(target_w, max_x)
    clipped_y2 = min(target_h, max_y)

    box_w = clipped_x2 - clipped_x1
    box_h = clipped_y2 - clipped_y1

    if box_w <= 1.0 or box_h <= 1.0:
        return None

    return (
        round(clipped_x1, 2),
        round(clipped_y1, 2),
        round(box_w, 2),
        round(box_h, 2),
    )


def parse_midv500_frame_json(json_content: Union[str, dict]) -> Optional[List[List[float]]]:
    """Parse MIDV-500/2019 per-frame JSON: {"quad": [[x, y], ...]}."""
    if isinstance(json_content, str):
        data = json.loads(json_content)
    else:
        data = json_content
    return data.get("quad")


def parse_midv2020_via_json(via_data: dict, file_key: str) -> Optional[List[List[float]]]:
    """Parse MIDV-2020 VGG Image Annotator (VIA v2) region 'doc_quad'.

    Supports both top-level metadata dicts and direct image metadata lookups.
    """
    # Check _via_img_metadata if present
    img_meta = via_data.get("_via_img_metadata", via_data)

    entry = img_meta.get(file_key)
    if not entry:
        # Match by filename
        for k, v in img_meta.items():
            if isinstance(v, dict) and v.get("filename") == file_key:
                entry = v
                break
    if not entry or not isinstance(entry, dict):
        return None

    regions = entry.get("regions", [])
    for region in regions:
        region_attrs = region.get("region_attributes", {})
        shape_attrs = region.get("shape_attributes", {})

        field_name = region_attrs.get("field_name") or region_attrs.get("type") or region_attrs.get("name")
        shape_name = shape_attrs.get("name")

        if field_name == "doc_quad" or shape_name == "doc_quad" or (shape_name == "polygon" and field_name == "doc_quad"):
            all_pts_x = shape_attrs.get("all_points_x", [])
            all_pts_y = shape_attrs.get("all_points_y", [])
            if len(all_pts_x) >= 4 and len(all_pts_y) >= 4:
                return [[float(x), float(y)] for x, y in zip(all_pts_x[:4], all_pts_y[:4])]

    return None


def convert_midv2020_dataset(
    raw_dir: Path,
    output_dir: Path,
    max_long_side: int = 1280,
    seed: int = 42,
) -> Dict[str, Any]:
    """Convert raw MIDV-2020 photos and VIA annotations to COCO format split by document type."""
    random.seed(seed)
    images_raw_dir = raw_dir / "images"
    annotations_raw_dir = raw_dir / "annotations"

    splits = ["train", "valid", "test"]
    coco_data: Dict[str, Dict[str, Any]] = {
        s: {
            "images": [],
            "annotations": [],
            "categories": [{"id": 1, "name": "Card", "supercategory": "none"}],
        }
        for s in splits
    }

    counts: Dict[str, Any] = {
        "splits": {s: {"images": 0, "boxes": 0, "types": {}, "conditions": {}} for s in splits},
        "total_images": 0,
        "total_boxes": 0,
    }

    ann_id_counters = {s: 1 for s in splits}
    img_id_counters = {s: 1 for s in splits}

    type_dirs = sorted([d for d in images_raw_dir.iterdir() if d.is_dir()])

    for type_dir in type_dirs:
        doc_type = type_dir.name
        split = get_split_for_midv_type(doc_type)

        ann_file = annotations_raw_dir / f"{doc_type}.json"
        if not ann_file.exists():
            logger.warning("Annotation file missing for type %s: %s", doc_type, ann_file)
            continue

        via_json = json.loads(ann_file.read_text(encoding="utf-8"))
        split_img_dir = output_dir / split / "images"
        split_img_dir.mkdir(parents=True, exist_ok=True)

        jpg_files = sorted(list(type_dir.glob("*.jpg")))
        for jpg_path in jpg_files:
            img_num = int(jpg_path.stem)
            condition = get_capture_condition(img_num)

            # Load and downscale with EXIF orientation normalization
            with Image.open(jpg_path) as raw_im:
                im = ImageOps.exif_transpose(raw_im)
                orig_w, orig_h = im.size
                long_side = max(orig_w, orig_h)
                scale = float(max_long_side) / float(long_side) if long_side > max_long_side else 1.0
                new_w = int(round(orig_w * scale))
                new_h = int(round(orig_h * scale))

                # Resize image
                resized = im.resize((new_w, new_h), Image.Resampling.BILINEAR)

            dest_filename = f"{doc_type}_{jpg_path.name}"
            dest_img_path = split_img_dir / dest_filename
            resized.save(dest_img_path, quality=90)

            # Parse annotation
            quad = parse_midv2020_via_json(via_json, jpg_path.name)
            box = quad_to_axis_aligned_box(quad, new_w, new_h, scale_factor=scale) if quad else None

            curr_img_id = img_id_counters[split]
            img_id_counters[split] += 1

            coco_data[split]["images"].append({
                "id": curr_img_id,
                "file_name": dest_filename,
                "width": new_w,
                "height": new_h,
                "doc_type": doc_type,
                "condition": condition,
                "orig_size": [orig_w, orig_h],
            })

            counts["splits"][split]["images"] += 1
            counts["splits"][split]["types"][doc_type] = counts["splits"][split]["types"].get(doc_type, 0) + 1
            counts["splits"][split]["conditions"][condition] = counts["splits"][split]["conditions"].get(condition, 0) + 1
            counts["total_images"] += 1

            if box is not None:
                bx, by, bw, bh = box
                coco_data[split]["annotations"].append({
                    "id": ann_id_counters[split],
                    "image_id": curr_img_id,
                    "category_id": 1,
                    "bbox": [bx, by, bw, bh],
                    "area": round(bw * bh, 2),
                    "iscrowd": 0,
                    "segmentation": [],
                })
                ann_id_counters[split] += 1
                counts["splits"][split]["boxes"] += 1
                counts["total_boxes"] += 1

    # Save COCO JSON files for each split
    for s in splits:
        split_dir = output_dir / s
        split_dir.mkdir(parents=True, exist_ok=True)
        ann_dest = split_dir / "_annotations.coco.json"
        ann_dest.write_text(json.dumps(coco_data[s], indent=2), encoding="utf-8")
        logger.info("Saved COCO annotations for %s: %s (%d images, %d boxes)", s, ann_dest, len(coco_data[s]["images"]), len(coco_data[s]["annotations"]))

    # Also symlink / copy valid to val for frameworks expecting 'val'
    val_dir = output_dir / "val"
    if not val_dir.exists():
        try:
            val_dir.symlink_to(output_dir / "valid", target_is_directory=True)
        except Exception:
            pass

    return counts


def generate_contact_sheet(
    coco_dir: Path,
    output_image_path: Path,
    num_per_split: int = 8,
    seed: int = 42,
) -> Path:
    """Draw ground truth boxes on sample images and save a visual verification contact sheet."""
    random.seed(seed)
    splits = ["train", "valid", "test"]
    selected_items: List[Tuple[Path, List[float], str]] = []

    for s in splits:
        ann_file = coco_dir / s / "_annotations.coco.json"
        if not ann_file.exists():
            continue
        data = json.loads(ann_file.read_text(encoding="utf-8"))
        img_map = {im["id"]: im for im in data["images"]}
        anns_by_img: Dict[int, List[List[float]]] = {}
        for a in data["annotations"]:
            anns_by_img.setdefault(a["image_id"], []).append(a["bbox"])

        valid_ids = [iid for iid in img_map.keys() if iid in anns_by_img]
        sampled_ids = random.sample(valid_ids, min(num_per_split, len(valid_ids)))
        for iid in sampled_ids:
            im_info = img_map[iid]
            im_path = coco_dir / s / "images" / im_info["file_name"]
            box = anns_by_img[iid][0]
            selected_items.append((im_path, box, f"{s}: {im_info['doc_type']}"))

    # Render grid (e.g. 4 rows x 6 columns), cells tall enough for portrait photos
    cell_w, cell_h = 240, 360
    cols = 6
    rows = (len(selected_items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), color=(30, 30, 30))

    for idx, (im_p, bbox, caption) in enumerate(selected_items):
        if not im_p.exists():
            continue
        with Image.open(im_p) as im:
            im_copy = im.copy()
            draw = ImageDraw.Draw(im_copy)
            bx, by, bw, bh = bbox
            draw.rectangle([bx, by, bx + bw, by + bh], outline=(0, 255, 0), width=6)
            thumb = ImageOps.contain(im_copy, (cell_w, cell_h - 24))

            cell_canvas = Image.new("RGB", (cell_w, cell_h), color=(20, 20, 20))
            tx = (cell_w - thumb.width) // 2
            ty = 24 + (cell_h - 24 - thumb.height) // 2
            cell_canvas.paste(thumb, (tx, ty))

            # Draw caption overlay
            tdraw = ImageDraw.Draw(cell_canvas)
            tdraw.rectangle([0, 0, cell_w, 22], fill=(0, 0, 0))
            tdraw.text((5, 4), caption, fill=(255, 255, 255))

            cx = (idx % cols) * cell_w
            cy = (idx // cols) * cell_h
            sheet.paste(cell_canvas, (cx, cy))

    output_image_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_image_path, quality=90)
    logger.info("Saved contact sheet: %s", output_image_path)
    return output_image_path


def verify_leakage(counts: Dict[str, Any]) -> bool:
    """Verify that no document type appears in more than one split."""
    splits = counts.get("splits", {})
    type_to_split: Dict[str, str] = {}
    leakage_found = False

    for s_name, s_data in splits.items():
        for doc_type in s_data.get("types", {}).keys():
            if doc_type in type_to_split:
                logger.error("LEAKAGE DETECTED! Type %s is in both %s and %s", doc_type, type_to_split[doc_type], s_name)
                leakage_found = True
            type_to_split[doc_type] = s_name

    return not leakage_found
