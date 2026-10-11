name: vercel-isolation
triggers: vercel, neon, staging, isolation, env vars, database_url, oauth, deployment, production site, test site
- Names only: `vercel env ls`; never print values. Compare two projects by SHA-256 prefix (8 hex) of each value, print same/different.
- Compare: DATABASE_URL, vault/master key, OAuth client id and secret, session secret, ML shared secret, HF token.
- Any shared value between staging and production = S1. Do NOT edit the production project; write exact owner commands.
- HF token inside a Vercel app project is only allowed if code in app/ or api/ reads it; the Space should hold a read-only token.
- Not logged in or CLI missing => BLOCKED with the exact owner commands. No retry loops.
