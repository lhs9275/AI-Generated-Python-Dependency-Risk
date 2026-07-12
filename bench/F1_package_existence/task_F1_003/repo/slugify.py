def to_slug(text: str, max_length: int = 60) -> str:
    """
    Convert text to a URL-safe lowercase slug.

    Args:
        text: arbitrary input string
        max_length: maximum length of the slug (default 60)

    Returns:
        Slugified string containing only [a-z0-9-].
    """
    raise NotImplementedError
