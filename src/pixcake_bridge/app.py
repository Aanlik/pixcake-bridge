import asyncio
import json
import re
import secrets
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode, urlparse

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from watchfiles import awatch

from .client import PicPeak
from .config import Config, ProjectConfig
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
            # Watch the delivery root recursively so projects added through
            # the dashboard are observed without restarting the container.
            roots = [cfg.delivery_root] if cfg.delivery_root.is_dir() else [p.final for p in cfg.projects]
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
                    "追加选片": sum(x.selected and x.added_during_editing for x in photos),
                    "RAW已匹配": sum(bool(x.raw_path) for x in photos),
                    "待精修": sum(bool(x.selected_path) and not x.delivery_hash for x in photos),
                    "已精修": len({x.photo_pk for x in deliveries}),
                    "已同步": sum(bool(x.delivery_hash) for x in photos),
                    "返修": sum(x.state == "SUCCESS" for x in deliveries) - len({x.photo_pk for x in deliveries if x.state == "SUCCESS"}),
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
        cfg = request.app.state.config
        return templates.get_template("dashboard.html").render(
            projects=view(request.app.state.engine), stages=STAGES, stage_names=STAGE_NAMES,
            project_setup_ready=cfg.raw_root.is_dir() and cfg.delivery_root.is_dir(),
            delivery_host_root=cfg.delivery_host_root,
            setup_error=request.query_params.get("setup_error", ""),
        )

    @app.get("/api/projects", dependencies=[Depends(authorize)])
    def projects(request: Request):
        return [{"event_id": x["project"].event_id, "name": x["project"].name, "stage": x["project"].stage, "connected": x["project"].connected, "summary": x["summary"]} for x in view(request.app.state.engine)]

    @app.post("/projects", dependencies=[Depends(authorize)])
    async def add_project(
        request: Request,
        name: str = Form(...),
        event_id: int = Form(...),
        raw_subdir: str = Form(...),
    ):
        cfg = request.app.state.config
        engine = request.app.state.engine
        def setup_error(message):
            return RedirectResponse("/?" + urlencode({"setup_error": message}), status_code=303)

        name = name.strip()
        if (not cfg.raw_root.is_dir() or cfg.raw_root.is_symlink() or
                not cfg.delivery_root.is_dir() or cfg.delivery_root.is_symlink()):
            return setup_error("未挂载 RAW 源目录或交付目录，请检查 NAS Compose 挂载")
        if not name or len(name) > 120 or event_id < 1:
            return setup_error("项目名称或 PicPeak 项目编号无效")
        if any(project.event_id == event_id for project in cfg.projects):
            return setup_error("这个 PicPeak 项目已经绑定")

        relative = Path(raw_subdir.strip() or ".")
        if relative.is_absolute() or any(part in {"..", ""} for part in relative.parts):
            return setup_error("RAW 子目录必须是 Camera 内的相对路径")
        raw = cfg.raw_root / relative
        try:
            if raw.is_symlink() or any((cfg.raw_root / Path(*relative.parts[:i])).is_symlink() for i in range(1, len(relative.parts) + 1)):
                raise ValueError("RAW 路径不能经过符号链接")
            resolved_raw = raw.resolve(strict=True)
            resolved_root = cfg.raw_root.resolve(strict=True)
            if resolved_root not in resolved_raw.parents and resolved_raw != resolved_root:
                raise ValueError("RAW 目录必须位于已挂载的 Camera 内")
            if not resolved_raw.is_dir():
                raise ValueError("RAW 路径不是文件夹")
        except (OSError, ValueError) as exc:
            return setup_error(str(exc))

        slug = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "-", name).strip("-")[:48] or "project"
        project_root = cfg.delivery_root / f"event-{event_id}-{slug}"
        try:
            resolved_delivery = cfg.delivery_root.resolve(strict=True)
            resolved_project = project_root.resolve(strict=False)
            if project_root.is_symlink() or (resolved_delivery not in resolved_project.parents):
                raise ValueError("交付目录路径不能经过符号链接或越出交付根目录")
        except OSError as exc:
            return setup_error("无法读取 NAS 交付目录")
        except ValueError as exc:
            return setup_error(str(exc))
        project = ProjectConfig(
            name=name,
            event_id=event_id,
            raw=resolved_raw,
            selected=project_root / "03_SELECTED_RAW",
            final=project_root / "04_FINAL",
            history=project_root / "05_HISTORY",
        )
        try:
            # Verify the token can see this PicPeak event before persisting a
            # binding that would otherwise remain permanently disconnected.
            await engine.client.photos(event_id)
            project.validate()
            current = list(cfg.projects)
            current.append(project)
            payload = [
                {"name": p.name, "event_id": p.event_id, "raw": str(p.raw), "selected": str(p.selected), "final": str(p.final), "history": str(p.history)}
                for p in current
            ]
            cfg.projects_file.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=cfg.projects_file.parent, delete=False) as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
                file.write("\n")
                tmp = Path(file.name)
            tmp.replace(cfg.projects_file)
            cfg.projects = current
            with engine.sessions() as session:
                if session.scalar(select(Project).where(Project.event_id == event_id)) is None:
                    session.add(Project(event_id=event_id, name=name))
                session.commit()
        except Exception as exc:
            return setup_error(f"绑定失败：请确认 PicPeak API 连接、目录权限和项目编号（{type(exc).__name__}）")
        return RedirectResponse("/", status_code=303)

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
