from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from kaburi_kenchi.duplicate_finder import DuplicateGroup
from kaburi_kenchi.scanner import VideoFile


class Action(str, Enum):
    KEEP = "keep"
    MOVE = "move"


@dataclass
class FileDecision:
    file: VideoFile
    action: Action
    is_ambiguous: bool = False  # True when the runner-up is very close in score


def quality_score(v: VideoFile) -> tuple[int, int, int, int]:
    """Higher is better. Tuple compares lexicographically.

    Order of importance:
      1. Pixel count (resolution)
      2. Bit rate
      3. File size
      4. Inverse path-depth tiebreak (shallower wins) — encoded as negative
    """
    pixels = (v.width or 0) * (v.height or 0)
    br = v.bit_rate or 0
    size = v.size or 0
    depth = -len(v.path.parts)
    return (pixels, br, size, depth)


def _score_close(a: tuple, b: tuple, *, pixel_tol: float = 0.0, br_tol: float = 0.10) -> bool:
    """True when two scores are 'practically the same' on resolution and bitrate.

    Used to flag visually-similar duplicates where the user may want to verify
    before discarding either one.
    """
    a_px, a_br, *_ = a
    b_px, b_br, *_ = b
    if a_px != b_px:
        return False
    if a_br == 0 or b_br == 0:
        return a_br == b_br
    diff_ratio = abs(a_br - b_br) / max(a_br, b_br)
    return diff_ratio <= br_tol


def decide_group(group: DuplicateGroup) -> list[FileDecision]:
    """Pick exactly one KEEP per group. Mark MOVE candidates as ambiguous when
    their score is close enough to the winner that the user may want to review.
    """
    if not group.files:
        return []

    scored = sorted(
        group.files,
        key=lambda f: (quality_score(f), -len(f.path.name)),
        reverse=True,
    )
    keeper = scored[0]
    keeper_score = quality_score(keeper)

    decisions: list[FileDecision] = [FileDecision(file=keeper, action=Action.KEEP)]
    for f in scored[1:]:
        ambiguous = _score_close(keeper_score, quality_score(f))
        decisions.append(FileDecision(file=f, action=Action.MOVE, is_ambiguous=ambiguous))
    return decisions


def decide_all(groups: list[DuplicateGroup]) -> dict[int, list[FileDecision]]:
    """Compute decisions for every group, keyed by id(group)."""
    return {id(g): decide_group(g) for g in groups}


def estimated_savings_bytes(decisions: dict[int, list[FileDecision]]) -> int:
    total = 0
    for decs in decisions.values():
        for d in decs:
            if d.action is Action.MOVE:
                total += d.file.size
    return total
