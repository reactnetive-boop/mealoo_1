from urllib.parse import urlparse


def validate_evidence_urls(value):
    """
    Evidence links are shown to admins as clickable links, so only plain
    https URLs are accepted: never javascript:, data:, file: or similar.
    """
    if value is None:
        return value
    cleaned = []
    for url in value:
        url = (url or "").strip()
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc or len(url) > 1000:
            raise ValueError("Evidence links must be https:// URLs")
        cleaned.append(url)
    return cleaned
