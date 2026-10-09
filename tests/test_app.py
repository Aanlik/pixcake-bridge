from fastapi.testclient import TestClient

from pixcake_bridge.app import create_app
from test_engine import setup


def test_admin_auth_actions_csrf(tmp_path):
    engine, remote, cfg, db = setup(tmp_path)
    cfg.raw_root = tmp_path / "camera"
    cfg.delivery_root = tmp_path / "delivery"
    cfg.projects_file = tmp_path / "projects.json"
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
