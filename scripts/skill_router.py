#!/usr/bin/env python
"""Pick at most 2 skill files for a task, so the agent never reads them all.

Usage:
  python scripts/skill_router.py "task description"   -> prints up to 2 lines: <score> <path>
  python scripts/skill_router.py --list                -> prints skill names only
Skill files: docs/agent_skills/*.md ; header = first lines "name:", "triggers:" (comma separated).
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "agent_skills"


def load():
    skills = []
    for p in sorted(ROOT.glob("*.md")):
        meta = {}
        for line in p.read_text(encoding="utf-8").splitlines()[:6]:
            m = re.match(r"^(name|triggers):\s*(.+)$", line)
            if m:
                meta[m.group(1)] = m.group(2).strip()
        if "triggers" in meta:
            skills.append((p, meta))
    return skills


def score(text, triggers):
    t = text.lower()
    s = 0
    for trig in (x.strip().lower() for x in triggers.split(",")):
        if not trig:
            continue
        if trig.isalnum() and len(trig) < 8:
            hit = re.search(r"\b" + re.escape(trig) + r"[a-z]{0,3}\b", t) is not None
        else:
            hit = trig in t
        if hit:
            s += 2 if (" " in trig or len(trig) >= 8) else 1
    return s


def main(argv):
    skills = load()
    if not argv or argv[0] == "--list":
        for p, meta in skills:
            print(meta.get("name", p.stem))
        return 0
    text = " ".join(argv)
    ranked = sorted(
        ((score(text, m["triggers"]), p) for p, m in skills),
        key=lambda x: (-x[0], x[1].name),
    )
    shown = 0
    for sc, p in ranked:
        if sc >= 2 and shown < 2:
            print(sc, p.relative_to(ROOT.parent.parent).as_posix())
            shown += 1
    if shown == 0:
        print("0 NONE (no skill needed; do not read any skill file)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
