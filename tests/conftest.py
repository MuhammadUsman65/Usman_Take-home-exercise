import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def customers():
    path = PROJECT_ROOT / "data" / "customers.json"
    return json.loads(path.read_text(encoding="utf-8"))