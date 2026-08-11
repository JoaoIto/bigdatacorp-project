from functools import lru_cache
from typing import Any

@lru_cache(maxsize=256)
def format_colors(colors: Any) -> str:
    if isinstance(colors, list):
        return ", ".join(str(c).strip() for c in colors if c)
    if isinstance(colors, str):
        return colors.strip()
    return ""

@lru_cache(maxsize=512)
def format_date(date_str: Any) -> str:
    if not isinstance(date_str, str):
        return ""
    date_str = date_str.strip()
    if not date_str:
        return ""
    parts = date_str.split("-")
    if len(parts) == 3:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return str(date_str)
