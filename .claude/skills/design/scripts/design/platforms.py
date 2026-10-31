"""Where a delivery goes and what that place requires: size, aspect, formats, file size, and the parts of the frame its interface covers or crops. proof and export both read it.

Each number carries its source and whether the platform states it for this use (`official`) or it comes from the platform's ad guidance or from outside (`guide`): a check built on a guide warns, it does not fail. Checked against the platforms' help pages on 2026-10-31; when a platform changes a number, it changes here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Platform", "PLATFORMS", "get", "violations"]


@dataclass(frozen=True)
class Zone:
    """A part of the frame, in fractions of width and height, that the platform covers or crops."""

    name: str
    box: tuple[float, float, float, float]  # x, y, w, h as fractions
    official: bool
    note: str


@dataclass(frozen=True)
class Platform:
    name: str
    size: tuple[int, int]  # the default delivery size
    aspect: tuple[int, int]
    formats: tuple[str, ...]
    max_bytes: int | None  # a limit the platform states for this use: over it fails
    warn_bytes: int | None  # a limit from guidance, or one path's limit (YouTube's phone upload): over it warns
    min_side: tuple[str, int] | None  # ("width" | "height", pixels)
    views: tuple[int, ...]  # widths it is commonly seen at on screen, smallest first: where legibility is judged (approximate, not a spec)
    zones: tuple[Zone, ...] = field(default_factory=tuple)
    sources: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)


IG_RES = "https://help.instagram.com/1631821640426723"
IG_CAROUSEL = "https://help.instagram.com/269314186824048"
META_STORY_AD = "https://www.facebook.com/business/ads-guide/update/image/instagram-story"
META_REELS_AD = "https://www.facebook.com/business/ads-guide/update/image/instagram-reels"
FB_FEED_AD = "https://www.facebook.com/business/ads-guide/update/image/facebook-feed"
FB_UPLOAD = "https://www.facebook.com/business/help/755224297893936"
YT_THUMB = "https://support.google.com/youtube/answer/72431"
YT_API = "https://developers.google.com/youtube/v3/docs/thumbnails/set"

MB = 1024 * 1024

# Instagram keeps a photo 320-1080 px wide at full resolution when its aspect lies between 1.91:1 and 3:4, and crops anything outside to fit.
_IG_FEED_NOTES = ("Instagram keeps 1080 px wide photos with an aspect between 1.91:1 and 3:4 at full resolution and crops other aspects to fit (official).", "A carousel takes up to 20 photos, all in one orientation (official).", "Instagram publishes no file size or format limit for posts; JPG and PNG are what its ad specs name.")
# The profile grid shows posts as 3:4 tiles; Instagram has not published the ratio and outside sources disagree (3:4 or 4:5).
_IG_GRID_45 = Zone("profile grid crop (3:4 tile)", (0.0417, 0.0, 0.9166, 1.0), False, "a 4:5 post loses about 4% of its width on each side in a 3:4 profile tile; Instagram has not published the tile ratio")
_IG_GRID_11 = Zone("profile grid crop (3:4 tile)", (0.125, 0.0, 0.75, 1.0), False, "a square post loses 12.5% of its width on each side in a 3:4 profile tile; Instagram has not published the tile ratio")
_STORY_ZONES = (
    Zone("top interface", (0.0, 0.0, 1.0, 0.14), False, "Meta's Stories and Reels ad guidance: keep the top 14% free of text and logos"),
    Zone("bottom interface", (0.0, 0.65, 1.0, 0.35), False, "Meta's Stories and Reels ad guidance: keep the bottom 35% free of text and logos"),
    Zone("left edge", (0.0, 0.0, 0.06, 1.0), False, "Meta's ad guidance: keep 6% on each side free"),
    Zone("right edge", (0.94, 0.0, 0.06, 1.0), False, "Meta's ad guidance: keep 6% on each side free"),
)
# YouTube draws the video's length over the thumbnail's bottom-right corner; it publishes no size for it, so this box is a cautious guess.
_YT_TIME = Zone("duration badge", (0.80, 0.84, 0.20, 0.16), False, "YouTube prints the video's length over the bottom-right corner; it publishes no size for it")

PLATFORMS: dict[str, Platform] = {
    "instagram-portrait": Platform("instagram-portrait", (1080, 1350), (4, 5), ("jpg", "png"), None, None, ("width", 320), (130, 390), (_IG_GRID_45,), (IG_RES, IG_CAROUSEL), _IG_FEED_NOTES),
    "instagram-tall": Platform("instagram-tall", (1080, 1440), (3, 4), ("jpg", "png"), None, None, ("width", 320), (130, 390), (), (IG_RES, IG_CAROUSEL), _IG_FEED_NOTES),
    "instagram-square": Platform("instagram-square", (1080, 1080), (1, 1), ("jpg", "png"), None, None, ("width", 320), (130, 390), (_IG_GRID_11,), (IG_RES, IG_CAROUSEL), _IG_FEED_NOTES),
    "instagram-story": Platform("instagram-story", (1080, 1920), (9, 16), ("jpg", "png"), None, 30 * MB, ("width", 500), (390,), _STORY_ZONES, (META_STORY_AD, META_REELS_AD), ("Instagram publishes no organic Stories or Reels spec; the size, file limit and safe zones are from its ad specs.",)),
    "facebook-feed": Platform("facebook-feed", (1080, 1350), (4, 5), ("jpg", "png"), 30 * MB, None, ("width", 600), (390, 500), (), (FB_FEED_AD, FB_UPLOAD), ("Meta recommends 4:5 for Facebook Feed (1440x1800 in its ad specs, 1:1 also accepted); every uploaded image is limited to 30 MB.",)),
    "youtube-thumbnail": Platform("youtube-thumbnail", (1920, 1080), (16, 9), ("jpg", "png"), 50 * MB, 2 * MB, ("width", 640), (168, 360), (_YT_TIME,), (YT_THUMB, YT_API), ("YouTube recommends 3840x2160 with a minimum width of 640; uploads are limited to 2 MB from a phone and 50 MB from a computer, so 1920x1080 under 2 MB works from both.",)),
    "youtube-shorts": Platform("youtube-shorts", (1080, 1920), (9, 16), ("jpg", "png"), 50 * MB, None, ("height", 640), (180, 390), (), (YT_THUMB,), ("YouTube recommends 9:16 and 2160x3840 for a Shorts thumbnail, at least 640 px high, and adds it only from YouTube Studio on a computer (50 MB limit).",)),
}

ASPECT_TOLERANCE = 0.01


def get(name: str) -> Platform:
    return PLATFORMS[name]


def violations(p: Platform, width: int, height: int, size_bytes: int | None, fmt: str) -> tuple[list[str], list[str]]:
    """What a delivery of this size, byte count and format breaks: (violations of what the platform states, warnings against its guidance)."""
    hard, soft = [], []
    want = p.aspect[0] / p.aspect[1]
    if abs((width / height) / want - 1) > ASPECT_TOLERANCE:
        hard.append(f"aspect {width}x{height} is not {p.aspect[0]}:{p.aspect[1]}")
    if p.min_side:
        side, px = p.min_side
        have = width if side == "width" else height
        if have < px:
            hard.append(f"{side} {have} px is under the {px} px minimum")
    if fmt not in p.formats:
        hard.append(f"format {fmt} is not one of {', '.join(p.formats)}")
    if size_bytes is not None:
        if p.max_bytes is not None and size_bytes > p.max_bytes:
            hard.append(f"{size_bytes / MB:.1f} MB is over the {p.max_bytes / MB:.0f} MB limit")
        elif p.warn_bytes is not None and size_bytes > p.warn_bytes:
            soft.append(f"{size_bytes / MB:.1f} MB is over {p.warn_bytes / MB:.0f} MB (see the platform's notes)")
    return hard, soft
