from __future__ import annotations

import hashlib
import re

_HEX_RE = re.compile(r"^[0-9A-Fa-f]{6}$")

# Distinct fallbacks are used only when GTFS route_color is absent. The official
# GTFS value always wins, so route badges follow the operator's published data.
_FALLBACK_PALETTE = (
    "1F6FEB",
    "A23B72",
    "E4572E",
    "17A398",
    "7B2CBF",
    "C78F00",
    "2D6A4F",
    "C1121F",
    "3A0CA3",
    "0081A7",
    "8A5A44",
    "5F6F52",
)


def normalize_hex_color(value: str | None, default: str | None = None) -> str | None:
    """Return a six-character uppercase GTFS color without ``#``.

    GTFS stores ``route_color`` and ``route_text_color`` as RRGGBB. Some feeds
    include a leading hash in practice, so the parser accepts both forms.
    """

    if value is None:
        return default
    cleaned = str(value).strip().lstrip("#")
    if not _HEX_RE.fullmatch(cleaned):
        return default
    return cleaned.upper()


def fallback_route_color(route_code: str) -> str:
    normalized = " ".join(str(route_code).upper().split()) or "TJ"
    digest = hashlib.blake2b(normalized.encode("utf-8"), digest_size=2).digest()
    index = int.from_bytes(digest, "big") % len(_FALLBACK_PALETTE)
    return _FALLBACK_PALETTE[index]


def readable_text_color(background: str, preferred: str | None = None) -> str:
    """Return black or white text with adequate contrast for a route badge."""

    preferred_clean = normalize_hex_color(preferred)
    bg = normalize_hex_color(background, "1F6FEB") or "1F6FEB"
    if preferred_clean:
        return preferred_clean
    red, green, blue = (int(bg[i : i + 2], 16) for i in (0, 2, 4))
    # W3C relative luminance approximation is unnecessary here; the YIQ
    # threshold gives predictable high-contrast labels on a compact badge.
    yiq = (red * 299 + green * 587 + blue * 114) / 1000
    return "000000" if yiq >= 150 else "FFFFFF"


def route_badge_style(
    route_code: str,
    gtfs_background: str | None = None,
    gtfs_text: str | None = None,
) -> tuple[str, str]:
    background = normalize_hex_color(gtfs_background) or fallback_route_color(route_code)
    text = readable_text_color(background, gtfs_text)
    return f"#{background}", f"#{text}"
