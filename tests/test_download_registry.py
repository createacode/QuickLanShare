from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quicklanshare.services.download_registry import DownloadRegistry


class DownloadRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.registry_path = self.root / "state" / "downloads.json"
        self.local = self.root / "a.txt"
        self.local.write_text("data", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_record_persist_and_remove(self) -> None:
        registry = DownloadRegistry(self.registry_path)
        self.assertEqual(registry.all(), {})
        registry.record("a.txt", self.local)
        self.assertEqual(registry.get("a.txt"), self.local)
        self.assertEqual(registry.count(), 1)

        reloaded = DownloadRegistry(self.registry_path)
        self.assertEqual(reloaded.get("a.txt"), self.local)
        reloaded.remove(["a.txt"])
        self.assertIsNone(reloaded.get("a.txt"))
        self.assertEqual(DownloadRegistry(self.registry_path).all(), {})

    def test_missing_target_is_dropped_on_load(self) -> None:
        registry = DownloadRegistry(self.registry_path)
        registry.record("gone.txt", self.local)
        self.local.unlink()
        reloaded = DownloadRegistry(self.registry_path)
        self.assertEqual(reloaded.all(), {})

    def test_corrupt_file_is_preserved(self) -> None:
        self.registry_path.parent.mkdir(parents=True)
        self.registry_path.write_text("{bad", encoding="utf-8")
        registry = DownloadRegistry(self.registry_path)
        self.assertEqual(registry.all(), {})
        self.assertTrue(self.registry_path.with_name("downloads.json.corrupt").exists())

    def test_payload_shape(self) -> None:
        registry = DownloadRegistry(self.registry_path)
        registry.record("a.txt", self.local)
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["files"]["a.txt"], str(self.local))


if __name__ == "__main__":
    unittest.main()
