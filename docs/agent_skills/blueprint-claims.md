name: blueprint-claims
triggers: blueprint, claims, ledger, render, placeholder, readiness, model card, documentation, doc rewrite
- Claims ledger `docs/claims/claims.json`: id, section, text, check kind, command, expect. Verdicts: VERIFIED, FALSE, UNVERIFIABLE.
- Blueprint is rendered from a template by script; every number is a placeholder resolved from `eval/runs/**/*.json`; the script fails on an unresolved placeholder.
- A checklist box is [x] only when the ledger says VERIFIED. Otherwise [ ] with the reason.
- No adjectives for results; tables. No legal-compliance claims ("designed with reference to ...; legal review pending").
