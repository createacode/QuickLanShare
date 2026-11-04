"""单实例守卫：使用 QLocalServer / QLocalSocket 激活已运行窗口。

服务名带当前用户标识，避免多用户会话互相干扰；第二个实例连接成功后发送
激活消息并退出，不创建主窗口。首个实例收到消息后显示窗口并置顶。
"""

from __future__ import annotations

import contextlib
import getpass
import hashlib
import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger("quicklanshare.single_instance")

_MESSAGE = b"activate"


def _server_name(app_name: str = "QuickLanShare") -> str:
    try:
        user = getpass.getuser()
    except Exception:  # pragma: no cover - 无用户环境变量
        user = "default"
    digest = hashlib.sha1(user.encode("utf-8", errors="replace")).hexdigest()[:10]
    return f"{app_name}-{digest}"


class SingleInstanceGuard(QObject):
    """获取单实例锁；失败时表示已有实例并在运行。"""

    activated = Signal()

    def __init__(self, app_name: str = "QuickLanShare", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._name = _server_name(app_name)
        self._server: QLocalServer | None = None

    @property
    def server_name(self) -> str:
        return self._name

    def acquire(self) -> bool:
        """返回 ``True`` 表示本进程是首个实例。"""
        socket = QLocalSocket(self)
        socket.connectToServer(self._name)
        if socket.waitForConnected(400):
            socket.write(_MESSAGE)
            socket.flush()
            socket.waitForBytesWritten(400)
            socket.disconnectFromServer()
            logger.info("检测到已运行实例，发送激活消息")
            return False

        QLocalServer.removeServer(self._name)
        server = QLocalServer(self)
        with contextlib.suppress(AttributeError):  # pragma: no cover - 旧版本 Qt
            server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(self._name):
            logger.warning("单实例监听失败（%s），继续启动", server.errorString())
            return True
        server.newConnection.connect(self._on_new_connection)
        self._server = server
        logger.info("单实例守卫已就绪: %s", self._name)
        return True

    def _on_new_connection(self) -> None:
        server = self._server
        if server is None:
            return
        while server.hasPendingConnections():
            connection = server.nextPendingConnection()
            if connection is None:
                continue
            connection.readyRead.connect(connection.readAll)
            connection.disconnected.connect(connection.deleteLater)
            connection.readAll()
            logger.info("收到新实例激活请求，显示主窗口")
            self.activated.emit()


__all__ = ["SingleInstanceGuard"]
