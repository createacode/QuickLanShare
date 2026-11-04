"""文本共享面板：与网页端实时同步的消息流、输入与发送。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..utils.format import human_time  # noqa: F401 - 保留给测试/外部复用
from . import theme

MAX_MESSAGE_LENGTH = 500
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _parse_time(message: dict[str, Any]) -> datetime:
    try:
        stamp = float(message.get("timestamp") or 0)
    except (TypeError, ValueError):
        stamp = 0.0
    if stamp > 0:
        try:
            return datetime.fromtimestamp(stamp)
        except (OSError, OverflowError, ValueError):
            pass
    text = str(message.get("time_str") or "")
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return datetime.now()


def _date_label(moment: datetime) -> str:
    today = datetime.now().date()
    if moment.date() == today:
        return "今天"
    delta = (today - moment.date()).days
    if delta == 1:
        return "昨天"
    return f"{moment.month}月{moment.day}日"


def _is_own(message: dict[str, Any]) -> bool:
    return str(message.get("client_ip") or "") in _LOOPBACK


def _message_time(message: dict[str, Any]) -> str:
    raw = str(message.get("time_str") or "")
    if len(raw) >= 5:
        return raw[-5:]
    return _parse_time(message).strftime("%H:%M")


class MessageBubble(QFrame):
    """一条文本消息气泡。"""

    deleteRequested = Signal(str)

    def __init__(self, message: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.message = message
        self._message_id = str(message.get("id") or "")
        own = _is_own(message)
        self.setObjectName("OwnBubble" if own else "OtherBubble")
        self.setMaximumWidth(380)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 9)
        layout.setSpacing(3)

        meta = QHBoxLayout()
        meta.setSpacing(8)
        sender = "我" if own else str(message.get("client_name") or "访客")
        name_label = QLabel(sender)
        name_label.setStyleSheet(
            f"color: {theme.ACCENT if own else theme.TEXT_SECONDARY}; font-size: 11px; font-weight: 600;"
        )
        meta.addWidget(name_label)
        meta.addStretch(1)
        time_label = QLabel(_message_time(message))
        time_label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px;")
        meta.addWidget(time_label)
        layout.addLayout(meta)

        text = QLabel(str(message.get("message") or ""))
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.setStyleSheet(f"color: {theme.TEXT}; font-size: 13px; line-height: 1.5;")
        layout.addWidget(text)
        raw_text = str(message.get("message") or "")
        metrics = text.fontMetrics()
        self.preferred_width = min(360, max(120, metrics.horizontalAdvance(raw_text) + 34))

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

    @property
    def message_id(self) -> str:
        return self._message_id

    def _show_menu(self, position: QPoint) -> None:
        menu = QMenu(self)
        copy_action = QAction("复制文本", menu)
        copy_action.triggered.connect(self.copy_text)
        menu.addAction(copy_action)
        delete_action = QAction("删除消息", menu)
        delete_action.triggered.connect(lambda: self.deleteRequested.emit(self._message_id))
        menu.addAction(delete_action)
        menu.exec(self.mapToGlobal(position))

    def copy_text(self) -> None:
        QGuiApplication.clipboard().setText(str(self.message.get("message") or ""))

    def mouseDoubleClickEvent(self, event: Any) -> None:
        self.copy_text()
        event.accept()


class TextPanel(QFrame):
    """消息流 + 输入框；数据来自服务端聊天室。"""

    sendRequested = Signal(str)
    deleteRequested = Signal(str)
    historyRefreshRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumWidth(330)
        theme.add_shadow(self)

        self._messages: dict[str, dict[str, Any]] = {}
        self._bubbles: dict[str, QWidget] = {}
        self._last_date = ""
        self._service_available = False
        self._sync_status = "offline"
        self._empty = QLabel("还没有共享文本\n发送第一条消息，手机和电脑都能看到")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)
        self._empty.setMinimumHeight(120)
        self._empty.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(4000)
        self._poll_timer.timeout.connect(self._poll_history)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("文本共享")
        title.setObjectName("SectionTitle")
        title_box.addWidget(title)
        self._subtitle = QLabel("与网页端共用同一份记录")
        self._subtitle.setObjectName("Muted")
        title_box.addWidget(self._subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        self._sync_chip = QLabel("已停止")
        self._sync_chip.setObjectName("StatusChip")
        self._sync_chip.setProperty("state", "error")
        header.addWidget(self._sync_chip)
        layout.addLayout(header)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("ChatScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._container = QWidget()
        self._messages_layout = QVBoxLayout(self._container)
        self._messages_layout.setContentsMargins(2, 4, 2, 4)
        self._messages_layout.setSpacing(8)
        self._messages_layout.addStretch(1)
        self._scroll.setWidget(self._container)

        self._empty_page = QWidget()
        empty_layout = QVBoxLayout(self._empty_page)
        empty_layout.setContentsMargins(16, 16, 16, 16)
        empty_layout.addStretch(1)
        empty_layout.addWidget(self._empty)
        empty_layout.addStretch(1)

        self._area = QStackedWidget()
        self._area.setObjectName("ChatArea")
        self._area.addWidget(self._scroll)
        self._area.addWidget(self._empty_page)
        self._area.setCurrentWidget(self._empty_page)
        layout.addWidget(self._area, 1)
        self._new_button = QPushButton("有新消息 ↓")
        self._new_button.setProperty("role", "soft")
        self._new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_button.clicked.connect(self._scroll_to_bottom)
        self._new_button.hide()
        layout.addWidget(self._new_button, 0, Qt.AlignmentFlag.AlignHCenter)

        composer = QFrame()
        composer.setObjectName("Composer")
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(12, 8, 8, 8)
        composer_layout.setSpacing(8)
        self._input = QLineEdit()
        self._input.setPlaceholderText("输入文字，Enter 发送")
        self._input.setMaxLength(MAX_MESSAGE_LENGTH)
        self._input.setFrame(False)
        self._input.setEnabled(False)
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._send)
        composer_layout.addWidget(self._input, 1)
        self._counter = QLabel(f"0/{MAX_MESSAGE_LENGTH}")
        self._counter.setObjectName("Muted")
        self._counter.setFixedWidth(54)
        self._counter.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        composer_layout.addWidget(self._counter)
        self._send_button = QPushButton("发送")
        self._send_button.setProperty("role", "primary")
        self._send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_button.setFixedHeight(34)
        self._send_button.setEnabled(False)
        self._send_button.clicked.connect(self._send)
        composer_layout.addWidget(self._send_button)
        layout.addWidget(composer)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet(f"color: {theme.DANGER}; font-size: 11px;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)
        self._error_timer = QTimer(self)
        self._error_timer.setSingleShot(True)
        self._error_timer.setInterval(5000)
        self._error_timer.timeout.connect(self._error_label.hide)

    # ------------------------------------------------------------------ state
    @property
    def input(self) -> QLineEdit:
        return self._input

    @property
    def send_button(self) -> QPushButton:
        return self._send_button

    @property
    def sync_chip(self) -> QLabel:
        return self._sync_chip

    @property
    def message_count(self) -> int:
        return len(self._messages)

    def messages(self) -> list[dict[str, Any]]:
        return list(self._messages.values())

    def set_service_available(self, available: bool) -> None:
        self._service_available = available
        self._input.setEnabled(available)
        self._send_button.setEnabled(available and bool(self._input.text().strip()))
        if not available:
            self._input.setPlaceholderText("启动服务后可发送文本")
            self._sync_chip.setText("已停止")
            self._set_chip_state("error")
            self._poll_timer.stop()
        else:
            self._input.setPlaceholderText("输入文字，Enter 发送")

    def set_sync_status(self, status: str) -> None:
        self._sync_status = status
        mapping = {
            "connected": ("实时同步", "ok"),
            "connecting": ("连接中", "busy"),
            "reconnecting": ("重连中", "warn"),
            "offline": ("已停止", "error"),
        }
        text, state = mapping.get(status, ("已停止", "error"))
        self._sync_chip.setText(text)
        self._set_chip_state(state)
        if status in ("reconnecting", "connecting"):
            self._poll_timer.start()
        else:
            self._poll_timer.stop()

    def _set_chip_state(self, state: str) -> None:
        self._sync_chip.setProperty("state", state)
        self._sync_chip.style().unpolish(self._sync_chip)
        self._sync_chip.style().polish(self._sync_chip)

    def _poll_history(self) -> None:
        if self._service_available and self._sync_status in ("reconnecting", "connecting"):
            self.historyRefreshRequested.emit()

    # ---------------------------------------------------------------- messages
    def set_history(self, messages: list[dict[str, Any]]) -> None:
        self._clear_messages()
        for message in messages:
            if isinstance(message, dict) and message.get("id"):
                self._append(message, scroll=False)
        if self._messages:
            self._area.setCurrentWidget(self._scroll)
            QTimer.singleShot(0, self._scroll_to_bottom)
        else:
            self._area.setCurrentWidget(self._empty_page)

    def append_message(self, message: dict[str, Any]) -> None:
        if not isinstance(message, dict):
            return
        message_id = str(message.get("id") or "")
        if not message_id or message_id in self._messages:
            return
        at_bottom = self._at_bottom()
        self._append(message, scroll=at_bottom or _is_own(message))
        self._area.setCurrentWidget(self._scroll)
        if not at_bottom and not _is_own(message):
            self._new_button.show()

    def remove_message(self, message_id: str) -> None:
        self._messages.pop(message_id, None)
        widget = self._bubbles.pop(message_id, None)
        if widget is not None:
            parent = widget.parentWidget() or widget
            parent.setParent(None)
            parent.deleteLater()
        if not self._messages:
            self._area.setCurrentWidget(self._empty_page)

    def show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
        self._error_timer.start()

    def clear_error(self) -> None:
        self._error_label.hide()
        self._error_timer.stop()

    def _append(self, message: dict[str, Any], *, scroll: bool) -> None:
        message_id = str(message.get("id") or "")
        if not message_id or message_id in self._messages:
            return
        moment = _parse_time(message)
        date_key = moment.strftime("%Y-%m-%d")
        if date_key != self._last_date:
            self._last_date = date_key
            separator = QLabel(_date_label(moment))
            separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
            separator.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px; padding: 4px 0;")
            self._messages_layout.addWidget(separator)
            self._bubbles[f"__date__{date_key}"] = separator

        bubble = MessageBubble(message)
        bubble.setMaximumWidth(max(200, min(360, self._scroll.viewport().width() - 48)))
        bubble.deleteRequested.connect(self.deleteRequested.emit)
        own = _is_own(message)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        if own:
            row_layout.addStretch(1)
            row_layout.addWidget(bubble)
        else:
            row_layout.addWidget(bubble)
            row_layout.addStretch(1)
        self._messages_layout.addWidget(row)
        self._messages[message_id] = message
        self._bubbles[message_id] = bubble
        if scroll:
            QTimer.singleShot(0, self._scroll_to_bottom)
        QTimer.singleShot(0, self._resize_bubbles)

    def _clear_messages(self) -> None:
        for message_id in list(self._bubbles):
            widget = self._bubbles.pop(message_id, None)
            if widget is None:
                continue
            target = widget.parentWidget() if isinstance(widget, MessageBubble) else widget
            target = target or widget
            target.setParent(None)
            target.deleteLater()
        self._messages.clear()
        self._last_date = ""
        self._new_button.hide()

    # ------------------------------------------------------------------ input
    def _on_text_changed(self, text: str) -> None:
        self._counter.setText(f"{len(text)}/{MAX_MESSAGE_LENGTH}")
        self._send_button.setEnabled(
            self._service_available and bool(text.strip()) and len(text) <= MAX_MESSAGE_LENGTH
        )

    def _send(self) -> None:
        if not self._service_available:
            self.show_error("服务未运行，无法发送文本")
            return
        text = self._input.text().strip()
        if not text:
            return
        if len(text) > MAX_MESSAGE_LENGTH:
            self.show_error(f"消息不能超过 {MAX_MESSAGE_LENGTH} 个字符")
            return
        self.clear_error()
        self._input.clear()
        self.sendRequested.emit(text)

    # ----------------------------------------------------------------- scroll
    def _at_bottom(self) -> bool:
        bar = self._scroll.verticalScrollBar()
        return bar.value() >= bar.maximum() - 24

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        self._new_button.hide()

    def _resize_bubbles(self) -> None:
        width = max(200, min(360, self._scroll.viewport().width() - 48))
        for widget in self._bubbles.values():
            if isinstance(widget, MessageBubble):
                widget.setMaximumWidth(width)
                widget.setMinimumWidth(min(width, widget.preferred_width))

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._resize_bubbles()


__all__ = ["MAX_MESSAGE_LENGTH", "MessageBubble", "TextPanel"]
