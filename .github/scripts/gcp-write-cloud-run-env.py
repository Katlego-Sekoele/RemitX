#!/usr/bin/env python3
"""Write a Cloud Run --env-vars-file from a JSON object (handles special chars)."""
from __future__ import annotations

import json
import sys


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: gcp-write-cloud-run-env.py <env.json> <out.env>", file=sys.stderr)
        sys.exit(2)
    data = json.loads(open(sys.argv[1], encoding="utf-8").read())
    lines: list[str] = []
    for key, value in data.items():
        if value is None:
            continue
        text = str(value)
        if any(ch in text for ch in "\n\r=#"):
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key}="{escaped}"')
        else:
            lines.append(f"{key}={text}")
    open(sys.argv[2], "w", encoding="utf-8").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
