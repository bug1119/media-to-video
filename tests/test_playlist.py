import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_to_video import build_music_playlist


class PlaylistTest(unittest.TestCase):
    def test_shuffle_cycles_avoid_adjacent_repeat_and_normalize_once(self):
        with tempfile.TemporaryDirectory() as temp:
            tracks = [Path("a.mp3"), Path("b.flac"), Path("c.wav")]
            with (
                patch("media_to_video.media_duration", side_effect=[7, 2, 2, 2]),
                patch("media_to_video.random.shuffle"),
                patch("media_to_video.run") as run,
                contextlib.redirect_stdout(io.StringIO()) as summary,
            ):
                manifest = build_music_playlist(Path("video.mp4"), tracks[2], tracks, Path(temp))
            self.assertEqual(run.call_count, 3)
            lines = manifest.read_text().splitlines()
            self.assertEqual(len(lines), 4)
            self.assertNotEqual(lines[2], lines[3])
            self.assertIn("起始 6.00 秒", summary.getvalue())


if __name__ == "__main__":
    unittest.main()
