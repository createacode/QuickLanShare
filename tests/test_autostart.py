from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from quicklanshare.services import autostart
from quicklanshare.services.autostart import (
    AutostartError,
    build_command,
    is_enabled,
)


@unittest.skipUnless(sys.platform == "win32", "Windows registry only")
class AutostartRegistryTests(unittest.TestCase):
    def test_enable_writes_run_value(self) -> None:
        with (
            patch("winreg.CreateKeyEx") as create_key,
            patch("winreg.SetValueEx") as set_value,
        ):
            autostart.apply_autostart(True, True)
        create_key.assert_called_once()
        args = set_value.call_args[0]
        self.assertEqual(args[1], autostart.VALUE_NAME)
        self.assertIn("--autostart", args[4])
        self.assertIn("--silent", args[4])

    def test_disable_deletes_run_value(self) -> None:
        with (
            patch("winreg.CreateKeyEx"),
            patch("winreg.DeleteValue") as delete_value,
        ):
            autostart.apply_autostart(False, False)
        delete_value.assert_called_once()

    def test_disable_missing_value_is_ignored(self) -> None:
        with (
            patch("winreg.CreateKeyEx"),
            patch("winreg.DeleteValue", side_effect=FileNotFoundError),
        ):
            autostart.apply_autostart(False, False)

    def test_registry_failure_is_reported(self) -> None:
        with (
            patch("winreg.CreateKeyEx", side_effect=OSError("denied")),
            self.assertRaises(AutostartError),
        ):
            autostart.apply_autostart(True, False)

    def test_is_enabled_reads_value(self) -> None:
        with (
            patch("winreg.OpenKey"),
            patch("winreg.QueryValueEx", return_value=("cmd", 1)),
        ):
            self.assertTrue(is_enabled())
        with (
            patch("winreg.OpenKey"),
            patch("winreg.QueryValueEx", side_effect=FileNotFoundError),
        ):
            self.assertFalse(is_enabled())


class AutostartCommandTests(unittest.TestCase):
    def test_frozen_command(self) -> None:
        command = build_command(
            False,
            frozen=True,
            executable=r"C:\Program Files\QuickLanShare\QuickLanShare.exe",
        )
        self.assertEqual(command.parts[0], r"C:\Program Files\QuickLanShare\QuickLanShare.exe")
        self.assertIn("--autostart", command.parts)
        self.assertNotIn("--silent", command.parts)
        self.assertIn('"C:\\Program Files\\QuickLanShare\\QuickLanShare.exe"', command.command_line)

    def test_silent_flag(self) -> None:
        command = build_command(True, frozen=True, executable=r"C:\Apps\QuickLanShare.exe")
        self.assertEqual(command.parts[-1], "--silent")
        self.assertIn('"C:\\Apps\\QuickLanShare.exe"', command.command_line)

    def test_dev_command_uses_script(self) -> None:
        command = build_command(False, frozen=False, executable=r"C:\Python311\python.exe")
        self.assertTrue(command.parts[0].endswith("python.exe"))
        self.assertTrue(command.parts[1].endswith("main.py"))
        self.assertEqual(command.parts[-1], "--autostart")


if __name__ == "__main__":
    unittest.main()
