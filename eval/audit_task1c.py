import os
import json
from PIL import Image, ImageOps
import numpy as np
import onnxruntime as ort
from app.yolo_roi import _run_yolo_onnx, letterbox, scale_boxes_to_original
from eval.metrics import compute_iou

def main():
    test_dir = os.path.join("data", "coco_card", "test")
    coco_ann = os.path.join(test_dir, "_annotations.coco.json")
    with open(coco_ann, "r", encoding="utf-8") as f:
        coco = json.load(f)

    # 1. EXIF and orientation check
    sample_img_info = coco["images"][0]
    sample_file = sample_img_info["file_name"]
    sample_path = os.path.join(test_dir, "images", sample_file)
    if not os.path.exists(sample_path):
        sample_path = os.path.join(test_dir, sample_file)

    # Path to raw file
    doc_type = sample_img_info["doc_type"]
    num_part = sample_file.replace(f"{doc_type}_", "")
    raw_path = os.path.join("data", "raw", "midv2020", "images", doc_type, num_part)

    print("=== TASK 1c (i): EXIF ORIENTATION AUDIT ===")
    print(f"Sample test file: {sample_file}")
    with Image.open(sample_path) as im:
        print(f"Converted test image dimensions: width={im.width}, height={im.height}")
    if os.path.exists(raw_path):
        with Image.open(raw_path) as raw_im:
            raw_exif = raw_im.getexif()
            exif_orient = raw_exif.get(0x0112)
            print(f"Raw image dimensions before exif_transpose: width={raw_im.width}, height={raw_im.height}, EXIF orientation={exif_orient}")
            transposed = ImageOps.exif_transpose(raw_im)
            print(f"Raw image dimensions after exif_transpose:  width={transposed.width}, height={transposed.height}")

    # 2. Coordinate frame & normalisation audit
    print("\n=== TASK 1c (ii) & (iii): LETTERBOX & INVERSE MAPPING CHECK ===")
    sample_img = Image.open(sample_path).convert("RGB")
    rgb = np.asarray(sample_img, dtype=np.uint8)
    canvas, scale, padding, orig_dim = letterbox(rgb, (640, 640))
    print(f"Original dim: {orig_dim}")
    print(f"Letterbox scale factor: {scale:.4f}, padding (dx, dy): {padding}")
    print(f"Letterbox canvas shape: {canvas.shape}")

    # 3. YOLO Predictions vs GT across all 300 test images at thresholds 0.1, 0.3, 0.5
    print("\n=== TASK 1c (iv): YOLO RECALL AT IoU 0.1, 0.3, 0.5 AND LOW CONFIDENCE ===")
    sess = ort.InferenceSession("ml_service/models/card.onnx", providers=["CPUExecutionProvider"])

    anns_by_img = {}
    for a in coco["annotations"]:
        anns_by_img.setdefault(a["image_id"], []).append(a)

    iou_hits_01 = 0
    iou_hits_03 = 0
    iou_hits_05 = 0
    total_gt = 0
    max_ious = []
    top_confs = []

    for idx, img_info in enumerate(coco["images"]):
        img_id = img_info["file_name"].rsplit(".", 1)[0]
        img_path = os.path.join(test_dir, "images", img_info["file_name"])
        if not os.path.exists(img_path):
            img_path = os.path.join(test_dir, img_info["file_name"])
        w, h = img_info["width"], img_info["height"]
        gts = [a["bbox"] for a in anns_by_img.get(img_info["id"], [])]

        img = Image.open(img_path).convert("RGB")
        rgb = np.asarray(img, dtype=np.uint8)

        # Extremely low confidence threshold to capture ANY candidate
        boxes = _run_yolo_onnx(rgb, sess, max_boxes=10, class_names=["Card"], conf_threshold=0.01)

        for g in gts:
            total_gt += 1
            gx1, gy1, gw, gh = g
            gt_box_norm = [gx1 / w, gy1 / h, (gx1 + gw) / w, (gy1 + gh) / h]

            best_iou = 0.0
            best_conf = 0.0
            for b in boxes:
                bx1, by1, bw, bh = b["x"], b["y"], b["w"], b["h"]
                pred_box_norm = [bx1, by1, bx1 + bw, by1 + bh]
                iou = compute_iou(pred_box_norm, gt_box_norm)
                if iou > best_iou:
                    best_iou = iou
                    best_conf = b["confidence"]

            max_ious.append(best_iou)
            top_confs.append(best_conf)
            if best_iou >= 0.10:
                iou_hits_01 += 1
            if best_iou >= 0.30:
                iou_hits_03 += 1
            if best_iou >= 0.50:
                iou_hits_05 += 1

        if idx < 5:
            print(f"\n--- Image {idx}: {img_info['file_name']} (w={w}, h={h}) ---")
            for g in gts:
                gx1, gy1, gw, gh = g
                print(f"  GT Box: norm=[{gx1/w:.3f}, {gy1/h:.3f}, {gw/w:.3f}, {gh/h:.3f}] px=[{gx1:.1f}, {gy1:.1f}, {gw:.1f}, {gh:.1f}]")
            print(f"  YOLO Detections (conf >= 0.01): count={len(boxes)}")
            for b in boxes[:4]:
                bx1, by1, bw, bh = b["x"], b["y"], b["w"], b["h"]
                iou = compute_iou([bx1, by1, bx1 + bw, by1 + bh], gt_box_norm) if gts else 0.0
                print(f"    Pred: conf={b['confidence']:.3f} norm=[{bx1:.3f}, {by1:.3f}, {bw:.3f}, {bh:.3f}] IoU_with_GT={iou:.3f}")

    print("\n=== SUMMARY OVER ALL 300 TEST IMAGES ===")
    print(f"Total Ground Truths: {total_gt}")
    print(f"Recall at IoU >= 0.10: {iou_hits_01} / {total_gt} ({iou_hits_01 / total_gt:.3%})")
    print(f"Recall at IoU >= 0.30: {iou_hits_03} / {total_gt} ({iou_hits_03 / total_gt:.3%})")
    print(f"Recall at IoU >= 0.50: {iou_hits_05} / {total_gt} ({iou_hits_05 / total_gt:.3%})")
    print(f"Max IoU across all images: max={np.max(max_ious):.4f}, median={np.median(max_ious):.4f}, 95th-pct={np.percentile(max_ious, 95):.4f}")
    print(f"Top confidence scores: max={np.max(top_confs):.4f}, median={np.median(top_confs):.4f}")

if __name__ == "__main__":
    main()
