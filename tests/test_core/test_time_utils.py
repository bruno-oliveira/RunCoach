"""Tests for app.core.time_utils — request-scoped user-local dates."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.time_utils import (
    local_now,
    local_today,
    parse_timezone,
    request_timezone,
    reset_request_timezone,
    set_request_timezone,
)


class TestParseTimezone:
    def test_valid_iana_name(self):
        tz = parse_timezone("Europe/Amsterdam")
        assert isinstance(tz, ZoneInfo)
        assert str(tz) == "Europe/Amsterdam"

    def test_none_and_empty(self):
        assert parse_timezone(None) is None
        assert parse_timezone("") is None
        assert parse_timezone("   ") is None

    def test_invalid_name(self):
        assert parse_timezone("Not/AZone") is None
        assert parse_timezone("<script>") is None

    def test_absurdly_long_name_rejected(self):
        assert parse_timezone("A" * 200) is None

    def test_whitespace_trimmed(self):
        assert parse_timezone(" Europe/Lisbon ") is not None


class TestRequestScope:
    def test_default_is_utc(self):
        assert request_timezone() == timezone.utc
        assert local_today() == datetime.now(timezone.utc).date()

    def test_set_and_reset(self):
        token = set_request_timezone("Asia/Tokyo")
        try:
            assert str(request_timezone()) == "Asia/Tokyo"
            assert local_now().tzinfo is not None
        finally:
            reset_request_timezone(token)
        assert request_timezone() == timezone.utc

    def test_invalid_tz_falls_back_to_utc(self):
        token = set_request_timezone("garbage")
        try:
            assert request_timezone() == timezone.utc
        finally:
            reset_request_timezone(token)

    def test_local_today_crosses_midnight_correctly(self):
        """The core bug: 00:30 in Amsterdam is 22:30 UTC *yesterday*.

        local_today() under an explicit timezone must agree with that zone's
        wall clock, not the server clock. We can't freeze time portably here,
        so assert the invariant: local date in UTC+14 minus local date in
        UTC-12 is always 1 or 2 days — i.e. the function really follows the
        zone, since a server-clock implementation would return one constant.
        """
        tok_e = set_request_timezone("Pacific/Kiritimati")  # UTC+14
        east = local_today()
        reset_request_timezone(tok_e)

        tok_w = set_request_timezone("Etc/GMT+12")  # UTC-12
        west = local_today()
        reset_request_timezone(tok_w)

        assert east - west in (timedelta(days=1), timedelta(days=2))

    def test_local_today_matches_zone_wall_clock(self):
        token = set_request_timezone("Europe/Amsterdam")
        try:
            expected = datetime.now(ZoneInfo("Europe/Amsterdam")).date()
            assert local_today() == expected
            assert isinstance(local_today(), date)
        finally:
            reset_request_timezone(token)
