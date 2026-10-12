name: csp-hardening
triggers: csp, content-security-policy, script-src, unsafe-inline, nonce, report-only, inline script, security headers
- Enforced header = baseline that works today; a stricter policy goes in Report-Only until someone checks the UI in a browser.
- Strict policy: no `unsafe-inline` in `script-src`; allow inline scripts by `'sha256-<base64>'` of the exact script text (UTF-8, between the tags, whitespace included); no `unsafe-eval`.
- Inline event handlers (`onclick=`) and `javascript:` URLs cannot be allowed by hashes: list them in docs/CSP_NOTES.md.
- Recompute hashes when the served HTML changes (mtime). Test: header hashes equal the real inline scripts.
- Never send the identical policy as both enforced and Report-Only. Say exactly which one is enforced in the blueprint.
