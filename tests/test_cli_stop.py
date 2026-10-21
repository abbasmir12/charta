"""`charta stop` — close the running instance cleanly, and only that one."""
from __future__ import annotations

import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading


def _run_cli(argv: list[str], env: dict, timeout: float = 60) -> str:
    return subprocess.run(
        [sys.executable, "-c",
         "import os,sys;sys.path.insert(0,os.getcwd());"
         "from charta.cli import main;sys.exit(main())", *argv],
        env=env, capture_output=True, text=True, timeout=timeout).stdout


def _piggyback_process() -> subprocess.Popen:
    """A process that holds a port, like the real backend does."""
    return subprocess.Popen(
        [sys.executable, "-c",
         "import socket,sys,time\n"
         "s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)\n"
         "s.bind(('127.0.0.1',0));s.listen(5)\n"
         "print(s.getsockname()[1],flush=True)\n"
         "sys.stdout.flush()\n"
         "for _ in range(600):\n"
         "    try:\n"
         "        s.settimeout(5);c,_=s.accept()\n"
         "        c.sendall(b'HTTP/1.0 200 OK\\n\\nok');c.close()\n"
         "    except OSError:\n"
         "        pass\n"],
        stdout=subprocess.PIPE, text=True)


def test_charta_stop_closes_a_running_instance():
    """The pid comes from the session file; nothing else is touched."""
    port = None
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        _ = probe  # only to prove nothing of ours leaks
    with tempfile.TemporaryDirectory() as home:
        (pathlib.Path(home) / "config.toml").write_text("", encoding="utf-8")
        env = {**os.environ, "CHARTA_CONFIG": str(pathlib.Path(home) / "config.toml"),
               "CHARTA_STATE_DIR": str(pathlib.Path(home) / "state")}
        proc = _piggyback_process()
        try:
            port_line = proc.stdout.readline()
            port = int(port_line.strip())
            with socket.socket() as sock:
                sock.settimeout(0.5)
                assert sock.connect_ex(("127.0.0.1", port)) == 0, "fixture must listen"
            # Record the running instance the way the launcher does.
            setup = subprocess.run(
                [sys.executable, "-c",
                 "import os,sys;sys.path.insert(0,os.getcwd());"
                 "from charta.core import applog;"
                 "from charta.core.config import AppConfig;"
                 "applog.setup(AppConfig.load());"
                 f"applog.write_session(AppConfig.load(), pid={proc.pid}, port={port})"],
                env=env, capture_output=True, text=True, cwd=os.getcwd(), timeout=60)
            assert setup.returncode == 0, setup.stderr
            out = _run_cli(["stop"], env=env)
            assert f"Stopped Charta: pid {proc.pid} (tree)" in out
            with socket.socket() as sock:
                sock.settimeout(0.5)
                assert sock.connect_ex(("127.0.0.1", port)) != 0, "the instance must be closed"
        finally:
            proc.kill()
            proc.wait(timeout=10)


def test_charta_stop_when_nothing_runs_says_so_and_clears():
    with tempfile.TemporaryDirectory() as home:
        (pathlib.Path(home) / "config.toml").write_text("", encoding="utf-8")
        env = {**os.environ, "CHARTA_CONFIG": str(pathlib.Path(home) / "config.toml"),
               "CHARTA_STATE_DIR": str(pathlib.Path(home) / "state")}
        out = _run_cli(["stop"], env=env)
        assert "not running" in out


def test_charta_stop_never_touches_a_stranger_when_the_port_is_dead():
    """A stale session whose port no longer answers is cleared, not killed."""
    with tempfile.TemporaryDirectory() as home:
        (pathlib.Path(home) / "config.toml").write_text("", encoding="utf-8")
        env = {**os.environ, "CHARTA_CONFIG": str(pathlib.Path(home) / "config.toml"),
               "CHARTA_STATE_DIR": str(pathlib.Path(home) / "state")}
        sleeper = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"])
        try:
            setup = subprocess.run(
                [sys.executable, "-c",
                 "import os,sys;sys.path.insert(0,os.getcwd());"
                 "from charta.core import applog;"
                 "from charta.core.config import AppConfig;"
                 "applog.setup(AppConfig.load());"
                 f"applog.write_session(AppConfig.load(), pid={sleeper.pid}, port=1)"],
                env=env, capture_output=True, text=True, cwd=os.getcwd(), timeout=60)
            assert setup.returncode == 0, setup.stderr
            out = _run_cli(["stop"], env=env)
            # Port 1 answers nothing, so the session is stale: the (innocent)
            # pid must still be alive, and the session file must be gone.
            assert sleeper.poll() is None
            assert "not running" in out
        finally:
            sleeper.kill()
            sleeper.wait(timeout=10)


def test_stop_sweeps_an_orphaned_backend_off_its_port():
    """A backend that survived its shell keeps serving old code on the port;
    stop must catch it even though the session file is already gone."""
    # The fixture listens and its command line contains the word "charta".
    proc = subprocess.Popen(
        [sys.executable, "-c",
         "import socket,sys,time\n"
         "s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)\n"
         "s.bind(('127.0.0.1',0));s.listen(5)\n"
         "print(s.getsockname()[1],flush=True)\n"
         "# charta is the marker the stop sweep matches on\n"
         "for _ in range(600):\n"
         "    try:\n"
         "        s.settimeout(5);c,_=s.accept()\n"
         "        c.sendall(b'HTTP/1.0 200 OK\\n\\nok');c.close()\n"
         "    except OSError:\n"
         "        pass\n"],
        stdout=subprocess.PIPE, text=True)
    try:
        port = int(proc.stdout.readline().strip())
        with tempfile.TemporaryDirectory() as home:
            (pathlib.Path(home) / "config.toml").write_text(
                f'[app]\nport = {port}\n', encoding="utf-8")
            env = {**os.environ, "CHARTA_CONFIG": str(pathlib.Path(home) / "config.toml"),
                   "CHARTA_STATE_DIR": str(pathlib.Path(home) / "state")}
            out = _run_cli(["stop"], env=env)
            assert f"(listening on port {port})" in out, out
            with socket.socket() as sock:
                sock.settimeout(0.5)
                assert sock.connect_ex(("127.0.0.1", port)) != 0, "orphan must be gone"
    finally:
        proc.kill()
        proc.wait(timeout=10)


def test_stop_never_touches_a_foreign_listener():
    """A listener that is not Charta's is left alone, and stop says so."""
    proc = _piggyback_process()  # its command line does not mention charta
    try:
        port = int(proc.stdout.readline().strip())
        with tempfile.TemporaryDirectory() as home:
            (pathlib.Path(home) / "config.toml").write_text(
                f'[app]\nport = {port}\n', encoding="utf-8")
            env = {**os.environ, "CHARTA_CONFIG": str(pathlib.Path(home) / "config.toml"),
                   "CHARTA_STATE_DIR": str(pathlib.Path(home) / "state")}
            out = _run_cli(["stop"], env=env)
            assert "not running" in out
            with socket.socket() as sock:
                sock.settimeout(0.5)
                assert sock.connect_ex(("127.0.0.1", port)) == 0, "foreign listener untouched"
    finally:
        proc.kill()
        proc.wait(timeout=10)
