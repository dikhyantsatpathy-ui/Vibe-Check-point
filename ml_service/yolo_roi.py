"""
YOLOv8 & Computer Vision Region of Interest (ROI) extraction suite (Microservice Edition).

Identifies key semantic zones on identity documents:
  - 'face': Portrait photograph of the holder
  - 'document': Primary document card boundary / frame
  - 'signature': Officer / holder signature box
  - 'qr_code': 2D barcode / Secure QR region
  - 'mrz_zone': Machine Readable Zone text band at bottom

Features:
  - Aspect-preserving letterbox with inverse coordinate mapping (640x640, fill 114)
  - Vectorized per-class NMS via NumPy
  - Output tensor shape detection (YOLOv8 standard vs end-to-end NMS-free)
  - Full EXIF orientation normalization
  - Semantic tagging with source ("model" vs "heuristic") and honest confidence
"""

import io
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger("ml_service.yolo_roi")

_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")

# Semantic class names for the 5-class Aadhaar field detector
_AADHAAR_CLASS_NAMES = ["Aadhaar_No", "DOB", "Gender", "Name", "Photo"]

DEFAULT_CONF_THRESHOLDS: Dict[str, float] = {
    "document": float(os.getenv("CONF_THRES_DOCUMENT", "0.35")),
    "card": float(os.getenv("CONF_THRES_DOCUMENT", "0.35")),
    "Aadhaar_No": float(os.getenv("CONF_THRES_AADHAAR_NO", "0.35")),
    "DOB": float(os.getenv("CONF_THRES_DOB", "0.35")),
    "Gender": float(os.getenv("CONF_THRES_GENDER", "0.35")),
    "Name": float(os.getenv("CONF_THRES_NAME", "0.35")),
    "Photo": float(os.getenv("CONF_THRES_PHOTO", "0.35")),
}


def _default_model_path() -> str:
    env = os.getenv("YOLO_ROI_ONNX_PATH")
    if env:
        return env
    for name in ("card.onnx", "yolov8n.onnx"):
        candidate = os.path.join(_MODEL_DIR, name)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(_MODEL_DIR, "yolov8n.onnx")


_ONNX_MODEL_PATH = _default_model_path()
_session = None
_session_attempted = False

_aadhaar_session = None
_aadhaar_session_attempted = False


def _get_onnx_session():
    global _session, _session_attempted
    if _session_attempted:
        return _session
    _session_attempted = True
    if not os.path.exists(_ONNX_MODEL_PATH):
        return None
    try:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _session = ort.InferenceSession(_ONNX_MODEL_PATH, sess_options=opts, providers=['CPUExecutionProvider'])
        return _session
    except Exception as exc:
        logger.warning(f"Failed to load ONNX card model at {_ONNX_MODEL_PATH}: {exc}")
        return None


def _get_aadhaar_session():
    global _aadhaar_session, _aadhaar_session_attempted
    if _aadhaar_session_attempted:
        return _aadhaar_session
    _aadhaar_session_attempted = True
    path = os.getenv("AADHAAR_FIELDS_ONNX_PATH")
    if not path:
        path = os.path.join(_MODEL_DIR, "aadhaar_fields.onnx")
    if not os.path.exists(path):
        return None
    try:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _aadhaar_session = ort.InferenceSession(path, sess_options=opts, providers=["CPUExecutionProvider"])
        return _aadhaar_session
    except Exception as exc:
        logger.warning(f"Failed to load ONNX aadhaar_fields model at {path}: {exc}")
        return None


def _open_rgb(data: bytes) -> np.ndarray | None:
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
    orig_h, orig_w = img_rgb.shape[:2]
    target_w, target_h = target_shape

    scale = min(target_w / orig_w, target_h / orig_h)
    new_unpad_w = int(round(orig_w * scale))
    new_unpad_h = int(round(orig_h * scale))

    dw = (target_w - new_unpad_w) / 2.0
    dh = (target_h - new_unpad_h) / 2.0

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
) -> List[Dict[str, Any]]:
    try:
        inp = session.get_inputs()[0]
        inp_h = inp.shape[2] if len(inp.shape) == 4 and isinstance(inp.shape[2], int) else 640
        inp_w = inp.shape[3] if len(inp.shape) == 4 and isinstance(inp.shape[3], int) else 640

        letterboxed, scale, padding, orig_dim = letterbox(rgb, (inp_w, inp_h))
        input_tensor = letterboxed.astype(np.float32).transpose(2, 0, 1) / 255.0
        input_tensor = np.expand_dims(input_tensor, axis=0)

        input_name = inp.name
        output_name = session.get_outputs()[0].name
        raw_preds = session.run([output_name], {input_name: input_tensor})[0]

        if raw_preds.ndim != 3:
            logger.error(f"Unexpected YOLO output dimensionality: ndim={raw_preds.ndim}, shape={raw_preds.shape}")
            return []

        if raw_preds.shape[1] <= 32 and raw_preds.shape[2] > raw_preds.shape[1]:
            nc = raw_preds.shape[1] - 4
            preds = raw_preds[0].transpose(1, 0)
            is_end2end = False
        else:
            preds = raw_preds[0]
            nc = preds.shape[1] - 4
            is_end2end = True

        if preds.shape[0] == 0:
            return []

        orig_w, orig_h = orig_dim
        resolved_boxes: List[Dict[str, Any]] = []

        if not is_end2end:
            cx = preds[:, 0]
            cy = preds[:, 1]
            bw = preds[:, 2]
            bh = preds[:, 3]

            x1 = cx - bw / 2.0
            y1 = cy - bh / 2.0
            x2 = cx + bw / 2.0
            y2 = cy + bh / 2.0
            boxes_xyxy_letterbox = np.stack([x1, y1, x2, y2], axis=1)

            scores_matrix = preds[:, 4:]
            class_ids = np.argmax(scores_matrix, axis=1)
            confidences = scores_matrix[np.arange(preds.shape[0]), class_ids]

            boxes_xyxy_orig = scale_boxes_to_original(boxes_xyxy_letterbox, scale, padding, orig_dim)

            unique_classes = np.unique(class_ids)
            all_kept_indices: List[int] = []

            for cid in unique_classes:
                c_mask = class_ids == cid
                if class_names and cid < len(class_names):
                    c_label = class_names[cid]
                else:
                    c_label = "document" if nc == 1 else f"class_{cid}"

                thresh = DEFAULT_CONF_THRESHOLDS.get(c_label, 0.35)
                valid_mask = c_mask & (confidences >= thresh)
                subset_indices = np.where(valid_mask)[0]

                if subset_indices.size == 0:
                    continue

                sub_boxes = boxes_xyxy_orig[subset_indices]
                sub_scores = confidences[subset_indices]

                kept_sub = nms_numpy(sub_boxes, sub_scores, iou_threshold=iou_threshold)
                all_kept_indices.extend(subset_indices[k] for k in kept_sub)

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
                })

            resolved_boxes.sort(key=lambda b: b.get("confidence", 0.0), reverse=True)
            return resolved_boxes[:max_boxes]

        else:
            for pred in preds:
                b_coords = pred[:4]
                score = float(pred[4])
                cid = int(pred[5]) if pred.shape[0] > 5 else 0
                label = class_names[cid] if class_names and cid < len(class_names) else "document"
                thresh = DEFAULT_CONF_THRESHOLDS.get(label, 0.35)
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
                    })
            resolved_boxes.sort(key=lambda b: b.get("confidence", 0.0), reverse=True)
            return resolved_boxes[:max_boxes]

    except Exception as exc:
        logger.error(f"_run_yolo_onnx inference failed: {exc}", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Computer Vision Heuristics (Honest confidence & source tagging)
# ---------------------------------------------------------------------------

def _detect_face_heuristic(rgb: np.ndarray) -> Optional[Dict[str, Any]]:
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
            "confidence": None,
            "source": "heuristic",
        }
    return None


def _detect_mrz_zone(rgb: np.ndarray) -> Optional[Dict[str, Any]]:
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
    if not image_bytes:
        return []

    rgb = _open_rgb(image_bytes)
    if rgb is None:
        return []

    session = _get_onnx_session()
    if session is not None:
        yolo_boxes = _run_yolo_onnx(rgb, session, max_boxes=2, class_names=["document"])
        if yolo_boxes:
            return yolo_boxes

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

    return boxes


def extract_aadhaar_fields(image_bytes: bytes) -> List[Dict[str, Any]]:
    if not image_bytes:
        return []

    rgb = _open_rgb(image_bytes)
    session = _get_aadhaar_session()
    if rgb is None or session is None:
        return []

    boxes = _run_yolo_onnx(
        rgb,
        session,
        max_boxes=8,
        class_names=_AADHAAR_CLASS_NAMES,
        iou_threshold=0.45,
    )
    class_best: Dict[str, Dict[str, Any]] = {}
    for b in boxes:
        lbl = b.get("label", "")
        if lbl not in class_best or (b.get("confidence") or 0.0) > (class_best[lbl].get("confidence") or 0.0):
            class_best[lbl] = b

    return list(class_best.values())


def crop_region_to_bytes(
    image_bytes: bytes,
    box: Dict[str, Any],
    padding: float = 0.0,
    fmt: str = "PNG",
) -> bytes | None:
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
    if not image_bytes:
        return image_bytes, None

    try:
        from rectification import rectify_card_image
    except ImportError:
        try:
            from app.rectification import rectify_card_image
        except ImportError:
            rectify_card_image = None

    try:
        boxes = extract_roi_boxes(image_bytes)
        doc_box = next((b for b in boxes if b.get("label") in ("document", "card")), None)
        if doc_box:
            bw = float(doc_box.get("w", 1.0))
            bh = float(doc_box.get("h", 1.0))
            area_ratio = bw * bh
            if 0.12 <= area_ratio <= 0.94 and (bw < 0.96 or bh < 0.96):
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
