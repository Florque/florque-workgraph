"""florque-client: one client interface, two implementations (HTTP and in-process).

The HTTP client needs only httpx. The in-process client and ``FlorqueApp`` need the
``florque-client[local]`` extra and are imported lazily.
"""

from __future__ import annotations

from importlib import metadata
from typing import TYPE_CHECKING, Any

from florque_client.base import Client
from florque_client.config import Config, load_config
from florque_client.http import HttpClient

if TYPE_CHECKING:
    from florque_client.app import FlorqueApp, build_app
    from florque_client.local import LocalClient, local_principal

try:
    __version__ = metadata.version("florque-client")
except metadata.PackageNotFoundError:  # running from a source tree
    __version__ = "0.0.0"

_LAZY = {
    "FlorqueApp": "florque_client.app",
    "build_app": "florque_client.app",
    "LocalClient": "florque_client.local",
    "local_principal": "florque_client.local",
}


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        import importlib

        return getattr(importlib.import_module(_LAZY[name]), name)
    raise AttributeError(name)


def local_available() -> bool:
    try:
        import florque_graph_core  # noqa: F401
        import florque_signal_hub  # noqa: F401
        import florque_workgraph_domain  # noqa: F401
    except ImportError:
        return False
    return True


def client_from_config(cfg: Config) -> Client:
    if cfg.mode == "remote":
        return HttpClient(cfg.api_url, cfg.token)
    if not local_available():
        raise RuntimeError(
            "Local mode needs the engine (pip install 'florque-cli[local]'). "
            "For the hosted service run `fwg login --api-url <url>` or set FLORQUE_MODE=remote."
        )
    from florque_client.local import LocalClient

    return LocalClient.from_config(cfg)


__all__ = [
    "Client",
    "Config",
    "FlorqueApp",
    "HttpClient",
    "LocalClient",
    "__version__",
    "build_app",
    "client_from_config",
    "load_config",
    "local_available",
    "local_principal",
]
