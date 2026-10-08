import importlib.util
import sqlite3
import subprocess
import threading
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("integration", Path(__file__).parents[1] / "scripts/integration.py")
integration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(integration)


def test_fixture_query_waits_for_writer_and_preserves_sql_errors(tmp_path, monkeypatch):
    db = tmp_path / "fixture.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE photos (id INTEGER)")
        conn.execute("INSERT INTO photos VALUES (4)")
    locked = threading.Event()
    release = threading.Event()

    def writer():
        with sqlite3.connect(db) as conn:
            conn.execute("BEGIN EXCLUSIVE")
            locked.set()
            release.wait(5)
            conn.commit()

    worker = threading.Thread(target=writer)
    worker.start()
    assert locked.wait(5)

    def docker_sqlite(*args):
        command = list(args[2:])
        command[command.index("/data/db/picpeak.db")] = str(db)
        # Prove the read cannot succeed while the writer holds its lock.
        with pytest.raises(subprocess.CalledProcessError):
            subprocess.check_output(["sqlite3", str(db), "SELECT id FROM photos"], stderr=subprocess.PIPE)
        threading.Timer(0.2, release.set).start()
        return subprocess.check_output(command, text=True)

    monkeypatch.setattr(integration, "docker", docker_sqlite)
    try:
        assert integration.fixture_db_query("pixcake-test", "SELECT id FROM photos") == [{"id": 4}]
    finally:
        release.set()
        worker.join(5)

    monkeypatch.setattr(integration, "docker", lambda *args: subprocess.check_output(
        ["sqlite3", "-cmd", ".timeout 10000", "-json", str(db), args[-1]], text=True, stderr=subprocess.PIPE,
    ))
    with pytest.raises(subprocess.CalledProcessError):
        integration.fixture_db_query("pixcake-test", "SELECT missing_column FROM photos")
