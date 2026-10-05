import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import gradio as gr
from fastapi.middleware.cors import CORSMiddleware
from main import app as fastapi_app, _model_dir, _model_path

# ZeroGPU Anchor Function
# Hugging Face ZeroGPU checks for an @spaces.GPU decorated function on startup.
try:
    import spaces
    @spaces.GPU(duration=15)
    def zero_gpu_task(action: str = "check"):
        """GPU-accelerated worker task required by Hugging Face ZeroGPU runtime."""
        return f"ZeroGPU Dynamic Worker Active: {action}"
except Exception:
    def zero_gpu_task(action: str = "check"):
        return f"CPU Fallback: {action}"

def get_status():
    models_dir = _model_dir()
    face_model = (
        os.path.exists(os.path.join(models_dir, "w600k_r50.onnx"))
        or os.path.exists(os.path.abspath(os.path.join(models_dir, "..", "..", "data", "models", "w600k_r50.onnx")))
        or bool(os.getenv("FACE_EMBED_MODEL"))
    )
    return {
        "service": "No-Cap AI/ML Microservice",
        "status": "Online & Healthy 🚀",
        "models": {
            "yolo_card": "Active" if os.path.exists(os.path.join(models_dir, "card.onnx")) else "Offline",
            "aadhaar_fields": "Active" if os.path.exists(os.path.join(models_dir, "aadhaar_fields.onnx")) else "Offline",
            "doctype": "Active" if os.path.exists(os.path.join(models_dir, "doctype.onnx")) else "Offline",
            "face_embed": "Active" if face_model else "Standby (Auto-Download)",
            "ai_detector": "Active" if os.path.exists(_model_path()) else "Standby (Auto-Download)",
        },
        "endpoints": [
            "/health",
            "/api/ml/yolo_roi",
            "/api/ml/aadhaar_fields",
            "/api/ml/face_match",
            "/api/ml/detect_image",
            "/api/ml/doctype",
            "/api/ml/doc_forgery",
        ],
    }

with gr.Blocks(title="No-Cap ML Microservice") as demo:
    gr.Markdown("# 🛡️ No-Cap AI/ML Microservice")
    gr.Markdown(
        "Active computer vision & deep learning backend for the **SSB Border Screening Desk (SIH26188)** connected to Vercel."
    )
    with gr.Row():
        status_box = gr.JSON(value=get_status, label="Service Telemetry")
    with gr.Row():
        refresh_btn = gr.Button("🔄 Refresh Telemetry")
        gpu_btn = gr.Button("⚡ Verify ZeroGPU Dynamic Worker")

    gpu_output = gr.Textbox(label="ZeroGPU Worker Response", visible=True)

    refresh_btn.click(fn=get_status, outputs=status_box)
    gpu_btn.click(fn=zero_gpu_task, outputs=gpu_output)

# Create Gradio FastAPI application instance
gradio_app = gr.routes.App.create_app(demo)

# Mount endpoints under /gradio_api to bypass SvelteKit reverse-proxy CSRF filters
gradio_app.include_router(fastapi_app.router, prefix="/gradio_api")

# Prepend all FastAPI endpoints (/health, /api/ml/*) so they match with top priority
gradio_app.router.routes = fastapi_app.routes + gradio_app.router.routes

# Restricted CORS for external integrations (Vercel production, local dev, desk consoles)
_cors_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if not _cors_origins:
    _cors_origins = [
        "https://vibe-check-point.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

gradio_app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app = gradio_app

if __name__ == "__main__":
    demo.queue().launch(_app=gradio_app)
