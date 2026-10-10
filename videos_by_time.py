#!/usr/bin/env python3
"""Recursively merge videos in recording-time order, preserving original audio."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "media-to-video"))
from media_to_video import (LOGGER, VIDEO_EXTENSIONS, parse_resolution,
                            render_directory, report)


def parse_time(value: str) -> float | None:
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        # Container timestamps without an offset are interpreted as UTC.
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.timestamp()
    except (ValueError, OverflowError, AttributeError):
        return None


def video_timestamp(path: Path, time_source: str) -> tuple[float, str]:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format_tags=creation_time:stream=codec_type:stream_tags=creation_time",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    info = json.loads(probe.stdout)
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    if not streams:
        raise ValueError("沒有視訊軌")
    if time_source == "recorded":
        tags = [info.get("format", {}).get("tags", {})] + [s.get("tags", {}) for s in streams]
        for tag in tags:
            timestamp = parse_time(tag.get("creation_time", ""))
            if timestamp is not None:
                return timestamp, "creation_time"
    return path.stat().st_mtime, "mtime"


def collect_videos(directory: Path, output: Path, time_source: str) -> list[tuple[float, Path, str]]:
    videos = []

    def walk_error(error: OSError) -> None:
        raise error

    for root, children, files in os.walk(directory, onerror=walk_error):
        folder = Path(root)
        children[:] = sorted(name for name in children if not (folder / name).is_symlink())
        for name in sorted(files):
            path = folder / name
            if path.suffix.lower() not in VIDEO_EXTENSIONS or path.resolve() == output:
                continue
            if not path.is_file():
                continue
            try:
                timestamp, source = video_timestamp(path, time_source)
            except (subprocess.CalledProcessError, ValueError) as error:
                report(f"跳過無效影片：{path}（{error}）")
                continue
            videos.append((timestamp, path, source))
    return sorted(videos, key=lambda item: (item[0], item[1].relative_to(directory).as_posix().casefold()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="遞迴找出影片，按時間由舊到新合併成一支 MP4，保留原音。")
    parser.add_argument("directory", type=Path, help="素材根目錄")
    parser.add_argument("--output", "-o", type=Path, help="輸出MP4（預設：目前目錄的 <素材目錄名稱>-videos.mp4）")
    parser.add_argument("--time-source", choices=("recorded", "mtime"), default="recorded",
                        help="recorded：影片creation_time，缺少時用修改時間；mtime：只用修改時間（預設recorded）")
    parser.add_argument("--resolution", type=parse_resolution, default=None, help="720p、1080p、2k、4k，或auto；亦支援寬x高（預設auto）")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--fit", choices=("pad", "crop"), default="pad")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--list-only", action="store_true", help="只列出影片與排序時間，不轉檔")
    args = parser.parse_args(argv)
    directory = args.directory.expanduser().resolve()
    output = args.output.expanduser().resolve() if args.output else Path(f"{directory.name}-videos.mp4").resolve()
    if not directory.is_dir():
        parser.error(f"找不到目錄：{directory}")
    if output.suffix.lower() != ".mp4" or output.is_dir():
        parser.error("--output 必須指定 .mp4 檔案")
    if min(args.fps, args.workers, args.threads) <= 0:
        parser.error("--fps、--workers、--threads 必須為正整數")
    if not shutil.which("ffprobe") or (not args.list_only and not shutil.which("ffmpeg")):
        parser.error("需要 ffmpeg / ffprobe，請執行 brew install ffmpeg")
    if output.exists() and not args.list_only:
        print(f"跳過：輸出已存在：{output}")
        return 0
    handler = None
    if not args.list_only:
        output.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(output.with_suffix(".log"), encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        LOGGER.addHandler(handler)
        LOGGER.setLevel(logging.INFO)
    started = time.perf_counter()
    try:
        videos = collect_videos(directory, output, args.time_source)
        if not videos:
            parser.error("指定目錄沒有有效影片")
        for index, (timestamp, path, source) in enumerate(videos, 1):
            moment = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
            report(f"[{index}/{len(videos)}] {moment} [{source}] {path.relative_to(directory)}")
        if args.list_only:
            return 0
        # Reuse the existing normalization/concat pipeline without photo filters or music.
        args.music_files = []
        args.photo_duration = 1.5
        args.audio_mode = "original"
        args.music_volume = 0
        _, count = render_directory([path for _, path, _ in videos], output, args, started)
        return 0 if count else 1
    finally:
        if handler:
            LOGGER.removeHandler(handler)
            handler.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (subprocess.CalledProcessError, OSError) as error:
        print(f"執行失敗：{error}", file=sys.stderr)
        raise SystemExit(1)
