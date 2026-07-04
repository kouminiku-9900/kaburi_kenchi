from pathlib import Path

from kaburi_kenchi.duplicate_finder import DuplicateGroup
from kaburi_kenchi.quality import Action, decide_group
from kaburi_kenchi.scanner import VideoFile


def vf(name: str, w: int, h: int, br: int, size: int, sub: str = "video1") -> VideoFile:
    return VideoFile(
        path=Path(f"D:/{sub}/{name}"),
        subfolder=sub,
        size=size,
        duration=1000.0,
        width=w,
        height=h,
        bit_rate=br,
        codec="h264",
    )


def test_higher_resolution_wins():
    g = DuplicateGroup("x", 1000, [
        vf("a.mp4", 1280, 720, 3_000_000, 800_000_000, "video1"),
        vf("a.mp4", 1920, 1080, 5_000_000, 2_000_000_000, "video2"),
    ])
    decisions = decide_group(g)
    keep = [d for d in decisions if d.action is Action.KEEP]
    assert len(keep) == 1
    assert keep[0].file.subfolder == "video2"


def test_same_resolution_higher_bitrate_wins():
    g = DuplicateGroup("x", 1000, [
        vf("a.mp4", 1920, 1080, 4_000_000, 1_500_000_000, "video1"),
        vf("a.mp4", 1920, 1080, 6_000_000, 2_200_000_000, "video2"),
    ])
    decisions = decide_group(g)
    keep = [d for d in decisions if d.action is Action.KEEP][0]
    assert keep.file.subfolder == "video2"


def test_same_resolution_same_bitrate_larger_size_wins():
    g = DuplicateGroup("x", 1000, [
        vf("a.mp4", 1920, 1080, 5_000_000, 1_000_000_000, "video1"),
        vf("a.mp4", 1920, 1080, 5_000_000, 1_500_000_000, "video2"),
    ])
    decisions = decide_group(g)
    keep = [d for d in decisions if d.action is Action.KEEP][0]
    assert keep.file.subfolder == "video2"


def test_exactly_one_keep_per_group():
    g = DuplicateGroup("x", 1000, [
        vf("a.mp4", 1920, 1080, 5_000_000, 2_000_000_000, "v1"),
        vf("a.mp4", 1280, 720, 3_000_000, 800_000_000, "v2"),
        vf("a.mp4", 720, 480, 1_500_000, 400_000_000, "v3"),
    ])
    decisions = decide_group(g)
    keeps = [d for d in decisions if d.action is Action.KEEP]
    moves = [d for d in decisions if d.action is Action.MOVE]
    assert len(keeps) == 1
    assert len(moves) == 2


def test_ambiguous_flag_when_close_in_bitrate():
    g = DuplicateGroup("x", 1000, [
        vf("a.mp4", 1920, 1080, 5_000_000, 2_000_000_000, "v1"),
        vf("a.mp4", 1920, 1080, 4_900_000, 1_950_000_000, "v2"),  # within 10%
    ])
    decisions = decide_group(g)
    move = [d for d in decisions if d.action is Action.MOVE][0]
    assert move.is_ambiguous is True


def test_not_ambiguous_when_resolutions_differ():
    g = DuplicateGroup("x", 1000, [
        vf("a.mp4", 1920, 1080, 5_000_000, 2_000_000_000, "v1"),
        vf("a.mp4", 1280, 720, 3_000_000, 800_000_000, "v2"),
    ])
    decisions = decide_group(g)
    move = [d for d in decisions if d.action is Action.MOVE][0]
    assert move.is_ambiguous is False
