import json
import os
import tempfile
import unittest

import discord_overlay


class ConfigMigrationTests(unittest.TestCase):
    def setUp(self):
        self.original_path = discord_overlay.CONFIG_PATH
        self.tempdir = tempfile.TemporaryDirectory()
        discord_overlay.CONFIG_PATH = os.path.join(self.tempdir.name, "config.json")

    def tearDown(self):
        discord_overlay.CONFIG_PATH = self.original_path
        self.tempdir.cleanup()

    def _write(self, config):
        with open(discord_overlay.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f)

    def test_new_config_uses_current_free_limit(self):
        cfg = discord_overlay.load_config()
        self.assertEqual(cfg["target_mb"], 20)
        self.assertEqual(cfg["free_limit_mb"], 20)

    def test_old_free_preset_is_migrated_to_20_mb(self):
        self._write({"target_mb": 10, "lang": "uk"})

        cfg = discord_overlay.load_config()

        self.assertEqual(cfg["target_mb"], 20)
        self.assertEqual(cfg["free_limit_mb"], 20)
        with open(discord_overlay.CONFIG_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["target_mb"], 20)

    def test_paid_tier_choice_is_preserved(self):
        self._write({"target_mb": 50})

        cfg = discord_overlay.load_config()

        self.assertEqual(cfg["target_mb"], 50)
        self.assertEqual(cfg["free_limit_mb"], 20)


if __name__ == "__main__":
    unittest.main()
