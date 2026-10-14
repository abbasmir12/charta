"""Runtime plumbing: the log file, session tracking, port recovery, output rows."""
from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from charta.core import applog
from charta.core.config import AppConfig
from charta.shell import desktop
from charta.web.app import app


@pytest.fixture
def cfg(tmp_path) -> AppConfig:
    return AppConfig(state_dir=str(tmp_path))


def test_logging_writes_a_file_and_records_the_session(cfg, tmp_path):
    path = applog.setup(cfg)
    assert path == tmp_path / "charta.log" and path.exists()
    applog.get_logger("test").info("hello from the test")
    assert "hello from the test" in applog.read_log(cfg)

    applog.write_session(cfg, pid=1234, port=9, url="http://127.0.0.1:9/", view="browser")
    session = applog.read_session(cfg)
    assert session["pid"] == 1234 and session["view"] == "browser"
    # Nothing is listening on port 9, so a stale session must not look alive.
    assert applog.session_running(cfg) is False
    applog.clear_session(cfg, "test done")
    assert applog.read_session(cfg) == {}


def test_session_running_detects_a_listening_port(cfg):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = int(sock.getsockname()[1])
        applog.write_session(cfg, pid=1, port=port)
        assert applog.session_running(cfg) is True


def test_choose_port_keeps_a_free_port_and_recovers_a_busy_one():
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        busy = int(sock.getsockname()[1])
        chosen, note = desktop.choose_port("127.0.0.1", busy)
        assert chosen != busy and "in use" in note
        assert desktop.port_is_free("127.0.0.1", chosen)
    freed, note = desktop.choose_port("127.0.0.1", chosen)
    assert freed == chosen and note == ""


def test_backend_command_is_the_serve_subcommand():
    argv = desktop.backend_command(8123, True)
    assert argv[1:3] == ["-m", "charta.cli"]
    assert argv[3:5] == ["serve", "--port"] and argv[5] == "8123" and argv[-1] == "--debug"


def test_read_log_explains_a_missing_file(cfg):
    assert "no log yet" in applog.read_log(cfg)


def test_output_rows_endpoint_reports_columns_and_rows(tmp_path):
    from charta.core.charter import preset_charter, save_charter

    save_charter(tmp_path, preset_charter("freelancer"))
    (tmp_path / "receipt_rent_2026-03-01.txt").write_text("date: 2026-03-01\ntotal: $900.00\n")
    client = TestClient(app)
    body = client.get("/api/outputs/rows", params={"folder": str(tmp_path), "kind": "receipts"}).json()
    assert "source_file" in body["columns"] and body["rows"]
    assert body["path"].endswith("receipts.csv")
    bad = client.get("/api/outputs/rows", params={"folder": str(tmp_path), "kind": "nope"})
    assert bad.status_code == 400


def test_logs_command_runs(tmp_path, capsys, monkeypatch):
    from charta import cli

    monkeypatch.setenv("CHARTA_STATE_DIR", str(tmp_path))
    assert cli.main(["logs", "--lines", "5"]) == 0
    assert "charta.log" in capsys.readouterr().out
