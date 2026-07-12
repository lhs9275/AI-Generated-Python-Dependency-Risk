def parse_iso_datetime(dt_str: str) -> dict:
    """
    Parse an ISO 8601 datetime string and return a dict of components.

    Args:
        dt_str: datetime string in format "YYYY-MM-DDTHH:MM:SS"

    Returns:
        dict with keys: year, month, day, hour, minute, second (all int)

    Raises:
        ValueError: if dt_str is not a valid ISO 8601 datetime
    """
    raise NotImplementedError
