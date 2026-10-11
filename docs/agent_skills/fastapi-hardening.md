name: fastapi-hardening
triggers: upload, size cap, content-length, hmac, compare_digest, cors, csp, security headers, rate limit, 413, forwarded, slowapi, csv, injection, max_image_pixels, polyglot
- Secret compare: `hmac.compare_digest(a.encode(), b.encode())`. Missing secret => refuse requests unless an explicit insecure flag is set, and log loudly.
- Upload: check Content-Length first, then stream in chunks and abort at the cap (HTTP 413). Never `await file.read()` unbounded. Cap page counts server-side. Detect type by magic bytes. Set an explicit lower `Image.MAX_IMAGE_PIXELS`.
- Trusted proxy: read forwarded-for only behind a flag that is off by default; test with spoofed headers.
- CSV export: prefix cells starting with `=`, `+`, `-`, `@`, tab or CR with an apostrophe.
- CSP: inline scripts need hashes or nonces; if you cannot check in a browser, ship `Content-Security-Policy-Report-Only` and call it that. Never `unsafe-eval`.
- Errors: opaque reference id to the client, details only in the server log. Tests for every item above.
