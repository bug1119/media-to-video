import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_to_video import main


class MusicTest(unittest.TestCase):
    def test_default_music_directory_is_used_or_skipped_when_missing(self):
        for exists in (False, True):
            with self.subTest(exists=exists), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                media = root / "media"
                media.mkdir()
                (media / "photo.jpg").touch()
                music = root / "default-music"
                if exists:
                    music.mkdir()
                    (music / "track.mp3").touch()
                summary = io.StringIO()
                with (
                    patch("media_to_video.DEFAULT_MUSIC_DIRECTORY", music),
                    patch.object(sys, "argv", [
                        "media_to_video.py", str(media), "--output", str(root / "output.mp4"),
                    ]),
                    patch("media_to_video.shutil.which", return_value="ffmpeg"),
                    patch("media_to_video.render_directory", return_value=(1, 0)) as render,
                    contextlib.redirect_stdout(summary),
                ):
                    self.assertEqual(main(), 0)
                self.assertEqual(
                    render.call_args.args[2].music_files,
                    [music / "track.mp3"] if exists else [],
                )
                if not exists:
                    self.assertIn("預設音樂目錄不存在", summary.getvalue())

    def test_batch_selects_music_for_each_video_and_excludes_music_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            music = root / "music"
            music.mkdir()
            tracks = [music / "a.MP3", music / "b.wav"]
            for track in tracks:
                track.touch()
            (music / "download-progress.json").touch()
            (music / "nested").mkdir()
            (music / "nested" / "ignored.mp3").touch()
            for name in ("album-a", "album-b"):
                (root / name).mkdir()
                (root / name / "photo.jpg").write_bytes(b"fixture")
            summary = io.StringIO()
            with (
                patch.object(sys, "argv", [
                    "media_to_video.py", temp, "--music", str(music), "--resolution", "320x180",
                ]),
                patch("media_to_video.shutil.which", return_value="ffmpeg"),
                patch("media_to_video.render_photo"),
                patch("media_to_video.dimensions", return_value=(320, 180)),
                patch("media_to_video.concat_segments"),
                patch("media_to_video.add_music") as add,
                patch("media_to_video.random.choice", side_effect=tracks) as choose,
                contextlib.redirect_stdout(summary),
            ):
                self.assertEqual(main(), 0)
            self.assertEqual(choose.call_count, 2)
            for call in choose.call_args_list:
                self.assertEqual(call.args[0], tracks)
            self.assertEqual([call.args[1] for call in add.call_args_list], tracks)
            self.assertEqual(
                [call.args[2] for call in add.call_args_list],
                [root / "album-a.mp4", root / "album-b.mp4"],
            )
            self.assertIn(f"背景音樂：{tracks[0]}", summary.getvalue())
            self.assertIn(f"背景音樂：{tracks[1]}", summary.getvalue())

    def test_single_file_and_original_mode(self):
        for mode in ("mix", "music", "original"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                (root / "photo.jpg").write_bytes(b"fixture")
                track = root / "music.mp3"
                if mode != "original":
                    track.touch()
                with (
                    patch.object(sys, "argv", [
                        "media_to_video.py", temp, "--music", str(track),
                        "--audio-mode", mode, "--resolution", "320x180",
                    ]),
                    patch("media_to_video.shutil.which", return_value="ffmpeg"),
                    patch("media_to_video.render_photo"),
                    patch("media_to_video.dimensions", return_value=(320, 180)),
                    patch("media_to_video.concat_segments"),
                    patch("media_to_video.shutil.copy2") as copy,
                    patch("media_to_video.add_music") as add,
                    patch("media_to_video.random.choice", return_value=track) as choose,
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(main(), 0)
                if mode == "original":
                    choose.assert_not_called()
                    add.assert_not_called()
                    copy.assert_called_once()
                else:
                    self.assertEqual(add.call_args.args[1], track)
                    self.assertEqual(add.call_args.args[3], mode)

    def test_missing_or_empty_music_directory_fails_before_render(self):
        for kind in ("missing", "empty", "non-audio"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "photo.jpg").touch()
                music = root / "music"
                if kind != "missing":
                    music.mkdir()
                if kind == "non-audio":
                    (music / "notes.json").touch()
                with (
                    patch.object(sys, "argv", ["media_to_video.py", temp, "--music", str(music)]),
                    patch("media_to_video.shutil.which", return_value="ffmpeg"),
                    patch("media_to_video.render_photo") as render,
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit) as error,
                ):
                    main()
                self.assertEqual(error.exception.code, 2)
                render.assert_not_called()


if __name__ == "__main__":
    unittest.main()
