import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_to_video import collect_media, convert_photo_to_jpg, main


class PhotoTest(unittest.TestCase):
    def test_heic_and_heif_are_included_case_insensitively(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for name in ("photo.jpg", "photo.HEIC", "photo.heif", "image.png"):
                (root / name).touch()
            with contextlib.redirect_stdout(io.StringIO()) as summary:
                media = collect_media(root, root / "output.mp4")
            self.assertEqual([path.name for path in media], ["image.png", "photo.HEIC", "photo.heif", "photo.jpg"])

    def test_non_jpeg_photos_are_converted_before_rendering_and_cleaned(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for name in ("01.JPG", "02.jpeg", "03.PNG", "04.webp", "05.HEIC", "06.heif"):
                (root / name).touch()
            conversions = {}
            rendered = []

            def convert(source, output):
                conversions[source.name] = output
                output.write_bytes(b"converted")

            def render(source, *args):
                rendered.append(source)
                self.assertTrue(source.exists())
                self.assertIn(source.suffix.lower(), (".jpg", ".jpeg"))

            with (
                patch.object(sys, "argv", [
                    "media_to_video.py", temp, "--output", str(root / "output.mp4"),
                    "--audio-mode", "original",
                ]),
                patch("media_to_video.shutil.which", return_value="ffmpeg"),
                patch("media_to_video.convert_photo_to_jpg", side_effect=convert),
                patch("media_to_video.auto_resolution", return_value=(320, 180)) as resolution,
                patch("media_to_video.render_photo", side_effect=render),
                patch("media_to_video.concat_segments"),
                patch("media_to_video.shutil.copy2"),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main(), 0)
            self.assertEqual(set(conversions), {"03.PNG", "04.webp", "05.HEIC", "06.heif"})
            self.assertEqual(len(rendered), 6)
            self.assertTrue(all(path.suffix.lower() in {".jpg", ".jpeg"} for path in resolution.call_args.args[0]))
            self.assertTrue(all(not path.exists() for path in conversions.values()))
            self.assertEqual((root / "03.PNG").read_bytes(), b"")

    def test_heic_uses_sips_when_available_and_ffmpeg_otherwise(self):
        for available in (True, False):
            with self.subTest(available=available), patch(
                "media_to_video.shutil.which", return_value="/usr/bin/sips" if available else None,
            ), patch("media_to_video.run") as run, contextlib.redirect_stdout(io.StringIO()):
                convert_photo_to_jpg(Path("photo.HEIC"), Path("photo.jpg"))
                self.assertEqual(run.call_args.args[0][0], "sips" if available else "ffmpeg")


if __name__ == "__main__":
    unittest.main()
