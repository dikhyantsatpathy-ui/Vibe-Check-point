# Content-Security-Policy (CSP) Notes & Enforcement Status

## 1. Static HTML Audit
- **Target File**: `app/static/index.html`
- **Inline Event Handlers**: None detected (`onclick=`, `onload=`, `onerror=`, etc. are absent in raw HTML attributes).
- **`javascript:` Pseudo-URLs**: None detected (`href="javascript:..."` is absent).
- **Conclusion**: Hash-based strict CSP script execution is not blocked by inline event handlers or `javascript:` pseudo-protocols.

## 2. CSP Dual-Policy Configuration
- **Enforced Policy (Baseline)**:
  - Documented as `baseline: script-src allows unsafe-inline`.
  - Transmitted via `Content-Security-Policy` header by default.
  - Permits `'self'`, `'unsafe-inline'`, and `https://accounts.google.com` in `script-src`.
  - Prohibits `'unsafe-eval'`.
- **Report-Only Policy (Strict)**:
  - Transmitted via `Content-Security-Policy-Report-Only` header.
  - Strips `'unsafe-inline'` from `script-src`.
  - Computes and injects `'sha256-...'` base64 digests for all inline `<script>` tags found in `app/static/index.html`.
  - Recomputes inline script hashes dynamically when `app/static/index.html` modification time (`mtime`) changes.
  - Prohibits `'unsafe-eval'`.

## 3. Strict Enforcement Flag
- **Environment Variable**: `CSP_STRICT_ENFORCE`
- **Default**: `0` (Off)
- **Activation**: Setting `CSP_STRICT_ENFORCE=1` switches the enforced `Content-Security-Policy` header from the baseline policy to the strict policy.
- **Verification Protocol**: Before setting `CSP_STRICT_ENFORCE=1`, inspect the browser DevTools Console across all application workflows to verify that no report-only CSP violation warnings are logged.
