import os
import tempfile
import unittest

import deps


class PathOrderingTests(unittest.TestCase):
    def test_existing_ffmpeg_dir_is_moved_to_front_and_deduplicated(self):
        original = os.environ.get("PATH", "")
        try:
            with tempfile.TemporaryDirectory() as root:
                stale = os.path.join(root, "stale")
                current = os.path.join(root, "current")
                os.makedirs(stale)
                os.makedirs(current)
                os.environ["PATH"] = os.pathsep.join((stale, current, stale))

                deps._prepend_path_dirs([current])

                parts = os.environ["PATH"].split(os.pathsep)
                self.assertEqual(os.path.normcase(parts[0]), os.path.normcase(current))
                self.assertEqual(parts.count(current), 1)
                self.assertEqual(parts.count(stale), 1)
        finally:
            os.environ["PATH"] = original


if __name__ == "__main__":
    unittest.main()
