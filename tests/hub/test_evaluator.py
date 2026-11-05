from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from florque_signal_hub.evaluator import EvaluatorConfig, Point, evaluate, satisfies

UTCZ = ZoneInfo("UTC")
EXP = {
    "comparator": ">=",
    "target_value": 100,
    "reducer": "last",
    "window_start": "2026-11-01",
    "window_end": "2026-11-30",
}


def pts(*pairs):
    return [Point(datetime(2026, 11, d, 12, tzinfo=UTC), float(v)) for d, v in pairs]


@pytest.mark.parametrize(
    "v,cmp,t,up,ok",
    [
        (5, ">=", 5, None, True),
        (4, ">=", 5, None, False),
        (5, "<=", 5, None, True),
        (3, "between", 2, 4, True),
        (5, "between", 2, 4, False),
    ],
)
def test_satisfies(v, cmp, t, up, ok):
    assert satisfies(v, cmp, t, up) is ok


def test_pending_while_open():
    ev = evaluate(EXP, pts((2, 50), (9, 80)), date(2026, 11, 10), UTCZ)
    assert ev.outcome == "pending" and ev.last_value == 80


def test_grace_then_final():
    p = pts((2, 50), (29, 120))
    assert evaluate(EXP, p, date(2026, 12, 1), UTCZ).outcome == "pending"  # inside the grace period
    assert evaluate(EXP, p, date(2026, 12, 3), UTCZ).outcome == "succeeded"
    assert evaluate(EXP, pts((29, 90)), date(2026, 12, 3), UTCZ).outcome == "failed"


def test_expired_is_not_failure():
    ev = evaluate(EXP, [], date(2026, 12, 5), UTCZ)
    assert ev.outcome == "expired" and ev.health == "no_data"
    ev = evaluate(EXP, pts((5, 200)), date(2026, 12, 5), UTCZ, EvaluatorConfig(min_points=3))
    assert ev.outcome == "expired"


def test_points_outside_window_ignored():
    p = [Point(datetime(2026, 10, 31, 12, tzinfo=UTC), 500.0)]
    assert evaluate(EXP, p, date(2026, 12, 5), UTCZ).outcome == "expired"


def test_window_uses_project_time_zone():
    # 23:30 UTC on Oct 31 is Nov 1 in Tokyo
    p = [Point(datetime(2026, 10, 31, 23, 30, tzinfo=UTC), 150.0)]
    assert evaluate(EXP, p, date(2026, 12, 5), ZoneInfo("Asia/Tokyo")).outcome == "succeeded"
    assert evaluate(EXP, p, date(2026, 12, 5), UTCZ).outcome == "expired"


def test_reducers():
    p = pts((2, 50), (10, 150), (20, 90))
    today = date(2026, 12, 10)
    assert evaluate({**EXP, "reducer": "last"}, p, today, UTCZ).outcome == "failed"
    assert evaluate({**EXP, "reducer": "max"}, p, today, UTCZ).outcome == "succeeded"
    assert (
        evaluate({**EXP, "reducer": "mean", "target_value": 96}, p, today, UTCZ).outcome
        == "succeeded"
    )
    assert (
        evaluate({**EXP, "reducer": "all_points", "target_value": 40}, p, today, UTCZ).outcome
        == "succeeded"
    )


def test_early_decisions():
    open_day = date(2026, 11, 21)
    assert (
        evaluate({**EXP, "reducer": "max"}, pts((10, 150)), open_day, UTCZ).outcome == "succeeded"
    )
    assert (
        evaluate({**EXP, "reducer": "all_points"}, pts((2, 150), (10, 20)), open_day, UTCZ).outcome
        == "failed"
    )


def test_health():
    today = date(2026, 11, 20)
    rising = pts((2, 10), (10, 50), (18, 90))  # projects past 100 by Nov 30
    assert evaluate(EXP, rising, today, UTCZ).health == "on_track"
    flat = pts((2, 10), (10, 11), (18, 12))
    assert evaluate(EXP, flat, today, UTCZ).health == "at_risk"
    stale = pts((2, 10))
    assert evaluate(EXP, stale, today, UTCZ).health == "no_data"


def test_deterministic():
    p = pts((2, 50), (9, 80))
    assert evaluate(EXP, p, date(2026, 11, 10), UTCZ) == evaluate(
        EXP, list(reversed(p)), date(2026, 11, 10), UTCZ
    )
