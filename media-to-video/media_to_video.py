#!/usr/bin/env python3
"""Combine photos and videos from a directory into one MP4 using ffmpeg."""

from __future__ import annotations

import argparse
import json
import logging
import random
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif", ".wma"}
MAX_VIDEO_BYTES = 200_000_000
MAX_VIDEO_COUNT = 10
RESOLUTION_TIERS = (
    ("4K", 3840, 2160),
    ("2K", 2560, 1440),
    ("1080p", 1920, 1080),
)
LOGGER = logging.getLogger(__name__)


def report(message: str) -> None:
    print(message)
    LOGGER.info(message)


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        LOGGER.error(message)
        super().error(message)


def run(command: list[str]) -> None:
    LOGGER.info("執行指令：%s", command)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.stderr:
        LOGGER.log(logging.ERROR if result.returncode else logging.INFO, result.stderr.rstrip())
        print(result.stderr, end="", file=sys.stderr)
    result.check_returncode()


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
            report(
                f"Auto resolution: {label} ({width}x{height}); "
                f"lowest {source_type} source bounds are {minimum_long}x{minimum_short}."
            )
            return width, height

    width, height = RESOLUTION_TIERS[-1][1:]
    report(
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


def convert_photo_to_jpg(source: Path, output: Path) -> None:
    report(f"轉換圖片為 JPG：{source.name}")
    if source.suffix.lower() in {".heic", ".heif"} and shutil.which("sips"):
        run(["sips", "-s", "format", "jpeg", str(source), "--out", str(output)])
        return
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-frames:v", "1", "-c:v", "mjpeg", "-q:v", "2", "-update", "1", str(output),
    ])


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


def collect_media(directory: Path, output: Path) -> list[Path]:
    candidates = sorted(
        (
            path for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in PHOTO_EXTENSIONS | VIDEO_EXTENSIONS
            and path.resolve() != output
        ),
        key=lambda path: path.name.casefold(),
    )
    video_count = sum(path.suffix.lower() in VIDEO_EXTENSIONS for path in candidates)
    media = []
    for path in candidates:
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            reasons = []
            if video_count > MAX_VIDEO_COUNT:
                reasons.append(f"目錄內有 {video_count} 部影片，超過 {MAX_VIDEO_COUNT} 部")
            if path.name.casefold().startswith("video"):
                reasons.append("檔名以 video 開頭")
            if path.stat().st_size > MAX_VIDEO_BYTES:
                reasons.append("檔案大於 200 MB")
            if reasons:
                report(f"排除影片：{path}（{'；'.join(reasons)}）")
                continue
        media.append(path)
    return media


def render_directory(
    media: list[Path], output: Path, args: argparse.Namespace, started: float,
) -> tuple[int, int]:
    photo_count = sum(path.suffix.lower() in PHOTO_EXTENSIONS for path in media)
    video_count = len(media) - photo_count
    music = random.choice(args.music_files) if args.music_files else None
    if music:
        report(f"背景音樂：{music}")

    with tempfile.TemporaryDirectory(prefix="media-to-video-") as temp:
        workdir = Path(temp)

        def prepare_source(item: tuple[int, Path]) -> Path:
            index, source = item
            if source.suffix.lower() in PHOTO_EXTENSIONS - {".jpg", ".jpeg"}:
                converted = workdir / f"photo-{index:06d}.jpg"
                convert_photo_to_jpg(source, converted)
                return converted
            return source

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            prepared = list(executor.map(prepare_source, enumerate(media, 1)))

        width, height = auto_resolution(prepared) if args.resolution is None else args.resolution
        output.parent.mkdir(parents=True, exist_ok=True)
        report(
            f"Found {len(media)} media files. Rendering {width}x{height} at {args.fps} fps "
            f"with {args.workers} workers and {args.threads} encoding threads per worker..."
        )

        def render_segment(item: tuple[int, Path]) -> Path:
            index, source = item
            segment = workdir / f"segment-{index:06d}.mp4"
            report(f"[{index}/{len(media)}] {media[index - 1].name}")
            if source.suffix.lower() in PHOTO_EXTENSIONS:
                render_photo(
                    source, segment, args.photo_duration, width, height, args.fps, args.fit,
                    args.threads,
                )
            else:
                render_video(source, segment, width, height, args.fps, args.fit, args.threads)
            return segment

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            segments = list(executor.map(render_segment, enumerate(prepared, 1)))

        joined = workdir / "joined.mp4"
        concat_segments(segments, joined, workdir)
        if music:
            add_music(
                joined, music, output,
                args.audio_mode, args.music_volume,
            )
        else:
            shutil.copy2(joined, output)

    report(f"Created: {output}")
    report(f"合併完成：{photo_count} 張照片、{video_count} 部影片，共 {len(media)} 個素材。")
    report(f"總執行時間：{time.perf_counter() - started:.2f} 秒。")
    return photo_count, video_count


def execute() -> int:
    started = time.perf_counter()
    parser = ArgumentParser(
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

  Render each immediate subdirectory into a separate video:
    %(prog)s /path/to/albums --output /path/to/output-directory
""",
    )
    parser.add_argument("-h", "--help", action="help", help="顯示此說明訊息並結束")
    parser.add_argument(
        "--log-file", type=Path,
        help="執行 log 路徑，包含時間戳記與錯誤，同名檔案追加紀錄（預設：輸出影片資料夾內的 <素材目錄名稱>.log）",
    )
    parser.add_argument(
        "directory", nargs="?", type=Path, help="包含照片與影片的資料夾",
    )
    parser.add_argument(
        "--output", "-o", type=Path,
        help="單目錄時為影片路徑（預設：目前工作目錄下的 <素材目錄名稱>.mp4）；有子目錄時為輸出資料夾（預設：指定的父目錄）",
    )
    parser.add_argument(
        "--music", type=Path,
        help="背景音樂檔或資料夾；資料夾內每支影片隨機選一首音樂，不遞迴子目錄（選填）",
    )
    parser.add_argument(
        "--photo-duration", type=float, default=1.5, help="每張照片的顯示秒數（預設：1.5）",
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
        "--music-volume", type=float, default=0.5,
        help="背景音樂音量倍率，0 為靜音、1 為原始音量（預設：0.5）",
    )
    args = parser.parse_args()

    if args.directory is None:
        parser.print_help(sys.stderr)
        return 2

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        parser.error("ffmpeg and ffprobe are required; install them with: brew install ffmpeg")
    directory = args.directory.expanduser().resolve()
    requested_output = args.output.expanduser().resolve() if args.output else None
    if not directory.is_dir():
        parser.error(f"not a directory: {directory}")
    music_path = args.music.expanduser().resolve() if args.music else None
    custom_log = args.log_file.expanduser().resolve() if args.log_file else None
    subdirectories = sorted(
        (path for path in directory.iterdir()
         if path.is_dir() and path.resolve() not in (
             requested_output, music_path, custom_log.parent if custom_log else None,
         )),
        key=lambda path: path.name.casefold(),
    )
    output = requested_output or Path(f"{directory.name}.mp4").resolve()
    output_directory = (requested_output or directory) if subdirectories else output.parent
    if subdirectories:
        if output_directory.exists() and not output_directory.is_dir():
            parser.error("批次模式的 --output 必須是輸出資料夾")
        if not output_directory.exists() and output_directory.suffix.lower() == ".mp4":
            parser.error("批次模式的 --output 請指定資料夾，而非 .mp4 檔案")
    log_file = custom_log or output_directory / f"{directory.name}.log"
    if log_file.suffix.lower() in PHOTO_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS:
        parser.error("--log-file 請指定 log 檔案，不可使用素材或音訊副檔名")
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_file, encoding="utf-8")
    except OSError as error:
        parser.error(f"無法建立 log 檔：{error}")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    report(f"執行 log：{log_file}")
    LOGGER.info("執行參數：%s", vars(args))
    args.music_files = []
    if music_path and args.audio_mode != "original":
        if music_path.is_file():
            args.music_files = [music_path]
        elif music_path.is_dir():
            args.music_files = sorted(
                (path for path in music_path.iterdir() if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS),
                key=lambda path: path.name.casefold(),
            )
            if not args.music_files:
                parser.error(f"音樂資料夾內沒有支援的音訊檔：{music_path}")
        else:
            parser.error(f"找不到背景音樂檔或資料夾：{music_path}")
    if args.photo_duration <= 0 or args.fps <= 0 or args.music_volume < 0:
        parser.error("durations/FPS must be positive and music volume cannot be negative")
    if args.workers <= 0 or args.threads <= 0:
        parser.error("--workers 與 --threads 必須為正整數")

    if not subdirectories:
        media = collect_media(directory, output)
        if not media:
            parser.error(f"no eligible photos or videos found in {directory} after filtering")
        render_directory(media, output, args, started)
        return 0

    jobs = []
    for child in subdirectories:
        output = output_directory / f"{child.name}.mp4"
        media = collect_media(child, output)
        if media:
            jobs.append((child, media, output))
        else:
            report(f"跳過：{child}（沒有支援或符合合併條件的照片或影片）")
    if not jobs:
        parser.error("所有子目錄都沒有支援或符合合併條件的照片或影片")

    total_photos = total_videos = 0
    for index, (child, media, output) in enumerate(jobs, 1):
        report(f"\n[{index}/{len(jobs)}] 處理子目錄：{child}")
        photos, videos = render_directory(media, output, args, time.perf_counter())
        total_photos += photos
        total_videos += videos
    report(
        f"\n批次完成：輸出 {len(jobs)} 支影片，合併 {total_photos} 張照片、"
        f"{total_videos} 部影片，共 {total_photos + total_videos} 個素材。"
    )
    report(f"整批執行時間：{time.perf_counter() - started:.2f} 秒。")
    return 0


def main() -> int:
    previous_handlers = set(LOGGER.handlers)
    try:
        return execute()
    except subprocess.CalledProcessError as error:
        if error.stderr:
            LOGGER.error("外部指令錯誤：%s", error.stderr)
        LOGGER.exception("執行失敗")
        raise
    except Exception:
        LOGGER.exception("執行失敗")
        raise
    finally:
        for handler in list(LOGGER.handlers):
            if handler not in previous_handlers:
                LOGGER.removeHandler(handler)
                handler.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        print(f"ffmpeg failed with exit code {error.returncode}", file=sys.stderr)
        raise SystemExit(error.returncode) from None
