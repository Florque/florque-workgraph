"""Deterministic expectation evaluation (spec 6.3). No I/O; the hub feeds it points."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import fmean
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class EvaluatorConfig:
    no_data_days: int = 7
    grace_days: int = 2
    min_points: int = 1


@dataclass(frozen=True)
class Point:
    observed_at: datetime
    value: float
    period: str | None = None


@dataclass(frozen=True)
class Evaluation:
    outcome: str
    health: str
    last_value: float | None
    last_observed_at: datetime | None
    points: int
    reason: str

    def fields(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "health": self.health,
            "last_value": self.last_value,
            "last_observed_at": self.last_observed_at,
        }


def satisfies(value: float, comparator: str, target: float, upper: float | None = None) -> bool:
    if comparator == ">=":
        return value >= target
    if comparator == "<=":
        return value <= target
    if comparator == "between":
        hi = upper if upper is not None else target
        return min(target, hi) <= value <= max(target, hi)
    raise ValueError(f"unknown comparator {comparator!r}")


def reduce(points: list[Point], reducer: str) -> float:
    values = [p.value for p in points]
    if reducer == "last":
        return values[-1]
    if reducer == "mean":
        return fmean(values)
    if reducer == "max":
        return max(values)
    raise ValueError(f"reducer {reducer!r} does not produce a value")


def _projection(points: list[Point], end: date, tz: ZoneInfo) -> float:
    """Least-squares linear projection of the series to the window end."""
    if len(points) < 2:
        return points[-1].value
    t0 = points[0].observed_at
    xs = [(p.observed_at - t0).total_seconds() / 86400 for p in points]
    ys = [p.value for p in points]
    mx, my = fmean(xs), fmean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return ys[-1]
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / den
    end_dt = datetime.combine(end, datetime.max.time(), tz)
    x_end = (end_dt - t0).total_seconds() / 86400
    return my + slope * (x_end - mx)


def evaluate(
    exp: dict[str, Any],
    points: list[Point],
    today: date,
    tz: ZoneInfo,
    cfg: EvaluatorConfig = EvaluatorConfig(),
) -> Evaluation:
    comparator = exp["comparator"]
    target = float(exp["target_value"])
    upper = exp.get("target_upper")
    reducer = exp["reducer"]
    ws, we = date.fromisoformat(exp["window_start"]), date.fromisoformat(exp["window_end"])

    pts = sorted(
        (p for p in points if ws <= p.observed_at.astimezone(tz).date() <= we),
        key=lambda p: p.observed_at,
    )
    last = pts[-1] if pts else None
    finalize = today > we + timedelta(days=cfg.grace_days)

    def ok(v: float) -> bool:
        return satisfies(v, comparator, target, upper)

    # outcome
    outcome, reason = "pending", "window open"
    if pts:
        if reducer == "all_points" and not all(ok(p.value) for p in pts):
            outcome, reason = "failed", "a point missed the target"
        elif reducer == "max" and comparator == ">=" and ok(max(p.value for p in pts)):
            outcome, reason = "succeeded", "maximum reached the target"
        elif reducer == "max" and comparator == "<=" and not ok(max(p.value for p in pts)):
            outcome, reason = "failed", "maximum exceeded the target"
    if outcome == "pending" and finalize:
        if len(pts) < cfg.min_points:
            outcome, reason = "expired", f"window closed with {len(pts)} point(s)"
        elif reducer == "all_points":
            outcome, reason = "succeeded", "every point met the target"
        else:
            v = reduce(pts, reducer)
            outcome = "succeeded" if ok(v) else "failed"
            reason = f"{reducer}={v:g} vs {comparator} {target:g}"
    elif outcome == "pending" and today > we:
        reason = f"grace period ({cfg.grace_days}d) before finalizing"

    # health
    if (
        last is None
        or today <= we
        and (today - last.observed_at.astimezone(tz).date()).days >= cfg.no_data_days
    ):
        health = "no_data"
    elif outcome == "succeeded":
        health = "on_track"
    elif outcome in ("failed", "expired"):
        health = "at_risk"
    elif reducer == "all_points":
        health = "on_track"
    elif reducer == "max":
        health = (
            "on_track"
            if ok(_projection(pts, we, tz)) or ok(max(p.value for p in pts))
            else "at_risk"
        )
    elif reducer == "mean":
        health = (
            "on_track"
            if ok(fmean(p.value for p in pts)) or ok(_projection(pts, we, tz))
            else "at_risk"
        )
    else:
        health = "on_track" if ok(_projection(pts, we, tz)) else "at_risk"

    return Evaluation(
        outcome=outcome,
        health=health,
        last_value=last.value if last else None,
        last_observed_at=last.observed_at if last else None,
        points=len(pts),
        reason=reason,
    )
