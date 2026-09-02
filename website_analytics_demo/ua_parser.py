"""
Minimal, dependency-free User-Agent sniffing. Good enough to tell
desktop vs mobile vs tablet and the major browser family from a real
browser's real User-Agent header. A production system would use a
proper parser library (e.g. user-agents on PyPI); this keeps the demo
dependency-free since it only needs a rough split.
"""


def parse_device_type(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if "ipad" in ua or "tablet" in ua:
        return "Tablet"
    if "mobi" in ua or "iphone" in ua or "android" in ua:
        return "Mobile"
    return "Desktop"


def parse_browser(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if "edg/" in ua:
        return "Edge"
    if "chrome/" in ua and "chromium" not in ua:
        return "Chrome"
    if "firefox/" in ua:
        return "Firefox"
    if "safari/" in ua and "chrome/" not in ua:
        return "Safari"
    return "Other"
