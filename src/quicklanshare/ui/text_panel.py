"""文本共享面板：与网页端实时同步的消息流、输入与发送。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
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
MAX_NAME_LENGTH = 20
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


def _same_ip(left: Any, right: Any) -> bool:
    return str(left or "") == str(right or "")


def _message_time(message: dict[str, Any]) -> str:
    raw = str(message.get("time_str") or "")
    if len(raw) >= 5:
        return raw[-5:]
    return _parse_time(message).strftime("%H:%M")


class TextInputDialog(QDialog):
    """中文输入对话框，避免系统原生按钮出现英文。"""

    def __init__(
        self,
        title: str,
        label: str,
        text: str,
        *,
        max_length: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(360)
        self._max_length = max_length
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
        hint = QLabel(label)
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._edit = QLineEdit()
        self._edit.setText(text)
        self._edit.setMaxLength(max_length)
        self._edit.setMinimumHeight(34)
        self._edit.selectAll()
        layout.addWidget(self._edit)

        self._error = QLabel("")
        self._error.setStyleSheet(f"color: {theme.DANGER}; font-size: 11px;")
        self._error.hide()
        layout.addWidget(self._error)

        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        save = QPushButton("保存")
        save.setProperty("role", "primary")
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.setDefault(True)
        save.clicked.connect(self._accept)
        footer.addWidget(save)
        layout.addLayout(footer)

    def _accept(self) -> None:
        value = self._edit.text().strip()
        if not value:
            self._error.setText("内容不能为空")
            self._error.show()
            return
        if len(value) > self._max_length:
            self._error.setText(f"最多 {self._max_length} 个字符")
            self._error.show()
            return
        self.accept()

    def value(self) -> str:
        return self._edit.text().strip()


class MessageBubble(QFrame):
    """一条文本消息气泡。"""

    deleteRequested = Signal(str)
    editRequested = Signal(str)
    selectionChanged = Signal(str, bool)

    def __init__(self, message: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.message = message
        self._message_id = str(message.get("id") or "")
        self._own = _is_own(message)
        self.setObjectName("OwnBubble" if self._own else "OtherBubble")
        self.setMaximumWidth(380)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 9)
        layout.setSpacing(3)

        meta = QHBoxLayout()
        meta.setSpacing(8)
        self._select = QCheckBox()
        self._select.setCursor(Qt.CursorShape.PointingHandCursor)
        self._select.setToolTip("选中这条消息")
        self._select.hide()
        self._select.toggled.connect(
            lambda checked: self.selectionChanged.emit(self._message_id, checked)
        )
        meta.addWidget(self._select)
        self._name_label = QLabel(self._sender_text())
        self._name_label.setStyleSheet(
            f"color: {theme.ACCENT if self._own else theme.TEXT_SECONDARY};"
            " font-size: 11px; font-weight: 600;"
        )
        meta.addWidget(self._name_label)
        meta.addStretch(1)
        self._time_label = QLabel(_message_time(message))
        self._time_label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px;")
        meta.addWidget(self._time_label)
        layout.addLayout(meta)

        raw_text = str(message.get("message") or "")
        self._text = QLabel(raw_text)
        self._text.setWordWrap(True)
        self._text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._text.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._text.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._text.customContextMenuRequested.connect(self._show_text_menu)
        self._text.installEventFilter(self)
        self._text.setStyleSheet(f"color: {theme.TEXT}; font-size: 13px; line-height: 1.5;")
        layout.addWidget(self._text)
        self._recalculate_width()

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

    def _sender_text(self) -> str:
        if self._own:
            return "我"
        return str(self.message.get("client_name") or "访客")

    def _recalculate_width(self) -> None:
        raw_text = str(self.message.get("message") or "")
        metrics = self._text.fontMetrics()
        self.preferred_width = min(360, max(120, metrics.horizontalAdvance(raw_text) + 34))

    @property
    def message_id(self) -> str:
        return self._message_id

    def set_manage_mode(self, enabled: bool) -> None:
        self._select.setVisible(enabled)
        if not enabled:
            self._select.setChecked(False)

    def set_selected(self, selected: bool) -> None:
        self._select.setChecked(selected)

    def is_selected(self) -> bool:
        return self._select.isChecked()

    def update_content(self, message: dict[str, Any]) -> None:
        self.message = message
        self._text.setText(str(message.get("message") or ""))
        self._time_label.setText(_message_time(message))
        self._name_label.setText(self._sender_text())
        self._recalculate_width()
        self.updateGeometry()

    def update_sender(self, name: str) -> None:
        if self._own:
            return
        self.message["client_name"] = name
        self._name_label.setText(name)

    def _show_text_menu(self, position: QPoint) -> None:
        self._show_menu(self._text.mapTo(self, position))

    def _show_menu(self, position: QPoint) -> None:
        menu = QMenu(self)
        copy_action = QAction("复制文本", menu)
        copy_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Copy))
        copy_action.triggered.connect(self.copy_text)
        menu.addAction(copy_action)
        select_all = QAction("全选文本", menu)
        select_all.triggered.connect(self._select_all_text)
        menu.addAction(select_all)
        menu.addSeparator()
        edit_action = QAction("编辑消息", menu)
        edit_action.triggered.connect(lambda: self.editRequested.emit(self._message_id))
        menu.addAction(edit_action)
        delete_action = QAction("删除消息", menu)
        delete_action.triggered.connect(lambda: self.deleteRequested.emit(self._message_id))
        menu.addAction(delete_action)
        menu.exec(self.mapToGlobal(position))

    def _select_all_text(self) -> None:
        self._text.setFocus(Qt.FocusReason.MouseFocusReason)
        self._text.setSelection(0, len(str(self.message.get("message") or "")))

    def copy_text(self) -> None:
        selected = self._text.selectedText().replace("\u2029", "\n").strip()
        QGuiApplication.clipboard().setText(selected or str(self.message.get("message") or ""))

    def mouseDoubleClickEvent(self, event: Any) -> None:
        self.copy_text()
        event.accept()

    def mousePressEvent(self, event: Any) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def eventFilter(self, watched: Any, event: Any) -> bool:
        if (
            watched is self._text
            and event.type() == QEvent.Type.KeyPress
            and event.matches(QKeySequence.StandardKey.Copy)
        ):
            self.copy_text()
            return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: Any) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_text()
            event.accept()
            return
        super().keyPressEvent(event)


class TextPanel(QFrame):
    """消息流 + 输入框；数据来自服务端聊天室。"""

    sendRequested = Signal(str)
    deleteRequested = Signal(str)
    deleteManyRequested = Signal(list)
    editRequested = Signal(str, str)
    renameRequested = Signal(str)
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
        self._manage_mode = False
        self._selected: set[str] = set()
        self._display_name = "访客"
        self._stick_to_bottom = True
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
        header.setSpacing(6)
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
        self._name_button = QPushButton("改名")
        self._name_button.setProperty("role", "link")
        self._name_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._name_button.setToolTip("修改自己在共享文本中的用户名")
        self._name_button.setEnabled(False)
        header.addWidget(self._name_button)
        self._manage_button = QPushButton("管理")
        self._manage_button.setProperty("role", "link")
        self._manage_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._manage_button.setToolTip("批量选择、编辑或删除消息")
        self._manage_button.setEnabled(False)
        header.addWidget(self._manage_button)
        self._sync_chip = QLabel("已停止")
        self._sync_chip.setObjectName("StatusChip")
        self._sync_chip.setProperty("state", "error")
        header.addWidget(self._sync_chip)
        layout.addLayout(header)

        self._manage_bar = QFrame()
        self._manage_bar.setObjectName("ManageBar")
        manage_layout = QHBoxLayout(self._manage_bar)
        manage_layout.setContentsMargins(10, 6, 8, 6)
        manage_layout.setSpacing(8)
        self._select_all = QCheckBox("全选")
        self._select_all.setTristate(True)
        self._select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        manage_layout.addWidget(self._select_all)
        self._manage_hint = QLabel("已选 0 条")
        self._manage_hint.setObjectName("Muted")
        manage_layout.addWidget(self._manage_hint)
        manage_layout.addStretch(1)
        self._delete_selected_button = QPushButton("删除选中")
        self._delete_selected_button.setProperty("role", "danger")
        self._delete_selected_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_selected_button.setEnabled(False)
        manage_layout.addWidget(self._delete_selected_button)
        self._manage_done_button = QPushButton("完成")
        self._manage_done_button.setProperty("role", "link")
        self._manage_done_button.setCursor(Qt.CursorShape.PointingHandCursor)
        manage_layout.addWidget(self._manage_done_button)
        self._manage_bar.hide()
        layout.addWidget(self._manage_bar)

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
        self._scroll.verticalScrollBar().rangeChanged.connect(self._on_scroll_range)

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

        self._name_button.clicked.connect(self._request_rename)
        self._manage_button.clicked.connect(self._toggle_manage)
        self._manage_done_button.clicked.connect(lambda: self.set_manage_mode(False))
        self._select_all.stateChanged.connect(self._on_select_all_changed)
        self._delete_selected_button.clicked.connect(self._delete_selected)

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
    def manage_mode(self) -> bool:
        return self._manage_mode

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def message_count(self) -> int:
        return len(self._messages)

    def messages(self) -> list[dict[str, Any]]:
        return list(self._messages.values())

    def set_service_available(self, available: bool) -> None:
        self._service_available = available
        self._input.setEnabled(available)
        self._send_button.setEnabled(available and bool(self._input.text().strip()))
        self._name_button.setEnabled(available)
        self._manage_button.setEnabled(available and bool(self._messages))
        if not available:
            self._input.setPlaceholderText("启动服务后可发送文本")
            self._sync_chip.setText("已停止")
            self._set_chip_state("error")
            self._poll_timer.stop()
            self.set_manage_mode(False)
        else:
            self._input.setPlaceholderText("输入文字，Enter 发送")

    def set_display_name(self, name: str) -> None:
        cleaned = str(name or "").strip() or "访客"
        self._display_name = cleaned[:MAX_NAME_LENGTH]
        self._subtitle.setText(f"与网页端共用同一份记录 · 我：{self._display_name}")
        self._subtitle.setToolTip(f"当前用户名：{self._display_name}")

    def _request_rename(self) -> None:
        dialog = TextInputDialog(
            "修改用户名",
            f"最多 {MAX_NAME_LENGTH} 个字符，修改后所有设备都会看到。",
            self._display_name,
            max_length=MAX_NAME_LENGTH,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.renameRequested.emit(dialog.value())

    def _toggle_manage(self) -> None:
        self.set_manage_mode(not self._manage_mode)

    def set_manage_mode(self, enabled: bool) -> None:
        if enabled and not self._messages:
            return
        self._manage_mode = enabled
        self._manage_bar.setVisible(enabled)
        self._manage_button.setText("退出管理" if enabled else "管理")
        self._select_all.blockSignals(True)
        self._select_all.setCheckState(Qt.CheckState.Unchecked)
        self._select_all.blockSignals(False)
        self._selected.clear()
        for bubble in self._messages.values():
            widget = self._bubbles.get(str(bubble.get("id") or ""))
            if isinstance(widget, MessageBubble):
                widget.set_manage_mode(enabled)
                widget.set_selected(False)
        self._update_manage_state()

    def _on_bubble_selection(self, message_id: str, selected: bool) -> None:
        if selected:
            self._selected.add(message_id)
        else:
            self._selected.discard(message_id)
        self._update_manage_state()

    def _on_select_all_changed(self, state: int) -> None:
        checked = state != int(Qt.CheckState.Unchecked.value)
        for message_id, widget in self._bubbles.items():
            if isinstance(widget, MessageBubble) and not message_id.startswith("__date__"):
                widget.set_selected(checked)
        self._update_manage_state()

    def _update_manage_state(self) -> None:
        count = len(self._selected)
        self._manage_hint.setText(f"已选 {count} 条")
        self._delete_selected_button.setEnabled(count > 0)
        total = len(self._messages)
        self._select_all.blockSignals(True)
        if not total or count == 0:
            self._select_all.setCheckState(Qt.CheckState.Unchecked)
        elif count >= total:
            self._select_all.setCheckState(Qt.CheckState.Checked)
        else:
            self._select_all.setCheckState(Qt.CheckState.PartiallyChecked)
        self._select_all.blockSignals(False)

    def _delete_selected(self) -> None:
        ids = [item for item in self._selected if item in self._messages]
        if not ids:
            return
        box = QMessageBox(self)
        box.setWindowTitle("删除消息")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(f"确定删除选中的 {len(ids)} 条消息吗？删除后不可恢复。")
        accept = box.addButton("删除", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not accept:
            return
        self.deleteManyRequested.emit(ids)

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
        self.set_manage_mode(False)
        self._clear_messages()
        for message in messages:
            if isinstance(message, dict) and message.get("id"):
                self._append(message, scroll=False)
        if self._messages:
            self._area.setCurrentWidget(self._scroll)
            self._stick_to_bottom = True
            QTimer.singleShot(0, self._scroll_to_bottom)
        else:
            self._area.setCurrentWidget(self._empty_page)
        self._manage_button.setEnabled(self._service_available and bool(self._messages))
        self._update_manage_state()

    def append_message(self, message: dict[str, Any]) -> None:
        if not isinstance(message, dict):
            return
        message_id = str(message.get("id") or "")
        if not message_id or message_id in self._messages:
            return
        at_bottom = self._at_bottom()
        own = _is_own(message)
        self._stick_to_bottom = at_bottom or own
        self._append(message, scroll=at_bottom or own)
        self._area.setCurrentWidget(self._scroll)
        self._manage_button.setEnabled(self._service_available)
        if not at_bottom and not own:
            self._new_button.show()

    def edit_message(self, message: dict[str, Any]) -> None:
        if not isinstance(message, dict):
            return
        message_id = str(message.get("id") or "")
        if not message_id or message_id not in self._messages:
            return
        self._messages[message_id] = message
        widget = self._bubbles.get(message_id)
        if isinstance(widget, MessageBubble):
            widget.update_content(message)

    def update_sender(self, client_ip: str, name: str) -> None:
        for message_id, message in self._messages.items():
            if _same_ip(message.get("client_ip"), client_ip):
                message["client_name"] = name
                widget = self._bubbles.get(message_id)
                if isinstance(widget, MessageBubble):
                    widget.update_sender(name)

    def remove_message(self, message_id: str) -> None:
        self.remove_messages([message_id])

    def remove_messages(self, message_ids: list[str]) -> None:
        for message_id in message_ids:
            self._messages.pop(message_id, None)
            self._selected.discard(message_id)
            widget = self._bubbles.pop(message_id, None)
            if widget is not None:
                parent = widget.parentWidget() or widget
                parent.setParent(None)
                parent.deleteLater()
        if not self._messages:
            self._area.setCurrentWidget(self._empty_page)
            self.set_manage_mode(False)
        self._manage_button.setEnabled(self._service_available and bool(self._messages))
        self._update_manage_state()

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
            self._messages_layout.insertWidget(self._messages_layout.count() - 1, separator)
            self._bubbles[f"__date__{date_key}"] = separator

        bubble = MessageBubble(message)
        bubble.setMaximumWidth(max(200, min(360, self._scroll.viewport().width() - 48)))
        bubble.deleteRequested.connect(self.deleteRequested.emit)
        bubble.editRequested.connect(self._edit_message)
        bubble.selectionChanged.connect(self._on_bubble_selection)
        bubble.set_manage_mode(self._manage_mode)
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
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, row)
        self._messages[message_id] = message
        self._bubbles[message_id] = bubble
        if scroll:
            self._stick_to_bottom = True
            QTimer.singleShot(0, self._scroll_to_bottom)
        QTimer.singleShot(0, self._resize_bubbles)

    def _edit_message(self, message_id: str) -> None:
        message = self._messages.get(message_id)
        if message is None:
            return
        dialog = TextInputDialog(
            "编辑消息",
            f"修改后所有设备同步更新，最多 {MAX_MESSAGE_LENGTH} 个字符。",
            str(message.get("message") or ""),
            max_length=MAX_MESSAGE_LENGTH,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        value = dialog.value()
        if value and value != str(message.get("message") or ""):
            self.editRequested.emit(message_id, value)

    def _clear_messages(self) -> None:
        self._selected.clear()
        self._select_all.blockSignals(True)
        self._select_all.setCheckState(Qt.CheckState.Unchecked)
        self._select_all.blockSignals(False)
        self._manage_hint.setText("已选 0 条")
        self._delete_selected_button.setEnabled(False)
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
        self._stick_to_bottom = True
        self._scroll_to_bottom()
        self.sendRequested.emit(text)

    # ----------------------------------------------------------------- scroll
    def _at_bottom(self) -> bool:
        bar = self._scroll.verticalScrollBar()
        return bar.value() >= bar.maximum() - 24

    def _on_scroll_range(self, _minimum: int, maximum: int) -> None:
        if self._stick_to_bottom:
            bar = self._scroll.verticalScrollBar()
            bar.setValue(maximum)

    def _scroll_to_bottom(self) -> None:
        self._stick_to_bottom = True
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


__all__ = [
    "MAX_MESSAGE_LENGTH",
    "MAX_NAME_LENGTH",
    "MessageBubble",
    "TextInputDialog",
    "TextPanel",
]
