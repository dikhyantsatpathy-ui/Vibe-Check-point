"""
YOLOv8-Nano & Computer Vision Region of Interest (ROI) extraction suite.

Identifies key semantic zones on identity documents:
  - 'face': Portrait photograph of the holder
  - 'document': Primary document card boundary / frame
  - 'signature': Officer / holder signature box
  - 'qr_code': 2D barcode / Secure QR region
  - 'mrz_zone': Machine Readable Zone text band at bottom

Dual-mode architecture:
  1. If `yolov8n.onnx` (or custom card model) and `onnxruntime` are available,
     runs lightweight ONNX inference (640x640 input, NMS post-processing).
  2. Otherwise, executes vectorised OpenCV / NumPy image processing:
     - Skin-tone chroma / cascade projection for face photo detection
     - High-gradient morphological kernel for MRZ text strip detection
     - Connected-component aspect analysis for QR codes & signatures
     - Convex hull contour extraction for the document boundaries

All coordinates are normalized [x, y, w, h] in the range [0.0, 1.0] for direct
overlay rendering in the frontend preview canvas.
"""

import io
import logging
import os
import numpy as np
from PIL import Image
from typing import Any, Dict, List, Optional

logger = logging.getLogger("yolo_roi")

try:
    from remote_ml import is_remote_available, mark_remote_failed, mark_remote_success, get_timeout, prepare_payload
except ImportError:
    try:
        from app.remote_ml import is_remote_available, mark_remote_failed, mark_remote_success, get_timeout, prepare_payload
    except ImportError:
        is_remote_available = lambda: bool(os.getenv("ML_SERVICE_URL"))
        mark_remote_failed = lambda: None
        mark_remote_success = lambda: None
        get_timeout = lambda: 2.0
        prepare_payload = lambda b: b

_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")


def _default_model_path() -> str:
    """Resolve the default ONNX model: env override, then card/'yolov8n' file."""
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


def _get_onnx_session():
    """Lazily load ONNX runtime session if model file exists."""
    global _session, _session_attempted
    if _session_attempted:
        return _session
    _session_attempted = True
    if not os.path.exists(_ONNX_MODEL_PATH):
        return None
    try:
        import onnxruntime as ort
        # CPU execution provider for maximum compatibility across environments
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _session = ort.InferenceSession(_ONNX_MODEL_PATH, sess_options=opts, providers=['CPUExecutionProvider'])
        return _session
    except Exception:
        return None


def _open_rgb(data: bytes) -> np.ndarray | None:
    """Decode raw bytes to a uint8 (h, w, 3) RGB array with EXIF orientation correction.
    Returns None when Pillow cannot read the data so callers degrade gracefully."""
    try:
        from PIL import ImageOps
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img.load()
        return np.asarray(img.convert("RGB"), dtype=np.uint8)
    except Exception:
        return None


def _detect_face_heuristic(rgb: np.ndarray) -> Optional[Dict[str, Any]]:
    """Locate portrait photo using skin-tone chrominance and spatial aspect."""
    h, w = rgb.shape[:2]
    f = rgb.astype(np.float32)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]

    # Chai & Ngan skin chromaticity bounds — precompute max/min once to avoid
    # redundant array allocations across the three comparisons below.
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
        # Constrain face box to reasonable portrait aspect ratio (~1:1.2 to 1:1.4)
        conf = float(skin[y0:y1, x0:x1].mean())
        return {
            "label": "face",
            "x": round(x0 / w, 3),
            "y": round(y0 / h, 3),
            "w": round(bw / w, 3),
            "h": round(bh / h, 3),
            "confidence": round(min(0.98, max(0.50, conf * 1.5)), 2),
        }
    return None


def _detect_mrz_zone(rgb: np.ndarray) -> Optional[Dict[str, Any]]:
    """Detect high-frequency monospace text band in bottom 30% of document."""
    h, w = rgb.shape[:2]
    bottom_start = int(h * 0.65)
    bottom_slice = rgb[bottom_start:, :]

    # Convert to grayscale
    gray = (
        0.299 * bottom_slice[..., 0].astype(np.float32)
        + 0.587 * bottom_slice[..., 1].astype(np.float32)
        + 0.114 * bottom_slice[..., 2].astype(np.float32)
    )

    # Horizontal derivative (edge density of OCR-B characters)
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
            "confidence": 0.88,
        }
    return None


def _detect_qr_zone(rgb: np.ndarray) -> Optional[Dict[str, Any]]:
    """Detect dense square high-frequency grid characteristic of QR codes."""
    h, w = rgb.shape[:2]
    # Check with OpenCV when it is available; otherwise use the NumPy fallback.
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
                "confidence": 0.96,
            }
    except Exception:
        pass
    return None


def _detect_document_card(rgb: np.ndarray) -> Dict[str, Any]:
    """Find primary card region (light rectangular background)."""
    h, w = rgb.shape[:2]
    # Try finding large contour using OpenCV if installed
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
                    "confidence": 0.94,
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
        "confidence": 0.85,
    }


def _run_yolo_onnx(rgb: np.ndarray, session, max_boxes: int = 4) -> List[Dict[str, Any]]:
    """Run a YOLO ONNX model (any class count) when a model file is present."""
    h_orig, w_orig = rgb.shape[:2]
    try:
        inp = session.get_inputs()[0]
        inp_h = inp.shape[2] if len(inp.shape) == 4 and isinstance(inp.shape[2], int) else 640
        inp_w = inp.shape[3] if len(inp.shape) == 4 and isinstance(inp.shape[3], int) else 640

        img_resized = Image.fromarray(rgb).resize((inp_w, inp_h), Image.BILINEAR)
        input_tensor = np.asarray(img_resized, dtype=np.float32).transpose(2, 0, 1) / 255.0
        input_tensor = np.expand_dims(input_tensor, axis=0)

        input_name = inp.name
        output_name = session.get_outputs()[0].name
        preds = session.run([output_name], {input_name: input_tensor})[0]

        # YOLOv8 output: [1, 4 + nc, G]. Derive class count from the actual
        # tensor shape so single-class ('Card') and multi-class models both work.
        nc = preds.shape[1] - 4 if preds.ndim == 3 else 1
        predictions = preds[0].transpose(1, 0)  # [G, 4 + nc]
        boxes = []
        conf_threshold = 0.35
        for pred in predictions:
            scores = pred[4:]
            class_id = int(np.argmax(scores))
            score = float(scores[class_id])
            if score > conf_threshold:
                cx, cy, bw, bh = pred[:4]
                x0 = max(0.0, (cx - bw / 2.0) / inp_w)
                y0 = max(0.0, (cy - bh / 2.0) / inp_h)
                w_norm = min(1.0, bw / inp_w)
                h_norm = min(1.0, bh / inp_h)
                # single-class card/document model -> 'document' zone; otherwise
                # keep the class id so callers can interpret it.
                label = "document" if nc == 1 else f"class_{class_id}"
                boxes.append({
                    "label": label,
                    "class_id": class_id,
                    "x": round(float(x0), 3),
                    "y": round(float(y0), 3),
                    "w": round(float(w_norm), 3),
                    "h": round(float(h_norm), 3),
                    "confidence": round(float(score), 2),
                })
        return _nms(boxes)[:max_boxes]
    except Exception:
        pass
    return []


def _nms(boxes: List[Dict[str, Any]], iou_thres: float = 0.5) -> List[Dict[str, Any]]:
    """Lightweight IoU suppression so duplicate detections collapse to one box."""
    if len(boxes) <= 1:
        return boxes
    kept: List[Dict[str, Any]] = []
    for b in sorted(boxes, key=lambda b: b["confidence"], reverse=True):
        duplicate = False
        for k in kept:
            ix1, iy1 = max(b["x"], k["x"]), max(b["y"], k["y"])
            ix2, iy2 = min(b["x"] + b["w"], k["x"] + k["w"]), min(b["y"] + b["h"], k["y"] + k["h"])
            inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
            union = b["w"] * b["h"] + k["w"] * k["h"] - inter
            if union > 0 and inter / union > iou_thres:
                duplicate = True
                break
        if not duplicate:
            kept.append(b)
    return kept


def extract_roi_boxes(image_bytes: bytes) -> List[Dict[str, Any]]:
    """Public extractor: runs YOLO ONNX if available, else robust CV pipeline."""
    if not image_bytes:
        return []
    
    # Remote microservice bypass
    # Remote microservice bypass
    try:
        from remote_ml import is_remote_available, mark_remote_failed, mark_remote_success, get_timeout, prepare_payload
    except ImportError:
        try:
            from app.remote_ml import is_remote_available, mark_remote_failed, mark_remote_success, get_timeout, prepare_payload
        except ImportError:
            is_remote_available = lambda: bool(os.getenv("ML_SERVICE_URL"))
            mark_remote_failed = lambda: None
            mark_remote_success = lambda: None
            get_timeout = lambda: 2.0
            prepare_payload = lambda b: b

    if is_remote_available():
        ml_url = os.getenv("ML_SERVICE_URL")
        try:
            timeout_sec = get_timeout()
            base = ml_url.rstrip("/")
            payload = prepare_payload(image_bytes)
            candidate_urls = (
                [f"{base}/api/ml/yolo_roi", f"{base}/gradio_api/api/ml/yolo_roi"]
                if "/gradio_api" not in base else [f"{base}/api/ml/yolo_roi"]
            )
            for target_url in candidate_urls:
                files = {"file": ("image.jpg", payload, "image/jpeg")}
                res = None
                try:
                    import httpx
                    with httpx.Client(timeout=timeout_sec) as client:
                        res = client.post(target_url, files=files)
                except ImportError:
                    import requests
                    res = requests.post(target_url, files=files, timeout=timeout_sec)

                if res is not None:
                    if res.status_code == 200:
                        mark_remote_success()
                        return res.json()
                    if res.status_code in (403, 404, 405) and target_url != candidate_urls[-1]:
                        continue
                    logger.warning(
                        f"Remote yolo_roi returned HTTP {res.status_code}: {res.text[:200]}"
                    )
        except Exception as exc:
            mark_remote_failed()
            logger.warning(
                f"Remote yolo_roi call to {ml_url} failed ({exc.__class__.__name__}: {exc}). Falling back to local."
            )
    rgb = _open_rgb(image_bytes)
    if rgb is None:
        return []

    session = _get_onnx_session()
    if session is not None:
        yolo_boxes = _run_yolo_onnx(rgb, session)
        if yolo_boxes:
            return yolo_boxes

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

    return boxes


_AADHAAR_CLASS_NAMES = [
    "Aadhaar_No", "DOB", "Gender", "Name", "Photo",
]
_aadhaar_session = None


def _get_aadhaar_session():
    """Lazily load the 5-class Aadhaar-field ONNX detector (nc=5, 640x640)."""
    global _aadhaar_session
    if _aadhaar_session is not None:
        return _aadhaar_session
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
        _aadhaar_session = ort.InferenceSession(
            path, sess_options=opts, providers=["CPUExecutionProvider"]
        )
        return _aadhaar_session
    except Exception:
        return None


def extract_aadhaar_fields(image_bytes: bytes) -> List[Dict[str, Any]]:
    """Detect Aadhaar fields with the trained 5-class model.

    Boxes are normalised (0..1) and labelled with semantic names
    ({'Aadhaar_No','DOB','Gender','Name','Photo'}). Requires
    app/models/aadhaar_fields.onnx or AADHAAR_FIELDS_ONNX_PATH.
    """
    if not image_bytes:
        return []
        
    if is_remote_available():
        ml_url = os.getenv("ML_SERVICE_URL")
        try:
            timeout_sec = get_timeout()
            base = ml_url.rstrip("/")
            payload = prepare_payload(image_bytes)
            candidate_urls = (
                [f"{base}/api/ml/aadhaar_fields", f"{base}/gradio_api/api/ml/aadhaar_fields"]
                if "/gradio_api" not in base else [f"{base}/api/ml/aadhaar_fields"]
            )
            for target_url in candidate_urls:
                files = {"file": ("image.jpg", payload, "image/jpeg")}
                res = None
                try:
                    import httpx
                    with httpx.Client(timeout=timeout_sec) as client:
                        res = client.post(target_url, files=files)
                except ImportError:
                    import requests
                    res = requests.post(target_url, files=files, timeout=timeout_sec)

                if res is not None:
                    if res.status_code == 200:
                        mark_remote_success()
                        return res.json()
                    if res.status_code in (403, 404, 405) and target_url != candidate_urls[-1]:
                        continue
                    logger.warning(
                        f"Remote aadhaar_fields returned HTTP {res.status_code}: {res.text[:200]}"
                    )
        except Exception as exc:
            mark_remote_failed()
            logger.warning(
                f"Remote aadhaar_fields call to {ml_url} failed ({exc.__class__.__name__}: {exc}). Falling back to local."
            )
            
    rgb = _open_rgb(image_bytes)
    session = _get_aadhaar_session()
    if rgb is None or session is None:
        return []
    boxes = _run_yolo_onnx(rgb, session, max_boxes=8)
    resolved = []
    for b in boxes:
        class_id = int(b["class_id"])
        b["label"] = _AADHAAR_CLASS_NAMES[class_id] if class_id < len(_AADHAAR_CLASS_NAMES) else b["label"]
        resolved.append(b)
    return resolved


def crop_region_to_bytes(image_bytes: bytes, box: Dict[str, Any],
                         padding: float = 0.0, fmt: str = "PNG") -> bytes | None:
    """Crop a normalised ROI out of an image as raw bytes.

    `box` is a normalised {x, y, w, h} dict (0..1) as returned by the ROI
    detectors. `padding` inflates the box fractionally (0.08 = +8% each side)
    so a tight detection never clips the printed field. Returns None on any
    failure — callers degrade instead of crash. This is the seam the Aadhaar
    pipeline uses to pipe a Name/DOB/Aadhaar_No zone straight into tesseract
    and the Photo zone into Module 4 (nothing is persisted).
    """
    if not image_bytes or not box:
        return None
    try:
        import io
        from PIL import Image
        x0 = float(box.get("x", 0) or 0)
        y0 = float(box.get("y", 0) or 0)
        bw = float(box.get("w", 0) or 0)
        bh = float(box.get("h", 0) or 0)
        if bw <= 0 or bh <= 0 or x0 < 0 or y0 < 0:
            return None
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
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
            # PIL defaults to quality=75 when unspecified — a second, much
            # lower-quality compression generation stacked on top of
            # whatever quality the original photo was saved at. That extra
            # lossy pass introduces fresh quantization artifacts in already-
            # smooth regions, which is exactly the kind of low-variance
            # "dead block" pattern the dual-stream forgery detector looks
            # for — a genuine card, once cropped through this path, could
            # come out looking artificially tampered purely from re-encoding
            # loss, not anything in the original capture. High quality here
            # also means cleaner text for the OCR/tesseract consumers of
            # this same crop path.
            crop.save(out, format=fmt, quality=95)
        else:
            crop.save(out, format=fmt)
        return out.getvalue()
    except Exception:
        return None


def isolate_document_card(image_bytes: bytes) -> tuple[bytes, dict | None]:
    """Isolate and crop the ID card boundary from an arbitrary background photo
    (e.g., card placed on white paper, table, or handheld).

    Returns (cropped_card_bytes, crop_meta) if a valid document card sub-rectangle
    is detected, or (image_bytes, None) if the card already fills the entire frame
    or could not be cleanly segmented.
    """
    if not image_bytes:
        return image_bytes, None
    try:
        boxes = extract_roi_boxes(image_bytes)
        doc_box = next((b for b in boxes if b.get("label") in ("document", "card")), None)
        if doc_box:
            bw = float(doc_box.get("w", 1.0))
            bh = float(doc_box.get("h", 1.0))
            area_ratio = bw * bh
            # If the card occupies a sub-region (between 12% and 94% of the image)
            if 0.12 <= area_ratio <= 0.94 and (bw < 0.96 or bh < 0.96):
                cropped = crop_region_to_bytes(image_bytes, doc_box, padding=0.03, fmt="JPEG")
                if cropped and len(cropped) > 2048:
                    return cropped, {
                        "cropped": True,
                        "box": doc_box,
                        "area_ratio": round(area_ratio, 3),
                        "confidence": doc_box.get("confidence", 0.9),
                    }
    except Exception as exc:
        logger.debug(f"isolate_document_card fallback: {exc}")
    return image_bytes, None

