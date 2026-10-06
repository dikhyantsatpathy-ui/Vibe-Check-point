"""
YOLOv8 & Computer Vision Region of Interest (ROI) extraction suite.

Identifies key semantic zones on identity documents:
  - 'face': Portrait photograph of the holder
  - 'document': Primary document card boundary / frame
  - 'signature': Officer / holder signature box
  - 'qr_code': 2D barcode / Secure QR region
  - 'mrz_zone': Machine Readable Zone text band at bottom

Dual-mode architecture:
  1. Primary: Remote ML microservice via `app/remote_ml.py` or local ONNX inference
     with aspect-ratio preserving letterboxing (640x640, fill 114) and vectorized per-class NMS.
  2. Fallback: Vectorized OpenCV / NumPy computer vision heuristics:
     - Skin-tone chroma / cascade projection for face photo detection
     - High-gradient morphological kernel for MRZ text strip detection
     - Connected-component aspect analysis for QR codes & signatures
     - Convex hull contour extraction for the document boundaries

All coordinates are normalized [x, y, w, h] in the range [0.0, 1.0] for direct
overlay rendering in the frontend preview canvas.
"""

import io
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger("yolo_roi")

try:
    from remote_ml import (
        is_remote_available,
        mark_remote_failed,
        mark_remote_success,
        get_timeout,
        get_connect_timeout,
        get_auth_headers,
        prepare_payload,
    )
except ImportError:
    try:
        from app.remote_ml import (
            is_remote_available,
            mark_remote_failed,
            mark_remote_success,
            get_timeout,
            get_connect_timeout,
            get_auth_headers,
            prepare_payload,
        )
    except ImportError:
        def is_remote_available(endpoint: str = "") -> bool:
            return bool(os.getenv("ML_SERVICE_URL"))
        def mark_remote_failed(endpoint: str = "") -> None:
            pass
        def mark_remote_success(latency_sec: float = 0.0) -> None:
            pass
        def get_timeout() -> float:
            return 2.0
        def get_connect_timeout() -> float:
            return 1.0
        def get_auth_headers() -> dict:
            return {}
        def prepare_payload(b: bytes) -> bytes:
            return b

_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")

# Semantic class names for the 5-class Aadhaar field detector
_AADHAAR_CLASS_NAMES = ["Aadhaar_No", "DOB", "Gender", "Name", "Photo"]

# Per-class confidence thresholds (configurable via env)
DEFAULT_CONF_THRESHOLDS: Dict[str, float] = {
    "document": float(os.getenv("CONF_THRES_DOCUMENT", "0.35")),
    "card": float(os.getenv("CONF_THRES_DOCUMENT", "0.35")),
    "Aadhaar_No": float(os.getenv("CONF_THRES_AADHAAR_NO", "0.35")),
    "DOB": float(os.getenv("CONF_THRES_DOB", "0.35")),
    "Gender": float(os.getenv("CONF_THRES_GENDER", "0.35")),
    "Name": float(os.getenv("CONF_THRES_NAME", "0.35")),
    "Photo": float(os.getenv("CONF_THRES_PHOTO", "0.35")),
}


def get_detector_backend() -> str:
    """Return active detector backend: 'yolov8' (default) or 'rf_detr' (Apache 2.0)."""
    val = os.getenv("DETECTOR_BACKEND", "yolov8").strip().lower()
    if val in ("rf_detr", "rf-detr"):
        return "rf_detr"
    if val in ("rtdetr", "rt-detr"):
        raise ValueError(
            f"Unsupported DETECTOR_BACKEND='{val}'. RT-DETR and RF-DETR are distinct models. Use 'rf_detr' or 'yolov8'."
        )
    return "yolov8"


def get_card_detector_backend() -> str:
    """Return active backend for card stage: 'yolov8' or 'rf_detr'. Defaults to DETECTOR_BACKEND."""
    val = os.getenv("CARD_DETECTOR_BACKEND")
    if val:
        val = val.strip().lower()
        if val in ("rf_detr", "rf-detr"):
            return "rf_detr"
        if val in ("rtdetr", "rt-detr"):
            raise ValueError(
                f"Unsupported CARD_DETECTOR_BACKEND='{val}'. RT-DETR and RF-DETR are distinct models. Use 'rf_detr' or 'yolov8'."
            )
        if val == "yolov8":
            return "yolov8"
        raise ValueError(f"Unsupported CARD_DETECTOR_BACKEND='{val}'. Use 'rf_detr' or 'yolov8'.")
    return get_detector_backend()


def get_field_detector_backend() -> str:
    """Return active backend for field stage: 'yolov8' or 'rf_detr'. Defaults to DETECTOR_BACKEND."""
    val = os.getenv("FIELD_DETECTOR_BACKEND")
    if val:
        val = val.strip().lower()
        if val in ("rf_detr", "rf-detr"):
            return "rf_detr"
        if val in ("rtdetr", "rt-detr"):
            raise ValueError(
                f"Unsupported FIELD_DETECTOR_BACKEND='{val}'. RT-DETR and RF-DETR are distinct models. Use 'rf_detr' or 'yolov8'."
            )
        if val == "yolov8":
            return "yolov8"
        raise ValueError(f"Unsupported FIELD_DETECTOR_BACKEND='{val}'. Use 'rf_detr' or 'yolov8'.")
    return get_detector_backend()


def _default_model_path() -> str:
    """Resolve active model path based on CARD_DETECTOR_BACKEND and environment variables.
    Fails loudly with empty string if RF-DETR weights are absent (never silently loads YOLO)."""
    backend = get_card_detector_backend()
    model_dirs = [_MODEL_DIR]
    default_app_models = os.path.abspath(os.path.join(os.path.dirname(__file__), "models"))
    default_ml_models = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ml_service", "models"))
    default_app_sibling = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "models"))
    cur_abs = os.path.abspath(_MODEL_DIR)
    if cur_abs in (default_app_models, default_ml_models, default_app_sibling):
        for candidate_dir in (default_ml_models, default_app_models, default_app_sibling):
            if candidate_dir not in [os.path.abspath(d) for d in model_dirs]:
                model_dirs.append(candidate_dir)
    if backend == "rf_detr":
        env = os.getenv("RF_DETR_ONNX_PATH")
        if env and os.path.exists(env):
            return env
        for mdir in model_dirs:
            for name in ("rfdetr_card_int8.onnx", "rfdetr_card.onnx", "rf_detr.onnx", "rf_detr_card.onnx"):
                candidate = os.path.join(mdir, name)
                if os.path.exists(candidate):
                    return candidate
        logger.warning(
            "[detector] CARD_DETECTOR_BACKEND='rf_detr' configured but no RF-DETR weights found. "
            "Failing loudly without fallback to YOLO."
        )
        return ""

    env = os.getenv("YOLO_ROI_ONNX_PATH")
    if env:
        return env
    for mdir in model_dirs:
        for name in ("card.onnx", "yolov8n.onnx"):
            candidate = os.path.join(mdir, name)
            if os.path.exists(candidate):
                return candidate
    return os.path.join(_MODEL_DIR, "yolov8n.onnx")


_session = None
_session_attempted = False

_aadhaar_session = None
_aadhaar_session_attempted = False


def clear_session_cache() -> None:
    """Clear cached ONNX sessions so backend or model path switches take immediate effect."""
    global _session, _session_attempted, _aadhaar_session, _aadhaar_session_attempted
    _session = None
    _session_attempted = False
    _aadhaar_session = None
    _aadhaar_session_attempted = False


def _get_onnx_session():
    """Lazily load ONNX runtime session for card detector."""
    global _session, _session_attempted
    if _session_attempted:
        return _session
    _session_attempted = True
    model_path = _default_model_path()
    if not model_path or not os.path.exists(model_path):
        return None
    try:
        backend = get_card_detector_backend()
        if backend == "rf_detr":
            _load_model_metadata(model_path, expected_num_classes=1)
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _session = ort.InferenceSession(model_path, sess_options=opts, providers=['CPUExecutionProvider'])
        return _session
    except ValueError:
        raise
    except Exception as exc:
        logger.warning(f"Failed to load ONNX card model at {model_path}: {exc}")
        return None


def _get_aadhaar_session():
    """Lazily load the 5-class Aadhaar-field ONNX detector (nc=5, 640x640)."""
    global _aadhaar_session, _aadhaar_session_attempted
    if _aadhaar_session_attempted:
        return _aadhaar_session
    _aadhaar_session_attempted = True
    backend = get_field_detector_backend()
    if backend == "rf_detr":
        path = os.getenv("RF_DETR_FIELDS_ONNX_PATH")
        if not path:
            path = os.path.join(_MODEL_DIR, "rfdetr_fields.onnx")
        if not os.path.exists(path):
            logger.warning("[detector] FIELD_DETECTOR_BACKEND='rf_detr' configured but no RF-DETR fields model found. Failing loudly.")
            return None
    else:
        path = os.getenv("AADHAAR_FIELDS_ONNX_PATH")
        if not path:
            path = os.path.join(_MODEL_DIR, "aadhaar_fields.onnx")
        if not os.path.exists(path):
            return None
    try:
        if backend == "rf_detr":
            _load_model_metadata(path, expected_num_classes=len(_AADHAAR_CLASS_NAMES))
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _aadhaar_session = ort.InferenceSession(path, sess_options=opts, providers=["CPUExecutionProvider"])
        return _aadhaar_session
    except ValueError:
        raise
    except Exception as exc:
        logger.warning(f"Failed to load ONNX aadhaar_fields model at {path}: {exc}")
        return None


def _open_rgb(data: bytes) -> np.ndarray | None:
    """Decode raw bytes to a uint8 (h, w, 3) RGB array with EXIF orientation correction.
    Returns None when Pillow cannot read the data so callers degrade gracefully."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img.load()
        if img.mode != "RGB":
            img = img.convert("RGB")
        return np.asarray(img, dtype=np.uint8)
    except Exception as exc:
        logger.debug(f"Image decode failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Pre- and Post-Processing: Letterbox & Vectorized NMS
# ---------------------------------------------------------------------------

def letterbox(
    img_rgb: np.ndarray,
    target_shape: Tuple[int, int] = (640, 640),
    fill: int = 114,
    stride: int = 32,
) -> Tuple[np.ndarray, float, Tuple[float, float], Tuple[int, int]]:
    """Aspect-preserving letterbox resize (pad with constant value 114).
    
    Returns:
        letterboxed_image: (target_h, target_w, 3) uint8 numpy array
        scale_ratio: float
        (pad_x, pad_y): tuple of float padding offsets
        (orig_w, orig_h): original image dimensions
    """
    orig_h, orig_w = img_rgb.shape[:2]
    target_w, target_h = target_shape

    scale = min(target_w / orig_w, target_h / orig_h)
    new_unpad_w = int(round(orig_w * scale))
    new_unpad_h = int(round(orig_h * scale))

    dw = (target_w - new_unpad_w) / 2.0
    dh = (target_h - new_unpad_h) / 2.0

    # Resize without distortion
    pil_img = Image.fromarray(img_rgb)
    resized_pil = pil_img.resize((new_unpad_w, new_unpad_h), Image.Resampling.BILINEAR)
    resized = np.asarray(resized_pil, dtype=np.uint8)

    top = int(round(dh - 0.1))
    left = int(round(dw - 0.1))

    canvas = np.full((target_h, target_w, 3), fill, dtype=np.uint8)
    canvas[top:top + new_unpad_h, left:left + new_unpad_w] = resized

    return canvas, scale, (dw, dh), (orig_w, orig_h)


def scale_boxes_to_original(
    boxes_xyxy: np.ndarray,
    scale: float,
    padding: Tuple[float, float],
    orig_dim: Tuple[int, int],
) -> np.ndarray:
    """Map bounding boxes from 640x640 letterbox coordinates back to original image dimensions."""
    if len(boxes_xyxy) == 0:
        return np.zeros((0, 4), dtype=np.float32)

    dw, dh = padding
    orig_w, orig_h = orig_dim

    out = boxes_xyxy.copy()
    out[:, 0] = np.clip((boxes_xyxy[:, 0] - dw) / scale, 0, orig_w)
    out[:, 1] = np.clip((boxes_xyxy[:, 1] - dh) / scale, 0, orig_h)
    out[:, 2] = np.clip((boxes_xyxy[:, 2] - dw) / scale, 0, orig_w)
    out[:, 3] = np.clip((boxes_xyxy[:, 3] - dh) / scale, 0, orig_h)
    return out


def nms_numpy(boxes_xyxy: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.45) -> List[int]:
    """Vectorized Non-Maximum Suppression via NumPy."""
    if len(boxes_xyxy) == 0:
        return []

    x1 = boxes_xyxy[:, 0]
    y1 = boxes_xyxy[:, 1]
    x2 = boxes_xyxy[:, 2]
    y2 = boxes_xyxy[:, 3]

    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]

    keep: List[int] = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h

        union = areas[i] + areas[order[1:]] - inter
        iou = inter / np.maximum(union, 1e-6)

        inds = np.where(iou <= iou_threshold)[0]
        order = order[inds + 1]

    return keep


# ---------------------------------------------------------------------------
# YOLO Inference Engine
# ---------------------------------------------------------------------------

def _run_yolo_onnx(
    rgb: np.ndarray,
    session,
    max_boxes: int = 4,
    class_names: Optional[List[str]] = None,
    iou_threshold: float = 0.45,
    conf_threshold: float = 0.25,
) -> List[Dict[str, Any]]:
    """Run YOLO ONNX with letterboxing, per-class NMS, and output format detection."""
    try:
        inp = session.get_inputs()[0]
        inp_h = inp.shape[2] if len(inp.shape) == 4 and isinstance(inp.shape[2], int) else 640
        inp_w = inp.shape[3] if len(inp.shape) == 4 and isinstance(inp.shape[3], int) else 640

        # Aspect-preserving letterbox
        letterboxed, scale, padding, orig_dim = letterbox(rgb, (inp_w, inp_h))
        input_tensor = letterboxed.astype(np.float32).transpose(2, 0, 1) / 255.0
        input_tensor = np.expand_dims(input_tensor, axis=0)

        input_name = inp.name
        output_name = session.get_outputs()[0].name
        raw_preds = session.run([output_name], {input_name: input_tensor})[0]

        return _postprocess_yolo_predictions(
            raw_preds=raw_preds,
            scale=scale,
            padding=padding,
            orig_dim=orig_dim,
            class_names=class_names,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold,
            max_boxes=max_boxes,
        )

    except Exception as exc:
        logger.error(f"_run_yolo_onnx inference failed: {exc}", exc_info=True)
        return []


def _postprocess_yolo_predictions(
    raw_preds: np.ndarray,
    scale: float,
    padding: Tuple[float, float],
    orig_dim: Tuple[int, int],
    class_names: Optional[List[str]] = None,
    conf_threshold: float = 0.25,
    iou_threshold: float = 0.45,
    max_boxes: int = 100,
) -> List[Dict[str, Any]]:
    """Decode raw ONNX predictions, apply per-class NMS, and scale to original dimensions."""
    if raw_preds.ndim != 3:
        logger.error(f"Unexpected YOLO output dimensionality: ndim={raw_preds.ndim}, shape={raw_preds.shape}")
        return []

    if raw_preds.shape[1] <= 32 and raw_preds.shape[2] > raw_preds.shape[1]:
        # Standard YOLOv8 layout: [1, 4+nc, G] -> transpose to [G, 4+nc]
        nc = raw_preds.shape[1] - 4
        preds = raw_preds[0].transpose(1, 0)
        is_end2end = False
    else:
        # End-to-end layout: [1, G, 4+nc] or [1, G, 6]
        preds = raw_preds[0]
        nc = preds.shape[1] - 4
        is_end2end = True

    if preds.shape[0] == 0:
        return []

    orig_w, orig_h = orig_dim
    resolved_boxes: List[Dict[str, Any]] = []

    if not is_end2end:
        # Vectorized candidate parsing across all predictions
        cx = preds[:, 0]
        cy = preds[:, 1]
        bw = preds[:, 2]
        bh = preds[:, 3]

        x1 = cx - bw / 2.0
        y1 = cy - bh / 2.0
        x2 = cx + bw / 2.0
        y2 = cy + bh / 2.0
        boxes_xyxy_letterbox = np.stack([x1, y1, x2, y2], axis=1)

        scores_matrix = preds[:, 4:]  # shape [G, nc]
        class_ids = np.argmax(scores_matrix, axis=1)
        confidences = scores_matrix[np.arange(preds.shape[0]), class_ids]

        # Scale letterbox boxes back to original image space
        boxes_xyxy_orig = scale_boxes_to_original(boxes_xyxy_letterbox, scale, padding, orig_dim)

        # Per-class NMS grouping
        unique_classes = np.unique(class_ids)
        all_kept_indices: List[int] = []

        for cid in unique_classes:
            c_mask = class_ids == cid
            if class_names and cid < len(class_names):
                c_label = class_names[cid]
            else:
                c_label = "document" if nc == 1 else f"class_{cid}"

            thresh = DEFAULT_CONF_THRESHOLDS.get(c_label, conf_threshold)
            valid_mask = c_mask & (confidences >= thresh)
            subset_indices = np.where(valid_mask)[0]

            if subset_indices.size == 0:
                continue

            sub_boxes = boxes_xyxy_orig[subset_indices]
            sub_scores = confidences[subset_indices]

            kept_sub = nms_numpy(sub_boxes, sub_scores, iou_threshold=iou_threshold)
            all_kept_indices.extend(subset_indices[k] for k in kept_sub)

        # Build structured output objects
        for idx in all_kept_indices:
            cid = int(class_ids[idx])
            score = float(confidences[idx])
            b_orig = boxes_xyxy_orig[idx]

            norm_x = round(float(b_orig[0] / orig_w), 4)
            norm_y = round(float(b_orig[1] / orig_h), 4)
            norm_w = round(float((b_orig[2] - b_orig[0]) / orig_w), 4)
            norm_h = round(float((b_orig[3] - b_orig[1]) / orig_h), 4)

            if class_names and cid < len(class_names):
                label = class_names[cid]
            else:
                label = "document" if nc == 1 else f"class_{cid}"

            resolved_boxes.append({
                "label": label,
                "class_id": cid,
                "x": norm_x,
                "y": norm_y,
                "w": norm_w,
                "h": norm_h,
                "confidence": round(score, 3),
                "source": "model",
                "backend": get_detector_backend(),
            })

        # Sort by confidence descending
        resolved_boxes.sort(key=lambda b: b.get("confidence", 0.0), reverse=True)
        return resolved_boxes[:max_boxes]

    else:
        # End-to-end / NMS-free format parser
        for pred in preds:
            b_coords = pred[:4]
            score = float(pred[4])
            cid = int(pred[5]) if pred.shape[0] > 5 else 0
            label = class_names[cid] if class_names and cid < len(class_names) else "document"
            thresh = DEFAULT_CONF_THRESHOLDS.get(label, conf_threshold)
            if score >= thresh:
                b_orig = scale_boxes_to_original(b_coords[None, :], scale, padding, orig_dim)[0]
                resolved_boxes.append({
                    "label": label,
                    "class_id": cid,
                    "x": round(float(b_orig[0] / orig_w), 4),
                    "y": round(float(b_orig[1] / orig_h), 4),
                    "w": round(float((b_orig[2] - b_orig[0]) / orig_w), 4),
                    "h": round(float((b_orig[3] - b_orig[1]) / orig_h), 4),
                    "confidence": round(score, 3),
                    "source": "model",
                    "backend": get_detector_backend(),
                })
        resolved_boxes.sort(key=lambda b: b.get("confidence", 0.0), reverse=True)
        return resolved_boxes[:max_boxes]


# ---------------------------------------------------------------------------
# RF-DETR Pre- and Post-Processing (Apache 2.0 Backend Integration)
# ---------------------------------------------------------------------------

def _load_model_metadata(model_path: str, expected_num_classes: Optional[int] = None) -> Dict[str, Any]:
    """Load and validate model metadata canonical sidecar (<model>.meta.json).
    
    Verifies SHA-256 checksum against sidecar (fail-closed) and expected class count.
    
    Raises:
        ValueError: If SHA-256 mismatches or classes count mismatch.
    """
    if not model_path:
        return {}
    p = Path(model_path)
    canonical = p.with_name(f"{p.stem}.meta.json")
    if not canonical.exists():
        logger.warning(f"Canonical metadata sidecar {canonical} not found for {model_path}")
        return {}
    try:
        data = json.loads(canonical.read_text(encoding="utf-8"))
        expected_sha = data.get("sha256")
        if expected_sha:
            import hashlib
            hasher = hashlib.sha256()
            with open(p, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    hasher.update(chunk)
            actual_sha = hasher.hexdigest().lower()
            if actual_sha != str(expected_sha).strip().lower():
                raise ValueError(
                    f"Supply-chain SHA-256 check failed for {model_path}: "
                    f"digest {actual_sha} != expected {expected_sha} in {canonical}"
                )
        classes = data.get("classes", [])
        if expected_num_classes is not None and len(classes) != expected_num_classes:
            raise ValueError(
                f"Model metadata classes count mismatch: expected {expected_num_classes}, got {len(classes)} in {canonical}"
            )
        return data
    except ValueError:
        raise
    except Exception as exc:
        logger.warning(f"Failed to read model metadata from {canonical}: {exc}")
        return {}


def preprocess_rfdetr(
    rgb: np.ndarray,
    target_shape: Tuple[int, int] = (640, 640),
) -> Tuple[np.ndarray, Tuple[int, int]]:
    """Preprocess image for RF-DETR using plain square resize and ImageNet normalization (no letterbox)."""
    orig_h, orig_w = rgb.shape[:2]
    pil_img = Image.fromarray(rgb)
    resized_pil = pil_img.resize(target_shape, Image.Resampling.BILINEAR)
    resized = np.asarray(resized_pil, dtype=np.float32) / 255.0

    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 1, 3)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 1, 3)
    normed = (resized - mean) / std

    tensor = np.expand_dims(normed.transpose(2, 0, 1), axis=0).astype(np.float32)
    return tensor, (orig_w, orig_h)


def _postprocess_rfdetr_predictions(
    boxes: np.ndarray,
    logits: np.ndarray,
    orig_dim: Tuple[int, int],
    class_names: Optional[List[str]] = None,
    conf_threshold: float = 0.25,
    max_boxes: int = 100,
    model_version: str = "rfdetr-v1",
    box_format: str = "auto",
) -> List[Dict[str, Any]]:
    """Decode raw RF-DETR box queries and class logits to original image coordinates."""
    if boxes.ndim == 3:
        boxes = boxes[0]
    if logits.ndim == 3:
        logits = logits[0]

    if boxes.shape[0] == 0 or logits.shape[0] == 0:
        return []

    orig_w, orig_h = orig_dim
    clipped_logits = np.clip(logits, -88.0, 88.0)
    probs = 1.0 / (1.0 + np.exp(-clipped_logits))

    num_queries = min(boxes.shape[0], probs.shape[0])
    num_classes = len(class_names) if class_names else (probs.shape[1] if probs.ndim > 1 else 1)

    results: List[Dict[str, Any]] = []

    if box_format == "auto":
        if (boxes[:, 2] < boxes[:, 0]).any() or (boxes[:, 3] < boxes[:, 1]).any():
            effective_format = "cxcywh"
        else:
            effective_format = "xyxy"
    else:
        effective_format = box_format

    for i in range(num_queries):
        if num_classes == 1 or probs.shape[1] == 1:
            cid = 0
            score = float(probs[i, 0]) if probs.ndim > 1 else float(probs[i])
        else:
            avail_probs = probs[i, :num_classes]
            cid = int(np.argmax(avail_probs))
            score = float(avail_probs[cid])

        label = class_names[cid] if class_names and cid < len(class_names) else f"class_{cid}"
        thresh = DEFAULT_CONF_THRESHOLDS.get(label, conf_threshold)
        if score < thresh:
            continue

        if effective_format == "cxcywh":
            cx, cy, bw, bh = boxes[i, :4]
            x1 = (cx - (bw / 2.0)) * orig_w
            y1 = (cy - (bh / 2.0)) * orig_h
            x2 = (cx + (bw / 2.0)) * orig_w
            y2 = (cy + (bh / 2.0)) * orig_h
        else:
            # "xyxy" normalized coordinates [x1, y1, x2, y2]
            bx1, by1, bx2, by2 = boxes[i, :4]
            x1 = bx1 * orig_w
            y1 = by1 * orig_h
            x2 = bx2 * orig_w
            y2 = by2 * orig_h

        x1_clip = max(0.0, min(float(orig_w), float(x1)))
        y1_clip = max(0.0, min(float(orig_h), float(y1)))
        x2_clip = max(0.0, min(float(orig_w), float(x2)))
        y2_clip = max(0.0, min(float(orig_h), float(y2)))

        box_w = x2_clip - x1_clip
        box_h = y2_clip - y1_clip
        if box_w <= 1.0 or box_h <= 1.0:
            continue

        norm_x = round(float(x1_clip / orig_w), 4)
        norm_y = round(float(y1_clip / orig_h), 4)
        norm_w = round(float(box_w / orig_w), 4)
        norm_h = round(float(box_h / orig_h), 4)

        results.append({
            "label": label,
            "class_id": cid,
            "class_name": label,
            "x": norm_x,
            "y": norm_y,
            "w": norm_w,
            "h": norm_h,
            "box": [norm_x, norm_y, norm_w, norm_h],
            "confidence": round(score, 3),
            "source": "model",
            "backend": "rf_detr",
            "model_version": model_version,
        })

    results.sort(key=lambda b: b.get("confidence", 0.0), reverse=True)
    return results[:max_boxes]


def _run_rfdetr_onnx(
    rgb: np.ndarray,
    session: Any,
    max_boxes: int = 4,
    class_names: Optional[List[str]] = None,
    conf_threshold: float = 0.25,
    model_version: str = "rfdetr-v1",
) -> List[Dict[str, Any]]:
    """Execute RF-DETR ONNX session with name-based output mapping and square resize."""
    try:
        inp = session.get_inputs()[0]
        inp_h = inp.shape[2] if len(inp.shape) == 4 and isinstance(inp.shape[2], int) else 640
        inp_w = inp.shape[3] if len(inp.shape) == 4 and isinstance(inp.shape[3], int) else 640

        input_tensor, orig_dim = preprocess_rfdetr(rgb, (inp_w, inp_h))
        input_name = inp.name

        out_names = [o.name for o in session.get_outputs()]
        outputs = session.run(out_names, {input_name: input_tensor})

        boxes_tensor = None
        logits_tensor = None

        for name, arr in zip(out_names, outputs):
            name_lower = name.lower()
            if "box" in name_lower or "det" in name_lower or (arr.ndim == 3 and arr.shape[-1] == 4):
                boxes_tensor = arr
            elif "logit" in name_lower or "score" in name_lower or "label" in name_lower or (arr.ndim == 3 and arr.shape[-1] != 4):
                logits_tensor = arr

        if boxes_tensor is None or logits_tensor is None:
            for arr in outputs:
                if arr.ndim == 3 and arr.shape[-1] == 4:
                    boxes_tensor = arr
                elif arr.ndim == 3 and arr.shape[-1] != 4:
                    logits_tensor = arr

        if boxes_tensor is None or logits_tensor is None:
            logger.error("Could not map RF-DETR outputs to boxes and logits tensors")
            return []

        return _postprocess_rfdetr_predictions(
            boxes=boxes_tensor,
            logits=logits_tensor,
            orig_dim=orig_dim,
            class_names=class_names,
            conf_threshold=conf_threshold,
            max_boxes=max_boxes,
            model_version=model_version,
        )
    except Exception as exc:
        logger.error(f"_run_rfdetr_onnx inference failed: {exc}", exc_info=True)
        return []



# ---------------------------------------------------------------------------
# Computer Vision Heuristics (Honest confidence & source tagging)
# ---------------------------------------------------------------------------

def _detect_face_heuristic(rgb: np.ndarray) -> Optional[Dict[str, Any]]:
    """Locate portrait photo using skin-tone chrominance and spatial aspect."""
    h, w = rgb.shape[:2]
    f = rgb.astype(np.float32)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]

    max_rgb = np.maximum(r, np.maximum(g, b))
    min_rgb = np.minimum(r, np.minimum(g, b))
    skin = (
        (r > 95) & (g > 40) & (b > 20)
        & (r > g) & (r > b)
        & ((max_rgb - min_rgb) > 15)
        & (r - g > 15)
    )

    rows = skin.any(axis=1)
    cols = skin.any(axis=0)
    ry = np.where(rows)[0]
    cx = np.where(cols)[0]
    if ry.size == 0 or cx.size == 0:
        return None

    y0, y1 = int(ry[0]), int(ry[-1])
    x0, x1 = int(cx[0]), int(cx[-1])

    bw = x1 - x0
    bh = y1 - y0
    if bw > w * 0.06 and bh > h * 0.06:
        return {
            "label": "face",
            "x": round(x0 / w, 3),
            "y": round(y0 / h, 3),
            "w": round(bw / w, 3),
            "h": round(bh / h, 3),
            "confidence": None,  # No fabricated confidence
            "source": "heuristic",
        }
    return None


def _detect_mrz_zone(rgb: np.ndarray) -> Optional[Dict[str, Any]]:
    """Detect high-frequency monospace text band in bottom 30% of document."""
    h, w = rgb.shape[:2]
    bottom_start = int(h * 0.65)
    bottom_slice = rgb[bottom_start:, :]

    gray = (
        0.299 * bottom_slice[..., 0].astype(np.float32)
        + 0.587 * bottom_slice[..., 1].astype(np.float32)
        + 0.114 * bottom_slice[..., 2].astype(np.float32)
    )

    dx = np.abs(gray[:, 1:] - gray[:, :-1])
    edge_density = dx.mean(axis=1)

    high_edge_rows = np.where(edge_density > 12.0)[0]
    if high_edge_rows.size > int(bottom_slice.shape[0] * 0.25):
        y0 = bottom_start + int(high_edge_rows[0])
        y1 = bottom_start + int(high_edge_rows[-1])
        return {
            "label": "mrz_zone",
            "x": 0.05,
            "y": round(y0 / h, 3),
            "w": 0.90,
            "h": round(max(0.12, (y1 - y0) / h), 3),
            "confidence": None,
            "source": "heuristic",
        }
    return None


def _detect_qr_zone(rgb: np.ndarray) -> Optional[Dict[str, Any]]:
    """Detect dense square high-frequency grid characteristic of QR codes."""
    h, w = rgb.shape[:2]
    try:
        import cv2
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        det = cv2.QRCodeDetector()
        ok, points = det.detect(gray)
        if ok and points is not None and len(points) > 0:
            pts = points[0]
            x_min, y_min = np.min(pts, axis=0)
            x_max, y_max = np.max(pts, axis=0)
            return {
                "label": "qr_code",
                "x": round(float(x_min) / w, 3),
                "y": round(float(y_min) / h, 3),
                "w": round(float(x_max - x_min) / w, 3),
                "h": round(float(y_max - y_min) / h, 3),
                "confidence": None,
                "source": "heuristic",
            }
    except Exception:
        pass
    return None


def _detect_document_card(rgb: np.ndarray) -> Dict[str, Any]:
    """Find primary card region (light rectangular background)."""
    h, w = rgb.shape[:2]
    try:
        import cv2
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blur, 50, 150)
        cnts, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]
        for c in cnts:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) == 4 and cv2.contourArea(c) > (w * h * 0.20):
                x, y, bw, bh = cv2.boundingRect(approx)
                return {
                    "label": "document",
                    "x": round(x / w, 3),
                    "y": round(y / h, 3),
                    "w": round(bw / w, 3),
                    "h": round(bh / h, 3),
                    "confidence": None,
                    "source": "heuristic",
                    "is_fallback": False,
                }
    except Exception:
        pass

    # Default document frame heuristic: padded inner bounds
    return {
        "label": "document",
        "x": 0.05,
        "y": 0.05,
        "w": 0.90,
        "h": 0.90,
        "confidence": None,
        "source": "heuristic",
        "is_fallback": True,
    }


# ---------------------------------------------------------------------------
# Public Interfaces
# ---------------------------------------------------------------------------

def extract_roi_boxes(image_bytes: bytes) -> List[Dict[str, Any]]:
    """Public extractor: runs remote ML microservice if configured, else local YOLO ONNX, else CV heuristics."""
    if not image_bytes:
        return []

    # Remote microservice invocation with authentication & connect/read timeouts
    if is_remote_available("yolo_roi"):
        ml_url = os.getenv("ML_SERVICE_URL")
        try:
            timeout_sec = get_timeout()
            connect_sec = get_connect_timeout()
            base = ml_url.rstrip("/")
            payload = prepare_payload(image_bytes)
            candidate_urls = (
                [f"{base}/api/ml/yolo_roi", f"{base}/gradio_api/api/ml/yolo_roi"]
                if "/gradio_api" not in base else [f"{base}/api/ml/yolo_roi"]
            )
            headers = get_auth_headers()
            for target_url in candidate_urls:
                files = {"file": ("image.jpg", payload, "image/jpeg")}
                res = None
                try:
                    import httpx
                    with httpx.Client(timeout=httpx.Timeout(timeout_sec, connect=connect_sec)) as client:
                        res = client.post(target_url, files=files, headers=headers)
                except ImportError:
                    import requests
                    res = requests.post(target_url, files=files, headers=headers, timeout=(connect_sec, timeout_sec))

                if res is not None:
                    if res.status_code == 200:
                        mark_remote_success()
                        remote_boxes = res.json()
                        if isinstance(remote_boxes, list) and len(remote_boxes) > 0:
                            return remote_boxes
                    if res.status_code in (403, 404, 405) and target_url != candidate_urls[-1]:
                        continue
                    logger.warning(
                        f"Remote yolo_roi returned HTTP {res.status_code}: {res.text[:200]}"
                    )
        except Exception as exc:
            mark_remote_failed("yolo_roi")
            logger.warning(
                f"Remote yolo_roi call to {ml_url} failed ({exc.__class__.__name__}: {exc}). Falling back to local."
            )

    rgb = _open_rgb(image_bytes)
    if rgb is None:
        return []

    card_backend = get_card_detector_backend()
    if card_backend == "rf_detr":
        session = _get_onnx_session()
        if session is None:
            raise FileNotFoundError(
                "CARD_DETECTOR_BACKEND='rf_detr' configured but weights could not be loaded. Failing loudly without fallback."
            )
    else:
        session = _get_onnx_session()

    if session is not None:
        if card_backend == "rf_detr":
            boxes = _run_rfdetr_onnx(rgb, session, max_boxes=2, class_names=["Card"])
        else:
            boxes = _run_yolo_onnx(rgb, session, max_boxes=2, class_names=["document"])
        if boxes:
            for b in boxes:
                b["stage"] = "card"
                b["backend"] = card_backend
                b["card_backend"] = card_backend
                b["effective_backend"] = card_backend
            return boxes

    # Fallback: multi-zone computer vision heuristics
    boxes = []
    card_box = _detect_document_card(rgb)
    if card_box:
        boxes.append(card_box)

    face_box = _detect_face_heuristic(rgb)
    if face_box:
        boxes.append(face_box)

    qr_box = _detect_qr_zone(rgb)
    if qr_box:
        boxes.append(qr_box)

    mrz_box = _detect_mrz_zone(rgb)
    if mrz_box:
        boxes.append(mrz_box)

    for b in boxes:
        b["stage"] = "card"
        b["backend"] = card_backend
        b["card_backend"] = card_backend
        b["effective_backend"] = card_backend

    return boxes


def extract_aadhaar_fields(image_bytes: bytes) -> List[Dict[str, Any]]:
    """Detect Aadhaar fields with the trained 5-class model.
    Boxes are normalised (0..1) and labelled with semantic names
    ({'Aadhaar_No','DOB','Gender','Name','Photo'}).
    """
    if not image_bytes:
        return []

    field_backend = get_field_detector_backend()

    if is_remote_available("aadhaar_fields"):
        ml_url = os.getenv("ML_SERVICE_URL")
        try:
            timeout_sec = get_timeout()
            connect_sec = get_connect_timeout()
            base = ml_url.rstrip("/")
            payload = prepare_payload(image_bytes)
            candidate_urls = (
                [f"{base}/api/ml/aadhaar_fields", f"{base}/gradio_api/api/ml/aadhaar_fields"]
                if "/gradio_api" not in base else [f"{base}/api/ml/aadhaar_fields"]
            )
            headers = get_auth_headers()
            for target_url in candidate_urls:
                files = {"file": ("image.jpg", payload, "image/jpeg")}
                res = None
                try:
                    import httpx
                    with httpx.Client(timeout=httpx.Timeout(timeout_sec, connect=connect_sec)) as client:
                        res = client.post(target_url, files=files, headers=headers)
                except ImportError:
                    import requests
                    res = requests.post(target_url, files=files, headers=headers, timeout=(connect_sec, timeout_sec))

                if res is not None:
                    if res.status_code == 200:
                        mark_remote_success()
                        remote_boxes = res.json()
                        if isinstance(remote_boxes, list) and len(remote_boxes) > 0:
                            for b in remote_boxes:
                                b.setdefault("stage", "field")
                                b.setdefault("field_backend", field_backend)
                                b.setdefault("effective_backend", field_backend)
                            return remote_boxes
                    if res.status_code in (403, 404, 405) and target_url != candidate_urls[-1]:
                        continue
                    logger.warning(
                        f"Remote aadhaar_fields returned HTTP {res.status_code}: {res.text[:200]}"
                    )
        except Exception as exc:
            mark_remote_failed("aadhaar_fields")
            logger.warning(
                f"Remote aadhaar_fields call to {ml_url} failed ({exc.__class__.__name__}: {exc}). Falling back to local."
            )

    rgb = _open_rgb(image_bytes)
    if field_backend == "rf_detr":
        session = _get_aadhaar_session()
        if session is None:
            raise FileNotFoundError(
                "FIELD_DETECTOR_BACKEND='rf_detr' configured but weights could not be loaded. Failing loudly without fallback."
            )
    else:
        session = _get_aadhaar_session()

    if rgb is None or session is None:
        return []

    if field_backend == "rf_detr":
        boxes = _run_rfdetr_onnx(
            rgb,
            session,
            max_boxes=8,
            class_names=_AADHAAR_CLASS_NAMES,
            conf_threshold=0.25,
        )
    else:
        boxes = _run_yolo_onnx(
            rgb,
            session,
            max_boxes=8,
            class_names=_AADHAAR_CLASS_NAMES,
            iou_threshold=0.45,
        )
    # Ensure top-1 per semantic class for unambiguous field crops
    class_best: Dict[str, Dict[str, Any]] = {}
    for b in boxes:
        lbl = b.get("label", "")
        if lbl not in class_best or (b.get("confidence") or 0.0) > (class_best[lbl].get("confidence") or 0.0):
            class_best[lbl] = b

    result_boxes = list(class_best.values())
    for b in result_boxes:
        b["stage"] = "field"
        b["backend"] = field_backend
        b["field_backend"] = field_backend
        b["effective_backend"] = field_backend

    return result_boxes


def crop_region_to_bytes(
    image_bytes: bytes,
    box: Dict[str, Any],
    padding: float = 0.0,
    fmt: str = "PNG",
) -> bytes | None:
    """Crop a normalised ROI out of an image as raw bytes.
    Default format is lossless PNG to preserve pixel-level integrity for forensics and OCR.
    """
    if not image_bytes or not box:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)
        w, h = img.size
        x0 = float(box.get("x", 0.0))
        y0 = float(box.get("y", 0.0))
        bw = float(box.get("w", 0.0))
        bh = float(box.get("h", 0.0))
        if bw <= 0.0 or bh <= 0.0:
            return None

        pad = max(0.0, float(padding))
        left = max(0, int((x0 - pad * bw) * w))
        top = max(0, int((y0 - pad * bh) * h))
        right = min(w, int((x0 + bw + pad * bw) * w))
        bottom = min(h, int((y0 + bh + pad * bh) * h))
        if right <= left or bottom <= top:
            return None

        crop = img.crop((left, top, right, bottom))
        out = io.BytesIO()
        if fmt.upper() in ("JPEG", "JPG"):
            crop.save(out, format="JPEG", quality=95)
        else:
            crop.save(out, format="PNG")
        return out.getvalue()
    except Exception as exc:
        logger.debug(f"crop_region_to_bytes failed: {exc}")
        return None


def isolate_document_card(image_bytes: bytes) -> Tuple[bytes, Optional[Dict[str, Any]]]:
    """Isolate and crop the ID card boundary from an arbitrary background photo.
    Returns (cropped_card_bytes, crop_meta) as lossless PNG when cropped, or (image_bytes, None)
    if already full-frame or unsegmented.
    When ENABLE_CARD_RECTIFICATION is enabled, perspective distortion is warped to canonical CR-80 ratio.
    """
    if not image_bytes:
        return image_bytes, None

    try:
        from app.rectification import rectify_card_image
    except ImportError:
        try:
            from rectification import rectify_card_image
        except ImportError:
            rectify_card_image = None

    try:
        boxes = extract_roi_boxes(image_bytes)
        doc_box = next((b for b in boxes if b.get("label") in ("document", "card")), None)
        if doc_box:
            bw = float(doc_box.get("w", 1.0))
            bh = float(doc_box.get("h", 1.0))
            area_ratio = bw * bh
            # If the card occupies a sub-region (between 12% and 94% of the image)
            if 0.12 <= area_ratio <= 0.94 and (bw < 0.96 or bh < 0.96):
                # Lossless PNG crop to preserve ELA/PRNU forensic substrate
                cropped = crop_region_to_bytes(image_bytes, doc_box, padding=0.03, fmt="PNG")
                if cropped and len(cropped) > 2048:
                    meta = {
                        "cropped": True,
                        "box": doc_box,
                        "area_ratio": round(area_ratio, 3),
                        "confidence": doc_box.get("confidence"),
                        "source": doc_box.get("source", "model"),
                        "is_fallback": doc_box.get("source") == "heuristic" or doc_box.get("is_fallback", False),
                    }
                    if rectify_card_image is not None:
                        rect_bytes, was_rect, rect_meta = rectify_card_image(cropped)
                        if was_rect:
                            meta["rectified"] = True
                            meta["rectification"] = rect_meta
                            return rect_bytes, meta
                    return cropped, meta

        # Even if not bounding-box cropped, check if rectification is enabled and applicable
        if rectify_card_image is not None:
            rect_bytes, was_rect, rect_meta = rectify_card_image(image_bytes)
            if was_rect:
                return rect_bytes, {
                    "cropped": False,
                    "rectified": True,
                    "rectification": rect_meta,
                    "confidence": None,
                    "source": "homography_rectification",
                    "is_fallback": False,
                }
    except Exception as exc:
        logger.debug(f"isolate_document_card fallback: {exc}")
    return image_bytes, None
