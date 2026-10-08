import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_to_video import main


class BatchTest(unittest.TestCase):
    def test_existing_outputs_are_skipped_for_single_and_batch_modes(self):
        for batch in (False, True):
            for all_existing in (False, True):
                with self.subTest(batch=batch, all_existing=all_existing), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp).resolve()
                    if batch:
                        for name in ("a", "b"):
                            (root / name).mkdir()
                            (root / name / "photo.jpg").touch()
                        output = root
                        (root / "a.mp4").write_bytes(b"existing")
                        if all_existing:
                            (root / "b.mp4").write_bytes(b"existing")
                        existing = root / "a.mp4"
                    else:
                        output = root / "result.mp4"
                        output.write_bytes(b"existing")
                        existing = output
                    summary = io.StringIO()
                    with (
                        patch.object(sys, "argv", ["media_to_video.py", temp, "--output", str(output)]),
                        patch("media_to_video.shutil.which", return_value="ffmpeg"),
                        patch("media_to_video.render_directory", return_value=(1, 0)) as render,
                        contextlib.redirect_stdout(summary),
                    ):
                        self.assertEqual(main(), 0)
                    self.assertEqual(render.call_count, 1 if batch and not all_existing else 0)
                    if render.called:
                        self.assertEqual(render.call_args.args[1], root / "b.mp4")
                    self.assertEqual(existing.read_bytes(), b"existing")
                    self.assertIn("輸出影片已存在", summary.getvalue())
                    self.assertIn("輸出影片已存在", (root / f"{root.name}.log").read_text())

    def test_single_directory_defaults_to_directory_name(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "202601"
            directory.mkdir()
            (directory / "photo.jpg").touch()
            with (
                patch.object(sys, "argv", ["media_to_video.py", str(directory)]),
                patch("media_to_video.shutil.which", return_value="ffmpeg"),
                patch("media_to_video.render_directory") as render,
            ):
                self.assertEqual(main(), 0)
            self.assertEqual(render.call_args.args[1], Path("202601.mp4").resolve())

    def test_subdirectories_produce_separate_outputs_and_skip_empty_folders(self):
        for custom_output in (False, True):
            with self.subTest(custom_output=custom_output), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                for name in ("b", "a", "empty", "nested-only"):
                    (root / name).mkdir()
                (root / "a" / "photo.JPG").touch()
                (root / "b" / "clip.mp4").touch()
                (root / "root.jpg").touch()
                (root / "nested-only" / "deeper").mkdir()
                (root / "nested-only" / "deeper" / "photo.jpg").touch()
                output_directory = root / "rendered" if custom_output else root
                argv = ["media_to_video.py", temp, "--photo-duration", "3"]
                if custom_output:
                    output_directory.mkdir()
                    (output_directory / "previous.mp4").touch()
                    argv += ["--output", str(output_directory)]
                summary = io.StringIO()
                with (
                    patch.object(sys, "argv", argv),
                    patch("media_to_video.shutil.which", return_value="ffmpeg"),
                    patch("media_to_video.render_directory", side_effect=[(1, 0), (0, 1)]) as render,
                    contextlib.redirect_stdout(summary),
                ):
                    self.assertEqual(main(), 0)
                self.assertEqual(render.call_count, 2)
                for call, name, filename in zip(render.call_args_list, ("a", "b"), ("photo.JPG", "clip.mp4")):
                    media, output, args, started = call.args
                    self.assertEqual(media, [root / name / filename])
                    self.assertEqual(output, output_directory / f"{name}.mp4")
                    self.assertEqual(args.photo_duration, 3)
                self.assertIn("跳過：", summary.getvalue())
                self.assertIn("批次完成：輸出 2 支影片，合併 1 張照片、1 部影片，共 2 個素材。", summary.getvalue())
                self.assertIn("整批執行時間：", summary.getvalue())

    def test_batch_rejects_file_output_and_empty_inputs(self):
        for output_kind in ("existing-file", "mp4-path", "empty"):
            with self.subTest(output_kind=output_kind), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "album").mkdir()
                argv = ["media_to_video.py", temp]
                if output_kind != "empty":
                    (root / "album" / "photo.jpg").touch()
                    output = root / "result.mp4"
                    if output_kind == "existing-file":
                        output.touch()
                    argv += ["--output", str(output)]
                with (
                    patch.object(sys, "argv", argv),
                    patch("media_to_video.shutil.which", return_value="ffmpeg"),
                    contextlib.redirect_stderr(io.StringIO()),
                    contextlib.redirect_stdout(io.StringIO()),
                    self.assertRaises(SystemExit) as error,
                ):
                    main()
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
