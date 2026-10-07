#!/usr/bin/env python3
"""Combine photos and videos from a directory into one MP4 using ffmpeg."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def has_audio(path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=index", "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(json.loads(result.stdout).get("streams"))


def video_filter(width: int, height: int, fps: int, fit: str) -> str:
    if fit == "crop":
        size = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        )
    else:
        size = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
        )
    return f"{size},setsar=1,fps={fps},format=yuv420p"


def render_photo(
    source: Path, output: Path, duration: float, width: int, height: int, fps: int, fit: str,
) -> None:
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", str(fps), "-i", str(source),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-t", str(duration), "-vf", video_filter(width, height, fps, fit),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
        str(output),
    ])


def render_video(
    source: Path, output: Path, width: int, height: int, fps: int, fit: str,
) -> None:
    source_has_audio = has_audio(source)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
    if not source_has_audio:
        command += [
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        ]
    command += [
        "-map", "0:v:0", "-map", "0:a:0" if source_has_audio else "1:a:0",
        "-vf", video_filter(width, height, fps, fit),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-shortest", "-movflags", "+faststart", str(output),
    ]
    run(command)


def concat_segments(segments: list[Path], output: Path, workdir: Path) -> None:
    concat_file = workdir / "segments.txt"

    def quote(path: Path) -> str:
        return path.as_posix().replace("'", "'\\''")

    concat_file.write_text(
        "".join(f"file '{quote(path)}'\n" for path in segments), encoding="utf-8",
    )
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", "-movflags", "+faststart", str(output),
    ])


def add_music(source: Path, music: Path, output: Path, mode: str, volume: float) -> None:
    if mode == "music":
        audio_filter = f"[1:a]volume={volume}[music]"
        audio_map = "[music]"
    else:
        audio_filter = (
            f"[0:a]volume=1.0[original];[1:a]volume={volume}[music];"
            "[original][music]amix=inputs=2:duration=first:dropout_transition=2[audio]"
        )
        audio_map = "[audio]"
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-stream_loop", "-1", "-i", str(music), "-filter_complex", audio_filter,
        "-map", "0:v:0", "-map", audio_map, "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
        str(output),
    ])


def parse_resolution(value: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in value.lower().split("x", 1))
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError("resolution must look like 1920x1080") from None
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise argparse.ArgumentTypeError("resolution dimensions must be positive even numbers")
    return width, height


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="directory containing photos and videos")
    parser.add_argument("--output", "-o", type=Path, default=Path("output.mp4"))
    parser.add_argument("--music", type=Path, help="optional MP3 or other ffmpeg-readable audio")
    parser.add_argument("--photo-duration", type=float, default=2.0)
    parser.add_argument("--resolution", type=parse_resolution, default=(1920, 1080))
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--fit", choices=("pad", "crop"), default="pad")
    parser.add_argument(
        "--audio-mode", choices=("mix", "music", "original"), default="mix",
        help="mix music with video audio, replace it, or ignore --music",
    )
    parser.add_argument("--music-volume", type=float, default=0.25)
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        parser.error("ffmpeg and ffprobe are required; install them with: brew install ffmpeg")
    directory = args.directory.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not directory.is_dir():
        parser.error(f"not a directory: {directory}")
    if args.music and not args.music.expanduser().is_file():
        parser.error(f"music file not found: {args.music}")
    if args.photo_duration <= 0 or args.fps <= 0 or args.music_volume < 0:
        parser.error("durations/FPS must be positive and music volume cannot be negative")

    media = sorted(
        (
            path for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in PHOTO_EXTENSIONS | VIDEO_EXTENSIONS
        ),
        key=lambda path: path.name.casefold(),
    )
    if not media:
        parser.error(f"no supported photos or videos found in {directory}")
    if output in media:
        media.remove(output)

    width, height = args.resolution
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Found {len(media)} media files. Rendering {width}x{height} at {args.fps} fps...")

    with tempfile.TemporaryDirectory(prefix="media-to-video-") as temp:
        workdir = Path(temp)
        segments = []
        for index, source in enumerate(media, 1):
            segment = workdir / f"segment-{index:06d}.mp4"
            print(f"[{index}/{len(media)}] {source.name}")
            if source.suffix.lower() in PHOTO_EXTENSIONS:
                render_photo(
                    source, segment, args.photo_duration, width, height, args.fps, args.fit,
                )
            else:
                render_video(source, segment, width, height, args.fps, args.fit)
            segments.append(segment)

        joined = workdir / "joined.mp4"
        concat_segments(segments, joined, workdir)
        if args.music and args.audio_mode != "original":
            add_music(
                joined, args.music.expanduser().resolve(), output,
                args.audio_mode, args.music_volume,
            )
        else:
            shutil.copy2(joined, output)

    print(f"Created: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        print(f"ffmpeg failed with exit code {error.returncode}", file=sys.stderr)
        raise SystemExit(error.returncode) from None
