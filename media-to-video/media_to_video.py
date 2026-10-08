#!/usr/bin/env python3
"""Combine photos and videos from a directory into one MP4 using ffmpeg."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
RESOLUTION_TIERS = (
    ("4K", 3840, 2160),
    ("2K", 2560, 1440),
    ("1080p", 1920, 1080),
)


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


def dimensions(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    streams = json.loads(result.stdout).get("streams", [])
    if not streams or not streams[0].get("width") or not streams[0].get("height"):
        raise ValueError(f"cannot determine dimensions: {path}")
    return int(streams[0]["width"]), int(streams[0]["height"])


def auto_resolution(media: list[Path]) -> tuple[int, int]:
    videos = [path for path in media if path.suffix.lower() in VIDEO_EXTENSIONS]
    sources = videos or media
    source_type = "video" if videos else "photo"
    measured = [(path, dimensions(path)) for path in sources]
    minimum_long = min(max(width, height) for _, (width, height) in measured)
    minimum_short = min(min(width, height) for _, (width, height) in measured)

    for label, width, height in RESOLUTION_TIERS:
        if minimum_long >= width and minimum_short >= height:
            print(
                f"Auto resolution: {label} ({width}x{height}); "
                f"lowest {source_type} source bounds are {minimum_long}x{minimum_short}."
            )
            return width, height

    width, height = RESOLUTION_TIERS[-1][1:]
    print(
        f"Auto resolution: 1080p ({width}x{height}); lowest {source_type} source bounds are "
        f"{minimum_long}x{minimum_short}, so smaller sources will be upscaled."
    )
    return width, height


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
    threads: int = 4,
) -> None:
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", str(fps), "-i", str(source),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-t", str(duration), "-vf", video_filter(width, height, fps, fit),
        "-c:v", "libx264", "-threads:v", str(threads), "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
        str(output),
    ])


def render_video(
    source: Path, output: Path, width: int, height: int, fps: int, fit: str,
    threads: int = 4,
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
        "-c:v", "libx264", "-threads:v", str(threads), "-preset", "medium", "-crf", "20",
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


def parse_resolution(value: str) -> tuple[int, int] | None:
    if value.lower() == "auto":
        return None
    try:
        width, height = (int(part) for part in value.lower().split("x", 1))
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError("resolution must look like 1920x1080") from None
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise argparse.ArgumentTypeError("resolution dimensions must be positive even numbers")
    return width, height


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
        epilog="""examples:
  Basic, with automatic 4K/2K/1080p selection:
    %(prog)s /path/to/media --output output.mp4

  Show each photo for 2 seconds and mix looping background music:
    %(prog)s /path/to/media --output output.mp4 \\
      --music music.mp3 --photo-duration 2 --audio-mode mix --music-volume 0.25

  Force 4K output and crop every item to fill the frame:
    %(prog)s /path/to/media --output output-4k.mp4 \\
      --resolution 3840x2160 --fit crop
""",
    )
    parser.add_argument("-h", "--help", action="help", help="顯示此說明訊息並結束")
    parser.add_argument(
        "directory", nargs="?", type=Path, help="包含照片與影片的資料夾",
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=Path("output.mp4"),
        help="輸出影片路徑（預設：output.mp4）",
    )
    parser.add_argument(
        "--music", type=Path, help="背景音樂路徑，可使用 MP3 或其他 ffmpeg 支援的音訊格式（選填）",
    )
    parser.add_argument(
        "--photo-duration", type=float, default=2.0, help="每張照片的顯示秒數（預設：2）",
    )
    parser.add_argument(
        "--resolution", type=parse_resolution, default=None,
        help="輸出解析度：auto 優先依影片選擇 4K/2K/1080p，無影片時依照片；或指定正偶數尺寸，例如 3840x2160（預設：auto）",
    )
    parser.add_argument("--fps", type=int, default=30, help="輸出影片每秒影格數（預設：30）")
    parser.add_argument(
        "--workers", type=int, default=2, help="同時轉檔的檔案數，須為正整數（預設：2）",
    )
    parser.add_argument(
        "--threads", type=int, default=4,
        help="每個轉檔工作的 H.264 編碼執行緒數，須為正整數（預設：4）",
    )
    parser.add_argument(
        "--fit", choices=("pad", "crop"), default="pad",
        help="畫面適配方式：pad 保留完整畫面並補黑邊；crop 裁切以填滿畫面（預設：pad）",
    )
    parser.add_argument(
        "--audio-mode", choices=("mix", "music", "original"), default="mix",
        help="音訊模式：mix 混合背景音樂與影片原音；music 僅使用背景音樂；original 保留原音並忽略 --music（預設：mix）",
    )
    parser.add_argument(
        "--music-volume", type=float, default=0.25,
        help="背景音樂音量倍率，0 為靜音、1 為原始音量（預設：0.25）",
    )
    args = parser.parse_args()

    if args.directory is None:
        parser.print_help(sys.stderr)
        return 2

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
    if args.workers <= 0 or args.threads <= 0:
        parser.error("--workers 與 --threads 必須為正整數")

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

    width, height = auto_resolution(media) if args.resolution is None else args.resolution
    output.parent.mkdir(parents=True, exist_ok=True)
    print(
        f"Found {len(media)} media files. Rendering {width}x{height} at {args.fps} fps "
        f"with {args.workers} workers and {args.threads} encoding threads per worker..."
    )

    with tempfile.TemporaryDirectory(prefix="media-to-video-") as temp:
        workdir = Path(temp)

        def render_segment(item: tuple[int, Path]) -> Path:
            index, source = item
            segment = workdir / f"segment-{index:06d}.mp4"
            print(f"[{index}/{len(media)}] {source.name}")
            if source.suffix.lower() in PHOTO_EXTENSIONS:
                render_photo(
                    source, segment, args.photo_duration, width, height, args.fps, args.fit,
                    args.threads,
                )
            else:
                render_video(source, segment, width, height, args.fps, args.fit, args.threads)
            return segment

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            segments = list(executor.map(render_segment, enumerate(media, 1)))

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
