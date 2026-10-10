import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_to_video import collect_recursive_media, main


class RecursiveTest(unittest.TestCase):
    def test_one_output_includes_nested_and_root_media_overrides_date_group(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source = root / "20240101"
            nested = source / "20240102" / "nested"
            nested.mkdir(parents=True)
            files = [source / "root.jpg", source / "20240102" / "a.jpg", nested / "clip.mp4"]
            for path in files:
                path.touch()
            sibling = root / "20240103"
            sibling.mkdir()
            (sibling / "outside.jpg").touch()
            output = root / "2024.mp4"
            with (
                patch.object(sys, "argv", ["media_to_video.py", str(source), "--recursive",
                                          "--output", str(output), "--audio-mode", "original"]),
                patch("media_to_video.shutil.which", return_value="ffmpeg"),
                patch("media_to_video.render_directory", return_value=(2, 1)) as render,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main(), 0)
            render.assert_called_once()
            self.assertEqual(render.call_args.args[0], sorted(files, key=lambda p: p.relative_to(source).as_posix().casefold()))
            self.assertEqual(render.call_args.args[1], output)

    def test_filters_per_directory_excludes_music_output_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source = root / "media"
            source.mkdir()
            music = source / "music"
            music.mkdir()
            (music / "cover.jpg").touch()
            crowded = source / "crowded"
            crowded.mkdir()
            for i in range(11):
                (crowded / f"clip{i}.mp4").touch()
            (crowded / "photo.jpg").touch()
            expected = [crowded / "photo.jpg"]
            for name in ("day1", "day2"):
                folder = source / name
                folder.mkdir()
                for i in range(6):
                    path = folder / f"clip{i}.mp4"
                    path.touch()
                    expected.append(path)
                (folder / "VIDEO_skip.mp4").touch()
            output = source / "result.mp4"
            output.touch()
            (source / "linked").symlink_to(crowded, target_is_directory=True)
            with contextlib.redirect_stdout(io.StringIO()):
                media = collect_recursive_media(source, output, music)
            self.assertEqual(media, sorted(expected, key=lambda p: p.relative_to(source).as_posix().casefold()))

    def test_existing_output_is_skipped_in_recursive_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp).resolve()
            (source / "nested").mkdir()
            output = source / "result.mp4"
            output.write_bytes(b"existing")
            with (
                patch.object(sys, "argv", ["media_to_video.py", str(source), "--recursive", "--output", str(output)]),
                patch("media_to_video.shutil.which", return_value="ffmpeg"),
                patch("media_to_video.render_directory") as render,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main(), 0)
            render.assert_not_called()
            self.assertEqual(output.read_bytes(), b"existing")
