import asyncio
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from watchfiles import awatch

from .client import PicPeak
from .config import Config
from .engine import Engine, STAGES
from .models import Delivery, Error, Photo, Project, SyncRun, database

security = HTTPBasic()
templates = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape())
STAGE_NAMES = {"SELECTING": "客户选片", "EDITING": "精修中", "DELIVERED": "已交付", "ARCHIVED": "已归档"}


def create_app(config=None, client=None, start_workers=True):
    @asynccontextmanager
    async def lifespan(app):
        cfg = config or Config.load()
        db_engine, sessions = database(cfg.database_url)
        api = client or PicPeak(cfg.base_url, cfg.token)
        engine = Engine(cfg, sessions, api)
        app.state.engine, app.state.config = engine, cfg
        tasks = []
        async def watch():
            roots = [p.final for p in cfg.projects]
            if roots:
                async for _ in awatch(*roots, debounce=500):
                    engine.wake.set()
        if start_workers:
            tasks = [asyncio.create_task(engine.loop()), asyncio.create_task(watch())]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await api.close()
            db_engine.dispose()

    app = FastAPI(title="PixCake Bridge", lifespan=lifespan, docs_url=None, redoc_url=None)

    def authorize(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
        correct_user = secrets.compare_digest(credentials.username.encode(), b"admin")
        correct_pass = secrets.compare_digest(credentials.password.encode(), request.app.state.config.admin_password.encode())
        if not (correct_user and correct_pass):
            raise HTTPException(401, "登录失败", headers={"WWW-Authenticate": "Basic"})
        if request.method not in {"GET", "HEAD"}:
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host"):
                raise HTTPException(403, "请求来源无效")
            if request.headers.get("sec-fetch-site") == "cross-site":
                raise HTTPException(403, "禁止跨站操作")

    def view(engine):
        with engine.sessions() as s:
            projects = []
            configured = {c.event_id for c in engine.config.projects}
            for p in s.scalars(select(Project).where(Project.event_id.in_(configured))):
                photos = list(s.scalars(select(Photo).where(Photo.project_id == p.id).order_by(Photo.photo_id)))
                deliveries = list(s.scalars(select(Delivery).join(Photo).where(Photo.project_id == p.id)))
                summary = {
                    "客户已选": sum(x.selected for x in photos),
                    "RAW已匹配": sum(bool(x.raw_path) for x in photos),
                    "待精修": sum(bool(x.selected_path) and not x.delivery_hash for x in photos),
                    "已精修": len({x.photo_pk for x in deliveries}),
                    "已同步": sum(bool(x.delivery_hash) for x in photos),
                    "返修": sum(x.attempts > 0 for x in deliveries) - len({x.photo_pk for x in deliveries if x.attempts > 0}),
                    "取消待确认": sum(x.cancelled and bool(x.selected_path) for x in photos),
                    "异常": sum(bool(x.error) for x in photos) + sum(x.state in {"FAILED", "UNKNOWN"} for x in deliveries),
                }
                projects.append({"project": p, "photos": photos, "deliveries": deliveries, "summary": summary,
                    "errors": list(s.scalars(select(Error).where(Error.project_id == p.id, Error.resolved == False).order_by(Error.created.desc()).limit(30))),
                    "runs": list(s.scalars(select(SyncRun).where(SyncRun.project_id == p.id).order_by(SyncRun.id.desc()).limit(5)))})
            return projects

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(authorize)])
    def dashboard(request: Request):
        return templates.get_template("dashboard.html").render(projects=view(request.app.state.engine), stages=STAGES, stage_names=STAGE_NAMES)

    @app.get("/api/projects", dependencies=[Depends(authorize)])
    def projects(request: Request):
        return [{"event_id": x["project"].event_id, "name": x["project"].name, "stage": x["project"].stage, "connected": x["project"].connected, "summary": x["summary"]} for x in view(request.app.state.engine)]

    @app.post("/projects/{event_id}/{action}", dependencies=[Depends(authorize)])
    async def action(request: Request, event_id: int, action: str, stage: str = Form(""), confirm_unknown: str = Form("")):
        engine = request.app.state.engine
        if event_id not in {p.event_id for p in engine.config.projects}:
            raise HTTPException(404, "项目不存在")
        async with engine.lock:
            try:
                if action == "stage":
                    engine.set_stage(event_id, stage)
                elif action == "retry":
                    if confirm_unknown != "checked":
                        raise ValueError("请先核对 PicPeak 中结果未知的任务")
                    engine.retry(event_id)
                elif action not in {"sync", "rescan"}:
                    raise ValueError("操作不存在")
            except ValueError as exc:
                raise HTTPException(400, str(exc))
        if action in {"sync", "rescan", "retry"}:
            await engine.sync(event_id)
        return RedirectResponse("/", status_code=303)

    return app


app = create_app()
