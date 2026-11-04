from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QLabel, QPushButton

from quicklanshare.core.version import window_title
from quicklanshare.ui import theme
from quicklanshare.ui.main_window import MainWindow
from quicklanshare.ui.settings_dialog import SettingsDialog
from quicklanshare.ui.widgets import FileTable
from quicklanshare.utils.app_config import AppConfig
from quicklanshare.utils.logging_setup import setup_logging


def make_window(tmp_path: Path, qtbot) -> MainWindow:
    config = AppConfig()
    config.server.port = 0
    config.server.auto_shutdown_enabled = True
    session = setup_logging(tmp_path / "logs", "DEBUG", console=False)
    window = MainWindow(
        config,
        tmp_path / "config.json",
        session,
        data_dir=tmp_path,
        autostart=False,
    )
    qtbot.addWidget(window)
    return window


def test_stylesheet_contains_light_palette(qapp: QApplication) -> None:
    stylesheet = theme.apply_theme(qapp)
    assert theme.BG in stylesheet
    assert theme.ACCENT in stylesheet
    assert "border-radius: 14px" in stylesheet


def test_main_window_title_and_initial_state(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    assert window.windowTitle() == window_title()
    assert window.power_button.toolTip() == "启动服务"
    assert not window.drop_zone.isEnabled()
    assert window.status_chip.text() == "未启动"
    assert window.file_table is not None
    assert window.log_panel is not None
    assert window.text_panel is not None
    assert window.text_panel.sync_chip.text() == "已停止"
    assert window.status_online.text() == "在线 0"
    assert window.status_countdown.text() == "未启动"


def test_main_window_start_and_stop_server(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    window.show()
    with qtbot.waitSignal(window.backend.started, timeout=20000):
        window.start_server()
    qtbot.waitUntil(lambda: window.backend.is_running, timeout=5000)
    assert window.backend.share_url.startswith("http://")
    assert window.address_button.text() in window.backend.share_url
    assert window.power_button.toolTip() == "停止服务"
    assert window.status_online.text() == "在线 0"
    qtbot.waitUntil(lambda: window.file_stack.currentWidget() is window.empty_state, timeout=8000)
    assert window.file_count_label.text() == "共 0 个"
    qtbot.waitUntil(lambda: window.text_panel.sync_chip.text() == "实时同步", timeout=8000)

    with qtbot.waitSignal(window.backend.stopped, timeout=15000):
        window.backend.stop_server("test-stop")
    qtbot.waitUntil(lambda: not window.backend.is_running, timeout=5000)
    assert window.power_button.toolTip() == "启动服务"
    assert window.text_panel.sync_chip.text() == "已停止"
    window.hide()


def test_text_panel_send_and_display(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    window.show()
    with qtbot.waitSignal(window.backend.started, timeout=20000):
        window.start_server()
    qtbot.waitUntil(lambda: window.text_panel.sync_chip.text() == "实时同步", timeout=8000)

    window.text_panel.input.setText("会议室在三楼，文件放共享盘")
    window.text_panel.send_button.click()
    qtbot.waitUntil(lambda: window.text_panel.message_count == 1, timeout=8000)
    messages = window.text_panel.messages()
    assert messages[0]["message"] == "会议室在三楼，文件放共享盘"
    assert messages[0]["client_ip"] in ("127.0.0.1", "::1")

    window.text_panel.input.setText("第二条")
    window.text_panel.input.returnPressed.emit()
    qtbot.waitUntil(lambda: window.text_panel.message_count == 2, timeout=8000)

    with qtbot.waitSignal(window.backend.stopped, timeout=15000):
        window.backend.stop_server("test-stop")
    qtbot.waitUntil(lambda: not window.backend.is_running, timeout=5000)
    window.hide()


def test_logs_drawer_and_connection_popup(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    window.show()
    assert window.log_drawer.is_open is False
    window.logs_button.click()
    qtbot.waitUntil(lambda: window.log_drawer.is_open, timeout=2000)
    window.logs_button.click()
    qtbot.waitUntil(lambda: window.log_drawer.is_open is False, timeout=2000)

    with qtbot.waitSignal(window.backend.started, timeout=20000):
        window.start_server()
    window.address_button.click()
    qtbot.waitUntil(lambda: window.connection_popup.isVisible(), timeout=3000)
    window.connection_popup.hide()
    with qtbot.waitSignal(window.backend.stopped, timeout=15000):
        window.backend.stop_server("test-stop")
    qtbot.waitUntil(lambda: not window.backend.is_running, timeout=5000)
    window.hide()


def test_settings_dialog_saves_values(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    dialog = SettingsDialog(window.app_config, window)
    qtbot.addWidget(dialog)
    assert dialog.height() <= 760
    dialog.port_spin.setValue(9123)
    dialog.browser_toggle.setChecked(True)
    dialog.ip_scope_combo.setCurrentIndex(dialog.ip_scope_combo.findData("last2"))
    dialog.auto_toggle.setChecked(False)
    dialog.hours_spin.setValue(12.0)
    dialog.tray_toggle.setChecked(False)
    dialog.level_combo.setCurrentText("DEBUG")
    dialog.autostart_toggle.setChecked(True)
    assert not dialog.silent_row.isHidden()
    dialog.silent_toggle.setChecked(True)
    custom_downloads = tmp_path / "downloads_custom"
    custom_downloads.mkdir()
    with patch(
        "quicklanshare.ui.settings_dialog.QFileDialog.getExistingDirectory",
        return_value=str(custom_downloads),
    ):
        dialog.download_dir_button.click()
    assert dialog.download_dir_edit.text() == str(custom_downloads)
    dialog._on_save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.result_config.server.port == 9123
    assert dialog.result_config.server.open_browser is True
    assert dialog.result_config.server.ip_scope == "last2"
    assert dialog.result_config.server.auto_shutdown_enabled is False
    assert dialog.result_config.server.auto_shutdown_hours == 12.0
    assert dialog.result_config.ui.close_to_tray is False
    assert dialog.result_config.ui.log_level == "DEBUG"
    assert dialog.result_config.ui.autostart is True
    assert dialog.result_config.ui.autostart_silent is True
    assert dialog.result_config.ui.download_dir == str(custom_downloads)
    window.hide()


def test_file_table_checkboxes_and_download_status(tmp_path: Path, qtbot) -> None:
    table = FileTable()
    qtbot.addWidget(table)
    local = tmp_path / "a.txt"
    local.write_text("data", encoding="utf-8")
    files = [
        {"name": "a.txt", "size": 4, "modified": 0, "download_count": 0},
        {"name": "b.txt", "size": 8, "modified": 0, "download_count": 2},
    ]
    table.set_files(files, {"a.txt": local}, {"b.txt"})
    assert table.rowCount() == 2
    assert table.checked_count() == 0

    table.set_all_checked(True)
    assert table.checked_count() == 2
    assert table.check_all_state() == Qt.CheckState.Checked

    status_texts: list[str] = []
    for row in range(table.rowCount()):
        label = table.cellWidget(row, table.COL_STATUS).findChild(QLabel)
        if label is not None:
            status_texts.append(label.text())
    assert "已下载" in status_texts
    assert "下载中" in status_texts

    folder_buttons = table.cellWidget(0, table.COL_ACTIONS).findChildren(QPushButton)
    assert folder_buttons
    with qtbot.waitSignal(table.openFolderRequested, timeout=2000):
        folder_buttons[-1].click()

    table.set_all_checked(False)
    assert table.checked_count() == 0
    first_box = table.cellWidget(0, table.COL_CHECK).findChild(QCheckBox)
    assert first_box is not None
    first_box.setChecked(True)
    assert table.checked_count() == 1
    assert table.check_all_state() == Qt.CheckState.PartiallyChecked


def test_open_download_folder_quotes_spaces(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    local = tmp_path / "新建 文本文档.txt"
    local.write_text("data", encoding="utf-8")
    window._download_registry.record(local.name, local)
    window._downloaded = window._download_registry.all()
    with patch("quicklanshare.ui.main_window.subprocess.Popen") as popen:
        window.open_download_folder(local.name)
    command = popen.call_args[0][0]
    assert command.startswith("explorer /select,")
    assert f'"{local}"' in command
    window.hide()


def test_open_data_dir_uses_uploads(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    with patch("quicklanshare.ui.main_window.QDesktopServices.openUrl") as open_url:
        window.open_data_dir()
    assert (tmp_path / "uploads").is_dir()
    opened = Path(open_url.call_args[0][0].toLocalFile())
    assert opened.resolve() == (tmp_path / "uploads").resolve()
    window.hide()


def test_main_window_download_state_filter_and_qr(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    window.show()
    with qtbot.waitSignal(window.backend.started, timeout=20000):
        window.start_server()
    qtbot.waitUntil(lambda: window.backend.is_running, timeout=5000)
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    window.app_config.ui.download_dir = str(download_dir)
    assert window._download_dir() == download_dir
    source = tmp_path / "sample.txt"
    source.write_text("download me", encoding="utf-8")
    target = download_dir / "sample.txt"
    window.backend.upload_paths([source])
    qtbot.waitUntil(
        lambda: any(item.get("name") == "sample.txt" for item in window._files),
        timeout=8000,
    )
    window.save_download("sample.txt")
    qtbot.waitUntil(
        lambda: window._download_registry.get("sample.txt") == target,
        timeout=10000,
    )
    assert target.exists()
    assert "已下载 1" in window.download_summary.text()

    local = tmp_path / "demo.txt"
    local.write_text("demo", encoding="utf-8")
    window._download_registry.record("demo.txt", local)
    window._downloaded = window._download_registry.all()
    window._apply_files([{"name": "demo.txt", "size": 4, "modified": 0, "download_count": 0}])
    assert "已下载 1" in window.download_summary.text()
    assert window.file_table.rowCount() == 1
    window.select_all_checkbox.setChecked(True)
    assert window.file_table.checked_count() == 1
    assert window.zip_button.isEnabled()
    assert window.delete_button.isEnabled()

    window.qr_button.click()
    qtbot.waitUntil(lambda: window.qr_overlay.isVisible(), timeout=3000)
    QTest.mouseClick(window.qr_overlay, Qt.MouseButton.LeftButton, pos=QPoint(8, 8))
    qtbot.waitUntil(lambda: not window.qr_overlay.isVisible(), timeout=2000)

    window.qr_button.hoverChanged.emit(True)
    qtbot.waitUntil(lambda: window.qr_peek.isVisible(), timeout=2000)
    window.qr_button.hoverChanged.emit(False)
    qtbot.waitUntil(lambda: not window.qr_peek.isVisible(), timeout=2000)

    with qtbot.waitSignal(window.backend.stopped, timeout=15000):
        window.backend.stop_server("test-stop")
    qtbot.waitUntil(lambda: not window.backend.is_running, timeout=5000)
    window.hide()
