"""Non-circular pace<->HR-at-threshold LTHR estimation.

Guards the root-cause fix: the LTHR estimate is read off the runner's own
pace<->HR fit *at their threshold pace* (a demonstrated performance from VDOT),
not from the average HR of runs *labelled* tempo -- a label that was itself
derived from the very HR zones being built, forming a self-reinforcing loop
that collapsed Zone 2 and made easy running read as "hard".
"""

import uuid
from datetime import datetime, timezone

from app.contexts.runner.fitness.hr_zone_service import get_user_threshold_hr
from app.core.training.hr_zone_calculator import HRZoneCalculator
from app.models import RunLog, User


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# A clean, perfectly-linear runner spanning easy to hard so the fit is
# unambiguous: HR = intercept + slope * speed(km/h). The wide 6.5..4.0 min/km
# pace span guarantees the VDOT threshold pace lands inside the observed data.
_PACES = [6.5, 6.2, 5.9, 5.6, 5.3, 5.0, 4.7, 4.4, 4.1, 4.0]


def _seed_runner(
    db, *, max_hr: int, intercept: float, slope: float, vdot: float = 50.0
) -> User:
    user = User(id=_uid(), email=f"{_uid()[:8]}@t.com", max_hr=max_hr)
    db.add(user)
    for pace in _PACES:
        speed = 60.0 / pace
        db.add(
            RunLog(
                user_id=user.id,
                date=_now(),
                distance_km=8.0,
                duration_minutes=8.0 * pace,
                avg_pace_min_km=pace,
                avg_heart_rate=round(intercept + slope * speed),
                vdot=vdot,
            )
        )
    db.flush()
    return user


class TestThresholdHRFromPaceHRFit:
    def test_grounded_on_threshold_pace(self, test_db):
        user = _seed_runner(test_db, max_hr=191, intercept=80.0, slope=6.5)
        lthr, source = get_user_threshold_hr(user, test_db)

        assert source == "estimated"
        # Predicted HR at the VDOT-50 threshold pace (~4:20/km) is ~170 -- well
        # clear of the collapsing ~154 the old circular tempo-median produced.
        assert 165 <= lthr <= 176
        zones = HRZoneCalculator.calculate_zones(191, lthr=lthr)
        # The whole point: an easy 150 bpm run now reads as Zone 2, not Zone 3/4.
        assert HRZoneCalculator.classify_hr(150, zones) == 2

    def test_clamped_to_plausible_fraction_of_max(self, test_db):
        # A genuinely high max paired with low HR-cost running would predict a
        # threshold below 70% of max; the estimate is clamped up to that floor
        # rather than anchoring the zones somewhere physiologically impossible.
        user = _seed_runner(test_db, max_hr=220, intercept=60.0, slope=6.0)
        lthr, source = get_user_threshold_hr(user, test_db)

        assert source == "estimated"
        assert lthr == round(0.70 * 220)  # 154

    def test_none_without_enough_samples(self, test_db):
        # Three runs sit below the 8-sample fit floor: no trustworthy fit, so no
        # estimate, and the zones fall back to the 88%-of-max default anchor.
        user = User(id=_uid(), email=f"{_uid()[:8]}@t.com", max_hr=191)
        test_db.add(user)
        for pace in (6.0, 5.0, 4.5):
            test_db.add(
                RunLog(
                    user_id=user.id,
                    date=_now(),
                    distance_km=8.0,
                    duration_minutes=8.0 * pace,
                    avg_pace_min_km=pace,
                    avg_heart_rate=round(100 + 6 * (60 / pace)),
                    vdot=50.0,
                )
            )
        test_db.flush()

        assert get_user_threshold_hr(user, test_db) == (None, "none")

    def test_manual_override_skips_estimate(self, test_db):
        # A manual threshold entry stays the highest-priority anchor.
        user = _seed_runner(test_db, max_hr=191, intercept=80.0, slope=6.5)
        user.threshold_hr = 168
        test_db.flush()

        assert get_user_threshold_hr(user, test_db) == (168, "user")
