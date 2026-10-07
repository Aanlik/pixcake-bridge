from fastapi.testclient import TestClient

from pixcake_bridge.app import create_app
from test_engine import setup


def test_admin_auth_actions_csrf(tmp_path):
    engine, remote, cfg, db = setup(tmp_path)
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
