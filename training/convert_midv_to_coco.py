"""MIDV to COCO conversion utility.

Handles:
1. MIDV-500 / MIDV-2019 per-frame {"quad": [[x, y], ...]} JSON
2. MIDV-2020 VIA format JSON with region 'doc_quad'
Converts arbitrary quadrilaterals to clipped axis-aligned bounding boxes.
Handles off-frame document boundaries (negatives).
Supports optional downscaling and document-type based leakage-free splitting.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from PIL import Image

logger = logging.getLogger(__name__)

# Proposed MIDV-2020 type splits to eliminate template-level leakage (Section 5.3)
MIDV_TYPE_SPLITS = {
    "test": {"alb_id", "est_id", "grc_passport", "srb_passport", "svk_id"},
    "val": {"fin_id", "aze_passport"},
    "train": {"esp_id", "lva_passport", "rus_internalpassport"},
}

# Mapping between MIDV-2020 types and MIDV-500/2019 document codes
MIDV_CODE_MAP = {
    "alb_id": 1,
    "aze_passport": 5,
    "esp_id": 21,
    "est_id": 22,
    "fin_id": 24,
    "grc_passport": 25,
    "lva_passport": 32,
    "rus_internalpassport": 39,
    "srb_passport": 41,
    "svk_id": 42,
}


def quad_to_axis_aligned_box(
    quad: List[List[float]],
    img_width: int,
    img_height: int,
    scale_factor: float = 1.0,
) -> Optional[Tuple[float, float, float, float]]:
    """Convert a 4-point quadrilateral to a clipped axis-aligned COCO bbox [x, y, w, h].

    Returns None if the document is completely outside the image frame (negative sample).
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
    """Parse MIDV-2020 VGG Image Annotator (VIA v2) region 'doc_quad'."""
    file_entry = via_data.get(file_key) or via_data.get(file_key.lower())
    if not file_entry:
        return None

    regions = file_entry.get("regions", [])
    for region in regions:
        region_attrs = region.get("region_attributes", {})
        shape_attrs = region.get("shape_attributes", {})
        # Check either region name or attribute
        name = shape_attrs.get("name") or region_attrs.get("type") or region_attrs.get("name")
        if name in ("doc_quad", "polygon", "quad"):
            all_pts_x = shape_attrs.get("all_points_x", [])
            all_pts_y = shape_attrs.get("all_points_y", [])
            if len(all_pts_x) >= 4 and len(all_pts_y) >= 4:
                return [[float(x), float(y)] for x, y in zip(all_pts_x[:4], all_pts_y[:4])]
    return None


def get_split_for_midv_type(doc_type: str) -> str:
    """Return 'train', 'val', or 'test' according to the strict type split in Section 5.3."""
    doc_type_clean = doc_type.strip().lower()
    for split_name, type_set in MIDV_TYPE_SPLITS.items():
        if doc_type_clean in type_set:
            return split_name
    return "train"
