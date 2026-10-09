from fastapi.testclient import TestClient
from sqlalchemy import select

from pixcake_bridge.app import create_app
from pixcake_bridge.models import Delivery, Photo, Project
from test_engine import setup


def test_admin_auth_actions_csrf(tmp_path):
    engine, remote, cfg, db = setup(tmp_path)
    cfg.raw_root = tmp_path / "camera"
    cfg.delivery_root = tmp_path / "delivery"
    cfg.projects_file = tmp_path / "projects.json"
    cfg.delivery_host_root = "/nas/Projects"
    raw_job = cfg.raw_root / "2026" / "portrait"
    raw_job.mkdir(parents=True)
    cfg.delivery_root.mkdir()
    db.dispose()
    with TestClient(create_app(cfg, remote, start_workers=False)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/").status_code == 401
        client.auth = ("admin", cfg.admin_password)
        assert "精修同步工作台" in client.get("/").text
        assert client.get("/api/projects").json()[0]["stage"] == "SELECTING"
        assert sum(1 for route in client.app.routes if getattr(route, "path", None) == "/api/projects/{event_id}/detail") == 1
        detail = client.get("/api/projects/7/detail").json()
        assert detail["event_id"] == 7
        assert detail["delivery_path"] == f"/nas/Projects/{tmp_path.name}"
        assert client.post("/api/projects/7/stage", json={"stage": "EDITING"}).json() == {"success": True, "stage": "EDITING"}
        assert client.post("/api/projects/7/stage", json={"stage": "UNKNOWN"}).status_code == 400
        assert client.post("/api/projects/7/sync").status_code == 200
        assert client.post("/api/projects/999/sync").status_code == 404
        assert client.post("/projects/7/stage", data={"stage": "EDITING"}, headers={"Origin": "http://evil.example"}).status_code == 403
        assert client.post("/projects/7/stage", data={"stage": "EDITING"}).status_code == 200
        assert client.post("/projects/7/stage", data={"stage": "SELECTING"}).status_code == 400
        assert client.post("/projects/7/retry").status_code == 400
        assert client.post("/projects/7/sync").status_code == 200
        assert client.post("/projects/999/sync").status_code == 404
        assert client.post("/projects/7/unknown").status_code == 400
        assert "摄影师怎么接手客户选片" in client.get("/").text
        response = client.post("/projects", data={
            "name": "新项目",
            "event_id": "9",
            "raw_subdir": "2026/portrait",
        }, follow_redirects=False)
        assert response.status_code == 303
        created = next(p for p in cfg.projects if p.event_id == 9)
        assert created.raw == raw_job
        assert created.selected.is_dir() and created.final.is_dir() and created.history.is_dir()
        assert '"event_id": 9' in cfg.projects_file.read_text()
        assert client.post("/projects", data={
            "name": "路径越界",
            "event_id": "10",
            "raw_subdir": "../../etc",
        }, follow_redirects=False).status_code == 303
        outside = tmp_path / "outside"
        outside.mkdir()
        (cfg.raw_root / "linked-escape").symlink_to(outside, target_is_directory=True)
        assert client.post("/projects", data={
            "name": "符号链接越界",
            "event_id": "11",
            "raw_subdir": "linked-escape",
        }, follow_redirects=False).status_code == 303
        (cfg.delivery_root / "event-12-链接目录").symlink_to(outside, target_is_directory=True)
        assert client.post("/projects", data={
            "name": "链接目录",
            "event_id": "12",
            "raw_subdir": "2026/portrait",
        }, follow_redirects=False).status_code == 303


def test_retry_requires_confirmation_for_unknown_upload(tmp_path):
    engine, remote, cfg, db = setup(tmp_path)
    with engine.sessions() as session:
        project = session.scalar(select(Project).where(Project.event_id == 7))
        photo = Photo(project_id=project.id, photo_id=999, source_filename="unknown.jpg", selected=True)
        session.add(photo)
        session.flush()
        session.add(Delivery(
            photo_pk=photo.id,
            sha256="a" * 64,
            marker="unknown.__bridge_" + "a" * 64 + ".jpg",
            snapshot=str(tmp_path / "snapshot.jpg"),
            state="UNKNOWN",
        ))
        session.commit()

    with TestClient(create_app(cfg, remote, start_workers=False)) as client:
        client.auth = ("admin", cfg.admin_password)
        blocked = client.post("/api/projects/7/retry", json={"confirm_unknown": False})
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "UNKNOWN_CONFIRMATION_REQUIRED"
        assert blocked.json()["detail"]["count"] == 1
        confirmed = client.post("/api/projects/7/retry", json={"confirm_unknown": True})
        assert confirmed.status_code == 200
        with engine.sessions() as session:
            delivery = session.scalar(select(Delivery))
            assert delivery.state == "PENDING"
    db.dispose()
