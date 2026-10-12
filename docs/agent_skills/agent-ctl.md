name: agent-ctl
triggers: agent_ctl, resume, queue, checkpoint, state file, get back to work, stopped, continue, journal, reconcile
- `python scripts/agent_ctl.py resume` first in every session; do its NEXT ACTION.
- start -> work -> `done <ID>` (verify command must pass) -> commit `[<ID>] ...` -> `checkpoint "<note>"`.
- Edit QUEUE.json / AGENT_STATE.json / JOURNAL.jsonl only through the script (atomic writes).
- Lost state: `init` then `reconcile`. Doubt about an old task: `recheck --phase <P>`.
- Interrupted task with uncommitted changes: `git diff --stat`, commit as `wip(<ID>)`, then `done <ID>`.
- Windows: never use os.kill to test a process (it terminates it); the script uses tasklist.
