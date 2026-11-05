"""Outcome-change events for alerts and agents (spec 6.7). Writes carry an origin tag to prevent loops."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from florque_signal_hub.store.repository import HubStore

ORIGIN = "hub"
Subscriber = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self, store: HubStore) -> None:
        self.store = store
        self._subs: list[Subscriber] = []

    def subscribe(self, fn: Subscriber) -> None:
        self._subs.append(fn)

    def publish(
        self, type: str, node_id: str | None, payload: dict[str, Any], origin: str = ORIGIN
    ) -> dict[str, Any]:
        evt = self.store.event_add(type, node_id, origin, payload)
        for fn in self._subs:
            if evt.get("origin") == ORIGIN and getattr(fn, "ignore_own", False):
                continue
            fn(evt)
        return evt
