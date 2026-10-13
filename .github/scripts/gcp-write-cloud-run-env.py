#!/usr/bin/env python3
"""Write a JSON map accepted by Cloud Run's ``--env-vars-file`` flag."""

from __future__ import annotations

import json
import sys


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "usage: gcp-write-cloud-run-env.py <env.json> <out.json>", file=sys.stderr
        )
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as source:
        data = json.load(source)
    if not isinstance(data, dict):
        raise SystemExit("input must be a JSON object")

    env = {str(key): str(value) for key, value in data.items() if value is not None}
    with open(sys.argv[2], "w", encoding="utf-8") as output:
        json.dump(env, output)
        output.write("\n")


if __name__ == "__main__":
    main()
