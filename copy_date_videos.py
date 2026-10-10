#!/usr/bin/env python3
"""Copy first-level videos from date-named folders, without overwriting files."""

import argparse
import re
import shutil
from datetime import date
from pathlib import Path


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}


def is_date_directory(name: str) -> bool:
    # Accept YYYY, YYYYMM, YYYYMMDD, extended day ranges, and hyphenated dates.
    if re.fullmatch(r"[12]\d{3}", name):
        return True
    match = re.fullmatch(r"([12]\d{3})-?(\d{2})(?:-?(\d{2})\d*)?", name)
    if not match:
        return False
    year, month, day = match.groups()
    try:
        date(int(year), int(month), int(day or 1))
        return True
    except ValueError:
        return False


def copy_videos(source: Path, destination: Path) -> tuple[int, int]:
    if source == destination or source.is_relative_to(destination):
        raise ValueError("目的目錄不可與來源相同或包含來源目錄")
    copied = skipped = 0
    for folder in sorted(source.iterdir(), key=lambda path: path.name.casefold()):
        if not folder.is_dir() or folder.is_symlink() or not is_date_directory(folder.name):
            continue
        if folder.resolve() == destination:
            continue
        target_directory = destination / folder.name
        if target_directory.is_symlink():
            raise ValueError(f"目的子目錄不可是符號連結：{target_directory}")
        target_directory.mkdir(parents=True, exist_ok=True)
        for video in sorted(folder.iterdir(), key=lambda path: path.name.casefold()):
            if not video.is_file() or video.is_symlink() or video.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            target = target_directory / video.name
            # Exclusive creation also prevents overwriting if another process copies it.
            try:
                output = target.open("xb")
            except FileExistsError:
                print(f"忽略已存在：{target}")
                skipped += 1
                continue
            try:
                with output, video.open("rb") as input_file:
                    shutil.copyfileobj(input_file, output)
                shutil.copystat(video, target)
            except BaseException:
                target.unlink(missing_ok=True)
                raise
            print(f"複製：{video} → {target}")
            copied += 1
    return copied, skipped


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="將日期子目錄第一層影片複製到目的地同名目錄；已存在就忽略。")
    parser.add_argument("source", type=Path, help="來源目錄")
    parser.add_argument("destination", type=Path, help="目的目錄（不存在會建立）")
    args = parser.parse_args(argv)
    source = args.source.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    if not source.is_dir():
        parser.error(f"來源不是目錄：{source}")
    if destination.exists() and not destination.is_dir():
        parser.error(f"目的地不是目錄：{destination}")
    try:
        copied, skipped = copy_videos(source, destination)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"完成：複製 {copied} 個影片，忽略 {skipped} 個已存在檔案。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
