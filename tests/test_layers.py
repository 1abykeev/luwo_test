"""The architecture requirement, checked mechanically: the upper layers must not know PostgreSQL.

Each module is imported in a FRESH interpreter (so other tests cannot hide a problem), then we look at what got
loaded. If SQLAlchemy, asyncpg, our DB models or the Postgres adapters appear, a layer above the repository
interfaces has started depending on the database, and swapping the data source would no longer be "only the adapter"."""

import subprocess
import sys

import pytest

FORBIDDEN = ("sqlalchemy", "asyncpg", "app.db", "app.repositories.postgres")

# The layers from the task, top to bottom (the HTTP layer and the container are allowed to know adapters)
LAYERS = [
    "app.agent.agent",
    "app.agent.memory",
    "app.agent.factory",
    "app.observability.telemetry",
    "app.observability.request_log",
    "app.tools",
    "app.services",
    "app.repositories.interfaces",
    "app.repositories.memory.unit_of_work",
    "app.domain.models",
]

PROBE = """
import importlib, sys
importlib.import_module(sys.argv[1])
forbidden = {names!r}
loaded = sorted(m for m in sys.modules if any(m == f or m.startswith(f + ".") for f in forbidden))
print(",".join(loaded))
"""


@pytest.mark.parametrize("module", LAYERS)
def test_a_layer_above_the_adapters_does_not_load_database_code(module):
    result = subprocess.run(
        [sys.executable, "-c", PROBE.format(names=FORBIDDEN), module],
        capture_output=True, text=True, check=True,
    )
    loaded = [name for name in result.stdout.strip().split(",") if name]
    assert loaded == [], f"importing {module} also loads database code: {loaded[:6]}"
