# NO-CAP (SIH26188) — RUNTIME DEPENDENCY LICENCES

## 1. Runtime Core & ML Dependencies

| Package | Version | Licence | Runtime Role | Copyleft Risk |
|---|---|---|---|---|
| **fastapi** | 0.141.1 | MIT | Web API framework | None (Permissive) |
| **uvicorn** | 0.52.4 | BSD-3-Clause | ASGI web server | None (Permissive) |
| **sqlalchemy** | 2.0.x | MIT | ORM and DB schema | None (Permissive) |
| **pydantic** | 2.13.4 | MIT | Data parsing and validation | None (Permissive) |
| **httpx** | 0.28.1 | BSD-3-Clause | Async HTTP client | None (Permissive) |
| **python-multipart** | 0.0.32 | Apache-2.0 | Form & file upload parsing | None (Permissive) |
| **pillow** | 12.3.0 | HPND | Image decoding & EXIF handling | None (Permissive) |
| **numpy** | 2.3.5 | BSD-3-Clause | Tensor & array processing | None (Permissive) |
| **opencv-python-headless** | 5.0.0.93 | Apache-2.0 | Image processing (no GUI) | None (Permissive) |
| **onnxruntime** | 1.29.0 / 1.30.0 | MIT | Model inference engine | None (Permissive) |
| **pypdf** | 6.16.2 | BSD-3-Clause | Digital PDF text extraction | None (Permissive) |
| **huggingface-hub** | 1.28.0 | Apache-2.0 | Authenticated weight download | None (Permissive) |

## 2. Copyleft & Training-Only Dependencies

| Package | Licence | Role & Isolation |
|---|---|---|
| **ultralytics** | **AGPL-3.0** | Used **offline only** for training YOLO checkpoints and exporting to ONNX. **Not included in root `requirements.txt`** and **not required in production runtime** (production runs solely via `onnxruntime` with custom NMS/letterbox decode). |

## 3. Supply Chain Security Audits
- `pip-audit 2.10.1` on `requirements.txt`: **0 known vulnerabilities found**
- `pip-audit 2.10.1` on `ml_service/requirements.txt`: **0 known vulnerabilities found**
- `npm audit --omit=dev` on `frontend/`: **0 known vulnerabilities found**
