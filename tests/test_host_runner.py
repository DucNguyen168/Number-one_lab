import sys
from types import SimpleNamespace

import pytest

from scripts import run_host


@pytest.mark.parametrize("port,server_port,expected", [
    (None, None, 8000), ("12345", "9000", 12345), (None, "9000", 9000),
])
def test_allocated_port_priority(monkeypatch, port, server_port, expected):
    for name, value in [("PORT", port), ("SERVER_PORT", server_port)]:
        monkeypatch.delenv(name, raising=False)
        if value:
            monkeypatch.setenv(name, value)
    assert run_host.host_port() == expected


@pytest.mark.parametrize("value", ["0", "65536", "invalid"])
def test_bad_port_fails_before_start(monkeypatch, value):
    monkeypatch.setenv("PORT", value)
    with pytest.raises(ValueError):
        run_host.host_port()


def test_web_starts_one_worker_without_reload(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "argv", ["run_host.py", "web"])
    monkeypatch.setattr(run_host, "configure_runtime", lambda: None)
    monkeypatch.setenv("PORT", "9010")
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=lambda *a, **kw: calls.append((a, kw))))
    run_host.main()
    assert calls == [(("app.main:app",), dict(host="0.0.0.0", port=9010, workers=1,
                                           reload=False, access_log=False))]


def test_runtime_limits_threads_but_preserves_explicit_overrides(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a: None)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                 "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MKL_NUM_THREADS", "2")
    run_host.configure_runtime()
    import os
    assert os.environ["OPENBLAS_NUM_THREADS"] == "1"
    assert os.environ["OMP_NUM_THREADS"] == "1"
    assert os.environ["MKL_NUM_THREADS"] == "2"
