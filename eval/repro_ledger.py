"""Reproducibility Ledger Generator (Work Order v5 — Phase T).

Traces every claimed headline number in docs/SWITCH_READINESS.md and docs/MODEL_CARD.md
to its source script, exact command, output JSON, re-run value, tolerance match, and verdict.
Outputs to docs/REPRO_LEDGER.md and eval/runs/<ts>_repro/ledger.json.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class ReproClaim:
    def __init__(
        self,
        claim_id: str,
        headline_doc: str,
        metric_name: str,
        claimed_value: Any,
        unit: str,
        script_path: str,
        command: str,
        tolerance_type: str = "pct_point",  # "pct_point", "rel_pct", "exact"
        tolerance_val: float = 0.5,
    ):
        self.claim_id = claim_id
        self.headline_doc = headline_doc
        self.metric_name = metric_name
        self.claimed_value = claimed_value
        self.unit = unit
        self.script_path = script_path
        self.command = command
        self.tolerance_type = tolerance_type
        self.tolerance_val = tolerance_val
        self.output_json_path: Optional[str] = None
        self.rerun_value: Optional[Any] = None
        self.match: Optional[bool] = None
        self.verdict: str = "UNMEASURED"  # "PASS", "FAIL", "UNPROVEN", "UNMEASURED"
        self.notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "headline_doc": self.headline_doc,
            "metric_name": self.metric_name,
            "claimed_value": self.claimed_value,
            "unit": self.unit,
            "script_path": self.script_path,
            "command": self.command,
            "output_json_path": self.output_json_path,
            "rerun_value": self.rerun_value,
            "match": self.match,
            "verdict": self.verdict,
            "notes": self.notes,
        }


def render_markdown_ledger(claims: List[ReproClaim], output_path: Path) -> None:
    lines = [
        "# NO-CAP (SIH26188) — REPRODUCIBILITY LEDGER (WORK ORDER v5)",
        "",
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "Rules: Claim matched within tolerance (<=0.5 percentage points for recall/precision, <=15% for latency).",
        "Verdict words: `PASS`, `FAIL`, `UNPROVEN`, `UNMEASURED`.",
        "",
        "| ID | Document | Metric | Claimed | Rerun | Unit | Tolerated? | Verdict | Output JSON | Command |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in claims:
        tol_str = "YES" if c.match is True else ("NO" if c.match is False else "-")
        rerun_str = str(c.rerun_value) if c.rerun_value is not None else "-"
        lines.append(
            f"| {c.claim_id} | {c.headline_doc} | {c.metric_name} | {c.claimed_value} | {rerun_str} | {c.unit} | {tol_str} | `{c.verdict}` | `{c.output_json_path or '-'}` | `{c.command}` |"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    print("Repro ledger skeleton initialized.")
