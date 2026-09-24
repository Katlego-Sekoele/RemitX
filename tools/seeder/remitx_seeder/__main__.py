"""`python -m remitx_seeder` opens the UI on http://127.0.0.1:8090.

With a command (`python -m remitx_seeder seed --target local ...`) it runs
that one operation instead: that is how the UI runs everything that touches a
database (runner.py).
"""

from __future__ import annotations

import sys


def main() -> int:
    argv = sys.argv[1:]
    if argv and not argv[0].startswith("-"):
        from remitx_seeder.runner import main as run_command

        return run_command(argv)
    from remitx_seeder.ui.app import serve

    serve(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
