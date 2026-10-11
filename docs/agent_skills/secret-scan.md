name: secret-scan
triggers: secret, token, credential, leak, history, gitignore, .env, password, private key, hf_
- Regexes (print file, line, first 4 chars, length only): `hf_[A-Za-z0-9]{20,}`, `ghp_[A-Za-z0-9]{30,}`, `github_pat_[A-Za-z0-9_]{30,}`, `sk-[A-Za-z0-9]{20,}`, `AKIA[0-9A-Z]{16}`, `-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----`, `postgres(ql)?://[^\s"']+:[^\s"'@]+@`.
- Scan tree, docs, eval/runs, logs, notebooks, and git history (`git rev-list --all` then `git grep -I -n -E` per revision, newest 300 plus tags; say so).
- A live-looking hit is S1: owner rotation steps into OWNER_TODO; never rewrite history; never print the value.
- `.gitignore` must keep `.env*` ignored but `!.env.example` tracked; check with `git check-ignore -v <path>`.
