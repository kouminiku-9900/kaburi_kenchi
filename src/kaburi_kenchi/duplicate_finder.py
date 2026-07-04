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
    """Group videos that share a normalized filename OR exact size, and a near-equal duration.

    Algorithm:
      1. Use Union-Find to track connected components of videos.
      2. Group by normalized name. Within each bucket, link videos with similar durations.
      3. Group by exact file size. Within each bucket, link videos with similar durations.
      4. Emit components of size >= 2 as DuplicateGroups.
    """
    videos_list = [v for v in videos if v.has_meta]
    if not videos_list:
        return []

    parent = {id(v): id(v) for v in videos_list}

    def find(i: int) -> int:
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    def union(i: int, j: int) -> None:
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    # 1. Link by normalized name & duration
    by_name: dict[str, list[VideoFile]] = {}
    for v in videos_list:
        key = normalize_name(v.stem)
        if key:
            by_name.setdefault(key, []).append(v)

    for items in by_name.values():
        if len(items) < 2:
            continue
        items.sort(key=lambda f: f.duration or 0.0)
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if (items[j].duration or 0.0) - (items[i].duration or 0.0) <= duration_tolerance:
                    union(id(items[i]), id(items[j]))
                else:
                    break

    # 2. Link by exact size & duration
    by_size: dict[int, list[VideoFile]] = {}
    for v in videos_list:
        by_size.setdefault(v.size, []).append(v)

    for items in by_size.values():
        if len(items) < 2:
            continue
        items.sort(key=lambda f: f.duration or 0.0)
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if (items[j].duration or 0.0) - (items[i].duration or 0.0) <= duration_tolerance:
                    union(id(items[i]), id(items[j]))
                else:
                    break

    # 3. Collect groups
    from collections import Counter

    groups_map: dict[int, list[VideoFile]] = {}
    for v in videos_list:
        root = find(id(v))
        groups_map.setdefault(root, []).append(v)

    groups: list[DuplicateGroup] = []
    for cluster in groups_map.values():
        if len(cluster) < 2:
            continue
        avg = sum(f.duration or 0.0 for f in cluster) / len(cluster)
        
        # Determine a representative name for the group
        names = [normalize_name(f.stem) for f in cluster]
        valid_names = [n for n in names if n]
        if valid_names:
            key_name = Counter(valid_names).most_common(1)[0][0]
        else:
            key_name = cluster[0].stem

        groups.append(
            DuplicateGroup(
                key_name=key_name,
                key_duration_sec=int(round(avg)),
                files=cluster,
            )
        )

    groups.sort(key=lambda g: (-sum(f.size for f in g.files), g.key_name))
    return groups


def collect_unprobed(videos: Iterable[VideoFile]) -> list[VideoFile]:
    return [v for v in videos if not v.has_meta]
