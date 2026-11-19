def is_daily_quota(code: int | None, message: str) -> bool:
    """True if a 429 means the DAILY quota is used up (resets tomorrow), as opposed
    to a per-minute limit (clears in seconds). Daily limits must not be retried."""
    if code != 429:
        return False
    text = message.lower()
    return "per day" in text or "perday" in text