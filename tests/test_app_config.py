from __future__ import annotations

import json
import unittest
from pathlib import Path

from quicklanshare.utils.app_config import (
    AppConfig,
    load_config,
    save_config,
)


class AppConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(__file__).parent / "_tmp_config"
        self._tmp.mkdir(parents=True, exist_ok=True)
        self.path = self._tmp / "config.json"
        for suffix in ("", ".bak", ".corrupt", ".tmp"):
            (self._tmp / f"config.json{suffix}").unlink(missing_ok=True)

    def tearDown(self) -> None:
        for item in self._tmp.glob("*"):
            item.unlink(missing_ok=True)
        self._tmp.rmdir()

    def test_defaults_match_product_policy(self) -> None:
        config = AppConfig()
        self.assertEqual(config.schema_version, 1)
        self.assertEqual(config.server.port, 8888)
        self.assertTrue(config.server.auto_shutdown_enabled)
        self.assertEqual(config.server.auto_shutdown_hours, 24.0)
        self.assertFalse(config.server.open_browser)
        self.assertTrue(config.ui.close_to_tray)

    def test_missing_file_creates_default(self) -> None:
        result = load_config(self.path)
        self.assertTrue(self.path.exists())
        self.assertEqual(result.config.server.port, 8888)
        self.assertEqual(result.messages, [])

    def test_roundtrip_and_backup(self) -> None:
        config = AppConfig()
        config.server.port = 9090
        config.server.auto_shutdown_enabled = False
        config.server.open_browser = True
        config.ui.log_level = "DEBUG"
        save_config(config, self.path)
        save_config(config, self.path)
        self.assertTrue(self.path.with_name("config.json.bak").exists())
        loaded = load_config(self.path)
        self.assertEqual(loaded.config.server.port, 9090)
        self.assertFalse(loaded.config.server.auto_shutdown_enabled)
        self.assertTrue(loaded.config.server.open_browser)
        self.assertEqual(loaded.config.ui.log_level, "DEBUG")

    def test_corrupt_file_falls_back_and_is_preserved(self) -> None:
        self.path.write_text("{not valid json", encoding="utf-8")
        result = load_config(self.path)
        self.assertEqual(result.config.server.port, 8888)
        corrupt = self.path.with_name("config.json.corrupt")
        self.assertTrue(corrupt.exists())
        self.assertIn("损坏", "".join(result.messages))
        self.assertTrue(self.path.exists())

    def test_invalid_values_are_clamped(self) -> None:
        payload = {
            "schema_version": 99,
            "server": {
                "port": 99999,
                "auto_shutdown_hours": -2,
                "auto_shutdown_enabled": "yes",
                "open_browser": True,
            },
            "ui": {"log_level": "NOPE", "column_widths": [10, 20, 30]},
            "window": {"width": 10, "height": 10},
        }
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        config = load_config(self.path).config
        self.assertEqual(config.server.port, 65535)
        self.assertEqual(config.server.auto_shutdown_hours, 0.1)
        self.assertTrue(config.server.auto_shutdown_enabled)
        self.assertEqual(config.ui.log_level, "INFO")
        self.assertEqual(len(config.ui.column_widths), 5)
        self.assertGreaterEqual(config.window.width, 800)
        self.assertGreaterEqual(config.window.height, 520)
        self.assertEqual(config.schema_version, 1)


if __name__ == "__main__":
    unittest.main()
