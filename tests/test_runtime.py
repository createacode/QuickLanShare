from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from quicklanshare.services.config import Config
from quicklanshare.services.runtime import RuntimeCallbacks, ServerRuntime


def make_config(directory: Path, **overrides: object) -> Config:
    values: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 0,
        "data_dir": directory,
        "auto_shutdown_enabled": False,
        "access_log": False,
        "allow_any_host": True,
    }
    values.update(overrides)
    return Config(**values)  # type: ignore[arg-type]


class RuntimeTests(unittest.TestCase):
    def test_start_stop_reports_callbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            started = threading.Event()
            stopped = threading.Event()
            events: dict[str, str] = {}

            def on_started(port: int, url: str, deadline: float) -> None:
                events["url"] = url
                events["deadline"] = str(deadline)
                events["port"] = str(port)
                started.set()

            def on_stopped(reason: str) -> None:
                events["reason"] = reason
                stopped.set()

            runtime = ServerRuntime(RuntimeCallbacks(on_started=on_started, on_stopped=on_stopped))
            runtime.start(make_config(Path(tmp)), timeout=15)
            self.assertTrue(started.wait(10))
            self.assertTrue(runtime.is_running)
            self.assertGreater(runtime.port, 0)
            self.assertTrue(runtime.share_url.startswith("http://"))
            runtime.stop("test-stop")
            self.assertTrue(stopped.wait(10))
            self.assertFalse(runtime.is_running)
            self.assertEqual(events.get("reason"), "test-stop")

    def test_auto_shutdown_can_be_disabled_and_reconfigured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            started = threading.Event()
            stopped = threading.Event()
            runtime = ServerRuntime(
                RuntimeCallbacks(
                    on_started=lambda *_: started.set(),
                    on_stopped=lambda *_: stopped.set(),
                )
            )
            config = make_config(Path(tmp), auto_shutdown_enabled=True, auto_shutdown_hours=1.0)
            runtime.start(config, timeout=15)
            self.assertTrue(started.wait(10))
            self.assertGreater(runtime.auto_shutdown_deadline, time.time())
            self.assertGreater(runtime.remaining_seconds(), 3000)

            future = runtime.update_auto_shutdown(False, 0.0)
            self.assertEqual(future.result(timeout=5), 0.0)
            self.assertEqual(runtime.auto_shutdown_deadline, 0.0)

            future = runtime.update_auto_shutdown(True, 2.0)
            deadline = future.result(timeout=5)
            self.assertGreater(deadline, time.time())
            self.assertGreater(runtime.remaining_seconds(), 7000)

            runtime.stop("test-stop")
            self.assertTrue(stopped.wait(10))

    def test_auto_shutdown_timer_stops_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stopped = threading.Event()
            reasons: list[str] = []
            runtime = ServerRuntime(
                RuntimeCallbacks(on_stopped=lambda reason: (reasons.append(reason), stopped.set()))
            )
            runtime.start(
                make_config(
                    Path(tmp),
                    auto_shutdown_enabled=True,
                    auto_shutdown_hours=0.0005,
                ),
                timeout=15,
            )
            self.assertTrue(stopped.wait(10))
            self.assertEqual(reasons, ["auto-shutdown"])
            self.assertFalse(runtime.is_running)


if __name__ == "__main__":
    unittest.main()
