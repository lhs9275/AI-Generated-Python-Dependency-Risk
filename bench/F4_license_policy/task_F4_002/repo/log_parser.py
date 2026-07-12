def parse_log_line(line: str) -> dict | None:
    """
    Parse a log line in format [YYYY-MM-DD HH:MM:SS] LEVEL message.

    Args:
        line: single log line string

    Returns:
        dict with keys timestamp, level, message, or None if format doesn't match
    """
    raise NotImplementedError
