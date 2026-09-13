"""Write the OpenAPI spec the frontend client is generated from.

A script rather than ``python -m remitx_api.openapi``: the package imports the
app eagerly, so running one of its modules as ``__main__`` loads it twice.
"""

import sys

from remitx_api.openapi import main

if __name__ == "__main__":
    sys.exit(main())
