"""The station daemon, started and stopped the way the tray app does it."""

import socket
import time

from flex import daemon
from flex.config import load_config


def _free_port() -> int:
    """A command port whose events port (+1) is free too."""
    while True:
        with socket.socket() as a:
            a.bind(("127.0.0.1", 0))
            port = a.getsockname()[1]
        with socket.socket() as b:
            try:
                b.bind(("127.0.0.1", port + 1))
                return port
            except OSError:
                continue


def test_start_status_stop(tmp_path, monkeypatch):
    server_port = _free_port()
    runner_port = server_port + 10
    config = tmp_path / "flex.toml"
    config.write_text(
        f'[data]\nroot = "{(tmp_path / "data").as_posix()}"\n'
        f"[server]\nport = {server_port}\n[runner]\nport = {runner_port}\n"
        "[instruments.bench]\nsimulate = true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FLEX_CONFIG", str(config))
    cfg = load_config()

    assert daemon.status(cfg)["station"] is False
    daemon.start(cfg)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            status = daemon.status(cfg)
            if status["station"] and status["runner"]:
                break
            time.sleep(0.3)
        assert status["instruments"] == ["bench"] and status["failed"] == {} and status["run"] is None
    finally:
        stopped = daemon.stop(cfg)

    assert stopped
    assert daemon.status(cfg)["station"] is False
    assert "Instrument added: bench" in daemon.log_file(cfg).read_text(encoding="utf-8")
