"""florque-client: one client interface, two implementations (in-process and HTTP)."""

from florque_client.app import FlorqueApp, build_app
from florque_client.base import Client
from florque_client.config import Config, load_config
from florque_client.http import HttpClient
from florque_client.local import LocalClient, local_principal


def client_from_config(cfg: Config) -> Client:
    if cfg.mode == "remote":
        return HttpClient(cfg.api_url, cfg.token)
    return LocalClient.from_config(cfg)


__all__ = [
    "Client",
    "Config",
    "FlorqueApp",
    "HttpClient",
    "LocalClient",
    "build_app",
    "client_from_config",
    "load_config",
    "local_principal",
]
