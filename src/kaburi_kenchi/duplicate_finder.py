from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from kaburi_kenchi.scanner import VideoFile

DURATION_TOLERANCE_SEC = 1.0

_WS_RE = re.compile(r"\s+")
# Strip common quality / source markers so "movie 1080p" and "movie 720p" normalize
# to the same key. The actual quality is recovered from ffprobe metadata, so the
# filename hint is redundant — and folding it makes detection more robust.
_QUALITY_TAG_RE = re.compile(
    r"\b(?:480p|720p|1080p|1440p|2160p|4k|8k|hd|fhd|uhd|sd|hq|lq|"
    r"x264|x265|h264|h265|hevc|avc|aac|mp3|"
    r"web[- ]?dl|webrip|bdrip|brrip|hdrip|dvdrip|bluray|hdtv)\b",
    re.IGNORECASE,
)
_BRACKETED_RE = re.compile(r"[\[\(\{][^\]\)\}]*[\]\)\}]")


def normalize_name(stem: str) -> str:
    """Normalize a filename stem for grouping.

    Order matters:
      1. Lowercase
      2. Strip [...] (...) {...} groups (release tags)
      3. Convert non-alnum runs (incl. `_`) to spaces — so `_1080p_` becomes `1080p`
         with whitespace boundaries that the next step's `\\b` can see
      4. Strip standalone quality / codec / source tags
      5. Collapse whitespace
    """
    s = stem.lower()
    s = _BRACKETED_RE.sub(" ", s)
    s = re.sub(r"[^0-9a-z぀-ヿ一-鿿]+", " ", s)
    s = _QUALITY_TAG_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


@dataclass
class DuplicateGroup:
    key_name: str
    key_duration_sec: int
    files: list[VideoFile] = field(default_factory=list)

    @property
    def representative_duration(self) -> float:
        durations = [f.duration for f in self.files if f.duration is not None]
        if not durations:
            return 0.0
        return sum(durations) / len(durations)


def find_duplicates(
    videos: Iterable[VideoFile],
    duration_tolerance: float = DURATION_TOLERANCE_SEC,
) -> list[DuplicateGroup]:
    """Group videos that share a normalized filename and a near-equal duration.

    Algorithm:
      1. Bucket by normalized name.
      2. Within each name bucket, cluster by duration with `duration_tolerance`
         as the linking distance (single-linkage along the time axis).
      3. Emit clusters of size >= 2 as DuplicateGroups.
    """
    by_name: dict[str, list[VideoFile]] = {}
    for v in videos:
        if not v.has_meta:
            continue
        key = normalize_name(v.stem)
        if not key:
            continue
        by_name.setdefault(key, []).append(v)

    groups: list[DuplicateGroup] = []
    for name_key, items in by_name.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda f: f.duration or 0.0)
        clusters: list[list[VideoFile]] = []
        current: list[VideoFile] = [items[0]]
        for prev, curr in zip(items, items[1:]):
            if abs((curr.duration or 0.0) - (prev.duration or 0.0)) <= duration_tolerance:
                current.append(curr)
            else:
                clusters.append(current)
                current = [curr]
        clusters.append(current)

        for cluster in clusters:
            if len(cluster) < 2:
                continue
            avg = sum(f.duration or 0.0 for f in cluster) / len(cluster)
            groups.append(
                DuplicateGroup(
                    key_name=name_key,
                    key_duration_sec=int(round(avg)),
                    files=cluster,
                )
            )

    groups.sort(key=lambda g: (-sum(f.size for f in g.files), g.key_name))
    return groups


def collect_unprobed(videos: Iterable[VideoFile]) -> list[VideoFile]:
    return [v for v in videos if not v.has_meta]
