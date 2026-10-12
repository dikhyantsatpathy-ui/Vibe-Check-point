#!/usr/bin/env python3
"""Render SIH26188_ENGINEERING_BLUEPRINT.md from docs/blueprint_template.md.

Replaces placeholders of the form:
  {{metric:<json_path>:<key_path>}}

Where:
  <json_path> is a path relative to the repo root, or a glob pattern (e.g. eval/runs/**/count.json).
  <key_path> is a dot-separated (or slash-separated) key path in the JSON file.

Supports:
  --check: Verifies rendered content matches SIH26188_ENGINEERING_BLUEPRINT.md on disk.
"""

from __future__ import annotations

import argparse
import difflib
import json
import pathlib
import re
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / "docs" / "blueprint_template.md"
OUTPUT_PATH = REPO_ROOT / "SIH26188_ENGINEERING_BLUEPRINT.md"


def resolve_json_file(json_path_str: str) -> pathlib.Path:
    """Resolve exact path or glob pattern to the latest matching JSON file."""
    if "*" in json_path_str:
        matches = list(REPO_ROOT.glob(json_path_str))
        if not matches:
            raise FileNotFoundError(f"No files matching glob pattern: {json_path_str}")
        # Sort by mtime descending, then path descending
        matches.sort(key=lambda p: (p.stat().st_mtime, str(p)), reverse=True)
        return matches[0]

    target = REPO_ROOT / json_path_str
    if not target.exists():
        raise FileNotFoundError(f"Evidence file not found: {json_path_str}")
    return target


def extract_key(data: Any, key_path: str) -> Any:
    """Extract nested value from JSON object by key path."""
    curr = data
    parts = key_path.split(".")
    i = 0
    while i < len(parts):
        if isinstance(curr, dict):
            matched = False
            # Try longest prefix of parts from len(parts) down to i + 1
            for j in range(len(parts), i, -1):
                sub_key = ".".join(parts[i:j])
                if sub_key in curr:
                    curr = curr[sub_key]
                    i = j
                    matched = True
                    break
            if not matched:
                raise KeyError(f"Key starting with '{parts[i]}' not found in data: {list(curr.keys())[:10]}")
        elif isinstance(curr, list) and parts[i].isdigit():
            curr = curr[int(parts[i])]
            i += 1
        else:
            raise KeyError(f"Cannot traverse part '{parts[i]}' on {type(curr)}")
    return curr


def resolve_placeholder(match: re.Match) -> str:
    """Resolve a single {{metric:<json_path>:<key_path>}} match."""
    json_path = match.group(1).strip()
    key_path = match.group(2).strip()

    # Support optional slice syntax at end of key, e.g. key[:8]
    slice_spec = None
    slice_match = re.search(r"\[(\d*):(\d*)\]$", key_path)
    if slice_match:
        start_str, end_str = slice_match.groups()
        start = int(start_str) if start_str else None
        end = int(end_str) if end_str else None
        slice_spec = slice(start, end)
        key_path = key_path[: slice_match.start()]

    target_file = resolve_json_file(json_path)
    with open(target_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    val = extract_key(data, key_path)

    if isinstance(val, str) and slice_spec:
        val = val[slice_spec]

    if isinstance(val, float):
        # Format cleanly
        return f"{val:.2f}" if not val.is_integer() else f"{int(val)}"
    return str(val)


def render_template(template_text: str) -> str:
    """Replace all {{metric:...}} placeholders and assert no unrendered placeholders."""
    pattern = re.compile(r"\{\{metric:([^:]+):([^}]+)\}\}")
    rendered = pattern.sub(resolve_placeholder, template_text)

    # Check for any remaining unresolved placeholders
    remaining = re.findall(r"\{\{.*?\}\}", rendered)
    if remaining:
        raise ValueError(f"Unresolved placeholders found in rendered output: {remaining}")

    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(description="Render blueprint from template.")
    parser.add_argument("--check", action="store_true", help="Check disk against rendered output.")
    args = parser.parse_args()

    if not TEMPLATE_PATH.exists():
        print(f"Error: Template not found at {TEMPLATE_PATH}", file=sys.stderr)
        return 1

    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")

    try:
        rendered = render_template(template_text)
    except Exception as e:
        print(f"Error rendering template: {e}", file=sys.stderr)
        return 1

    if args.check:
        if not OUTPUT_PATH.exists():
            print(f"Error: Output file {OUTPUT_PATH} does not exist on disk.", file=sys.stderr)
            return 1

        disk_content = OUTPUT_PATH.read_text(encoding="utf-8")
        if disk_content != rendered:
            diff = difflib.unified_diff(
                disk_content.splitlines(keepends=True),
                rendered.splitlines(keepends=True),
                fromfile="disk",
                tofile="rendered",
                n=3,
            )
            print("Mismatch between rendered blueprint and disk:", file=sys.stderr)
            sys.stderr.writelines(diff)
            return 1
        print("OK: SIH26188_ENGINEERING_BLUEPRINT.md matches rendered template.")
        return 0

    # Write output to disk
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"Successfully rendered {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
