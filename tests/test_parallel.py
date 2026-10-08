import contextlib
import io
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from media_to_video import main


class ParallelTest(unittest.TestCase):
    def test_parallel_rendering_preserves_order_and_passes_threads(self):
        for options, threads in (([], 4), (["--workers", "2", "--threads", "3"], 3)):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                (directory / "01.jpg").touch()
                (directory / "02.mp4").touch()
                barrier = threading.Barrier(2, timeout=5)
                second_finished = threading.Event()

                def photo(source, output, *args):
                    self.assertEqual(args[-1], threads)
                    barrier.wait()
                    self.assertTrue(second_finished.wait(timeout=5))

                def video(source, output, *args):
                    self.assertEqual(args[-1], threads)
                    barrier.wait()
                    second_finished.set()

                argv = ["media_to_video.py", temp, "--resolution", "320x180", *options]
                with (
                    patch.object(sys, "argv", argv),
                    patch("media_to_video.shutil.which", return_value="ffmpeg"),
                    patch("media_to_video.render_photo", side_effect=photo),
                    patch("media_to_video.render_video", side_effect=video),
                    patch("media_to_video.concat_segments") as concat,
                    patch("media_to_video.shutil.copy2"),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(main(), 0)
                segments = concat.call_args.args[0]
                self.assertEqual(
                    [segment.name for segment in segments],
                    ["segment-000001.mp4", "segment-000002.mp4"],
                )
                self.assertFalse(segments[0].parent.exists())

    def test_invalid_worker_and_thread_counts(self):
        for option in ("--workers", "--threads"):
            for value in ("0", "-1", "1.5"):
                with self.subTest(option=option, value=value), tempfile.TemporaryDirectory() as temp:
                    with (
                        patch.object(sys, "argv", ["media_to_video.py", temp, option, value]),
                        patch("media_to_video.shutil.which", return_value="ffmpeg"),
                        contextlib.redirect_stderr(io.StringIO()),
                        self.assertRaises(SystemExit) as error,
                    ):
                        main()
                    self.assertEqual(error.exception.code, 2)

    def test_render_failure_prevents_concatenation_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "01.jpg").touch()
            outputs = []

            def fail(source, output, *args):
                outputs.append(output)
                raise subprocess.CalledProcessError(1, ["ffmpeg"])

            with (
                patch.object(sys, "argv", ["media_to_video.py", temp, "--resolution", "320x180"]),
                patch("media_to_video.shutil.which", return_value="ffmpeg"),
                patch("media_to_video.render_photo", side_effect=fail),
                patch("media_to_video.concat_segments") as concat,
                contextlib.redirect_stdout(io.StringIO()),
                self.assertRaises(subprocess.CalledProcessError),
            ):
                main()
            concat.assert_not_called()
            self.assertFalse(outputs[0].parent.exists())


if __name__ == "__main__":
    unittest.main()
