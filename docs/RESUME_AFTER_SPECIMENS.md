# NO-CAP (SIH26188) — RESUME AFTER SPECIMEN CAPTURE

**Status:** Indian Specimen Generalisation: **NOT MEASURED**  
**Date:** October 2026  
**Target Path:** `data/indian_specimens_photos/`

---

## 1. Overview & Current Status

During Phase 9 autonomous evaluation, `data/indian_specimens_photos/` was not present on disk.  
In strict compliance with Work Order §9.2 and the honest reporting contract:
- Card Detector v2 real-world Indian physical specimen performance is marked **NOT MEASURED**.
- Document-Type Classifier v2 real-world Indian physical specimen performance is marked **NOT MEASURED**.
- Print-ready specimen sheets have already been generated at `training/indian_specimens/out/indian_specimen_sheets_300dpi.pdf`.

Once the physical specimens are printed, cut, and photographed, follow the exact steps below to resume and complete evaluation.

---

## 2. Step-by-Step Instructions & PowerShell Commands

### Step 1: Print & Photograph Specimens
1. Open and print [`training/indian_specimens/out/indian_specimen_sheets_300dpi.pdf`](../training/indian_specimens/out/indian_specimen_sheets_300dpi.pdf) at **100% scale** (A4 paper, no scaling or "Fit to page").
2. Cut out the 16 ID card specimens along the guide lines.
3. Using $\ge 2$ different smartphones (e.g. Android + iPhone), capture $\ge 150$ photos under varied conditions (refer to [`training/indian_specimens/CAPTURE_PROTOCOL.md`](../training/indian_specimens/CAPTURE_PROTOCOL.md)):
   - Indoor warm / white lighting
   - Outdoor direct sunlight / shade
   - Card held in hand / fingers slightly occluding border
   - Card resting on wood table, cloth, keyboard, paper
   - Perspective tilt ($\pm 15^\circ$ to $\pm 30^\circ$)
   - Overhead glare
4. Capture 50 negative control photos (desks, keyboards, books, receipts without any card).
5. Transfer all photos to:
   ```powershell
   New-Item -ItemType Directory -Force -Path "data/indian_specimens_photos"
   # Copy JPEG/PNG photo files into data/indian_specimens_photos
   ```

---

### Step 2: Label 4 Card Corners (OpenCV Clicker)
Run the corner clicker tool to label the 4 corners of each card:
```powershell
python -m training.label_cards `
  --image-dir data/indian_specimens_photos `
  --output-json data/indian_specimens_annotations.json
```
*Note: Click top-left, top-right, bottom-right, bottom-left. Press `Space` to confirm, `r` to reset, `s` to skip negatives.*

---

### Step 3: Import into Evaluation Dataset
Convert annotations and photos into a structured COCO test dataset:
```powershell
python -m training.indian_specimens.import_indian_specimens `
  --image-dir data/indian_specimens_photos `
  --ann-json data/indian_specimens_annotations.json `
  --output-dir data/coco_card_indian/test
```

---

### Step 4: Evaluate Card Detector v2 & Document Classifier
Run the evaluation harness against the captured specimen test set:
```powershell
python -m eval.task2_negatives_and_stress `
  --model ml_service/models/rfdetr_card_int8.onnx `
  --test-dir data/coco_card_indian/test `
  --output-dir eval/runs/indian_specimen_eval
```
The script will report:
- `INDIAN SPECIMEN TEST n=<N>` (Outputs `SAMPLE TOO SMALL` if $N < 100$)
- Recall@0.5 and Precision@0.5
- Negative False Positive Rate on real unconstrained backgrounds

---

### Step 5: Optional Fine-Tune (If Card Gate Fails)
If Recall@0.5 on real Indian specimens falls below the 0.95 gate:
1. Split 70% of specimens into `data/coco_card_v2/images/train` and 30% into test (stratified by design).
2. Execute ONE fine-tune run (3 epochs, lr=1e-5) on GPU:
   ```powershell
   python -m training.train_card_rfdetr `
     --data-dir data/coco_card_v2 `
     --epochs 3 `
     --batch-size 4 `
     --resume training/runs/card_run2/checkpoint_best_ema.pth `
     --output-dir training/runs/card_run3_specimen_ft
   ```
3. Export and re-quantize:
   ```powershell
   python -m training.export_rfdetr_onnx `
     --checkpoint training/runs/card_run3_specimen_ft/checkpoint_best_ema.pth `
     --output ml_service/models/rfdetr_card.onnx `
     --quantize-int8
   ```
4. Re-run evaluation and verify all gates pass.
