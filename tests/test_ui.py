from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog

from quicklanshare.core.version import window_title
from quicklanshare.ui import theme
from quicklanshare.ui.main_window import MainWindow
from quicklanshare.ui.settings_dialog import SettingsDialog
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
    dialog.port_spin.setValue(9123)
    dialog.browser_toggle.setChecked(True)
    dialog.auto_toggle.setChecked(False)
    dialog.hours_spin.setValue(12.0)
    dialog.tray_toggle.setChecked(False)
    dialog.level_combo.setCurrentText("DEBUG")
    dialog._on_save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.result_config.server.port == 9123
    assert dialog.result_config.server.open_browser is True
    assert dialog.result_config.server.auto_shutdown_enabled is False
    assert dialog.result_config.server.auto_shutdown_hours == 12.0
    assert dialog.result_config.ui.close_to_tray is False
    assert dialog.result_config.ui.log_level == "DEBUG"
    window.hide()
