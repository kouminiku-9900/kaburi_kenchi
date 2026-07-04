from pathlib import Path

from kaburi_kenchi.duplicate_finder import find_duplicates, normalize_name
from kaburi_kenchi.scanner import VideoFile


def make_video(name: str, sub: str, duration: float, width: int = 1920, height: int = 1080,
               bit_rate: int = 5_000_000, size: int = 1_000_000_000) -> VideoFile:
    return VideoFile(
        path=Path(f"D:/test/{sub}/{name}"),
        subfolder=sub,
        size=size,
        duration=duration,
        width=width,
        height=height,
        bit_rate=bit_rate,
        codec="h264",
    )


def test_normalize_strips_quality_tags():
    assert normalize_name("anime_ep01_1080p_x264") == normalize_name("anime_ep01_720p_x265")


def test_normalize_strips_brackets():
    assert normalize_name("[Group] Show 01 [1080p][AAC]") == normalize_name("Show 01")


def test_normalize_lowercases_and_collapses():
    assert normalize_name("My  MOVIE  Title") == "my movie title"


def test_basic_grouping_same_name_same_duration():
    videos = [
        make_video("ep01.mp4", "video1", 1440.0),
        make_video("ep01.mp4", "video2", 1440.0),
        make_video("ep02.mp4", "video1", 1500.0),
    ]
    groups = find_duplicates(videos)
    assert len(groups) == 1
    assert {f.subfolder for f in groups[0].files} == {"video1", "video2"}


def test_extension_difference_does_not_split():
    videos = [
        make_video("movie.mp4", "video1", 3600.0),
        make_video("movie.mkv", "video2", 3600.0),
    ]
    groups = find_duplicates(videos)
    assert len(groups) == 1
    assert len(groups[0].files) == 2


def test_duration_within_one_second_is_same_group():
    videos = [
        make_video("a.mp4", "video1", 600.0),
        make_video("a.mp4", "video2", 600.7),
        make_video("a.mp4", "video3", 601.5),
    ]
    groups = find_duplicates(videos)
    assert len(groups) == 1
    # 600.0 -> 600.7 -> 601.5 each within 1.0s of the next (single-linkage)
    assert len(groups[0].files) == 3


def test_duration_over_tolerance_splits():
    videos = [
        make_video("a.mp4", "video1", 600.0),
        make_video("a.mp4", "video2", 605.0),
    ]
    groups = find_duplicates(videos)
    assert groups == []


def test_quality_tags_in_name_normalize_together():
    videos = [
        make_video("show_1080p.mp4", "video1", 1440.0),
        make_video("show_720p.mp4", "video2", 1440.0),
    ]
    groups = find_duplicates(videos)
    assert len(groups) == 1


def test_unprobed_videos_are_skipped():
    v = VideoFile(path=Path("D:/x/a.mp4"), subfolder="x", size=1000, duration=None)
    groups = find_duplicates([v, make_video("a.mp4", "y", 100.0)])
    assert groups == []


def test_singleton_is_not_a_group():
    videos = [make_video("only.mp4", "video1", 100.0)]
    groups = find_duplicates(videos)
    assert groups == []
