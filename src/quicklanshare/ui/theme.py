"""浅色现代主题：配色、字体、阴影与全局样式表。

设计目标：Windows 10 / 11 上一致的浅色外观，卡片化布局、克制的蓝色强调色、
清晰的层级与状态反馈；不依赖任何第三方主题库。
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QWidget

# ------------------------------------------------------------------ 调色板
BG = "#F4F7FB"
SURFACE = "#FFFFFF"
SURFACE_MUTED = "#F8FAFD"
SURFACE_ALT = "#F1F5FB"
BORDER = "#E4EAF3"
BORDER_STRONG = "#CBD5E1"
TEXT = "#0F172A"
TEXT_SECONDARY = "#475569"
TEXT_MUTED = "#8494AC"
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
ACCENT_PRESSED = "#1E40AF"
ACCENT_SOFT = "#EFF4FF"
SUCCESS = "#15803D"
SUCCESS_SOFT = "#ECFDF3"
WARNING = "#B45309"
WARNING_SOFT = "#FFF8EB"
DANGER = "#B91C1C"
DANGER_SOFT = "#FEF2F2"
INFO = "#0369A1"
INFO_SOFT = "#F0F9FF"


def _pick_font_family(app: QApplication) -> str:
    available = set(QFontDatabase.families())
    for family in ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI Variable Text", "Segoe UI"):
        if family in available:
            return family
    return app.font().family()


def add_shadow(
    widget: QWidget,
    *,
    blur: int = 26,
    offset_y: int = 6,
    alpha: int = 22,
    color: str = "#0F172A",
) -> None:
    """给卡片添加柔和阴影，提升层次感。"""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, offset_y)
    shadow_color = QColor(color)
    shadow_color.setAlpha(alpha)
    effect.setColor(shadow_color)
    widget.setGraphicsEffect(effect)


def apply_theme(app: QApplication) -> str:
    """应用调色板、字体与样式表，返回样式表文本（便于测试校验）。"""
    app.setStyle("Fusion")
    family = _pick_font_family(app)
    font = QFont(family)
    font.setPointSize(10)
    app.setFont(font)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE_MUTED))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_MUTED))
    app.setPalette(palette)

    stylesheet = build_stylesheet(family)
    app.setStyleSheet(stylesheet)
    return stylesheet


def build_stylesheet(family: str) -> str:
    """生成全局 QSS；``family`` 为运行环境实际可用的字体。"""
    return f"""
* {{
    font-family: "{family}";
    outline: none;
}}
QMainWindow, QDialog, QWidget#Root {{
    background-color: {BG};
    color: {TEXT};
}}
QScrollArea#ContentScroll {{
    background-color: {BG};
    border: none;
}}
QScrollArea#ContentScroll > QWidget > QWidget {{
    background-color: {BG};
}}
QWidget {{
    color: {TEXT};
    font-size: 13px;
}}
QFrame#Card, QWidget#Card {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#Hero {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #FFFFFF, stop:0.55 #F7FAFF, stop:1 #EDF4FF);
    border: 1px solid {BORDER};
    border-radius: 18px;
}}
QWidget#Header {{
    background-color: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}
QWidget#StatusBar {{
    background-color: {SURFACE};
    border-top: 1px solid {BORDER};
}}
QWidget#StatusBar QLabel#Muted {{
    font-size: 11px;
}}
QSplitter#MainSplitter::handle {{
    background-color: transparent;
}}
QSplitter#MainSplitter::handle:hover {{
    background-color: {BORDER};
    border-radius: 2px;
}}
QFrame#Popup {{
    background-color: transparent;
    border: none;
}}
QFrame#QrPeek {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#QrCard {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 16px;
}}
QWidget#QrOverlay {{
    background-color: transparent;
}}
QFrame#Drawer {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#LogPanel {{
    background-color: transparent;
    border: none;
}}
QScrollArea#ChatScroll,
QScrollArea#TransferScroll {{
    background-color: transparent;
    border: none;
}}
QStackedWidget#ChatArea {{
    background-color: transparent;
}}
QStackedWidget#ChatArea > QWidget {{
    background-color: transparent;
}}
QScrollArea#ChatScroll > QWidget > QWidget,
QScrollArea#TransferScroll > QWidget > QWidget {{
    background-color: transparent;
}}
QFrame#OwnBubble {{
    background-color: #EAF1FF;
    border: 1px solid #D9E6FF;
    border-radius: 12px;
}}
QFrame#OtherBubble {{
    background-color: {SURFACE_MUTED};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#ScopeControl {{
    background-color: {SURFACE_MUTED};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#ScopeTitle {{
    color: {TEXT_SECONDARY};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#ScopeDigit {{
    color: {TEXT_MUTED};
    font-size: 9px;
}}
QFrame#ManageBar {{
    background-color: {SURFACE_MUTED};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#Composer {{
    background-color: {SURFACE_MUTED};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#Composer QLineEdit {{
    background: transparent;
    border: none;
    padding: 4px 2px;
    font-size: 13px;
}}
QFrame#Composer QLineEdit:focus {{
    border: none;
    background: transparent;
}}
QWidget#Divider {{
    background-color: {BORDER};
    max-height: 1px;
    min-height: 1px;
}}
QLabel {{
    background: transparent;
    color: {TEXT};
}}
QLabel#BrandName {{
    font-size: 17px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#BrandSub {{
    font-size: 11px;
    color: {TEXT_MUTED};
}}
QLabel#PageTitle {{
    font-size: 22px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#PageSubtitle {{
    font-size: 13px;
    color: {TEXT_SECONDARY};
}}
QLabel#SectionTitle {{
    font-size: 15px;
    font-weight: 600;
    color: {TEXT};
}}
QLabel#Muted {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QLabel#Secondary {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
}}
QLabel#UrlText {{
    color: {ACCENT};
    font-size: 15px;
    font-weight: 600;
}}
QLabel#StatValue {{
    font-size: 20px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#StatLabel {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}
QLabel#VersionBadge {{
    background-color: {ACCENT_SOFT};
    color: {ACCENT};
    border-radius: 9px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#StatusChip {{
    border-radius: 11px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 600;
    background-color: {SURFACE_ALT};
    color: {TEXT_SECONDARY};
}}
QLabel#StatusChip[state="ok"] {{
    background-color: {SUCCESS_SOFT};
    color: {SUCCESS};
}}
QLabel#StatusChip[state="warn"] {{
    background-color: {WARNING_SOFT};
    color: {WARNING};
}}
QLabel#StatusChip[state="error"] {{
    background-color: {DANGER_SOFT};
    color: {DANGER};
}}
QLabel#StatusChip[state="busy"] {{
    background-color: {ACCENT_SOFT};
    color: {ACCENT};
}}
QLabel#Pill {{
    background-color: {SURFACE_MUTED};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 4px 10px;
    color: {TEXT_SECONDARY};
    font-size: 12px;
}}
QLabel#FieldLabel {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#Hint {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}
QLabel#Toast {{
    background-color: #0F172A;
    color: #FFFFFF;
    border-radius: 10px;
    padding: 10px 18px;
    font-size: 12px;
}}
QLabel#EmptyIcon {{
    color: {BORDER_STRONG};
}}
QLabel#QrFrame {{
    background-color: #FFFFFF;
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QPushButton {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 500;
    min-height: 18px;
}}
QPushButton:hover {{
    background-color: {SURFACE_MUTED};
    border-color: #AFC0D6;
}}
QPushButton:pressed {{
    background-color: {SURFACE_ALT};
}}
QPushButton:disabled {{
    color: #A9B6C8;
    border-color: {BORDER};
    background-color: {SURFACE_MUTED};
}}
QPushButton[role="primary"] {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
    color: #FFFFFF;
    font-weight: 600;
    padding: 8px 18px;
}}
QPushButton[role="primary"]:hover {{
    background-color: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton[role="primary"]:pressed {{
    background-color: {ACCENT_PRESSED};
}}
QPushButton[role="primary"]:disabled {{
    background-color: #9DBBF7;
    border-color: #9DBBF7;
    color: #FFFFFF;
}}
QPushButton[role="ghost"] {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {TEXT_SECONDARY};
}}
QPushButton[role="ghost"]:hover {{
    background-color: {SURFACE_ALT};
    color: {TEXT};
}}
QPushButton[role="soft"] {{
    background-color: {ACCENT_SOFT};
    border: 1px solid transparent;
    color: {ACCENT};
    font-weight: 600;
}}
QPushButton[role="soft"]:hover {{
    background-color: #E2ECFF;
}}
QPushButton[role="danger"] {{
    background-color: {SURFACE};
    border: 1px solid #F3C9C9;
    color: {DANGER};
}}
QPushButton[role="danger"]:hover {{
    background-color: {DANGER_SOFT};
    border-color: #E9A8A8;
}}
QPushButton[role="danger"]:disabled,
QPushButton[role="soft"]:disabled {{
    background-color: {SURFACE_MUTED};
    border-color: {BORDER};
    color: #A9B6C8;
}}
QPushButton[role="tiny"] {{
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 11px;
    min-height: 16px;
}}
QPushButton[role="refresh"] {{
    background-color: transparent;
    border: 1px solid {BORDER};
    color: {TEXT_SECONDARY};
    padding: 5px 10px;
    font-size: 12px;
}}
QPushButton[role="refresh"]:hover {{
    background-color: {SURFACE_MUTED};
}}
QPushButton[role="icon"] {{
    background-color: transparent;
    border: 1px solid transparent;
    padding: 4px;
}}
QPushButton[role="icon"]:hover {{
    background-color: {SURFACE_ALT};
    border-color: {BORDER};
}}
QPushButton[role="icon"]:pressed {{
    background-color: {BORDER};
}}
QPushButton[role="icon"][tone="danger"]:hover {{
    background-color: {DANGER_SOFT};
    border-color: #F3C9C9;
}}
QPushButton[role="iconDanger"] {{
    background-color: transparent;
    border: 1px solid transparent;
    padding: 4px;
}}
QPushButton[role="iconDanger"]:hover {{
    background-color: {DANGER_SOFT};
    border-color: #F3C9C9;
}}
QPushButton[role="address"] {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {ACCENT};
    font-size: 12px;
    font-weight: 600;
    text-align: left;
    padding: 5px 8px;
}}
QPushButton[role="address"]:hover {{
    background-color: {ACCENT_SOFT};
    border-color: #D9E6FF;
}}
QPushButton[role="address"]:disabled {{
    color: {TEXT_MUTED};
    background-color: transparent;
}}
QPushButton[role="link"] {{
    background: transparent;
    border: none;
    color: {ACCENT};
    padding: 2px 4px;
    font-size: 12px;
}}
QPushButton[role="link"]:hover {{
    color: {ACCENT_HOVER};
    text-decoration: underline;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    padding: 6px 10px;
    min-height: 20px;
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
}}
QCheckBox {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
    spacing: 6px;
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    border-color: #A9BBD4;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
    background-color: #FFFFFF;
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    background-color: {SURFACE_MUTED};
    color: {TEXT_MUTED};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 18px;
    border: none;
    background: transparent;
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {ACCENT};
    outline: none;
    padding: 4px;
}}
QTableWidget {{
    background-color: {SURFACE};
    border: none;
    gridline-color: transparent;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT};
    alternate-background-color: {SURFACE_MUTED};
}}
QTableWidget::item {{
    padding: 4px 8px;
    border: none;
    border-bottom: 1px solid #F1F5FA;
}}
QTableWidget::item:selected {{
    background-color: {ACCENT_SOFT};
    color: {TEXT};
}}
QHeaderView::section {{
    background-color: {SURFACE};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px 8px;
    font-size: 11px;
    font-weight: 600;
}}
QTableCornerButton::section {{
    background-color: {SURFACE};
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #D7E0EC;
    border-radius: 4px;
    min-height: 36px;
}}
QScrollBar::handle:vertical:hover {{
    background: #B9C7DA;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
    height: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #D7E0EC;
    border-radius: 4px;
    min-width: 36px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
    width: 0px;
}}
QPlainTextEdit, QTextEdit {{
    background-color: #FBFDFF;
    border: 1px solid {BORDER};
    border-radius: 10px;
    color: {TEXT_SECONDARY};
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
    padding: 6px;
}}
QProgressBar {{
    background-color: #EDF2F9;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 4px;
}}
QProgressBar[state="done"]::chunk {{
    background-color: {SUCCESS};
}}
QProgressBar[state="error"]::chunk {{
    background-color: {DANGER};
}}
QToolTip {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 6px 8px;
}}
QMenu {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 22px 7px 12px;
    border-radius: 6px;
    color: {TEXT};
}}
QMenu::item:selected {{
    background-color: {ACCENT_SOFT};
    color: {ACCENT};
}}
QMenu::separator {{
    height: 1px;
    background-color: {BORDER};
    margin: 5px 8px;
}}
QDialog QLabel#SectionTitle {{
    color: {TEXT};
}}
QFrame#SettingGroup {{
    background-color: {SURFACE_MUTED};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#TransferRow {{
    background-color: transparent;
    border-bottom: 1px solid #F1F5FA;
}}
QPushButton#CloseButton {{
    background: transparent;
    border: none;
    color: {TEXT_SECONDARY};
    font-size: 14px;
    padding: 4px 8px;
}}
QPushButton#CloseButton:hover {{
    background-color: {DANGER_SOFT};
    color: {DANGER};
    border-radius: 6px;
}}
QMessageBox {{
    background-color: {SURFACE};
}}
"""
