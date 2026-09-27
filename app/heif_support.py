"""Optional HEIC/HEIF decode support.

Every iPhone since iOS 11 (2017) saves camera-roll photos as .HEIC by default
unless the user has manually switched their camera to "Most Compatible" mode.
Pillow cannot open .HEIC files on its own — it needs the pillow-heif plugin
registered before the first Image.open() call.

Importing this module (for its side effect) registers the plugin if
pillow-heif is installed. If it isn't installed (e.g. a minimal Vercel
build), this is a silent no-op — the app behaves exactly as it did before,
just without HEIC decode capability, following the same
present-locally-absent-on-Vercel graceful-degradation pattern already used
for onnxruntime elsewhere in this codebase.
"""

HEIF_SUPPORTED = False
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:
    pass
