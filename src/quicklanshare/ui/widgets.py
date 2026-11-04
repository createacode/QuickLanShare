"""可复用的界面组件：卡片、开关、拖拽区、骨架屏、文件表、传输面板、日志面板。"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..utils.format import format_mtime, human_size
from . import icons, theme


def make_card(parent: QWidget | None = None) -> QFrame:
    """创建统一样式的卡片容器。"""
    card = QFrame(parent)
    card.setObjectName("Card")
    card.setFrameShape(QFrame.Shape.NoFrame)
    return card


class Card(QFrame):
    """带阴影的白色卡片。"""

    def __init__(self, parent: QWidget | None = None, *, shadow: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFrameShape(QFrame.Shape.NoFrame)
        if shadow:
            theme.add_shadow(self)


class GlyphLabel(QLabel):
    """使用 Windows 图标字体绘制的图标标签。"""

    def __init__(
        self,
        glyph: str,
        *,
        size: int = 18,
        color: str = theme.TEXT_SECONDARY,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._glyph = icons.GLYPHS.get(glyph, glyph)
        self._color = color
        self._size = size
        self.setFixedSize(QSize(size + 4, size + 4))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"color: {color}; font-family: 'Segoe Fluent Icons', 'Segoe MDL2 Assets', 'Segoe UI Symbol';"
            f" font-size: {size}px;"
        )
        self.setText(self._glyph)


class Divider(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class ToggleSwitch(QAbstractButton):
    """现代化开关，替代原生复选框。"""

    def __init__(self, parent: QWidget | None = None, *, checked: bool = False) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(46, 26)
        self._offset = 1.0 if checked else 0.0
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(160)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        super().setChecked(checked)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:
        return QSize(46, 26)

    def get_offset(self) -> float:
        return self._offset

    def set_offset(self, value: float) -> None:
        self._offset = float(value)
        self.update()

    offset = Property(float, fget=get_offset, fset=set_offset)

    def _animate(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track = QRectF(1, 3, self.width() - 2, self.height() - 6)
        track_color = QColor(theme.ACCENT if self._offset > 0.5 else "#CBD5E1")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(track_color))
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        diameter = self.height() - 10
        travel = self.width() - diameter - 10
        knob_x = 5 + travel * self._offset
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.drawEllipse(QRectF(knob_x, 5, diameter, diameter))
        painter.end()


class DropZone(QFrame):
    """拖拽 / 点击上传区域。"""

    filesDropped = Signal(list)
    browseRequested = Signal()

    def __init__(self, parent: QWidget | None = None, *, compact: bool = False) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._compact = compact
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._active = False
        self._enabled = True
        self._browse_button: QPushButton | None = None
        layout: QLayout

        if compact:
            self.setMinimumHeight(78)
            self.setMaximumHeight(92)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(18, 12, 18, 12)
            layout.setSpacing(14)

            self._icon = GlyphLabel("upload", size=26, color=theme.ACCENT)
            self._icon.setFixedSize(38, 38)
            layout.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignVCenter)

            text_box = QVBoxLayout()
            text_box.setSpacing(2)
            title = QLabel("拖拽文件到这里")
            title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {theme.TEXT};")
            text_box.addWidget(title)
            self._hint = QLabel("或点击选择文件 · 支持多文件 · 分块续传 · 单文件最大 25 GB")
            self._hint.setObjectName("Muted")
            text_box.addWidget(self._hint)
            layout.addLayout(text_box, 1)

            self._browse_button = QPushButton("选择文件")
            self._browse_button.setProperty("role", "primary")
            self._browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._browse_button.setFixedHeight(34)
            self._browse_button.clicked.connect(self.browseRequested.emit)
            layout.addWidget(self._browse_button, 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            self.setMinimumHeight(128)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(20, 14, 20, 14)
            layout.setSpacing(4)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            self._icon = GlyphLabel("upload", size=30, color=theme.ACCENT)
            self._icon.setFixedSize(44, 44)
            self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignHCenter)

            title = QLabel("拖拽文件到这里，或点击选择")
            title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {theme.TEXT};")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(title)

            self._hint = QLabel("支持多文件 · 分块续传 · 单文件最大 25 GB")
            self._hint.setObjectName("Muted")
            self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self._hint)

        self._title = title

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self._enabled = enabled
        self._hint.setText(
            "或点击选择文件 · 支持多文件 · 分块续传 · 单文件最大 25 GB"
            if enabled and self._compact
            else (
                "支持多文件 · 分块续传 · 单文件最大 25 GB"
                if enabled
                else "服务未运行，启动后可上传文件"
            )
        )
        if self._browse_button is not None:
            self._browse_button.setEnabled(enabled)
        self.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.update()

    def _extract_paths(self, event: Any) -> list[Path]:
        paths: list[Path] = []
        mime = event.mimeData()
        if not mime.hasUrls():
            return paths
        for url in mime.urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.is_dir():
                    try:
                        paths.extend(sorted(item for item in path.rglob("*") if item.is_file()))
                    except OSError:
                        continue
                elif path.is_file():
                    paths.append(path)
        return paths

    def dragEnterEvent(self, event: Any) -> None:
        if self._enabled and event.mimeData().hasUrls():
            self._active = True
            self.update()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: Any) -> None:
        self._active = False
        self.update()

    def dropEvent(self, event: Any) -> None:
        self._active = False
        self.update()
        if not self._enabled:
            return
        paths = self._extract_paths(event)
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()

    def mouseReleaseEvent(self, event: Any) -> None:
        if self._enabled and event.button() == Qt.MouseButton.LeftButton:
            self.browseRequested.emit()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(1.0, 1.0, self.width() - 2.0, self.height() - 2.0)
        fill = QColor("#F6FAFF" if self._active else theme.SURFACE)
        if not self._enabled:
            fill = QColor(theme.SURFACE_MUTED)
        painter.setBrush(QBrush(fill))
        pen_color = QColor(theme.ACCENT if self._active else "#B9CBE6")
        pen = QPen(pen_color, 1.4)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setDashPattern([5, 4])
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 14, 14)
        painter.end()


class SkeletonList(QWidget):
    """贴近文件列表布局的骨架屏，加载完成后平滑切换。"""

    def __init__(self, parent: QWidget | None = None, rows: int = 5) -> None:
        super().__init__(parent)
        self._rows = max(1, rows)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(32)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(self._rows * 52 + 8)

    def start(self) -> None:
        self._phase = 0.0
        self._timer.start()
        self.show()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.045) % 1.4
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width = self.width()
        row_height = 52
        base = QColor("#EDF2F9")
        for index in range(self._rows):
            top = 8 + index * row_height
            if top > self.height():
                break
            bar = QRectF(16, top + 12, width * 0.34, 12)
            bar2 = QRectF(16, top + 30, width * 0.18, 10)
            circle = QRectF(width - 96, top + 14, 16, 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(base))
            painter.drawRoundedRect(bar, 6, 6)
            painter.drawRoundedRect(bar2, 5, 5)
            painter.drawRoundedRect(circle, 8, 8)
        gradient = QLinearGradient(0, 0, width, 0)
        gradient.setColorAt(max(0.0, self._phase - 0.25), QColor(255, 255, 255, 0))
        gradient.setColorAt(min(1.0, self._phase), QColor(255, 255, 255, 130))
        gradient.setColorAt(min(1.0, self._phase + 0.25), QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(gradient))
        painter.drawRect(self.rect())
        painter.end()


class EmptyState(QWidget):
    """空 / 错误 / 未启动状态。"""

    actionRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(24, 30, 24, 30)
        self._layout.setSpacing(8)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icon = GlyphLabel("folder", size=34, color=theme.BORDER_STRONG)
        self._layout.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignHCenter)
        self._title = QLabel("暂无共享文件")
        self._title.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {theme.TEXT_SECONDARY};"
        )
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._title)
        self._detail = QLabel("上传或拖拽文件后，这里会显示文件列表")
        self._detail.setObjectName("Muted")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail.setWordWrap(True)
        self._layout.addWidget(self._detail)
        self._action = QPushButton("选择文件上传")
        self._action.setProperty("role", "soft")
        self._action.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action.clicked.connect(self.actionRequested.emit)
        self._layout.addWidget(self._action, 0, Qt.AlignmentFlag.AlignHCenter)

    def set_state(
        self,
        title: str,
        detail: str,
        *,
        glyph: str = "folder",
        action_text: str | None = None,
        tone: str = "muted",
    ) -> None:
        self._icon.setText(icons.GLYPHS.get(glyph, glyph))
        self._icon.setStyleSheet(
            f"color: {theme.DANGER if tone == 'error' else theme.BORDER_STRONG};"
            " font-family: 'Segoe Fluent Icons', 'Segoe MDL2 Assets', 'Segoe UI Symbol'; font-size: 32px;"
        )
        self._title.setText(title)
        self._detail.setText(detail)
        if action_text:
            self._action.setText(action_text)
            self._action.show()
        else:
            self._action.hide()


class FileTable(QTableWidget):
    """共享文件列表：复选框、下载状态、下载/删除/打开文件夹。"""

    downloadRequested = Signal(str)
    deleteRequested = Signal(list)
    copyLinkRequested = Signal(str)
    openFolderRequested = Signal(str)
    selectionCountChanged = Signal(int)

    HEADERS = ("", "文件名", "大小", "修改时间", "下载", "状态", "操作")
    COL_CHECK = 0
    COL_NAME = 1
    COL_SIZE = 2
    COL_TIME = 3
    COL_COUNT = 4
    COL_STATUS = 5
    COL_ACTIONS = 6

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._files: list[dict[str, Any]] = []
        self._checked: set[str] = set()
        self._downloaded: dict[str, Path] = {}
        self._downloading: set[str] = set()
        self.setColumnCount(len(self.HEADERS))
        self.setHorizontalHeaderLabels(list(self.HEADERS))
        for column in range(len(self.HEADERS)):
            header_item = self.horizontalHeaderItem(column)
            if header_item is not None:
                header_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                    if column == self.COL_NAME
                    else Qt.AlignmentFlag.AlignCenter
                )
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setAlternatingRowColors(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(46)
        self.horizontalHeader().setFixedHeight(36)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 34)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for index, width in (
            (self.COL_SIZE, 76),
            (self.COL_TIME, 108),
            (self.COL_COUNT, 48),
            (self.COL_STATUS, 72),
            (self.COL_ACTIONS, 104),
        ):
            self.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(index, width)
        self.setIconSize(QSize(16, 16))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        self.doubleClicked.connect(self._on_double_click)
        self.itemSelectionChanged.connect(self._emit_selection)
        self._updating_checks = False

    # ------------------------------------------------------------ column state
    def column_widths(self) -> list[int]:
        """固定列宽，用于写入配置（不含复选框与文件名列）。"""
        return [
            self.columnWidth(self.COL_SIZE),
            self.columnWidth(self.COL_TIME),
            self.columnWidth(self.COL_COUNT),
            self.columnWidth(self.COL_STATUS),
            self.columnWidth(self.COL_ACTIONS),
        ]

    def apply_column_widths(self, widths: list[int]) -> None:
        if not isinstance(widths, list):
            return
        for offset, width in enumerate(widths[:5]):
            try:
                value = int(width)
            except (TypeError, ValueError):
                continue
            if value >= 40:
                self.setColumnWidth(self.COL_SIZE + offset, min(320, value))

    # ------------------------------------------------------------------ data
    def set_files(
        self,
        files: list[dict[str, Any]],
        downloaded: dict[str, Path] | None = None,
        downloading: set[str] | None = None,
    ) -> None:
        self._files = files
        self._downloaded = dict(downloaded or {})
        self._downloading = set(downloading or {})
        self.blockSignals(True)
        self.setRowCount(0)
        self.setRowCount(len(files))
        for row, entry in enumerate(files):
            name = str(entry.get("name") or "")
            self.setCellWidget(row, self.COL_CHECK, self._check_cell(name))

            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, name)
            name_item.setToolTip(name)
            name_item.setIcon(icons.glyph_icon("file", size=15, color=theme.TEXT_MUTED))
            self.setItem(row, self.COL_NAME, name_item)

            size_item = QTableWidgetItem(human_size(entry.get("size", 0)))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, self.COL_SIZE, size_item)

            full_time = format_mtime(float(entry.get("modified") or 0))
            time_item = QTableWidgetItem(full_time[5:] if full_time != "-" else "-")
            time_item.setToolTip(full_time)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            time_item.setForeground(QBrush(QColor(theme.TEXT_SECONDARY)))
            self.setItem(row, self.COL_TIME, time_item)

            count_item = QTableWidgetItem(str(int(entry.get("download_count") or 0)))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            count_item.setForeground(QBrush(QColor(theme.TEXT_MUTED)))
            self.setItem(row, self.COL_COUNT, count_item)

            self.setCellWidget(row, self.COL_STATUS, self._status_cell(name))
            self.setCellWidget(row, self.COL_ACTIONS, self._actions(name))
        self.blockSignals(False)
        self._emit_selection()

    def _check_cell(self, name: str) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        check = QCheckBox()
        check.setChecked(name in self._checked)
        check.setCursor(Qt.CursorShape.PointingHandCursor)
        check.setToolTip(f"选择 {name}")
        check.stateChanged.connect(lambda state, value=name: self._on_check_widget(value, state))
        layout.addWidget(check, 0, Qt.AlignmentFlag.AlignCenter)
        return container

    def _on_check_widget(self, name: str, state: int) -> None:
        if self._updating_checks:
            return
        if state == int(Qt.CheckState.Checked.value):
            self._checked.add(name)
        else:
            self._checked.discard(name)
        self._emit_selection()

    def _status_cell(self, name: str) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        label = QLabel()
        if name in self._downloading:
            label.setText("下载中")
            label.setStyleSheet(f"color: {theme.ACCENT}; font-size: 11px;")
        elif name in self._downloaded:
            label.setText("已下载")
            label.setStyleSheet(f"color: {theme.SUCCESS}; font-size: 11px;")
        else:
            label.setText("未下载")
            label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        layout.addStretch(1)
        layout.addWidget(label, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        return container

    def _actions(self, name: str) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        layout.addStretch(1)

        download = QPushButton()
        download.setProperty("role", "icon")
        download.setIcon(icons.glyph_icon("download", size=15, color=theme.TEXT_SECONDARY))
        download.setIconSize(QSize(15, 15))
        download.setFixedSize(30, 30)
        download.setCursor(Qt.CursorShape.PointingHandCursor)
        download.setToolTip(f"下载 {name}")
        download.clicked.connect(lambda _=False, value=name: self.downloadRequested.emit(value))

        delete = QPushButton()
        delete.setProperty("role", "iconDanger")
        delete.setIcon(icons.glyph_icon("delete", size=15, color=theme.DANGER))
        delete.setIconSize(QSize(15, 15))
        delete.setFixedSize(30, 30)
        delete.setCursor(Qt.CursorShape.PointingHandCursor)
        delete.setToolTip(f"删除 {name}")
        delete.clicked.connect(lambda _=False, value=name: self.deleteRequested.emit([value]))

        layout.addWidget(download)
        layout.addWidget(delete)

        folder = self._downloaded.get(name)
        if folder is not None:
            open_folder = QPushButton()
            open_folder.setProperty("role", "icon")
            open_folder.setIcon(icons.glyph_icon("folder", size=15, color=theme.TEXT_SECONDARY))
            open_folder.setIconSize(QSize(15, 15))
            open_folder.setFixedSize(30, 30)
            open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
            open_folder.setToolTip(f"打开所在文件夹\n{folder}")
            open_folder.clicked.connect(
                lambda _=False, value=name: self.openFolderRequested.emit(value)
            )
            layout.addWidget(open_folder)

        layout.addStretch(1)
        return container

    # -------------------------------------------------------------- selection
    def checked_names(self) -> list[str]:
        return [name for name in self._checked if name in self.visible_names()]

    def selected_names(self) -> list[str]:
        """兼容旧调用：批量操作使用复选框结果。"""
        return self.checked_names()

    def checked_count(self) -> int:
        return len(self.checked_names())

    def visible_names(self) -> list[str]:
        names: list[str] = []
        for row in range(self.rowCount()):
            item = self.item(row, self.COL_NAME)
            if item is not None:
                value = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(value, str) and value:
                    names.append(value)
        return names

    def set_all_checked(self, checked: bool) -> None:
        names = self.visible_names()
        self._updating_checks = True
        self._checked = set(names) if checked else set()
        for row in range(self.rowCount()):
            container = self.cellWidget(row, self.COL_CHECK)
            if container is not None:
                box = container.findChild(QCheckBox)
                if box is not None:
                    box.setChecked(checked)
        self._updating_checks = False
        self._emit_selection()

    def clear_checked(self) -> None:
        self.set_all_checked(False)

    def check_all_state(self) -> Qt.CheckState:
        total = self.rowCount()
        checked = self.checked_count()
        if total == 0 or checked == 0:
            return Qt.CheckState.Unchecked
        if checked >= total:
            return Qt.CheckState.Checked
        return Qt.CheckState.PartiallyChecked

    def _emit_selection(self) -> None:
        self.selectionCountChanged.emit(self.checked_count())

    def _on_double_click(self, index: Any) -> None:
        item = self.item(index.row(), self.COL_NAME)
        if item is not None:
            value = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(value, str):
                self.downloadRequested.emit(value)

    def _show_menu(self, position: QPoint) -> None:
        index = self.indexAt(position)
        if not index.isValid():
            return
        item = self.item(index.row(), self.COL_NAME)
        if item is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        checked = self.checked_names()
        if name not in checked:
            checked = [str(name)]
        menu = QMenu(self)
        download_action = QAction("下载", menu)
        download_action.triggered.connect(lambda: self.downloadRequested.emit(str(name)))
        menu.addAction(download_action)
        copy_action = QAction("复制下载链接", menu)
        copy_action.triggered.connect(lambda: self.copyLinkRequested.emit(str(name)))
        menu.addAction(copy_action)
        menu.addSeparator()
        delete_action = QAction("删除所选", menu)
        delete_action.triggered.connect(lambda: self.deleteRequested.emit(checked))
        menu.addAction(delete_action)
        menu.exec(self.viewport().mapToGlobal(position))


class TransferRow(QFrame):
    """单个传输任务行。"""

    cancelRequested = Signal(str)

    def __init__(self, task_id: str, name: str, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.task_id = task_id
        self.kind = kind
        self._finished = False
        self.setObjectName("TransferRow")
        self.setMinimumHeight(56)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet(f"font-weight: 600; color: {theme.TEXT};")
        self.name_label.setToolTip(name)
        self.name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        top.addWidget(self.name_label, 1)
        self.status_label = QLabel("等待中")
        self.status_label.setObjectName("Muted")
        top.addWidget(self.status_label, 0)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setProperty("role", "link")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(lambda: self.cancelRequested.emit(self.task_id))
        top.addWidget(self.cancel_button, 0)
        layout.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(7)
        layout.addWidget(self.progress)

    def update_progress(self, done: int, total: int) -> None:
        if self._finished:
            return
        if total > 0:
            percent = int(done * 100 / total)
            self.progress.setRange(0, 100)
            self.progress.setValue(max(0, min(100, percent)))
            self.status_label.setText(
                f"{'上传' if self.kind == 'upload' else '下载'} {human_size(done)} / "
                f"{human_size(total)} · {percent}%"
            )
        else:
            self.progress.setRange(0, 0)
            self.status_label.setText(
                f"{'上传' if self.kind == 'upload' else '下载'} {human_size(done)}"
            )

    def finish(self, ok: bool, message: str = "") -> None:
        self._finished = True
        self.cancel_button.hide()
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if ok else self.progress.value())
        self.progress.setProperty("state", "done" if ok else "error")
        self.progress.style().unpolish(self.progress)
        self.progress.style().polish(self.progress)
        self.progress.hide()
        self.setFixedHeight(36)
        self.status_label.setText(message or ("已完成" if ok else "失败"))
        self.status_label.setStyleSheet(
            f"color: {theme.SUCCESS if ok else theme.DANGER}; font-size: 11px;"
        )

    def mark_cancelled(self) -> None:
        self.finish(False, "已取消")


class TransferPanel(QFrame):
    """传输任务卡片；没有任务时自动隐藏。"""

    cancelRequested = Signal(str)
    contentVisibilityChanged = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        theme.add_shadow(self)
        self._rows: dict[str, TransferRow] = {}
        self._order: list[str] = []
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.setInterval(6000)
        self._collapse_timer.timeout.connect(self._auto_collapse)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 10)
        layout.setSpacing(2)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("传输任务")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        self._count = QLabel("0 个")
        self._count.setObjectName("Muted")
        header.addWidget(self._count)
        header.addStretch(1)
        self._clear = QPushButton("清除已完成")
        self._clear.setProperty("role", "link")
        self._clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear.clicked.connect(self.clear_finished)
        header.addWidget(self._clear)
        layout.addLayout(header)

        self._container = QWidget()
        self._rows_layout = QVBoxLayout(self._container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)
        self._rows_layout.addStretch(1)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("TransferScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setMaximumHeight(168)
        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll)
        self.hide()

    def add_task(self, task_id: str, name: str, kind: str) -> TransferRow:
        self._collapse_timer.stop()
        row = TransferRow(task_id, name, kind)
        row.cancelRequested.connect(self.cancelRequested.emit)
        self._rows[task_id] = row
        self._order.append(task_id)
        self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
        self._refresh_count()
        self._set_visible(True)
        return row

    def row(self, task_id: str) -> TransferRow | None:
        return self._rows.get(task_id)

    def update_task(self, task_id: str, done: int, total: int) -> None:
        row = self._rows.get(task_id)
        if row is not None:
            row.update_progress(done, total)

    def finish_task(self, task_id: str, ok: bool, message: str = "") -> None:
        row = self._rows.get(task_id)
        if row is not None:
            row.finish(ok, message)
            self._refresh_count()
            if not any(not item._finished for item in self._rows.values()):
                # 全部完成后保留 6 秒展示结果，再自动收起，避免长期占用文件列表空间。
                self._collapse_timer.start()

    def _auto_collapse(self) -> None:
        if any(not row._finished for row in self._rows.values()):
            return
        self.clear_finished()

    def cancel_task(self, task_id: str) -> None:
        row = self._rows.get(task_id)
        if row is not None:
            row.mark_cancelled()

    def clear_finished(self) -> None:
        self._collapse_timer.stop()
        for task_id in list(self._order):
            row = self._rows.get(task_id)
            if row is None or row._finished:
                self._remove(task_id)
        self._refresh_count()
        if not self._rows:
            self._set_visible(False)

    def _remove(self, task_id: str) -> None:
        row = self._rows.pop(task_id, None)
        if row is not None:
            row.setParent(None)
            row.deleteLater()
        if task_id in self._order:
            self._order.remove(task_id)

    def _refresh_count(self) -> None:
        running = sum(1 for row in self._rows.values() if not row._finished)
        self._count.setText(f"{running} 个进行中" if running else "已全部完成")

    def _set_visible(self, visible: bool) -> None:
        if self.isVisible() == visible and not visible:
            return
        self.setVisible(visible)
        self.contentVisibilityChanged.emit(visible)


class LogPanel(QFrame):
    """运行日志面板：级别过滤、自动滚动、打开日志目录。"""

    openLogDirRequested = Signal()
    closeRequested = Signal()
    errorReceived = Signal()

    LEVELS = ("全部", "信息及以上", "警告及以上", "仅错误")
    _COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": theme.TEXT_MUTED,
        "INFO": theme.TEXT_SECONDARY,
        "WARNING": theme.WARNING,
        "ERROR": theme.DANGER,
        "CRITICAL": theme.DANGER,
    }
    _THRESHOLD: ClassVar[dict[str, int]] = {
        "DEBUG": 0,
        "INFO": 1,
        "WARNING": 2,
        "ERROR": 3,
        "CRITICAL": 4,
    }

    def __init__(self, parent: QWidget | None = None, *, closable: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("LogPanel" if closable else "Card")
        if not closable:
            theme.add_shadow(self)
        self._buffer: list[tuple[str, str]] = []
        self._minimum_level = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("运行日志")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        self._filter = _combo(self.LEVELS)
        self._filter.setFixedWidth(118)
        self._filter.currentIndexChanged.connect(self._on_filter_changed)
        header.addWidget(self._filter)
        open_button = QPushButton("打开目录")
        open_button.setProperty("role", "refresh")
        open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        open_button.clicked.connect(self.openLogDirRequested.emit)
        header.addWidget(open_button)
        clear_button = QPushButton("清空")
        clear_button.setProperty("role", "refresh")
        clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_button.clicked.connect(self.clear)
        header.addWidget(clear_button)
        if closable:
            close_button = QPushButton("关闭")
            close_button.setProperty("role", "refresh")
            close_button.setCursor(Qt.CursorShape.PointingHandCursor)
            close_button.clicked.connect(self.closeRequested.emit)
            header.addWidget(close_button)
        layout.addLayout(header)

        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._view.setMaximumBlockCount(3000)
        self._view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._view.setFont(QFont("Cascadia Mono", 9))
        self._view.setPlaceholderText("服务启动后，运行日志会显示在这里")
        layout.addWidget(self._view, 1)

    @property
    def view(self) -> QPlainTextEdit:
        return self._view

    def append_message(self, level: str, message: str) -> None:
        level = (level or "INFO").upper()
        self._buffer.append((level, message))
        if len(self._buffer) > 3000:
            self._buffer = self._buffer[-3000:]
        if self._passes(level):
            self._append_html(level, message)
        if level in ("ERROR", "CRITICAL"):
            self.errorReceived.emit()

    def _passes(self, level: str) -> bool:
        return self._THRESHOLD.get(level, 1) >= self._minimum_level

    def _append_html(self, level: str, message: str) -> None:
        scrollbar = self._view.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 4
        stamp = datetime.now().strftime("%H:%M:%S")
        color = self._COLORS.get(level, theme.TEXT_SECONDARY)
        label = {
            "INFO": "信息",
            "DEBUG": "调试",
            "WARNING": "警告",
            "ERROR": "错误",
            "CRITICAL": "严重",
        }.get(level, level)
        text = (
            f'<span style="color:{theme.TEXT_MUTED};">{stamp}</span> '
            f'<span style="color:{color}; font-weight:600;">[{html.escape(label)}]</span> '
            f'<span style="color:{theme.TEXT_SECONDARY};">{html.escape(message)}</span>'
        )
        self._view.appendHtml(text)
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def _on_filter_changed(self, index: int) -> None:
        self._minimum_level = index
        self._render_all()

    def _render_all(self) -> None:
        self._view.clear()
        for level, message in self._buffer:
            if self._passes(level):
                self._append_html(level, message)

    def clear(self) -> None:
        self._buffer.clear()
        self._view.clear()

    def set_level_filter(self, index: int) -> None:
        self._filter.setCurrentIndex(max(0, min(len(self.LEVELS) - 1, index)))


class Toast(QLabel):
    """底部居中的轻提示，自带淡入淡出。"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self._opacity = 1.0

    def show_message(self, text: str, duration: int = 2600) -> None:
        self.setText(text)
        self.adjustSize()
        self.reposition()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(duration)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        x = max(16, (parent.width() - self.width()) // 2)
        y = max(16, parent.height() - self.height() - 46)
        self.move(x, y)

    def _fade_out(self) -> None:
        self.hide()


def _combo(items: tuple[str, ...] | list[str]) -> Any:
    from PySide6.QtWidgets import QComboBox

    combo = QComboBox()
    combo.addItems(list(items))
    combo.setCursor(Qt.CursorShape.PointingHandCursor)
    return combo


def stat_block(label: str, value: str = "0") -> tuple[QWidget, QLabel]:
    """生成“数值 + 说明”的小统计块。"""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(1)
    value_label = QLabel(value)
    value_label.setObjectName("StatValue")
    caption = QLabel(label)
    caption.setObjectName("StatLabel")
    layout.addWidget(value_label)
    layout.addWidget(caption)
    return container, value_label


def elide_label(
    label: QLabel, text: str, mode: Qt.TextElideMode = Qt.TextElideMode.ElideMiddle
) -> None:
    metrics = QFontMetrics(label.font())
    label.setText(metrics.elidedText(text, mode, max(80, label.width())))
