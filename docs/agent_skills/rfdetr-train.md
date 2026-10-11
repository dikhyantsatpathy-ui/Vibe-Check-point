name: rfdetr-train
triggers: train, training, rfdetr, epochs, checkpoint, colab, gpu, cuda, oom, fine-tune
- Check GPU first (`nvidia-smi`, torch CUDA flag). No GPU => write a Colab guide, mark BLOCKED.
- Read the installed library source for arguments; never guess.
- Caps: <= 30 epochs, patience 7, <= 4 h, <= 2 attempts. Smoke test (1 epoch, 32 images) before any full run.
- Split by document type/design; hash-dedupe across splits; never touch frozen manifests.
- OOM ladder: batch 2 + accumulation 8, then smaller image size, then BLOCKED.
- Launch once as a background job, then one blocking wait.
