import json
import os
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
    unknown_seconds: float = 120
    max_bytes: int = 100 * 1024 * 1024
    history_keep: int = 3
    materialize_mode: str = "auto"
    projects: list[ProjectConfig] = field(default_factory=list)

    @classmethod
    def load(cls):
        projects = json.loads(Path(os.getenv("PROJECTS_FILE", "/config/projects.json")).read_text())
        cfg = cls(
            base_url=os.getenv("PICPEAK_URL", "http://picpeak:3000").rstrip("/"),
            token=os.getenv("PICPEAK_TOKEN", ""),
            database_url=os.getenv("DATABASE_URL", "sqlite:////data/bridge.db"),
            admin_password=os.getenv("BRIDGE_ADMIN_PASSWORD", ""),
            poll_seconds=float(os.getenv("POLL_SECONDS", "30")),
            stable_seconds=float(os.getenv("STABLE_SECONDS", "10")),
            unknown_seconds=float(os.getenv("UNKNOWN_SECONDS", "120")),
            max_bytes=int(os.getenv("MAX_FINAL_BYTES", str(100 * 1024 * 1024))),
            history_keep=int(os.getenv("HISTORY_KEEP", "3")),
            materialize_mode=os.getenv("RAW_MATERIALIZE_MODE", "auto"),
            projects=[ProjectConfig(**{**p, **{k: Path(p[k]) for k in ("raw", "selected", "final", "history")}}) for p in projects],
        )
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

