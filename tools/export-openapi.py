"""Export the OpenAPI schema from the FastAPI app without starting a server.

Usage:
    uv run --project backend python tools/export-openapi.py [OUTPUT_PATH]

When OUTPUT_PATH is omitted the JSON is written to stdout.
"""

import json
import os
import sys


_here = os.path.dirname(os.path.abspath(__file__))
_backend = os.path.abspath(os.path.join(_here, "..", "backend"))

# resolve output path (relative to caller CWD) before we chdir
output = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None

# chdir to backend so .env and relative imports resolve correctly
os.chdir(_backend)
sys.path.insert(0, _backend)

# skip database / redis access during import
os.environ.setdefault("TESTING", "true")

from api.main import app  # noqa: E402


schema = app.openapi()

if output:
	os.makedirs(os.path.dirname(output), exist_ok=True) if os.path.dirname(
		output
	) else None
	with open(output, "w", encoding="utf-8") as f:
		json.dump(schema, f)
else:
	json.dump(schema, sys.stdout)
