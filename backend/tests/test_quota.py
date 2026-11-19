from backend.app.quota import is_daily_quota


def test_daily_limit_detected():
    # The exact wording Google returned when ky hit the limit.
    msg = "Embed content requests per day limit exceeded on Free Tier"
    assert is_daily_quota(429, msg)


def test_per_minute_429_is_not_daily():
    assert not is_daily_quota(429, "Quota exceeded for metric: requests per minute")


def test_other_codes_are_never_daily():
    assert not is_daily_quota(503, "per day")