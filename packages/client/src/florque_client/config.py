"""Configuration with precedence: flags > environment > .florque/config.yaml > user config (spec 8).

Tokens are read from the environment (or flags) only, never from a config file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import yaml

ENV = {
    "mode": "FLORQUE_MODE",
    "api_url": "FLORQUE_API_URL",
    "token": "FLORQUE_TOKEN",
    "project": "FLORQUE_PROJECT",
    "actor_id": "FLORQUE_ACTOR",
    "agent": "FLORQUE_AGENT",
    "store": "FLORQUE_STORE",
    "data_file": "FLORQUE_DATA_FILE",
    "hub_db": "FLORQUE_HUB_DB",
    "neo4j_uri": "NEO4J_URI",
    "neo4j_user": "NEO4J_USER",
    "neo4j_password": "NEO4J_PASSWORD",
    "neo4j_database": "NEO4J_DATABASE",
}
FILE_FORBIDDEN = {"token", "neo4j_password"}


@dataclass
class Config:
    mode: str = "local"  # local | remote
    api_url: str = "http://127.0.0.1:8000"
    token: str | None = None
    project: str | None = None
    actor_id: str | None = None
    agent: bool = False
    store: str = "neo4j"  # graph store in local mode: neo4j | file | memory
    data_file: str = ".florque/graph.json"
    hub_db: str = ".florque/hub.sqlite"
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None
    neo4j_database: str | None = None
    config_dir: str | None = None

    def resolved_actor(self) -> str:
        return self.actor_id or os.environ.get("USER") or "local"


def _find_project_config(start: Path) -> Path | None:
    for d in [start, *start.parents]:
        p = d / ".florque" / "config.yaml"
        if p.is_file():
            return p
    return None


def _user_config() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "florque" / "config.yaml"


def _read(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return {k: v for k, v in data.items() if k not in FILE_FORBIDDEN}


def _bool(v: Any) -> bool:
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")


def load_config(flags: dict[str, Any] | None = None, cwd: Path | None = None) -> Config:
    cwd = cwd or Path.cwd()
    merged: dict[str, Any] = {}
    merged.update(_read(_user_config()))
    project_file = _find_project_config(cwd)
    merged.update(_read(project_file))
    for key, var in ENV.items():
        if os.environ.get(var):
            merged[key] = os.environ[var]
    merged.update({k: v for k, v in (flags or {}).items() if v is not None})
    known = {f.name for f in fields(Config)}
    cfg = Config(**{k: v for k, v in merged.items() if k in known})
    cfg.agent = _bool(cfg.agent)
    base = project_file.parent.parent if project_file else cwd
    cfg.config_dir = str(base / ".florque")
    for attr in ("data_file", "hub_db"):
        p = Path(getattr(cfg, attr))
        if not p.is_absolute():
            setattr(cfg, attr, str(base / p))
    return cfg
