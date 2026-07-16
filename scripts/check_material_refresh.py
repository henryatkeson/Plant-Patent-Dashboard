#!/usr/bin/env python3
"""Report whether an automated refresh changed patent record content."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def load_json(text: str) -> dict:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def records_changed(base_ref: str, path: Path) -> bool:
    previous = subprocess.run(
        ["git", "show", f"{base_ref}:{path.as_posix()}"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    before = load_json(previous.stdout)
    after = load_json(path.read_text(encoding="utf-8"))
    return before.get("records", []) != after.get("records", [])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--path", default="data/plant_patents.json")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT", ""))
    args = parser.parse_args()

    changed = records_changed(args.base, Path(args.path))
    value = "true" if changed else "false"
    print(f"Substantive patent record changes: {value}")
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as output:
            output.write(f"changed={value}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
