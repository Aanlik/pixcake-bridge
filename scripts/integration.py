#!/usr/bin/env python3
"""Real PicPeak container + real guest HTTP selection + Bridge filesystem E2E.

Run only against a dedicated test container, never a production installation.
Admin cookies are used solely to create a disposable fixture and API token;
the Bridge itself receives only the token with read/write scopes.
"""
import argparse
import asyncio
import json
import os
import secrets
import subprocess
import time
from pathlib import Path

import httpx
from PIL import Image
from sqlalchemy import select

from pixcake_bridge.client import PicPeak
from pixcake_bridge.config import Config, ProjectConfig
from pixcake_bridge.engine import Engine
from pixcake_bridge.files import sha256
from pixcake_bridge.models import Delivery, database


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


async def wait_ready(url):
    async with httpx.AsyncClient(timeout=5) as c:
        for _ in range(60):
            try:
                r = await c.get(url + "/health")
                if r.status_code == 200:
                    return
            except httpx.TransportError:
                pass
            await asyncio.sleep(1)
    raise RuntimeError("PicPeak 容器在 60 秒内没有启动")


async def main(args):
    root = args.root.resolve()
    if (root / "bridge.db").exists():
        raise RuntimeError("请选择新的测试目录，避免旧阶段和任务影响测试")
    if not args.container.startswith("pixcake-"):
        raise RuntimeError("测试容器名称必须以 pixcake- 开头，拒绝操作其他容器")
    if args.count < 100:
        raise RuntimeError("E2E 至少需要 100 张照片")
    await wait_ready(args.url)
    proof = root / "proofs/shoot"
    raw, selected, final, history = [root / x for x in ("01_RAW", "03_SELECTED_RAW", "04_FINAL", "05_HISTORY")]
    for p in (proof, raw, selected, final, history):
        p.mkdir(parents=True, exist_ok=True)
    for i in range(1, args.count + 1):
        Image.new("RGB", (64, 48), (i % 255, 80, 180)).save(proof / f"DSC{i:05}.JPG")
        (raw / f"DSC{i:05}.ARW").write_bytes(b"SYNTHETIC RAW TEST FIXTURE\x00" + str(i).encode())
    before = {p.name: sha256(p) for p in raw.iterdir()}
    async with httpx.AsyncClient(base_url=args.url, timeout=180, headers={"Origin": args.url}) as admin:
        status = (await admin.get("/api/setup/status")).json()
        # A fresh test installation is mandatory so this cannot silently log
        # into or alter an existing photographer's installation.
        token_path = docker("exec", args.container, "cat", "/data/db/SETUP_TOKEN")
        password = "FixtureA9!" + secrets.token_hex(16)
        result = await admin.post("/api/setup/admin", json={"token": token_path, "email": "fixture@example.com", "username": "fixture", "password": password})
        assert result.status_code == 201, f"Fixture setup failed: HTTP {result.status_code}; use a fresh test volume"
        language = await admin.put("/api/admin/settings/general", json={"general_default_language": "zh-CN"})
        assert language.status_code == 200, language.text
        create = await admin.post("/api/admin/api-tokens", json={"name": "Fixture seed", "scopes": ["read", "write", "admin"]})
        assert create.status_code == 201, create.text
        seed_token = create.json()["token"]
        event = await admin.post("/api/v1/events", headers={"Authorization": "Bearer " + seed_token}, json={"event_name": "PixCake E2E", "event_type": "other", "require_password": False, "feedback_enabled": True, "allow_color_labels": True, "allow_ratings": True, "allow_comments": True, "moderate_comments": False})
        assert event.status_code == 201, event.text
        info = event.json()
        eid, slug = info["id"], info["slug"]
        imported = await admin.post(f"/api/admin/external-media/events/{eid}/import-external", json={"external_path": "shoot", "recursive": True})
        assert imported.status_code == 200, imported.text
        settings = await admin.put(f"/api/admin/feedback/events/{eid}/feedback-settings", json={"feedback_enabled": True, "allow_color_labels": True, "allow_ratings": True, "allow_comments": True, "allow_favorites": True, "moderate_comments": False, "identity_mode": "simple", "require_name_email": False, "show_feedback_to_guests": True})
        assert settings.status_code == 200, settings.text
        bridge_token = await admin.post("/api/admin/api-tokens", json={"name": "Bridge read/write only", "scopes": ["read", "write"]})
        assert bridge_token.status_code == 201
        api = PicPeak(args.url, bridge_token.json()["token"])
        # Revoke bootstrap admin-scoped token: Bridge must not need it.
        assert (await admin.delete(f"/api/admin/api-tokens/{create.json()['id']}")).status_code == 200
    cfg = Config(base_url=args.url, token=bridge_token.json()["token"], database_url="sqlite:///" + str(root / "bridge.db"), stable_seconds=0, materialize_mode="copy", projects=[ProjectConfig("E2E 摄影项目", eid, raw, selected, final, history)])
    db, sessions = database(cfg.database_url)
    engine = Engine(cfg, sessions, api)
    photos = await api.photos(eid)
    assert len(photos) == args.count, (len(photos), imported.text)
    by_name = {p["source_filename"]: p for p in photos}
    def photo_id(i):
        return by_name[f"DSC{i:05}.JPG"]["id"]
    async with httpx.AsyncClient(base_url=args.url, headers={"Origin": args.url}, timeout=30) as guest:
        async def feedback(i, **payload):
            r = await guest.post(f"/api/gallery/{slug}/photos/{photo_id(i)}/feedback", json=payload)
            assert r.status_code < 300, r.text
        async def mark(i, color="green"):
            # Official API toggles OFF when submitting the current colour;
            # null is not a valid colour_label value.
            await feedback(i, feedback_type="color_label", color_label=color or "green")
        for i in range(1, 51):
            await mark(i)
        await feedback(4, feedback_type="rating", rating=5)
        await feedback(4, feedback_type="comment", comment_text="保留这条精修建议", guest_name="测试客户")
        await feedback(4, feedback_type="favorite")
        await engine.sync()
        assert len(list(selected.glob("*.ARW"))) == 50
        for i in range(51, 56):
            await mark(i)
        for i in (1, 2):
            await mark(i, None)
        await engine.sync()
        assert len(list(selected.glob("*.ARW"))) == 53
        engine.set_stage(eid, "EDITING")
        await mark(3, None)
        await engine.sync()
        assert (selected / "DSC00003.ARW").exists()
        # Snapshot physical DB preservation fields solely for validation.
        db_fields = ["id", "source_filename", "category_id", "uploaded_at", "captured_at", "type", "visibility"]
        def fixture_db_photo():
            stmt = "SELECT " + ",".join(db_fields) + " FROM photos WHERE id=" + str(photo_id(4))
            return json.loads(docker("exec", args.container, "sqlite3", "-json", "/data/db/picpeak.db", stmt))[0]
        original_fields = fixture_db_photo()
        name_order_before = [p["id"] for p in sorted(await api.photos(eid), key=lambda p: (p["original_filename"] or p["filename"]).casefold())]
        prior = next(p for p in await api.photos(eid) if p["id"] == photo_id(4))
        for i in range(3, 56):
            Image.new("RGB", (128, 96), (30, i % 255, 60)).save(final / f"DSC{i:05}.JPG")
        await engine.sync()
        await engine.sync()
        with sessions() as s:
            assert len(list(s.scalars(select(Delivery).where(Delivery.state == "SUCCESS")))) == 53
        Image.new("RGB", (128, 96), (210, 30, 70)).save(final / "DSC00004.JPG")
        await engine.sync()
        await engine.sync()
        after = next(p for p in await api.photos(eid) if p["id"] == photo_id(4))
        assert fixture_db_photo() == original_fields
        name_order_after = [p["id"] for p in sorted(await api.photos(eid), key=lambda p: (p["original_filename"] or p["filename"]).casefold())]
        assert name_order_after == name_order_before
        for key in ("id", "source_filename", "color_label", "comment_count", "favorite_count", "average_rating"):
            assert after[key] == prior[key], (key, prior[key], after[key])
        assert after["original_filename"] != prior["original_filename"]
        guest_feedback = (await guest.get(f"/api/gallery/{slug}/photos/{photo_id(4)}/feedback")).json()
        assert "保留这条精修建议" in json.dumps(guest_feedback, ensure_ascii=False)
        # Stop/restart the real PicPeak container and recover the same SQLite.
        docker("stop", args.container)
        await engine.sync()
        assert len(list(selected.glob("*.ARW"))) == 53
        docker("start", args.container)
        await wait_ready(args.url)
        db.dispose()
        db, sessions = database(cfg.database_url)
        engine = Engine(cfg, sessions, api)
        await engine.sync()
        await engine.sync()
        with sessions() as s:
            deliveries = list(s.scalars(select(Delivery)))
            assert len(deliveries) == 54
            assert sum(d.attempts for d in deliveries) == 54, "重启后发生重复上传"
        share_path = "/" + info["share_url"].split("/", 3)[-1] if info["share_url"].startswith("http") else info["share_url"]
        assert (await guest.get(share_path)).status_code == 200
        # Verify actual downloaded final bytes, not only the filename marker.
        managed = json.loads(docker("exec", args.container, "sqlite3", "-json", "/data/db/picpeak.db", "SELECT path FROM photos WHERE id=" + str(photo_id(4))))[0]["path"]
        remote_hash = docker("exec", args.container, "sha256sum", "/data/storage/events/active/" + managed).split()[0]
        assert remote_hash == sha256(final / "DSC00004.JPG")
        assert {p.name: sha256(p) for p in raw.iterdir()} == before
        report = {"proof_count": args.count, "selected_initial": 50, "added": 5, "cancelled_selecting": 2, "cancelled_editing_raw_preserved": True, "deliveries": 54, "raw_sha256_unchanged": args.count, "photo_id_feedback_sort_share_preserved": True, "restart_duplicate_uploads": 0, "guest_share_path": share_path, "event_id": eid, "slug": slug, "fixture_root": str(root), "tested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        # Credentials deliberately excluded; this report is safe to publish.
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        await api.close()
        db.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:19300")
    parser.add_argument("--container", default="pixcake-spike-picpeak")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--report", type=Path, default=Path("integration-report.json"))
    asyncio.run(main(parser.parse_args()))
