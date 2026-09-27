"""Frame sampling by presentation timestamp (PTS), safe for variable-frame-rate iPhone video.

Offsets are milliseconds from the first decoded frame's PTS; see docs/contracts/analysis.md §3.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

import numpy as np

from .schema import InvalidVideoError


@dataclass
class VideoInfo:
    rotation_deg: int = 0
    frames_decoded: int = 0
    frames_sampled: int = 0
    duration_ms: int = 0
    sample_fps: float = 0.0
    width: int = 0
    height: int = 0
    extra: dict = field(default_factory=dict)


def _rotate(img: np.ndarray, deg: int) -> np.ndarray:
    # deg = clockwise rotation needed for display
    k = {90: 3, 180: 2, 270: 1}.get(deg % 360, 0)  # np.rot90 rotates counter-clockwise
    return np.ascontiguousarray(np.rot90(img, k)) if k else img


def _display_rotation(stream, frame) -> int:
    """Clockwise degrees to rotate decoded pixels for upright display."""
    rot = getattr(frame, "rotation", None)  # PyAV >= 14: counter-clockwise degrees from display matrix
    if rot is not None:
        return int(-rot) % 360
    tag = (stream.metadata or {}).get("rotate")
    return int(tag) % 360 if tag else 0


def sample_frames(video_path: str, sample_fps: float, info: VideoInfo) -> Iterator[tuple[int, np.ndarray]]:
    """Yield (offset_ms, upright BGR image) at roughly `sample_fps`, chosen by PTS.

    Fills `info` as it goes. Raises InvalidVideoError if the file can't be decoded or has no frames.
    """
    import av  # imported lazily so fixture mode/tests don't need PyAV

    if sample_fps <= 0:
        raise ValueError("sample_fps must be > 0")
    interval_ms = 1000.0 / sample_fps
    info.sample_fps = sample_fps
    try:
        container = av.open(video_path)
    except Exception as e:  # noqa: BLE001 - PyAV raises many types
        raise InvalidVideoError(f"cannot open video {video_path!r}: {e}") from e

    with container:
        if not container.streams.video:
            raise InvalidVideoError(f"no video stream in {video_path!r}")
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        first_pts_s = None
        next_target_ms = 0.0
        last_ms = 0
        try:
            for frame in container.decode(stream):
                if frame.pts is None:
                    continue
                t_s = float(frame.pts * frame.time_base)
                if first_pts_s is None:
                    first_pts_s = t_s
                    info.rotation_deg = _display_rotation(stream, frame)
                offset_ms = int(round((t_s - first_pts_s) * 1000.0))
                if offset_ms < 0:  # B-frame reorder artifacts before the first shown frame
                    continue
                info.frames_decoded += 1
                last_ms = max(last_ms, offset_ms)
                if offset_ms + 0.5 < next_target_ms:
                    continue
                img = _rotate(frame.to_ndarray(format="bgr24"), info.rotation_deg)
                info.height, info.width = img.shape[:2]
                info.frames_sampled += 1
                next_target_ms = (int(offset_ms / interval_ms) + 1) * interval_ms
                yield offset_ms, img
        except av.error.FFmpegError as e:
            if info.frames_decoded == 0:
                raise InvalidVideoError(f"cannot decode {video_path!r}: {e}") from e
            # Truncated tail (e.g. interrupted upload): keep what decoded, record it.
            info.extra["decode_warning"] = str(e)
    if info.frames_decoded == 0:
        raise InvalidVideoError(f"no decodable frames in {video_path!r}")
    info.duration_ms = last_ms
