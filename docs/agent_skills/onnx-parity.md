name: onnx-parity
triggers: onnx, export, parity, int8, quantiz, opset, sidecar, sha256, meta.json, simplify
- Smoke first: 1 epoch / 32 images -> checkpoint -> ONNX -> read real input/output names with onnxruntime -> parity run.
- Parity: same 100 images through reference (torch/FP32) and ONNX; compare boxes (IoU >= 0.95) or logits (max abs diff reported). INT8 or FP16 needs its own parity AND its own metric rerun.
- Sidecar `<model>.meta.json`: input name/shape/dtype, output names, class order, preprocessing, decode rule, SHA-256, bytes, producer versions. Generate by script, never by hand.
- Loader refuses a model whose SHA-256 differs from the sidecar (fail closed, clear error).
- Never assume output names or sigmoid/softmax decode; derive from the real exported file.
