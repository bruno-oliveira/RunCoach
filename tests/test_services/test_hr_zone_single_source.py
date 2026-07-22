"""One HR-zone source of truth: band parity + Intervals anchor sync.

Guards the unification described in the home-stats/HR-zone plan:
  * the pace-zone table's BPM bands are the SAME as the canonical HR zones
    (previously a separate flat-%max computation diverged for any runner whose
    LTHR wasn't exactly 88% of max);
  * HR anchors sync from Intervals.icu into their own columns, with a manual
    entry always winning over the synced value.
"""

import uuid

from app.contexts.runner.fitness.hr_zone_service import (
    get_user_max_hr,
    get_user_resting_hr,
    get_user_threshold_hr,
)
from app.core.training.hr_zone_calculator import HRZoneCalculator
from app.core.training.zone_calculator import calculate_zones
from app.infrastructure.integrations.intervals_service import (
    apply_hr_settings_to_user,
    parse_athlete_hr_settings,
)
from app.models import User

# Pace-zone slug order == canonical zones 1..5.
_SLUGS = [
    "zone_1_recovery",
    "zone_2_aerobic",
    "zone_3_tempo",
    "zone_4_vo2max",
    "zone_5_race",
]


def _uid() -> str:
    return str(uuid.uuid4())


class TestPacePanelBandsMatchCanonical:
    def test_bands_match_with_measured_lthr(self):
        """The case that used to diverge: LTHR != 88% of max.

        max 190, LTHR 160 -> 0.842 of max. The old flat-%max path ignored LTHR;
        the pace panel and the HR-zones panel disagreed. Now both anchor on the
        same LTHR and the BPM bands are identical.
        """
        max_hr, lthr = 190, 160
        canonical = HRZoneCalculator.calculate_zones(max_hr, lthr=lthr)
        zones = calculate_zones(vdot=50, max_hr=max_hr, lthr=lthr)

        for slug, czone in zip(_SLUGS, canonical):
            assert (
                zones[slug]["hr_bpm_range"]
                == f"{czone['min_bpm']}-{czone['max_bpm']} BPM"
            )

    def test_lthr_actually_shifts_the_bands(self):
        """A measured LTHR moves the bands off the 88%-of-max default."""
        default = calculate_zones(vdot=50, max_hr=190)
        measured = calculate_zones(vdot=50, max_hr=190, lthr=160)
        assert (
            default["zone_3_tempo"]["hr_bpm_range"]
            != measured["zone_3_tempo"]["hr_bpm_range"]
        )


class TestIntervalsAnchorParsing:
    def test_reads_run_sport_settings_and_resting(self):
        athlete = {
            "sportSettings": [
                {"types": ["Ride"], "max_hr": 175, "lthr": 150},
                {"types": ["Run"], "max_hr": 191, "lthr": 170},
            ],
            "icu_resting_hr": 47,
        }
        assert parse_athlete_hr_settings(athlete) == {
            "max_hr": 191,
            "lthr": 170,
            "resting_hr": 47,
        }

    def test_junk_values_filtered_to_none(self):
        athlete = {"sportSettings": [{"types": ["Run"], "max_hr": 999, "lthr": 0}]}
        assert parse_athlete_hr_settings(athlete) == {
            "max_hr": None,
            "lthr": None,
            "resting_hr": None,
        }


class TestApplyAndResolveProvenance:
    def test_apply_writes_only_intervals_columns(self, test_db):
        user = User(id=_uid(), email=f"{_uid()[:8]}@t.com", max_hr=200)
        test_db.add(user)
        test_db.flush()

        changed = apply_hr_settings_to_user(
            user, {"max_hr": 191, "lthr": 170, "resting_hr": 47}
        )
        assert changed is True
        assert user.intervals_max_hr == 191
        assert user.intervals_lthr == 170
        assert user.intervals_resting_hr == 47
        # The manual value is never touched.
        assert user.max_hr == 200

    def test_manual_wins_over_synced(self, test_db):
        user = User(id=_uid(), email=f"{_uid()[:8]}@t.com", max_hr=200)
        user.intervals_max_hr = 191
        test_db.add(user)
        test_db.flush()
        hr, source = get_user_max_hr(user.id, test_db)
        assert (hr, source) == (200, "user")

    def test_synced_used_when_no_manual(self, test_db):
        user = User(id=_uid(), email=f"{_uid()[:8]}@t.com")
        user.intervals_max_hr = 191
        user.intervals_lthr = 170
        user.intervals_resting_hr = 47
        test_db.add(user)
        test_db.flush()

        assert get_user_max_hr(user.id, test_db) == (191, "intervals")
        assert get_user_threshold_hr(user, test_db) == (170, "intervals")
        assert get_user_resting_hr(user) == (47, "intervals")
