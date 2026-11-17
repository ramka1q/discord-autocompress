import os
import shutil
import subprocess
import tempfile
import unittest

import dc_core
import media

HAVE_FF = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _ff(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                   check=True, creationflags=dc_core.NO_WINDOW)


def _probe(path, entries):
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                           "-show_entries", entries, "-of", "csv=p=0", path],
                          capture_output=True, text=True,
                          creationflags=dc_core.NO_WINDOW).stdout.strip()


class ScaleTests(unittest.TestCase):
    def test_portrait_uses_short_side(self):
        # вертикальне 1080x1920 при достатньому бітрейті не зменшується
        info = {"duration": 10, "width": 1080, "height": 1920, "has_audio": True}
        self.assertEqual(dc_core.pick_auto_scale(info, 20, 128), 0)

    def test_never_upscales_small_video(self):
        info = {"duration": 3000, "width": 320, "height": 240, "has_audio": True}
        self.assertEqual(dc_core.pick_auto_scale(info, 20, 128), 0)

    def test_long_video_is_downscaled(self):
        info = {"duration": 600, "width": 1920, "height": 1080, "has_audio": True}
        self.assertIn(dc_core.pick_auto_scale(info, 20, 128), (480, 360, 240))


class MessageTests(unittest.TestCase):
    def tearDown(self):
        dc_core.LANG = "en"

    def test_messages_follow_language(self):
        dc_core.LANG = "en"
        self.assertEqual(dc_core.cancelled_msg(), "Cancelled.")
        dc_core.LANG = "uk"
        self.assertEqual(dc_core.cancelled_msg(), "Скасовано.")

    def test_low_bitrate_message_is_localized(self):
        dc_core.LANG = "en"
        info = {"duration": 100000, "width": 640, "height": 360, "has_audio": False, "fps": 30}
        ok, msg, _ = dc_core.compress("x.mp4", "y.mp4", 1, 0, 0, info)
        self.assertFalse(ok)
        self.assertIn("Bitrate", msg)


class OutputDirTests(unittest.TestCase):
    def test_writable_dir_keeps_original_folder(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "clip.mp4")
            self.assertEqual(dc_core.output_name(p, 20), os.path.join(d, "clip_discord_20mb.mp4"))

    def test_missing_dir_falls_back_to_temp(self):
        p = os.path.join(tempfile.gettempdir(), "no_such_dir_dac_test", "clip.mp4")
        out = dc_core.output_name(p, 20)
        self.assertTrue(out.startswith(dc_core.FALLBACK_DIR))
        self.assertTrue(out.endswith("clip_discord_20mb.mp4"))


@unittest.skipUnless(HAVE_FF, "ffmpeg missing")
class EncodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="dac_test_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_yuv444_source_becomes_playable_yuv420p(self):
        src = os.path.join(self.tmp, "src444.mp4")
        _ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=4", "-f", "lavfi", "-i", "sine=d=4",
            "-pix_fmt", "yuv444p", "-c:v", "libx264", "-c:a", "aac", "-shortest", src)
        info = dc_core.ffprobe_info(src)
        out = os.path.join(self.tmp, "out.mp4")
        ok, msg, mb = dc_core.compress(src, out, 1, 0, 64, info)
        self.assertTrue(ok, msg)
        self.assertLessEqual(mb, dc_core.target_ceiling(1))
        self.assertEqual(_probe(out, "stream=pix_fmt"), "yuv420p")

    def test_portrait_trim_keeps_orientation(self):
        src = os.path.join(self.tmp, "portrait.mp4")
        _ff("-f", "lavfi", "-i", "testsrc2=s=360x640:r=30:d=4", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", src)
        info = dc_core.ffprobe_info(src)
        out = os.path.join(self.tmp, "portrait_out.mp4")
        ok, msg, _ = dc_core.compress(src, out, 1, 240, 0, info, start=1.0, dur=2.0)
        self.assertTrue(ok, msg)
        w, h = (int(v) for v in _probe(out, "stream=width,height").split(","))
        self.assertEqual(w, 240)
        self.assertGreater(h, w)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                    "-of", "csv=p=0", out], capture_output=True, text=True,
                                   creationflags=dc_core.NO_WINDOW).stdout)
        self.assertAlmostEqual(dur, 2.0, delta=0.15)

    def test_split_produces_parts_under_limit(self):
        src = os.path.join(self.tmp, "long.mp4")
        _ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=15:d=6", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", src)
        info = dc_core.ffprobe_info(src)
        ok, msg, outs = dc_core.split_compress(src, 1, False, 0, info, n_parts=2)
        self.assertTrue(ok, msg)
        self.assertEqual(len(outs), 2)
        for p in outs:
            self.assertLessEqual(os.path.getsize(p) / 1048576, dc_core.target_ceiling(1))

    def test_animated_gif_stays_animated_and_loops(self):
        src = os.path.join(self.tmp, "anim.gif")
        _ff("-f", "lavfi", "-i", "testsrc2=s=200x200:r=10:d=2", src)
        out = os.path.join(self.tmp, "anim.webp")
        ok, msg, mb = media.compress_image(src, out, 1)
        self.assertTrue(ok, msg)
        with open(out, "rb") as f:
            data = f.read()
        self.assertIn(b"ANIM", data)          # анімований WebP
        anim = data.index(b"ANIM")
        loops = int.from_bytes(data[anim + 12:anim + 14], "little")
        self.assertEqual(loops, 0)            # 0 = крутиться без кінця

    def test_cpu_mode_and_forced_encoders(self):
        src = os.path.join(self.tmp, "enc.mp4")
        _ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", src)
        info = dc_core.ffprobe_info(src)
        dc_core.configure({"encoder": "cpu"})
        try:
            self.assertEqual(dc_core.active_hw(), "")
            out = os.path.join(self.tmp, "cpu.mp4")
            ok, msg, mb = dc_core.compress(src, out, 0.5, 0, 0, info)
            self.assertTrue(ok, msg)
            self.assertLessEqual(mb, dc_core.target_ceiling(0.5))
        finally:
            dc_core.configure({})
        hw = dc_core.hw_encoder()
        if hw:
            out = os.path.join(self.tmp, "gpu.mp4")
            ok, msg, mb = dc_core.compress(src, out, 0.5, 0, 0, info, force_enc=hw)
            self.assertTrue(ok, msg)
            self.assertLessEqual(mb, dc_core.target_ceiling(0.5))
            self.assertEqual(_probe(out, "stream=pix_fmt"), "yuv420p")

    def test_auto_mode_follows_benchmark(self):
        dc_core.configure({"encoder": "auto", "encoder_best": "x264"})
        try:
            self.assertEqual(dc_core.active_hw(), "")
        finally:
            dc_core.configure({})

    def test_big_image_fits_limit(self):
        src = os.path.join(self.tmp, "noise.png")
        _ff("-f", "lavfi", "-i", "nullsrc=s=2400x1800,geq=random(1)*255:128:128", "-frames:v", "1", src)
        out = os.path.join(self.tmp, "noise.webp")
        ok, msg, mb = media.compress_image(src, out, 0.5)
        self.assertTrue(ok, msg)
        self.assertLessEqual(mb, dc_core.target_ceiling(0.5))


if __name__ == "__main__":
    unittest.main()
