"""Minimal OpenCV click tool for labeling card bounding quadrilaterals.

Usage:
    python -m training.label_cards --input-dir training/indian_specimens/raw --out quads.json

Controls:
    Left click : add corner point (up to 4 points per image)
    'u'        : undo last clicked point
    's'        : save current quad to disk
    'n'        : proceed to next image
    'q' / ESC  : quit tool
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class CardLabeler:
    def __init__(self, image_paths: List[Path], out_file: Path, existing_data: Optional[Dict] = None):
        self.image_paths = sorted(image_paths)
        self.out_file = out_file
        self.data: Dict[str, List[List[float]]] = existing_data or {}
        self.current_idx = 0
        self.current_points: List[Tuple[int, int]] = []
        self.scale_factor = 1.0
        self.window_name = "NO-CAP Card Labeler (click 4 corners; 'u'=undo, 'n'=next, 's'=save, 'q'=quit)"

    def _mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(self.current_points) < 4:
                # Convert from display scale to original image coordinates
                orig_x = int(round(x / self.scale_factor))
                orig_y = int(round(y / self.scale_factor))
                self.current_points.append((orig_x, orig_y))
                logger.info("Point %d added: (%d, %d)", len(self.current_points), orig_x, orig_y)

    def load_transposed_image(self, path: Path) -> np.ndarray:
        """Load image with EXIF transposition into BGR format for OpenCV."""
        pil_img = Image.open(path)
        pil_img = ImageOps.exif_transpose(pil_img)
        rgb = np.asarray(pil_img.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    def save_labels(self):
        """Save labeled quads to out_file."""
        self.out_file.parent.mkdir(parents=True, exist_ok=True)
        self.out_file.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        logger.info("Saved %d quads to %s", len(self.data), self.out_file)

    def run(self):
        if not self.image_paths:
            logger.warning("No images to label.")
            return

        cv2.namedWindow(self.window_name, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)

        while 0 <= self.current_idx < len(self.image_paths):
            img_path = self.image_paths[self.current_idx]
            bgr = self.load_transposed_image(img_path)
            orig_h, orig_w = bgr.shape[:2]

            # Fit to screen resolution if large (max 1280x900 for display)
            max_disp_w, max_disp_h = 1280, 850
            scale_w = min(1.0, max_disp_w / orig_w)
            scale_h = min(1.0, max_disp_h / orig_h)
            self.scale_factor = min(scale_w, scale_h)

            # Load previously saved points if any
            if img_path.name in self.data and not self.current_points:
                self.current_points = [(int(p[0]), int(p[1])) for p in self.data[img_path.name]]

            while True:
                disp_w = int(orig_w * self.scale_factor)
                disp_h = int(orig_h * self.scale_factor)
                disp_img = cv2.resize(bgr, (disp_w, disp_h), interpolation=cv2.INTER_AREA)

                # Draw points and polygon lines
                pts_scaled = [
                    (int(round(pt[0] * self.scale_factor)), int(round(pt[1] * self.scale_factor)))
                    for pt in self.current_points
                ]

                for i, (px, py) in enumerate(pts_scaled):
                    cv2.circle(disp_img, (px, py), 6, (0, 0, 255), -1)
                    cv2.putText(disp_img, str(i + 1), (px + 8, py - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

                if len(pts_scaled) >= 2:
                    for i in range(len(pts_scaled) - 1):
                        cv2.line(disp_img, pts_scaled[i], pts_scaled[i + 1], (0, 255, 0), 2)
                if len(pts_scaled) == 4:
                    cv2.line(disp_img, pts_scaled[3], pts_scaled[0], (0, 255, 0), 2)

                # Overlay status text
                status_text = f"[{self.current_idx + 1}/{len(self.image_paths)}] {img_path.name} | Points: {len(self.current_points)}/4"
                cv2.rectangle(disp_img, (0, 0), (disp_w, 35), (20, 20, 20), -1)
                cv2.putText(disp_img, status_text, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

                cv2.imshow(self.window_name, disp_img)
                key = cv2.waitKey(20) & 0xFF

                if key in (27, ord('q')):  # ESC or 'q'
                    self.save_labels()
                    cv2.destroyAllWindows()
                    return
                elif key == ord('u'):  # Undo
                    if self.current_points:
                        self.current_points.pop()
                        logger.info("Undid last point. Remaining: %d", len(self.current_points))
                elif key == ord('s'):  # Save
                    if len(self.current_points) == 4:
                        self.data[img_path.name] = [[float(p[0]), float(p[1])] for p in self.current_points]
                        self.save_labels()
                    else:
                        logger.warning("Need exactly 4 points to save quad.")
                elif key in (13, ord('n')):  # Enter or 'n' -> next
                    if len(self.current_points) == 4:
                        self.data[img_path.name] = [[float(p[0]), float(p[1])] for p in self.current_points]
                    self.current_points = []
                    self.current_idx += 1
                    self.save_labels()
                    break

        self.save_labels()
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="Minimal OpenCV click tool to annotate 4-corner document quads.")
    parser.add_argument("--input-dir", type=Path, default=Path("training/indian_specimens/raw"), help="Directory of photos.")
    parser.add_argument("--out", type=Path, default=Path("training/indian_specimens/quads.json"), help="Output JSON file.")
    args = parser.parse_args()

    files = list(args.input_dir.glob("*.jpg")) + list(args.input_dir.glob("*.png")) + list(args.input_dir.glob("*.jpeg"))
    if not files:
        print(f"No images found in {args.input_dir}")
        return

    existing = {}
    if args.out.exists():
        try:
            existing = json.loads(args.out.read_text(encoding="utf-8"))
        except Exception:
            pass

    labeler = CardLabeler(files, args.out, existing)
    labeler.run()


if __name__ == "__main__":
    main()
