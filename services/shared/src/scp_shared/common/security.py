"""Security utilities for masking sensitive data in logs."""

from urllib.parse import urlparse, urlunparse


def mask_connection_url(url: str) -> str:
    """Mask credentials in connection URLs for safe logging.

    Replaces username:password in URLs with username:*** to prevent
    credential exposure in logs.

    Args:
        url: Connection URL (e.g., postgresql://user:pass@host:port/db)

    Returns:
        Masked URL with password replaced by ***

    Examples:
        >>> mask_connection_url("postgresql://user:pass@localhost:5432/db")
        'postgresql://user:***@localhost:5432/db'

        >>> mask_connection_url("redis://:password@localhost:6379")
        'redis://:***@localhost:6379'

        >>> mask_connection_url("postgresql://localhost:5432/db")
        'postgresql://localhost:5432/db'
    """
    if not url or not isinstance(url, str):
        return "<connection_url_masked>"

    try:
        parsed = urlparse(url)

        # Check if URL has a valid scheme (indicates it's a proper URL)
        if not parsed.scheme:
            # Not a valid URL format, return safe message
            return "<connection_url_masked>"

        # If no username/password, return as-is
        if not parsed.username and not parsed.password:
            return url

        # Mask password while preserving username
        masked_netloc = parsed.netloc
        if "@" in masked_netloc:
            # Split netloc into auth and host:port
            auth_part, host_part = masked_netloc.rsplit("@", 1)

            if ":" in auth_part:
                # Has username:password or :password (password only)
                username = auth_part.split(":")[0]
                if username:
                    # username:password format - mask password, preserve username
                    masked_netloc = f"{username}:***@{host_part}"
                else:
                    # :password format (password only, no username) - mask password
                    masked_netloc = f":***@{host_part}"
            else:
                # Just username (no password) - preserve username, no masking needed
                masked_netloc = f"{auth_part}@{host_part}"

        # Reconstruct URL with masked credentials
        masked_parsed = parsed._replace(netloc=masked_netloc)
        return urlunparse(masked_parsed)

    except Exception:
        # If parsing fails, return a safe generic message
        # This prevents errors from breaking logging
        return "<connection_url_masked>"
