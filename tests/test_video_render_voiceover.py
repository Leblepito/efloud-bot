"""Voice-over clips keep the whole narration at a platform loudness (T-20261107-21).

Before: `-t 8` (DEFAULT_DURATION) + `-shortest` cut any voice-over longer than
8 s, so a trade-explainer narration lost its ending; the voice was also passed
through at whatever level it was recorded.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.video_render import probe, render_clip

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg/ffprobe not installed")


def _still(tmp: Path) -> Path:
    p = tmp / "still.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x101828:s=540x540",
                    "-frames:v", "1", str(p)], check=True)
    return p


def _tone(tmp: Path, seconds: float, volume_db: float = -35.0) -> Path:
    p = tmp / f"voice_{seconds}.m4a"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"sine=frequency=440:duration={seconds}", "-af", f"volume={volume_db}dB",
                    "-c:a", "aac", str(p)], check=True)
    return p


def _integrated_lufs(path: Path) -> float:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", out)[-1])


def test_voiceover_longer_than_default_is_not_cut(tmp_path):
    out, _ = render_clip(_still(tmp_path), tmp_path / "o.mp4", backend="ffmpeg", fmt="square",
                         fps=10, audio_path=_tone(tmp_path, 10.5))
    assert probe(out)["duration"] == pytest.approx(10.5, abs=0.4)


def test_explicit_duration_still_wins(tmp_path):
    out, _ = render_clip(_still(tmp_path), tmp_path / "o.mp4", backend="ffmpeg", fmt="square",
                         fps=10, duration=2.0, audio_path=_tone(tmp_path, 10.5))
    assert probe(out)["duration"] == pytest.approx(2.0, abs=0.4)


def test_voiceover_is_loudness_normalised(tmp_path):
    out, _ = render_clip(_still(tmp_path), tmp_path / "o.mp4", backend="ffmpeg", fmt="square",
                         fps=10, audio_path=_tone(tmp_path, 4.0, volume_db=-35.0))
    assert _integrated_lufs(out) == pytest.approx(-16.0, abs=2.0)


def test_silent_clip_keeps_default_duration(tmp_path):
    out, _ = render_clip(_still(tmp_path), tmp_path / "o.mp4", backend="ffmpeg", fmt="square", fps=10)
    info = probe(out)
    assert info["duration"] == pytest.approx(8.0, abs=0.4) and info["audio_codec"] == "aac"
