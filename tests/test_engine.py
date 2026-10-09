from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy import select

from pixcake_bridge.client import ApiError
from pixcake_bridge.config import Config, ProjectConfig
from pixcake_bridge.engine import Engine
from pixcake_bridge.files import sha256
from pixcake_bridge.models import Delivery, Photo, Project, database


class FakePicPeak:
    def __init__(self, rows):
        self.rows, self.uploads = rows, []
        self.offline = False
        self.lost_response = False

    async def photos(self, event):
        if self.offline:
            raise ApiError(503)
        return deepcopy(self.rows)

    async def replace(self, event, photo, file, name):
        if self.offline:
            raise ApiError(503, uncertain=True)
        self.uploads.append((photo, sha256(file)))
        next(x for x in self.rows if x["id"] == photo)["original_filename"] = name
        if self.lost_response:
            raise ApiError(0, uncertain=True)
        return {"replaced": True, "photo": {"id": photo}}

    async def close(self):
        pass


def setup(tmp_path, count=1):
    dirs = [tmp_path / x for x in ("01_RAW", "03_SELECTED_RAW", "04_FINAL", "05_HISTORY")]
    for d in dirs:
        d.mkdir()
    cfg = Config(database_url="sqlite:///" + str(tmp_path / "state.db"), stable_seconds=0, admin_password="test-password-1234", materialize_mode="copy", projects=[ProjectConfig("测试项目", 7, *dirs)])
    rows = []
    for i in range(1, count + 1):
        name = f"DSC{i:05}"
        (dirs[0] / (name + ".ARW")).write_bytes(f"RAW-{i}".encode())
        rows.append({"id": i, "source_filename": name + ".JPG", "original_filename": name + ".JPG", "color_label": "green"})
    client = FakePicPeak(rows)
    db, sessions = database(cfg.database_url)
    return Engine(cfg, sessions, client), client, cfg, db


async def test_selection_add_cancel_and_editing_protection(tmp_path):
    engine, client, cfg, db = setup(tmp_path, 3)
    client.rows[2]["color_label"] = None
    await engine.sync()
    assert len(list(cfg.projects[0].selected.iterdir())) == 2
    client.rows[0]["color_label"] = None
    client.rows[2]["color_label"] = "green"
    await engine.sync()
    assert not (cfg.projects[0].selected / "DSC00001.ARW").exists()
    assert (cfg.projects[0].selected / "DSC00003.ARW").exists()
    engine.set_stage(7, "EDITING")
    client.rows[1]["color_label"] = None
    await engine.sync()
    assert (cfg.projects[0].selected / "DSC00002.ARW").exists()
    with engine.sessions() as s:
        photo = s.scalar(select(Photo).where(Photo.photo_id == 2))
        assert photo.cancelled
    engine.set_stage(7, "SELECTING")
    assert (cfg.projects[0].selected / "DSC00002.ARW").exists()
    db.dispose()


async def test_hash_versions_restart_and_history(tmp_path):
    engine, client, cfg, db = setup(tmp_path)
    raw_before = sha256(cfg.projects[0].raw / "DSC00001.ARW")
    for i in range(1, 6):
        folder = cfg.projects[0].final / f"V{i}"
        folder.mkdir(exist_ok=True)
        (folder / "DSC00001.JPG").write_bytes(f"FINAL-{i}".encode())
        await engine.sync()
        await engine.sync()
        if i < 5:
            prepared = engine.prepare_next_version_folder(7, 1, i)
            assert prepared["version"] == i + 1
    assert len(client.uploads) == 5
    assert len(list(cfg.projects[0].history.rglob("*.jpg"))) == 3
    db.dispose()
    db, sessions = database(cfg.database_url)
    restarted = Engine(cfg, sessions, client)
    await restarted.sync()
    await restarted.sync()
    assert len(client.uploads) == 5
    assert sha256(cfg.projects[0].raw / "DSC00001.ARW") == raw_before
    # Re-exporting an identical historical render remains hash-deduplicated.
    (cfg.projects[0].final / "V6" / "DSC00001.JPG").parent.mkdir(exist_ok=True)
    (cfg.projects[0].final / "V6" / "DSC00001.JPG").write_bytes(b"FINAL-1")
    await restarted.sync()
    await restarted.sync()
    assert len(client.uploads) == 5
    db.dispose()


async def test_cancel_after_delivery_blocks_next_version_until_reselected(tmp_path):
    engine, client, cfg, db = setup(tmp_path)
    await engine.sync()
    first = cfg.projects[0].final / "V1" / "DSC00001.JPG"
    first.write_bytes(b"first delivery")
    await engine.sync()
    await engine.sync()
    engine.set_stage(7, "EDITING")
    next_folder = engine.prepare_next_version_folder(7, 1, 1)["folder"]
    Path(next_folder, "DSC00001.JPG").write_bytes(b"revision")
    client.rows[0]["color_label"] = None
    await engine.sync()
    assert len(client.uploads) == 1
    assert Path(next_folder, "DSC00001.JPG").exists()
    client.rows[0]["color_label"] = "green"
    await engine.sync()
    await engine.sync()
    assert len(client.uploads) == 2
    db.dispose()


async def test_cancel_during_editing_keeps_first_delivery_in_progress(tmp_path):
    engine, client, cfg, db = setup(tmp_path)
    await engine.sync()
    engine.set_stage(7, "EDITING")
    client.rows[0]["color_label"] = None
    await engine.sync()
    assert (cfg.projects[0].selected / "DSC00001.ARW").exists()
    first = cfg.projects[0].final / "V1" / "DSC00001.JPG"
    first.parent.mkdir(exist_ok=True)
    first.write_bytes(b"edit already in progress")
    await engine.sync()
    await engine.sync()
    assert len(client.uploads) == 1
    assert client.rows[0]["original_filename"].startswith("DSC00001.__bridge_")
    db.dispose()


async def test_lost_response_reconciles_without_duplicate(tmp_path):
    engine, client, cfg, db = setup(tmp_path)
    (cfg.projects[0].final / "DSC00001.JPG").write_bytes(b"final")
    client.lost_response = True
    await engine.sync()
    await engine.sync()
    with engine.sessions() as s:
        assert s.scalar(select(Delivery)).state == "UNKNOWN"
    db.dispose()
    db, sessions = database(cfg.database_url)
    engine = Engine(cfg, sessions, client)
    await engine.sync()
    await engine.sync()
    assert len(client.uploads) == 1
    with sessions() as s:
        assert s.scalar(select(Delivery)).state == "SUCCESS"
    db.dispose()


async def test_ambiguous_upload_not_automatically_repeated(tmp_path):
    engine, client, cfg, db = setup(tmp_path)
    (cfg.projects[0].final / "DSC00001.JPG").write_bytes(b"final")
    async def lost(*args):
        client.uploads.append(args)
        raise ApiError(0, uncertain=True)
    client.replace = lost
    for _ in range(5):
        await engine.sync()
    assert len(client.uploads) == 1
    engine.retry(7)
    await engine.sync()
    assert len(client.uploads) == 2
    db.dispose()


async def test_offline_does_not_delete_selected(tmp_path):
    engine, client, cfg, db = setup(tmp_path)
    await engine.sync()
    client.rows[0]["color_label"] = None
    client.offline = True
    await engine.sync()
    assert (cfg.projects[0].selected / "DSC00001.ARW").exists()
    client.offline = False
    await engine.sync()
    assert not (cfg.projects[0].selected / "DSC00001.ARW").exists()
    db.dispose()


async def test_original_changed_or_selected_tampered_blocks(tmp_path):
    engine, client, cfg, db = setup(tmp_path)
    await engine.sync()
    selected = cfg.projects[0].selected / "DSC00001.ARW"
    selected.chmod(0o644)
    selected.write_bytes(b"changed")
    client.rows[0]["color_label"] = None
    await engine.sync()
    assert selected.exists()
    client.rows[0]["color_label"] = "green"
    raw = cfg.projects[0].raw / "DSC00001.ARW"
    raw.write_bytes(b"changed original")
    await engine.sync()
    with engine.sessions() as s:
        assert "SHA256" in s.scalar(select(Photo)).error
    db.dispose()


async def test_missing_remote_and_conflicting_final_preserved(tmp_path):
    engine, client, cfg, db = setup(tmp_path)
    await engine.sync()
    client.rows.clear()
    await engine.sync()
    assert (cfg.projects[0].selected / "DSC00001.ARW").exists()
    db.dispose()


@pytest.mark.parametrize("count", [100, 1000])
async def test_large_selection_workflow(tmp_path, count):
    engine, client, cfg, db = setup(tmp_path, count)
    before = {p.name: sha256(p) for p in cfg.projects[0].raw.iterdir()}
    for row in client.rows[50:]:
        row["color_label"] = None
    await engine.sync()
    assert len(list(cfg.projects[0].selected.iterdir())) == 50
    for row in client.rows[50:55]:
        row["color_label"] = "green"
    for row in client.rows[:2]:
        row["color_label"] = None
    await engine.sync()
    assert len(list(cfg.projects[0].selected.iterdir())) == 53
    engine.set_stage(7, "EDITING")
    client.rows[2]["color_label"] = None
    await engine.sync()
    assert len(list(cfg.projects[0].selected.iterdir())) == 53
    for row in client.rows[2:55]:
        (cfg.projects[0].final / "V1" / row["source_filename"]).write_bytes(f"final-{row['id']}".encode())
    await engine.sync()
    await engine.sync()
    assert len(client.uploads) == 53
    revision = engine.prepare_next_version_folder(7, 4, 1)
    (Path(revision["folder"]) / "DSC00004.JPG").write_bytes(b"revision")
    await engine.sync()
    await engine.sync()
    assert len(client.uploads) == 54
    assert {p.name: sha256(p) for p in cfg.projects[0].raw.iterdir()} == before
    db.dispose()



async def test_changed_final_cannot_bypass_unknown_upload(tmp_path):
    engine, client, cfg, db = setup(tmp_path)
    final = cfg.projects[0].final / "DSC00001.JPG"
    final.write_bytes(b"version-one")
    async def lost(*args):
        client.uploads.append(args)
        raise ApiError(0, uncertain=True)
    client.replace = lost
    await engine.sync()
    await engine.sync()
    final.write_bytes(b"version-two")
    for _ in range(3):
        await engine.sync()
    assert len(client.uploads) == 1
    db.dispose()
