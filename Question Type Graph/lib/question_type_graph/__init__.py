"""Profile-driven supplementary-book question graph compiler."""

import os
import sys


if os.name == "nt":
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


SCHEMA_VERSION = 1
