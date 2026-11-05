"""Dedupe keys and similarity (spec 5.4)."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from rapidfuzz import fuzz


def normalize_title(title: str) -> str:
    t = unicodedata.normalize("NFKC", title).lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return " ".join(t.split())


def dedupe_key(cls: str, kind: str | None, scope_key: str | None, title: str) -> str:
    raw = "|".join([cls, kind or "", scope_key or "", normalize_title(title)])
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def similarity(a: str, b: str) -> float:
    return float(fuzz.ratio(normalize_title(a), normalize_title(b)))
