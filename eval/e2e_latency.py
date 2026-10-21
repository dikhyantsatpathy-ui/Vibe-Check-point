"""End-to-End Screening Latency Measurement Script (SIH26188 Phase V8 / Fix 18).

Measures full production screening pipeline latency end-to-end:
Upload -> Card ROI -> Doc-type -> Field Extraction -> Tampering/ELA -> Face Match -> Risk Scoring -> Ledger/DB Commit.

Outputs p50, p90, p95, max total latency, and per-stage breakdown against SLA targets:
Warm/in-process target: p50 < 3.0s, p95 < 6.0s.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("e2e_latency")


def make_specimen_pair(label: str) -> tuple[bytes, bytes]:
    """Generate in-memory valid document image and live portrait selfie."""
    # Document card image
    doc = Image.new("RGB", (700, 440), color=(240, 242, 245))
    draw = ImageDraw.Draw(doc)
    draw.rectangle([15, 15, 685, 425], outline=(40, 40, 40), width=2)
    draw.text((40, 40), f"GOVERNMENT OF INDIA - {label.upper()}", fill=(10, 10, 10))
    draw.text((40, 100), "Holder Name: John Doe", fill=(30, 30, 30))
    draw.text((40, 160), "Aadhaar: 9876 5432 1098", fill=(10, 10, 10))
    draw.text((40, 220), "DOB: 01/01/1990", fill=(30, 30, 30))
    # Simple simulated face portrait box
    draw.rectangle([500, 80, 640, 250], fill=(210, 180, 150), outline=(20, 20, 20), width=2)

    buf_doc = io.BytesIO()
    doc.save(buf_doc, format="JPEG", quality=85)

    # Live frame selfie
    selfie = Image.new("RGB", (320, 320), color=(220, 190, 160))
    draw_s = ImageDraw.Draw(selfie)
    draw_s.ellipse([80, 80, 240, 240], fill=(200, 170, 140))

    buf_selfie = io.BytesIO()
    selfie.save(buf_selfie, format="JPEG", quality=85)

    return buf_doc.getvalue(), buf_selfie.getvalue()


def measure_e2e_latency(iterations: int = 20, out_file: Path | None = None) -> dict:
    """Execute end-to-end screening runs and collect per-stage latency telemetry."""
    from app.screening import run_screening

    # Ensure offline execution for deterministic benchmark baseline
    os.environ["ML_SERVICE_URL"] = ""

    total_latencies = []
    ocr_latencies = []
    tamper_latencies = []
    face_latencies = []
    card_roi_latencies = []

    logger.info(f"Starting {iterations} end-to-end screening evaluation passes...")

    doc_bytes, live_bytes = make_specimen_pair("aadhaar")

    # Warm-up pass to initialize model weights and ONNX runtime sessions
    try:
        run_screening(
            doc_bytes,
            filename="warmup.jpg",
            doc_type="aadhaar",
            checkpoint="Panitanki",
            declared={"name": "John Doe", "aadhaar": "987654321098"},
            live_frame=live_bytes,
        )
    except Exception as exc:
        logger.warning(f"Warm-up pass note: {exc}")

    for i in range(iterations):
        t_start = time.perf_counter()

        report = run_screening(
            doc_bytes,
            filename=f"latency_specimen_{i}.jpg",
            doc_type="aadhaar",
            checkpoint="Panitanki",
            declared={"name": "John Doe", "aadhaar": "987654321098"},
            live_frame=live_bytes,
        )

        t_end = time.perf_counter()
        dur_ms = (t_end - t_start) * 1000.0
        total_latencies.append(dur_ms)

        # Stage breakdowns from report metrics
        tamper_data = report.get("modules", {}).get("tampering", {})
        tamper_ms = (tamper_data.get("ela") or {}).get("latency_ms", 0.0) or 0.0
        tamper_latencies.append(float(tamper_ms))

        ocr_ms = ((report.get("modules", {}).get("extraction", {}).get("ocr") or {}).get("latency_ms", 0.0)) or 0.0
        ocr_latencies.append(float(ocr_ms))

        ai_ms = report.get("ai_detection", {}).get("latency_ms", 0.0) or 0.0
        card_roi_latencies.append(float(ai_ms))

        face_ms = report.get("face_match", {}).get("latency_ms", 0.0) or 0.0
        face_latencies.append(float(face_ms))

    total_latencies.sort()
    n = len(total_latencies)
    p50 = total_latencies[int(n * 0.50)]
    p90 = total_latencies[int(n * 0.90)]
    p95 = total_latencies[int(n * 0.95)]
    max_lat = max(total_latencies)
    mean_lat = sum(total_latencies) / n

    # Target SLA gates: p50 < 3000ms, p95 < 6000ms
    passed_p50 = p50 < 3000.0
    passed_p95 = p95 < 6000.0

    metrics = {
        "benchmark": "e2e_screening_latency",
        "iterations": iterations,
        "total_latency_ms": {
            "mean": round(mean_lat, 2),
            "p50": round(p50, 2),
            "p90": round(p90, 2),
            "p95": round(p95, 2),
            "max": round(max_lat, 2),
        },
        "per_stage_breakdown_ms": {
            "tampering_ela_p50": round(sorted(tamper_latencies)[int(n * 0.50)], 2),
            "ocr_extraction_p50": round(sorted(ocr_latencies)[int(n * 0.50)], 2),
            "card_roi_ai_p50": round(sorted(card_roi_latencies)[int(n * 0.50)], 2),
            "face_verification_p50": round(sorted(face_latencies)[int(n * 0.50)], 2),
        },
        "sla_budgets": {
            "target_p50_ms": 3000.0,
            "target_p95_ms": 6000.0,
            "passed_p50": passed_p50,
            "passed_p95": passed_p95,
        },
        "status": "PASS" if (passed_p50 and passed_p95) else "WARNING_DEGRADED_SLA",
    }

    if out_file:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        logger.info(f"Latency report written to {out_file}")

    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure end-to-end screening latency.")
    parser.add_argument("--iterations", type=int, default=20, help="Number of benchmark iterations (default: 20).")
    parser.add_argument("--out-dir", type=Path, default=None, help="Output directory for latency metrics JSON.")
    args = parser.parse_args()

    out_file = (args.out_dir / "e2e_latency.json") if args.out_dir else None
    results = measure_e2e_latency(args.iterations, out_file)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
