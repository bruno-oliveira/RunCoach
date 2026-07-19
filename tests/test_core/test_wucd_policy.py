"""Warm-up/cool-down policy invariants.

The single policy in ``workout_steps.primitives`` sizes bookends for every
family (road generic builders, key-workout overlays, performance segments).
These tests pin the safety properties: hard sessions never open on a token
jog, bookends never crowd out the working set, both construction directions
(top-down from a session total, bottom-up from a work block) agree, and the
prose rewrites cite exactly the warm-up the executable steps carry.
"""

import re

import pytest

from app.core.training.key_workout_data import WORKOUTS
from app.core.training.key_workout_library.builders import build_key_workout_steps
from app.core.training.key_workout_library.rewrites import (
    _DISTANCE_REWRITES,
    _rewrite_key_workout_description,
)
from app.core.training.workout_steps.primitives import (
    HARD_SESSION_TYPES,
    _wucd_m,
    _wucd_m_for_work,
    wucd_profile,
)

_BY_ID = {w["id"]: w for w in WORKOUTS}

_WU_RE = re.compile(r"[Ww]arm up (\d+(?:\.\d+)?)\s*km")


class TestWucdPolicy:
    def test_hard_sessions_get_real_warmup(self):
        # From 4 km upward a hard session opens on at least 1 km of easy running.
        for total_m in (4000, 5000, 8000, 12000, 20000):
            assert _wucd_m(total_m, hard=True) >= 1000, f"total={total_m}"

    def test_bookends_never_exceed_half_the_session(self):
        for hard in (False, True):
            for total_m in range(1000, 22000, 500):
                wu = _wucd_m(total_m, hard=hard)
                assert 2 * wu <= total_m, f"total={total_m} hard={hard} wu={wu}"

    def test_hard_profile_never_smaller_than_tempo(self):
        for total_m in range(2000, 22000, 500):
            assert _wucd_m(total_m, hard=True) >= _wucd_m(total_m, hard=False)

    def test_caps_and_snapping(self):
        # Absolute caps hold and every value sits on the 100 m grid.
        for hard, cap in ((False, 1600), (True, 2000)):
            for total_m in range(1000, 30000, 700):
                wu = _wucd_m(total_m, hard=hard)
                assert wu <= cap
                assert wu % 100 == 0

    def test_work_based_helper_agrees_with_total_based(self):
        # Bottom-up (performance family) and top-down (road family) must
        # produce the same bookends for the same resulting session.
        for hard in (False, True):
            for work_m in range(2000, 15000, 500):
                wu = _wucd_m_for_work(work_m, hard=hard)
                total_m = work_m + 2 * wu
                assert abs(_wucd_m(total_m, hard=hard) - wu) <= 100, (
                    f"work={work_m} hard={hard}"
                )

    def test_profile_context_scopes_hardness(self):
        total = 8000
        with wucd_profile("interval"):
            assert _wucd_m(total) == _wucd_m(total, hard=True)
        with wucd_profile("tempo"):
            assert _wucd_m(total) == _wucd_m(total, hard=False)
        # Default (no scope): tempo profile.
        assert _wucd_m(total) == _wucd_m(total, hard=False)

    def test_hard_session_types_cover_known_types(self):
        assert {"interval", "hill", "vo2max", "race_pace"} <= HARD_SESSION_TYPES
        assert "tempo" not in HARD_SESSION_TYPES


@pytest.mark.parametrize("wid", sorted(_DISTANCE_REWRITES))
def test_rewrite_warmup_matches_step_warmup(wid):
    """Prose 'Warm up X km' must equal the executable warm-up step, per id."""
    w = _BY_ID.get(wid)
    if w is None:
        pytest.skip(f"{wid} rewrite has no catalog entry")
    for d in (5.0, 8.0, 12.0):
        desc = _rewrite_key_workout_description(w["description"], wid, d)
        m = _WU_RE.search(desc)
        if not m:
            continue  # session has no distance-cited warm-up (split longs etc.)
        prose_wu_km = float(m.group(1))
        steps = build_key_workout_steps(w, w.get("structure", ""), d, w["type"], None)
        step_wu_m = sum(
            (s.get("distance_m") or 0) * s.get("repeat", 1)
            for s in steps
            if s.get("kind") == "warmup"
        )
        if step_wu_m == 0:
            continue
        assert abs(prose_wu_km - step_wu_m / 1000.0) <= 0.05, (
            f"{wid} at {d}km: prose warm-up {prose_wu_km}km, "
            f"steps warm-up {step_wu_m / 1000.0}km"
        )
