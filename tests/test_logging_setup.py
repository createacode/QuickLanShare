from __future__ import annotations

import logging
import os
import re
import time
import unittest
from pathlib import Path

from quicklanshare.utils.logging_setup import (
    LOG_FILE_RE,
    SessionFileHandler,
    cleanup_old_logs,
    setup_logging,
)


class LoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(__file__).parent / "_tmp_logs"
        self.directory.mkdir(parents=True, exist_ok=True)
        for item in self.directory.glob("*"):
            item.unlink(missing_ok=True)

    def tearDown(self) -> None:
        for item in self.directory.glob("*"):
            item.unlink(missing_ok=True)
        self.directory.rmdir()

    def test_file_name_pattern_and_content(self) -> None:
        session = setup_logging(self.directory, "INFO", console=False)
        session.logger.info("hello 日志")
        handler = session.handler
        self.assertIsNotNone(handler)
        assert handler is not None and handler.current_path is not None
        handler.flush()
        path = handler.current_path
        self.assertRegex(path.name, LOG_FILE_RE)
        self.assertIn("hello 日志", path.read_text(encoding="utf-8"))
        handler.close()

    def test_rotation_creates_new_file_after_size_limit(self) -> None:
        handler = SessionFileHandler(self.directory, max_bytes=64 * 1024)
        handler.setFormatter(logging.Formatter("%(message)s"))
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "x" * 40000, None, None)
        handler.emit(record)
        first = handler.current_path
        handler.emit(record)
        second = handler.current_path
        handler.close()
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(list(self.directory.glob("log_*.log"))), 2)

    def test_cleanup_keeps_newest_and_removes_old(self) -> None:
        old = self.directory / "log_20200101_000000_00.log"
        old.write_text("old", encoding="utf-8")
        past = time.time() - 40 * 86400
        os.utime(old, (past, past))
        for index in range(5):
            (self.directory / f"log_20260101_00000{index}_00.log").write_text(
                "new", encoding="utf-8"
            )
        removed = cleanup_old_logs(self.directory, max_age_days=30, max_files=3)
        self.assertGreaterEqual(removed, 1)
        self.assertFalse(old.exists())
        remaining = list(self.directory.glob("log_*.log"))
        self.assertLessEqual(len(remaining), 3)

    def test_unmatched_files_are_ignored(self) -> None:
        keep = self.directory / "faulthandler.log"
        keep.write_text("x", encoding="utf-8")
        removed = cleanup_old_logs(self.directory, max_age_days=0, max_files=0)
        self.assertEqual(removed, 0)
        self.assertTrue(keep.exists())
        self.assertTrue(re.match(LOG_FILE_RE, "log_20261104_201500_00.log"))


if __name__ == "__main__":
    unittest.main()
