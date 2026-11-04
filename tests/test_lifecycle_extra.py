from __future__ import annotations

import asyncio
import socket
import tempfile
import unittest
from pathlib import Path

from quicklanshare.services.config import Config
from quicklanshare.services.server import FileTransferServer


class PortFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)

    async def test_port_falls_back_when_occupied(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            blocker.bind(("127.0.0.1", 0))
            blocked_port = blocker.getsockname()[1]
            blocker.listen(1)
            try:
                config = Config(
                    host="127.0.0.1",
                    port=blocked_port,
                    port_attempts=3,
                    data_dir=Path(tmp),
                    open_browser=False,
                    auto_shutdown_enabled=False,
                    access_log=False,
                    allow_any_host=True,
                )
                server = FileTransferServer(config)
                try:
                    actual = await server.start()
                finally:
                    await server.aclose()
                self.assertGreater(actual, blocked_port)
                self.assertLessEqual(actual, blocked_port + 3)
            finally:
                blocker.close()


if __name__ == "__main__":
    unittest.main()
