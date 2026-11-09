"""Configuration with precedence: flags > environment > .florque/config.yaml > user config (spec 8).

Secrets never come from config files. A token comes from FLORQUE_TOKEN, or from the
credentials file that ``fwg register`` / ``fwg login`` write (0600, outside the repository:
``~/.config/florque/credentials.json`` or FLORQUE_CREDENTIALS). When credentials exist and
no mode is configured, the CLI talks to the default server (remote mode).
"""

from __future__ import annotations

import json
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
    "ontology_db": "FLORQUE_ONTOLOGY_DB",
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
    ontology_db: str = ".florque/ontologies.sqlite"
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


# ---------------------------------------------------------------- credentials


def credentials_path() -> Path:
    env = os.environ.get("FLORQUE_CREDENTIALS")
    if env:
        return Path(env)
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "florque" / "credentials.json"


def read_credentials() -> dict[str, Any]:
    try:
        data = json.loads(credentials_path().read_text())
    except (OSError, ValueError):
        return {"default": None, "servers": {}}
    data.setdefault("servers", {})
    data.setdefault("default", None)
    return data  # type: ignore[no-any-return]


def _write_credentials(data: dict[str, Any]) -> Path:
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    return path


def save_credentials(api_url: str, entry: dict[str, Any], make_default: bool = True) -> Path:
    data = read_credentials()
    data["servers"][api_url.rstrip("/")] = entry
    if make_default or not data.get("default"):
        data["default"] = api_url.rstrip("/")
    return _write_credentials(data)


def remove_credentials(api_url: str) -> bool:
    data = read_credentials()
    key = api_url.rstrip("/")
    if key not in data["servers"]:
        return False
    del data["servers"][key]
    if data.get("default") == key:
        data["default"] = next(iter(data["servers"]), None)
    _write_credentials(data)
    return True


def project_config_path(cwd: Path | None = None) -> Path:
    """The .florque/config.yaml that applies here (nearest upward), or a new one in cwd."""
    cwd = cwd or Path.cwd()
    return _find_project_config(cwd) or cwd / ".florque" / "config.yaml"


def update_project_config(
    values: dict[str, Any], remove: tuple[str, ...] = (), cwd: Path | None = None
) -> Path:
    """Set or remove keys in the project config, keeping the others. Secrets are refused."""
    bad = FILE_FORBIDDEN & set(values)
    if bad:
        raise ValueError(f"{', '.join(sorted(bad))} must not be stored in a config file")
    path = project_config_path(cwd)
    data: dict[str, Any] = {}
    if path.is_file():
        data = yaml.safe_load(path.read_text()) or {}
    data.update(values)
    for key in remove:
        data.pop(key, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


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
    creds = read_credentials()
    if "mode" not in merged and creds.get("default"):
        merged["mode"] = "remote"
        merged.setdefault("api_url", creds["default"])
    if merged.get("mode") == "remote" and not merged.get("token"):
        url = str(merged.get("api_url") or Config.api_url).rstrip("/")
        entry = creds["servers"].get(url)
        if entry and entry.get("token"):
            merged["token"] = entry["token"]
    known = {f.name for f in fields(Config)}
    cfg = Config(**{k: v for k, v in merged.items() if k in known})
    cfg.agent = _bool(cfg.agent)
    base = project_file.parent.parent if project_file else cwd
    cfg.config_dir = str(base / ".florque")
    for attr in ("data_file", "hub_db", "ontology_db"):
        p = Path(getattr(cfg, attr))
        if str(p) != ":memory:" and not p.is_absolute():
            setattr(cfg, attr, str(base / p))
    return cfg
