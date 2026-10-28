import sys

import pytest

sys.path.insert(0, "/root/shared_jainam")
import session_cache as _session_cache  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_shared_jainam_session_cache(tmp_path, monkeypatch):
    """Tests must never read or write the REAL shared session cache at
    /root/shared_jainam/.jainam_session.json -- that file is live
    production state shared across 3 separate trading projects on this
    box (see jainam/broker/xts_client.py's SessionInvalidatedError
    docstring)."""
    monkeypatch.setattr(_session_cache, "SESSION_FILE", str(tmp_path / "session.json"))
    monkeypatch.setattr(_session_cache, "_LOCK_FILE", str(tmp_path / "session.json.lock"))
