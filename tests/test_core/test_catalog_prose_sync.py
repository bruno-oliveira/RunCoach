"""Drift prevention: catalog prose must never contradict the steps.

Every key workout either has a distance rewrite (so its numbers are
regenerated from the actual assigned distance) or carries no literal distance
in its prose at all. And where a rewrite cites a warm-up, that number must be
exactly the warm-up step the builders execute — the two are derived from the
same helper, and this locks that contract in.
"""

import re

import pytest

from app.core.training.key_workout_data import WORKOUTS
from app.core.training.key_workout_library.builders import build_key_workout_steps
from app.core.training.key_workout_library.rewrites import (
    _DISTANCE_REWRITES,
    _rewrite_key_workout_description,
)

_DISTANCE_TOKEN = re.compile(r"\d+(\.\d+)?\s*(km|m\b)")
_WARMUP_CITE = re.compile(r"^Warm up (\d+(?:\.\d+)?)\s*km")

_BY_ID = {w["id"]: w for w in WORKOUTS}


@pytest.mark.parametrize("wid", sorted(_BY_ID))
def test_every_id_is_rewritten_or_distance_free(wid):
    """A catalog id with literal distances in its prose needs a rewrite.

    Without one, the displayed numbers are frozen at authoring time while the
    executable steps scale with the assigned distance — the P6 class of bug
    ("Warm up 2km" on a 3.6 km card).
    """
    if wid in _DISTANCE_REWRITES:
        return
    w = _BY_ID[wid]
    for field in ("description", "structure"):
        m = _DISTANCE_TOKEN.search(w.get(field, ""))
        assert not m, (
            f"{wid}.{field} contains the literal distance '{m.group(0)}' but "
            f"has no _DISTANCE_REWRITES entry — prose will contradict the "
            f"steps as soon as the assigned distance differs"
        )


@pytest.mark.parametrize("wid", sorted(_DISTANCE_REWRITES))
@pytest.mark.parametrize("d", [6.0, 8.0, 12.0])
def test_rewritten_warmup_matches_the_warmup_step(wid, d):
    """The warm-up the prose cites is the warm-up step the runner executes."""
    w = _BY_ID.get(wid)
    if w is None:
        pytest.skip(f"{wid} not in the standard catalog")
    desc = _rewrite_key_workout_description(w["description"], wid, d)
    cited = _WARMUP_CITE.match(desc)
    if not cited:
        pytest.skip("rewrite does not open with a warm-up sentence")
    steps = build_key_workout_steps(w, w["structure"], d, w["type"], None)
    warmups = [s for s in steps if s["kind"] == "warmup"]
    assert warmups, f"{wid}: prose cites a warm-up but steps have none"
    step_km = warmups[0]["distance_m"] / 1000.0
    assert abs(float(cited.group(1)) - step_km) < 0.005, (
        f"{wid} at {d}km: prose warm-up {cited.group(1)}km != step warm-up {step_km}km"
    )
