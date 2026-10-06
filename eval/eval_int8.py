import os
import json
from PIL import Image
import numpy as np
import onnxruntime as ort
from app.yolo_roi import _run_rfdetr_onnx
from eval.metrics import evaluate_dataset_map

def main():
    model_path = os.path.join("ml_service", "models", "rfdetr_card_int8.onnx")
    test_dir = os.path.join("data", "coco_card", "test")
    coco_ann = os.path.join(test_dir, "_annotations.coco.json")

    with open(coco_ann, "r", encoding="utf-8") as f:
        coco = json.load(f)

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    sess = ort.InferenceSession(model_path, sess_options=opts, providers=["CPUExecutionProvider"])

    card_gts = []
    card_dets = []

    anns_by_img = {}
    for a in coco["annotations"]:
        anns_by_img.setdefault(a["image_id"], []).append(a)

    for img_info in coco["images"]:
        img_id = img_info["file_name"].rsplit(".", 1)[0]
        img_path = os.path.join(test_dir, "images", img_info["file_name"])
        if not os.path.exists(img_path):
            img_path = os.path.join(test_dir, img_info["file_name"])
        w, h = img_info["width"], img_info["height"]
        for ann in anns_by_img.get(img_info["id"], []):
            bx, by, bw, bh = ann["bbox"]
            card_gts.append({
                "img_id": img_id,
                "label": "Card",
                "x1": bx / w,
                "y1": by / h,
                "x2": (bx + bw) / w,
                "y2": (by + bh) / h,
            })

        img = Image.open(img_path).convert("RGB")
        rgb = np.asarray(img, dtype=np.uint8)
        boxes = _run_rfdetr_onnx(rgb, sess, max_boxes=4, class_names=["Card"], conf_threshold=0.05)
        for b in boxes:
            card_dets.append({
                "img_id": img_id,
                "label": b["label"],
                "confidence": b.get("confidence", 0.0),
                "x1": b["x"],
                "y1": b["y"],
                "x2": b["x"] + b["w"],
                "y2": b["y"] + b["h"],
            })

    metrics = evaluate_dataset_map(card_dets, card_gts, ["Card"])
    m = metrics["classes"]["Card"]
    print("INT8 EVALUATION RESULTS ON 300 TEST PHOTOS:")
    print(f"  mAP50:     {m.get('mAP50', 0):.4f}")
    print(f"  mAP50-95:  {m.get('mAP50_95', 0):.4f}")
    print(f"  Precision: {m.get('precision', 0):.4f}")
    print(f"  Recall:    {m.get('recall', 0):.4f}")

    results = {
        "model": "rfdetr_card_int8.onnx",
        "mAP50": m.get("mAP50", 0),
        "mAP50_95": m.get("mAP50_95", 0),
        "precision": m.get("precision", 0),
        "recall": m.get("recall", 0),
    }
    with open("eval/runs/20261006_090847_rfdetr_card_eval/int8_metrics.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
