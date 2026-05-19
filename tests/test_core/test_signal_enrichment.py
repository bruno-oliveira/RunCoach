"""Tests for P1 §2.2 — quality drift modifier and race-effort cap."""

import uuid
from datetime import datetime, timedelta, timezone

from app.contexts.plan.adaptation.signal_computer import (
    compute_adjustment_signals,
    _compute_quality_drift,
    _count_recent_race_efforts,
)


def _today():
    return datetime.now(timezone.utc).replace(tzinfo=None).date()


def _uid():
    return str(uuid.uuid4())


class _MockRun:
    def __init__(
        self,
        wtype="easy",
        dist=8.0,
        effort=5.0,
        date=None,
        effort_quality_score=None,
        effort_class=None,
        daily_workout_id=None,
    ):
        self.id = _uid()
        self.workout_type = wtype
        self.distance_km = dist
        self.perceived_effort = effort
        self.date = date or _today()
        self.effort_quality_score = effort_quality_score
        self.effort_class = effort_class
        self.daily_workout_id = daily_workout_id


class _MockWorkout:
    def __init__(self, wid=None, wtype="easy", dist=8.0):
        self.id = wid or _uid()
        self.workout_type = wtype
        self.distance_km = dist
        self.baseline_distance_km = dist


class _MockDB:
    def __init__(self, completed_ids):
        self._ids = completed_ids

    def query(self, *_):
        class _Q:
            def __init__(self, ids):
                self._ids = ids
            def filter(self, *_):
                return self
            def all(self):
                return [(i,) for i in self._ids]
        return _Q(self._ids)


def _build_planned(workouts, today):
    return [(w, today) for w in workouts]


def _recency_one(_d):
    return 1.0


class TestQualityDriftHelper:
    def test_returns_none_when_fewer_than_four_scores(self):
        today = _today()
        runs = [_MockRun(effort_quality_score=80, date=today) for _ in range(3)]
        delta, modifier = _compute_quality_drift(runs, today)
        assert delta is None
        assert modifier == 0.0

    def test_negative_drift_returns_minus_two_pct(self):
        today = _today()
        runs = [
            _MockRun(effort_quality_score=90, date=today - timedelta(days=8)),
            _MockRun(effort_quality_score=88, date=today - timedelta(days=7)),
            _MockRun(effort_quality_score=85, date=today - timedelta(days=6)),
            _MockRun(effort_quality_score=86, date=today - timedelta(days=5)),
            _MockRun(effort_quality_score=70, date=today - timedelta(days=3)),
            _MockRun(effort_quality_score=68, date=today - timedelta(days=2)),
            _MockRun(effort_quality_score=65, date=today - timedelta(days=1)),
            _MockRun(effort_quality_score=66, date=today),
        ]
        delta, modifier = _compute_quality_drift(runs, today)
        assert delta is not None
        assert delta < -10
        assert modifier == -0.02

    def test_positive_drift_returns_plus_two_pct(self):
        today = _today()
        runs = [
            _MockRun(effort_quality_score=60, date=today - timedelta(days=8)),
            _MockRun(effort_quality_score=62, date=today - timedelta(days=7)),
            _MockRun(effort_quality_score=64, date=today - timedelta(days=6)),
            _MockRun(effort_quality_score=63, date=today - timedelta(days=5)),
            _MockRun(effort_quality_score=80, date=today - timedelta(days=3)),
            _MockRun(effort_quality_score=82, date=today - timedelta(days=2)),
            _MockRun(effort_quality_score=85, date=today - timedelta(days=1)),
            _MockRun(effort_quality_score=83, date=today),
        ]
        delta, modifier = _compute_quality_drift(runs, today)
        assert delta is not None
        assert delta > 10
        assert modifier == 0.02

    def test_flat_drift_returns_zero(self):
        today = _today()
        runs = [
            _MockRun(effort_quality_score=75, date=today - timedelta(days=i))
            for i in range(8)
        ]
        delta, modifier = _compute_quality_drift(runs, today)
        assert delta == 0.0
        assert modifier == 0.0


class TestRaceEffortCount:
    def test_no_race_efforts(self):
        today = _today()
        runs = [_MockRun(effort_class="easy_aerobic", date=today) for _ in range(5)]
        assert _count_recent_race_efforts(runs, today) == 0

    def test_one_race_effort_in_14_days(self):
        today = _today()
        runs = [
            _MockRun(effort_class="race_effort", date=today - timedelta(days=5)),
            _MockRun(effort_class="easy_aerobic", date=today),
        ]
        assert _count_recent_race_efforts(runs, today) == 1

    def test_race_effort_older_than_14_days_ignored(self):
        today = _today()
        runs = [
            _MockRun(effort_class="race_effort", date=today - timedelta(days=20)),
            _MockRun(effort_class="race_effort", date=today - timedelta(days=5)),
        ]
        assert _count_recent_race_efforts(runs, today) == 1


class _MockReadinessLog:
    def __init__(self, score):
        self.score = score


class TestReadinessSignal:
    def _build(self, readiness_logs):
        today = _today()
        runs = [_MockRun(wtype="easy") for _ in range(3)]
        planned = _build_planned(
            [_MockWorkout(wtype="easy") for _ in runs], today
        )
        for r, (w, _) in zip(runs, planned):
            r.daily_workout_id = w.id
        ids = {w.id for w, _ in planned}
        return compute_adjustment_signals(
            runs, planned, ids, today, "plan1",
            _MockDB([w.id for w, _ in planned]),
            _recency_one,
            current_phase="build",
            readiness_logs=readiness_logs,
        )

    def test_low_scores_reduce_multiplier(self):
        low = [_MockReadinessLog(30) for _ in range(3)]
        signals = self._build(low)
        assert signals["readiness_log_count"] == 3
        # readiness_factor: 0.92 + 0.30 * 0.13 = 0.959
        assert signals["readiness_factor"] < 1.0
        assert signals["readiness_weight"] > 0

    def test_high_scores_boost_multiplier(self):
        high = [_MockReadinessLog(90) for _ in range(3)]
        signals = self._build(high)
        assert signals["readiness_log_count"] == 3
        # readiness_factor: 0.92 + 0.90 * 0.13 = 1.037
        assert signals["readiness_factor"] > 1.0

    def test_insufficient_logs_zeros_weight(self):
        signals = self._build([_MockReadinessLog(80), _MockReadinessLog(70)])
        assert signals["readiness_log_count"] == 2
        assert signals["readiness_factor"] == 1.0
        assert signals["readiness_weight"] == 0.0

    def test_no_logs_zeros_weight(self):
        signals = self._build(None)
        assert signals["readiness_log_count"] == 0
        assert signals["readiness_weight"] == 0.0


class TestTrainingLoadSignal:
    def _build(self, training_load, current_phase="build", history=None):
        today = _today()
        runs = [_MockRun(wtype="easy") for _ in range(3)]
        planned = _build_planned(
            [_MockWorkout(wtype="easy") for _ in runs], today
        )
        for r, (w, _) in zip(runs, planned):
            r.daily_workout_id = w.id
        ids = {w.id for w, _ in planned}
        return compute_adjustment_signals(
            runs, planned, ids, today, "plan1",
            _MockDB([w.id for w, _ in planned]),
            _recency_one,
            current_phase=current_phase,
            training_load=training_load,
            adaptation_history=history,
        )

    def test_overreached_tsb_caps_multiplier(self):
        signals = self._build({
            "available": True,
            "current": {"tsb": -30, "ctl": 60, "atl": 90},
        })
        assert signals["tsb_form"] == "overreached"
        assert signals["multiplier"] <= 0.92

    def test_primed_tsb_in_peak_allows_expanded_range(self):
        signals = self._build({
            "available": True,
            "current": {"tsb": 12, "ctl": 65, "atl": 53},
        }, current_phase="peak")
        assert signals["tsb_form"] == "primed"
        # Expanded range upper bound is 1.25
        assert signals["expanded_range"] is True

    def test_neutral_tsb_keeps_standard_range(self):
        signals = self._build({
            "available": True,
            "current": {"tsb": 0, "ctl": 50, "atl": 50},
        })
        assert signals["tsb_form"] == "neutral"
        assert signals["expanded_range"] is False

    def test_no_training_load_leaves_tsb_none(self):
        signals = self._build(None)
        assert signals["tsb"] is None
        assert signals["tsb_form"] is None

    def test_unavailable_training_load_leaves_tsb_none(self):
        signals = self._build({"available": False, "reason": "No runs"})
        assert signals["tsb"] is None
        assert signals["tsb_form"] is None


class TestSignalIntegration:
    def test_two_race_efforts_caps_multiplier(self):
        today = _today()
        runs = [
            _MockRun(wtype="tempo", effort_class="race_effort",
                     date=today - timedelta(days=4)),
            _MockRun(wtype="tempo", effort_class="race_effort",
                     date=today - timedelta(days=1)),
            _MockRun(wtype="easy", date=today),
        ]
        planned = _build_planned([
            _MockWorkout(runs[0].id, "tempo"),
            _MockWorkout(runs[1].id, "tempo"),
            _MockWorkout(runs[2].id, "easy"),
        ], today)
        for r, (w, _) in zip(runs, planned):
            r.daily_workout_id = w.id
        ids = {w.id for w, _ in planned}

        signals = compute_adjustment_signals(
            runs, planned, ids, today, "plan1",
            _MockDB([w.id for w, _ in planned]),
            _recency_one,
            current_phase="build",
        )

        assert signals["recent_race_effort_count"] == 2
        assert signals["overreach_detected"] is True
        assert signals["multiplier"] <= 0.95

    def test_quality_drift_appears_in_result_dict(self):
        today = _today()
        runs = []
        for i in range(8):
            r = _MockRun(
                wtype="easy",
                effort_quality_score=80 - i,
                date=today - timedelta(days=8 - i),
            )
            runs.append(r)

        planned = _build_planned(
            [_MockWorkout(r.id, "easy") for r in runs], today
        )
        for r, (w, _) in zip(runs, planned):
            r.daily_workout_id = w.id

        signals = compute_adjustment_signals(
            runs, planned, {w.id for w, _ in planned},
            today, "plan1",
            _MockDB([w.id for w, _ in planned]),
            _recency_one,
            current_phase="build",
        )

        assert "quality_drift" in signals
        assert "quality_drift_modifier" in signals
        assert "recent_race_effort_count" in signals
        assert signals["recent_race_effort_count"] == 0
