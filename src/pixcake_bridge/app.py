import asyncio
import json
import os
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


def host_project_path(host_root, container_root, project_root):
    if not host_root:
        return None
    try:
        relative = Path(project_root).relative_to(Path(container_root))
    except ValueError:
        # Keep compatibility with manually configured legacy projects whose
        # work directory predates the dedicated delivery mount.
        relative = Path(project_root).name
    return Path(host_root) / relative


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
            # Watch every mounted delivery root. A project-specific bind can
            # live outside the default /delivery mount, and must be observed
            # without making the Camera tree writable.
            roots = list(dict.fromkeys(
                cfg.delivery_root_for(event_id)
                for event_id in ({p.event_id for p in cfg.projects} | set(cfg.project_delivery_mounts))
                if cfg.delivery_root_for(event_id).is_dir()
            ))
            if not roots and cfg.delivery_root.is_dir():
                roots = [cfg.delivery_root]
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
                    "已精修": len({x.photo_pk for x in deliveries if x.state == "SUCCESS"}),
                    "已同步": sum(bool(x.delivery_hash) for x in photos),
                    "返修": max(0, sum(x.state == "SUCCESS" for x in deliveries) - len({x.photo_pk for x in deliveries if x.state == "SUCCESS"})),
                    "取消待确认": sum(x.cancelled and bool(x.selected_path) for x in photos),
                    "异常": sum(bool(x.error) for x in photos) + sum(x.state in {"FAILED", "UNKNOWN"} for x in deliveries),
                }
                project_config = next((c for c in engine.config.projects if c.event_id == p.event_id), None)
                host_root = engine.config.delivery_host_root_for(p.event_id)
                delivery_path = None
                if project_config and host_root:
                    mount_root = engine.config.delivery_root_for(p.event_id)
                    delivery_path = str(host_project_path(host_root, mount_root, project_config.selected.parent))
                projects.append({"project": p, "config": project_config,
                    "delivery_host_root": host_root, "delivery_host_path": delivery_path,
                    "photos": photos, "deliveries": deliveries, "summary": summary,
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
            project_setup_ready=cfg.raw_root.is_dir() and (any(cfg.delivery_root_for(eid).is_dir() for eid in {p.event_id for p in cfg.projects}) if cfg.projects else cfg.delivery_root.is_dir()),
            delivery_host_root=cfg.delivery_host_root,
            setup_error=request.query_params.get("setup_error", ""),
        )

    @app.get("/api/projects", dependencies=[Depends(authorize)])
    def projects(request: Request):
        return [{"event_id": x["project"].event_id, "name": x["project"].name, "stage": x["project"].stage, "connected": x["project"].connected, "summary": x["summary"]} for x in view(request.app.state.engine)]

    @app.get("/api/projects/{event_id}/mount-status", dependencies=[Depends(authorize)])
    def project_mount_status(request: Request, event_id: int):
        cfg = request.app.state.config
        raw_subdir = request.query_params.get("raw_subdir", "").strip()
        relative = Path(raw_subdir)
        ready = False
        if (cfg.raw_host_root and raw_subdir and not relative.is_absolute()
                and relative.parts and ".." not in relative.parts):
            raw_path = cfg.raw_root / relative
            expected_host = cfg.raw_host_root / relative / "PixCakeDelivery"
            actual_host = cfg.delivery_host_root_for(event_id)
            no_symlink_components = not any(
                (cfg.raw_root / Path(*relative.parts[:index])).is_symlink()
                for index in range(1, len(relative.parts) + 1)
            )
            ready = (
                raw_path.is_dir()
                and not raw_path.is_symlink()
                and no_symlink_components
                and cfg.delivery_root_for(event_id).is_dir()
                and bool(actual_host)
                and os.path.normpath(str(expected_host)) == os.path.normpath(str(actual_host))
            )
        return {"writable_mount_ready": ready}

    # PicPeak's authenticated server-side proxy uses these endpoints to render
    # the photographer workflow in the PicPeak admin UI. They are protected by
    # the same Bridge credentials as its standalone dashboard; no Bridge
    # credential is ever sent to a customer browser.
    @app.get("/api/projects/{event_id}/detail", dependencies=[Depends(authorize)])
    def project_detail(request: Request, event_id: int):
        engine = request.app.state.engine
        if event_id not in {p.event_id for p in engine.config.projects}:
            raise HTTPException(404, "项目尚未绑定")
        entry = next((item for item in view(engine) if item["project"].event_id == event_id), None)
        if entry is None:
            raise HTTPException(404, "项目不存在")
        versions_by_photo = {}
        with engine.sessions() as session:
            deliveries = list(session.scalars(
                select(Delivery).join(Photo).where(Photo.project_id == entry["project"].id, Delivery.state == "SUCCESS")
            ))
            for delivery in deliveries:
                versions_by_photo[delivery.photo_pk] = versions_by_photo.get(delivery.photo_pk, 0) + 1
        project_cfg = next((item for item in engine.config.projects if item.event_id == event_id), None)
        delivery_host_root = engine.config.delivery_host_root_for(event_id)
        delivery_container_root = engine.config.delivery_root_for(event_id)
        photos = []
        for photo in entry["photos"]:
            version = versions_by_photo.get(photo.id, 0)
            photo_deliveries = [delivery for delivery in entry["deliveries"] if delivery.photo_pk == photo.id]
            latest_delivery = max(photo_deliveries, key=lambda delivery: delivery.updated, default=None)
            photos.append({
                "photo_id": photo.photo_id,
                "source_filename": photo.source_filename,
                "selected": bool(photo.selected),
                "selection_cancelled": bool(photo.cancelled),
                "added_during_editing": bool(photo.added_during_editing),
                "cancelled": bool(photo.cancelled),
                "raw_matched": bool(photo.raw_path),
                "ready_for_editing": bool(photo.selected_path),
                "current_version": version,
                "next_version": version + 1,
                "next_version_folder": str(
                    (host_project_path(delivery_host_root, delivery_container_root, project_cfg.selected.parent) / "04_FINAL" / f"V{version + 1}")
                    if delivery_host_root
                    else project_cfg.final / f"V{version + 1}"
                ),
                "delivered": version > 0,
                "error": bool(photo.error),
                "error_message": photo.error or (latest_delivery.error if latest_delivery else None),
                "delivery_state": latest_delivery.state if latest_delivery else None,
            })
        project = entry["project"]
        project_root = next((cfg.selected.parent for cfg in engine.config.projects if cfg.event_id == event_id), None)
        delivery_path = None
        if project_root is not None and delivery_host_root:
            delivery_path = str(host_project_path(delivery_host_root, delivery_container_root, project_root))
        return {
            "event_id": project.event_id,
            "name": project.name,
            "stage": project.stage,
            "connected": bool(project.connected),
            "delivery_path": delivery_path,
            "summary": entry["summary"],
            "photos": photos,
            "errors": [{"message": error.message, "created_at": error.created.isoformat() if error.created else None} for error in entry["errors"]],
        }

    @app.post("/api/projects/{event_id}/stage", dependencies=[Depends(authorize)])
    async def update_project_stage(request: Request, event_id: int):
        payload = await request.json()
        try:
            request.app.state.engine.set_stage(event_id, payload.get("stage", ""))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return {"success": True, "stage": payload["stage"]}

    @app.post("/api/projects/{event_id}/restore", dependencies=[Depends(authorize)])
    def restore_project_stage(request: Request, event_id: int):
        if event_id not in {p.event_id for p in request.app.state.config.projects}:
            raise HTTPException(404, "项目尚未绑定")
        try:
            stage = request.app.state.engine.restore_stage(event_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc))
        return {"success": True, "stage": stage}

    @app.post("/api/projects/{event_id}/photos/{photo_id}/version-folder", dependencies=[Depends(authorize)])
    async def prepare_version_folder(request: Request, event_id: int, photo_id: int):
        if event_id not in {p.event_id for p in request.app.state.config.projects}:
            raise HTTPException(404, "项目尚未绑定")
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        expected = payload.get("expected_current_version")
        try:
            return request.app.state.engine.prepare_next_version_folder(event_id, photo_id, expected)
        except ValueError as exc:
            status = 409 if "版本已更新" in str(exc) else 400
            raise HTTPException(status, str(exc))

    @app.post("/api/projects/{event_id}/photos/{photo_id}/withdraw", dependencies=[Depends(authorize)])
    async def withdraw_photo(request: Request, event_id: int, photo_id: int):
        if event_id not in {p.event_id for p in request.app.state.config.projects}:
            raise HTTPException(404, "项目尚未绑定")
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        if not isinstance(payload.get("delete_delivered"), bool):
            raise HTTPException(400, "必须明确选择是否删除已交付成片")
        try:
            return await request.app.state.engine.withdraw_photo(event_id, photo_id, payload["delete_delivered"])
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        except Exception as exc:
            raise HTTPException(503, f"撤回未完成：{type(exc).__name__}")

    @app.post("/api/projects/{event_id}/sync", dependencies=[Depends(authorize)])
    async def sync_project(request: Request, event_id: int):
        if event_id not in {p.event_id for p in request.app.state.config.projects}:
            raise HTTPException(404, "项目不存在")
        await request.app.state.engine.sync(event_id)
        return {"success": True}

    @app.post("/api/projects/{event_id}/rescan", dependencies=[Depends(authorize)])
    async def rescan_project(request: Request, event_id: int):
        if event_id not in {p.event_id for p in request.app.state.config.projects}:
            raise HTTPException(404, "项目不存在")
        await request.app.state.engine.sync(event_id)
        return {"success": True}

    @app.post("/api/projects/{event_id}/retry", dependencies=[Depends(authorize)])
    async def retry_project(request: Request, event_id: int):
        engine = request.app.state.engine
        if event_id not in {p.event_id for p in engine.config.projects}:
            raise HTTPException(404, "项目不存在")
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        with engine.sessions() as session:
            project = session.scalar(select(Project).where(Project.event_id == event_id))
            unknown = list(session.scalars(
                select(Delivery).join(Photo).where(Photo.project_id == project.id, Delivery.state == "UNKNOWN")
            ))
        if unknown and payload.get("confirm_unknown") is not True:
            raise HTTPException(409, detail={
                "error": "PicPeak 中核对这些照片的结果后，才能重试未知任务",
                "code": "UNKNOWN_CONFIRMATION_REQUIRED",
                "count": len(unknown),
            })
        engine.retry(event_id)
        await engine.sync(event_id)
        return {"success": True}

    @app.post("/projects", dependencies=[Depends(authorize)])
    async def add_project(
        request: Request,
        name: str = Form(...),
        event_id: int = Form(...),
        raw_subdir: str = Form(...),
        auto_mount: bool = Form(False),
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

        delivery_root = cfg.delivery_root_for(event_id)
        delivery_host_root = cfg.delivery_host_root_for(event_id)
        if cfg.raw_host_root or auto_mount:
            # New deployments use only project-scoped delivery mounts. The
            # Camera tree itself remains read-only; reject any mount that
            # points outside this project's PixCakeDelivery directory.
            expected_mount = Path(cfg.raw_host_root) / relative / "PixCakeDelivery" if cfg.raw_host_root else None
            actual_mount = Path(delivery_host_root) if delivery_host_root else None
            if not expected_mount or not actual_mount or os.path.normpath(str(expected_mount)) != os.path.normpath(str(actual_mount)):
                return setup_error("请先在 NAS Compose 中把此项目的 PixCakeDelivery 文件夹单独挂载为 Bridge 可写目录；Camera/RAW 挂载保持只读")
        if not delivery_root.is_dir() or delivery_root.is_symlink():
            return setup_error("此项目的 PixCakeDelivery 挂载不可用，请检查 NAS Compose 路径")

        slug = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "-", name).strip("-")[:48] or "project"
        # A project is already scoped to its own PixCakeDelivery mount. Put
        # workflow folders directly in that mount; repeating the event name
        # here created an unnecessary second project directory.
        project_root = delivery_root
        try:
            resolved_delivery = delivery_root.resolve(strict=True)
            resolved_project = project_root.resolve(strict=False)
            if project_root.is_symlink() or resolved_project != resolved_delivery:
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
