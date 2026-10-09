import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class ProjectConfig:
    name: str
    event_id: int
    raw: Path
    selected: Path
    final: Path
    history: Path

    def validate(self):
        if self.event_id < 1 or not self.name.strip():
            raise ValueError("项目名称和 event_id 无效")
        paths = [p.resolve() for p in (self.raw, self.selected, self.final, self.history)]
        for i, a in enumerate(paths):
            for b in paths[i + 1:]:
                if a == b or a in b.parents or b in a.parents:
                    raise ValueError("RAW、待精修、成片、历史目录必须互相独立")
        if not self.raw.is_dir() or self.raw.is_symlink():
            raise ValueError(f"RAW 目录不存在或为符号链接: {self.raw}")
        for p in (self.selected, self.final, self.history):
            if p.is_symlink():
                raise ValueError("不能使用符号链接目录")
            p.mkdir(parents=True, exist_ok=True)


@dataclass
class Config:
    base_url: str = "http://picpeak:3000"
    token: str = ""
    database_url: str = "sqlite:////data/bridge.db"
    admin_password: str = ""
    poll_seconds: float = 30
    stable_seconds: float = 10
    max_bytes: int = 100 * 1024 * 1024
    history_keep: int = 3
    materialize_mode: str = "auto"
    projects: list[ProjectConfig] = field(default_factory=list)
    projects_file: Path = Path("/config/projects.json")
    raw_root: Path = Path("/external-media/Camera")
    raw_host_root: Path | None = None
    delivery_root: Path = Path("/delivery")
    delivery_host_root: str = ""
    project_delivery_mounts: dict[int, dict[str, str]] = field(default_factory=dict)

    def delivery_root_for(self, event_id: int) -> Path:
        mount = self.project_delivery_mounts.get(int(event_id))
        return Path(mount["container"]) if mount else self.delivery_root

    def delivery_host_root_for(self, event_id: int) -> str:
        mount = self.project_delivery_mounts.get(int(event_id))
        return mount["host"] if mount else self.delivery_host_root

    def migrate_legacy_delivery_layout(self):
        """Move the old per-project child folders into their scoped mount.

        Each mount already represents one project. The previous layout added
        ``event-ID-name`` below it, so migrate only that exact legacy shape and
        refuse to overwrite any non-empty destination.
        """
        changed = False
        for project in self.projects:
            root = self.delivery_root_for(project.event_id)
            legacy = project.selected.parent
            if legacy == root or legacy.is_symlink() or root.is_symlink():
                continue
            try:
                is_legacy = (
                    legacy.parent.resolve() == root.resolve() and
                    legacy.name.startswith(f"event-{project.event_id}-")
                )
            except OSError:
                is_legacy = False
            if not is_legacy:
                continue

            names = ("03_SELECTED_RAW", "04_FINAL", "05_HISTORY")
            moves = [(legacy / name, root / name) for name in names]
            for source, destination in moves:
                if source.is_symlink() or destination.is_symlink():
                    raise ValueError("旧交付目录中存在符号链接，已停止自动整理")
                if source.exists() and destination.exists():
                    source_has_data = any(source.iterdir()) if source.is_dir() else True
                    destination_has_data = any(destination.iterdir()) if destination.is_dir() else True
                    if source_has_data and destination_has_data:
                        raise ValueError(f"新旧交付目录均有文件，需先人工检查冲突：{name}")
            for source, destination in moves:
                if not source.exists():
                    continue
                if destination.exists():
                    if not any(destination.iterdir()):
                        destination.rmdir()
                    else:
                        source.rmdir()
                        continue
                source.rename(destination)
            try:
                legacy.rmdir()
            except OSError:
                pass
            project.selected = root / "03_SELECTED_RAW"
            project.final = root / "04_FINAL"
            project.history = root / "05_HISTORY"
            changed = True

        if changed:
            self.projects_file.parent.mkdir(parents=True, exist_ok=True)
            payload = [
                {"name": p.name, "event_id": p.event_id, "raw": str(p.raw),
                 "selected": str(p.selected), "final": str(p.final), "history": str(p.history)}
                for p in self.projects
            ]
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.projects_file.parent, delete=False) as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
                file.write("\n")
                temporary = Path(file.name)
            temporary.replace(self.projects_file)

    @classmethod
    def load(cls):
        projects_file = Path(os.getenv("PROJECTS_FILE", "/config/projects.json"))
        projects = json.loads(projects_file.read_text())
        raw_mounts = json.loads(os.getenv("PROJECT_DELIVERY_MOUNTS", "{}"))
        mounts = {}
        for key, mount in raw_mounts.items():
            event_id = int(key)
            container = str(mount.get("container", ""))
            host = str(mount.get("host", ""))
            if event_id < 1 or not Path(container).is_absolute() or not Path(host).is_absolute():
                raise ValueError("项目交付挂载必须使用正数项目编号和绝对路径")
            mounts[event_id] = {"container": container, "host": host}
        cfg = cls(
            base_url=os.getenv("PICPEAK_URL", "http://picpeak:3000").rstrip("/"),
            token=os.getenv("PICPEAK_TOKEN", ""),
            database_url=os.getenv("DATABASE_URL", "sqlite:////data/bridge.db"),
            admin_password=os.getenv("BRIDGE_ADMIN_PASSWORD", ""),
            poll_seconds=float(os.getenv("POLL_SECONDS", "30")),
            stable_seconds=float(os.getenv("STABLE_SECONDS", "10")),
            max_bytes=int(os.getenv("MAX_FINAL_BYTES", str(100 * 1024 * 1024))),
            history_keep=int(os.getenv("HISTORY_KEEP", "3")),
            materialize_mode=os.getenv("RAW_MATERIALIZE_MODE", "auto"),
            projects=[ProjectConfig(**{**p, **{k: Path(p[k]) for k in ("raw", "selected", "final", "history")}}) for p in projects],
            projects_file=projects_file,
            raw_root=Path(os.getenv("RAW_ROOT", "/external-media/Camera")),
            raw_host_root=Path(os.getenv("RAW_HOST_ROOT")) if os.getenv("RAW_HOST_ROOT") else None,
            delivery_root=Path(os.getenv("DELIVERY_ROOT", "/delivery")),
            delivery_host_root=os.getenv("DELIVERY_HOST_ROOT", ""),
            project_delivery_mounts=mounts,
        )
        cfg.migrate_legacy_delivery_layout()
        if not cfg.token.startswith("pp_live_") or len(cfg.admin_password) < 12:
            raise ValueError("请配置 Public API Token 和至少 12 位的 Bridge 管理密码")
        url = urlparse(cfg.base_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.query or url.fragment:
            raise ValueError("PICPEAK_URL 无效")
        if cfg.poll_seconds < 1 or cfg.stable_seconds < 1 or cfg.history_keep < 1 or cfg.max_bytes < 1 or cfg.materialize_mode not in {"auto", "copy"}:
            raise ValueError("同步参数无效")
        if len({p.event_id for p in cfg.projects}) != len(cfg.projects):
            raise ValueError("一个 PicPeak 画廊只能绑定一个项目")
        for p in cfg.projects:
            p.validate()
        return cfg
