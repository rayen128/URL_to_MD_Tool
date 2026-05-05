import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "Code"))

import pytest


@pytest.fixture(autouse=True)
def _isolate_persistence(monkeypatch, tmp_path):
    """Redirect every test's job-persistence writes to tmp_path. Without this,
    bare `JobStore()` instances in tests that don't set up their own monkeypatch
    persist jobs into the real `output/_meta/`, polluting user state."""
    import jobs as jobs_module
    import server
    monkeypatch.setattr(jobs_module, "META_DIR", tmp_path / "_meta")
    monkeypatch.setattr(server, "MERGED_DIR", tmp_path / "_merged")
