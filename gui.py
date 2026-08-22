"""PySide6 Fluent dark GUI for the Windows System Information Viewer."""

from __future__ import annotations

import base64
import ctypes
import datetime
import json
import os
import re
import subprocess
import tempfile
import threading
import time
from typing import Any

from PySide6.QtCore import Qt, Signal, QObject, QByteArray, QSize, QPoint, QRect, QMetaObject
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QIcon,
                          QKeySequence, QPainter, QPen, QPixmap, QPolygon,
                          QShortcut)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QLayout, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
    QProgressBar, QProgressDialog, QPushButton, QRadioButton, QScrollArea,
    QSizePolicy, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem,
    QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from app_logger import get_logger
from collectors import Collector
from config import get_config, reload_config
from paths import icon_path, icons_dir, lib_dir, data_dir
from sensors import SENSOR_TYPE_ORDER, fmt_sensor_value
from tools import CATEGORIES as TOOL_CATEGORIES, PREAMBLE as TOOL_PREAMBLE
from tools import resolve_placeholders as resolve_tool_placeholders
from updater import LibraryUpdater

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
#  Colors & QSS
# ---------------------------------------------------------------------------

# Dark theme (default)
_DARK = {
    "bg": "#1c1c1c",
    "sidebar_bg": "#252525",
    "card_bg": "#2d2d2d",
    "accent": "#60cdff",
    "text_primary": "#ffffff",
    "text_secondary": "#9a9a9a",
    "text_dim": "#6a6a6a",
    "divider": "#3a3a3a",
    "error": "#e07b7b",
    "green": "#5fcf80",
    "yellow": "#f0c040",
    "red": "#e07b7b",
    "table_alt": "#333333",
    "hover": "#3a3a3a",
}

# Light theme
_LIGHT = {
    "bg": "#f5f5f5",
    "sidebar_bg": "#e8e8e8",
    "card_bg": "#ffffff",
    "accent": "#0078d4",
    "text_primary": "#1a1a1a",
    "text_secondary": "#666666",
    "text_dim": "#999999",
    "divider": "#d0d0d0",
    "error": "#c0392b",
    "green": "#2e7d32",
    "yellow": "#f57f17",
    "red": "#c0392b",
    "table_alt": "#f0f0f0",
    "hover": "#e0e0e0",
}

# Current active theme colors (set by build_qss)
_BG = ""
_SIDEBAR_BG = ""
_CARD_BG = ""
_ACCENT = ""
_TEXT_PRIMARY = ""
_TEXT_SECONDARY = ""
_TEXT_DIM = ""
_DIVIDER = ""
_ERROR = ""
_GREEN = ""
_YELLOW = ""
_RED = ""


class _SelBlackItem(QTableWidgetItem):
    """Table item that shows black foreground when selected.

    A programmatically-set foreground brush (via ``setForeground``) has
    higher priority than the QSS ``::item:selected`` color rule, so
    colour-coded cells (green/red/yellow State, Source, Level, etc.)
    would keep their colour on a selected row instead of turning black
    like the rest of the row.  This subclass overrides ``data()`` for
    the ForegroundRole so that whenever the item is selected the
    foreground collapses to black, matching the QSS selected style.
    """

    def data(self, role: int):
        if role == Qt.ItemDataRole.ForegroundRole and self.isSelected():
            return QColor("#000000")
        return super().data(role)


class _NumericItem(_SelBlackItem):
    """Table item that sorts numerically by a stored value.

    Stores a numeric value in ``Qt.ItemDataRole.UserRole`` and overrides
    ``__lt__`` so the column sorts by the numeric value rather than the
    display text.  Inherits the black-on-select foreground behaviour
    from ``_SelBlackItem`` so it can also be colour-coded via
    ``setForeground()``.
    """

    def __init__(self, text: str, value: float | int):
        super().__init__(text)
        self.setData(Qt.ItemDataRole.UserRole, value)

    def __lt__(self, other):
        other_val = other.data(Qt.ItemDataRole.UserRole)
        if other_val is None:
            return super().__lt__(other)
        my_val = self.data(Qt.ItemDataRole.UserRole)
        try:
            return (my_val if my_val is not None else 0) < (
                other_val if other_val is not None else 0)
        except TypeError:
            return super().__lt__(other)


class _Sparkline(QWidget):
    """Mini sparkline graph widget — draws a rolling window of values.

    Paints a filled line chart of the last N samples using QPainter.
    Used for CPU usage, RAM usage, CPU temp, GPU temp historical graphs.
    """

    def __init__(self, parent=None, max_samples: int = 60,
                 color: str = "#60cdff", label: str = ""):
        super().__init__(parent)
        self._samples: list[float] = []
        self._max = max_samples
        self._color = color
        self._label = label
        self.setMinimumHeight(70)
        self.setMinimumWidth(160)

    def add_sample(self, value: float) -> None:
        self._samples.append(value)
        if len(self._samples) > self._max:
            self._samples.pop(0)
        self.update()

    def set_samples(self, samples: list[float]) -> None:
        self._samples = list(samples[-self._max:])
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        p.fillRect(0, 0, w, h, QColor(_CARD_BG))

        if not self._samples:
            p.setPen(QColor(_TEXT_SECONDARY))
            p.drawText(0, h - 4, "No data")
            return

        vals = self._samples
        n = len(vals)
        vmin = min(vals)
        vmax = max(vals)
        flat = vmax == vmin
        if flat:
            vmax = vmin + 1
        pad = 6
        gw = w - pad * 2
        gh = h - pad * 2 - 12

        poly = QPolygon()
        for i, v in enumerate(vals):
            x = pad + int(gw * i / max(n - 1, 1))
            if flat:
                y = pad + gh // 2
            else:
                y = pad + gh - int(gh * (v - vmin) / (vmax - vmin))
            poly.append(QPoint(x, y))

        fill = QColor(self._color)
        fill.setAlpha(50)
        p.setBrush(QBrush(fill))
        p.setPen(Qt.PenStyle.NoPen)
        fill_poly = QPolygon(poly)
        fill_poly.append(QPoint(pad + gw, pad + gh))
        fill_poly.append(QPoint(pad, pad + gh))
        p.drawPolygon(fill_poly)

        p.setPen(QPen(QColor(self._color), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolyline(poly)

        last = vals[-1]
        p.setPen(QColor(_TEXT_PRIMARY))
        p.setFont(QFont("Consolas", 9))
        p.drawText(pad, h - 2,
                   f"{self._label}: {last:.1f}  (min {vmin:.1f} / max {vmax:.1f})")


def build_qss(theme: str = "dark") -> str:
    """Build the QSS stylesheet for the given theme.

    Also sets module-level color constants so code that references them
    (sensor highlighting, error text, etc.) uses the right colors.
    """
    global _BG, _SIDEBAR_BG, _CARD_BG, _ACCENT, _TEXT_PRIMARY
    global _TEXT_SECONDARY, _TEXT_DIM, _DIVIDER, _ERROR
    global _GREEN, _YELLOW, _RED

    c = _LIGHT if theme == "light" else _DARK
    _BG = c["bg"]
    _SIDEBAR_BG = c["sidebar_bg"]
    _CARD_BG = c["card_bg"]
    _ACCENT = c["accent"]
    _TEXT_PRIMARY = c["text_primary"]
    _TEXT_SECONDARY = c["text_secondary"]
    _TEXT_DIM = c["text_dim"]
    _DIVIDER = c["divider"]
    _ERROR = c["error"]
    _GREEN = c["green"]
    _YELLOW = c["yellow"]
    _RED = c["red"]

    _alt = c["table_alt"]
    _hover = c["hover"]

    return f"""
QMainWindow, QWidget {{
    background-color: {_BG};
    color: {_TEXT_PRIMARY};
}}
QFrame#sidebar {{
    background-color: {_SIDEBAR_BG};
    border-right: 1px solid {_DIVIDER};
}}
QLabel#app-title {{
    color: {_TEXT_PRIMARY};
    font-size: 18px;
    font-weight: 700;
}}
QLabel#hostname {{
    color: {_TEXT_DIM};
    font-size: 12px;
}}
QLabel#copyright {{
    color: {_TEXT_DIM};
    font-size: 10px;
    padding: 4px 0px 0px 0px;
}}
QPushButton#nav-btn {{
    text-align: left;
    padding: 10px 16px 10px 14px;
    border: none;
    border-left: 3px solid transparent;
    background: transparent;
    color: {_TEXT_SECONDARY};
    font-size: 15px;
}}
QPushButton#nav-btn:hover {{
    background-color: {_CARD_BG};
}}
QPushButton#nav-btn:checked {{
    background-color: {_CARD_BG};
    color: {_ACCENT};
    border-left: 3px solid {_ACCENT};
    font-weight: 600;
}}
QLabel#page-title {{
    color: {_TEXT_PRIMARY};
    font-size: 24px;
    font-weight: 700;
}}
QLineEdit#search {{
    background-color: {_CARD_BG};
    border: 1px solid {_DIVIDER};
    border-radius: 6px;
    padding: 7px 12px;
    color: {_TEXT_PRIMARY};
    font-size: 13px;
    selection-background-color: {_ACCENT};
    selection-color: #000000;
}}
QLineEdit#search:focus {{
    border: 1px solid {_ACCENT};
}}
QFrame#card {{
    background-color: {_CARD_BG};
    border-radius: 8px;
}}
QLabel#card-title {{
    color: {_ACCENT};
    font-size: 14px;
    font-weight: 700;
    padding-bottom: 6px;
}}
QLabel#row-key {{
    color: {_TEXT_SECONDARY};
    font-size: 14px;
}}
QLabel#row-key-compact {{
    color: {_TEXT_SECONDARY};
    font-size: 12px;
}}
QLabel#row-value {{
    color: {_TEXT_PRIMARY};
    font-size: 14px;
}}
QLabel#row-value-compact {{
    color: {_TEXT_PRIMARY};
    font-size: 12px;
}}
QLabel#error-text {{
    color: {_ERROR};
    font-size: 14px;
}}
QLabel#no-results {{
    color: {_TEXT_DIM};
    font-size: 16px;
    padding: 40px;
    alignment: center;
}}
QScrollArea {{
    border: none;
    background-color: {_BG};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {_DIVIDER};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:horizontal {{
    background: {_DIVIDER};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {_TEXT_DIM};
}}
QScrollBar::handle:horizontal:hover {{
    background: {_TEXT_DIM};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
QTabWidget#sensor-tabs::pane, QTabWidget#hardware-tabs::pane {{
    border: none;
    background: transparent;
    top: -1px;
}}
QTabBar#sensor-tabbar, QTabBar#hardware-tabbar {{
    background: transparent;
}}
QTabBar#sensor-tabbar::tab, QTabBar#hardware-tabbar::tab {{
    background: {_CARD_BG};
    color: {_TEXT_SECONDARY};
    border: 1px solid {_DIVIDER};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 16px;
    margin-right: 2px;
    font-size: 12px;
    min-width: 60px;
}}
QTabBar#sensor-tabbar::tab:hover, QTabBar#hardware-tabbar::tab:hover {{
    background: {_hover};
    color: {_TEXT_PRIMARY};
}}
QTabBar#sensor-tabbar::tab:selected, QTabBar#hardware-tabbar::tab:selected {{
    background: {_BG};
    color: {_ACCENT};
    border-color: {_DIVIDER};
    font-weight: 600;
}}
QPushButton#update-btn {{
    background-color: {_CARD_BG};
    border: 1px solid {_DIVIDER};
    border-radius: 6px;
    padding: 8px 14px;
    color: {_TEXT_SECONDARY};
    font-size: 12px;
}}
QPushButton#update-btn:hover {{
    background-color: {_hover};
    border: 1px solid {_ACCENT};
    color: {_ACCENT};
}}
QPushButton#update-btn:disabled {{
    color: {_TEXT_DIM};
    border: 1px solid {_DIVIDER};
}}
QLabel#update-status {{
    color: {_TEXT_DIM};
    font-size: 11px;
    padding: 2px 0px;
}}
QLabel#update-status-success {{
    color: {_GREEN};
    font-size: 11px;
    padding: 2px 0px;
}}
QLabel#update-status-error {{
    color: {_ERROR};
    font-size: 11px;
    padding: 2px 0px;
}}
QStatusBar {{
    background: {_SIDEBAR_BG};
    border-top: 1px solid {_DIVIDER};
}}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{
    color: {_TEXT_SECONDARY};
    font-size: 11px;
    padding: 0px 8px;
}}
QLabel#refresh-dot {{
    background: {_TEXT_DIM};
    border-radius: 4px;
    min-width: 8px;
    max-width: 8px;
    min-height: 8px;
    max-height: 8px;
    margin: 0px 4px 0px 8px;
}}
QLabel#refresh-dot-active {{
    background: {_GREEN};
    border-radius: 4px;
    min-width: 8px;
    max-width: 8px;
    min-height: 8px;
    max-height: 8px;
    margin: 0px 4px 0px 8px;
}}
QProgressBar {{
    background: {_BG};
    border: 1px solid {_DIVIDER};
    border-radius: 3px;
    text-align: center;
    color: {_TEXT_SECONDARY};
    font-size: 11px;
    min-height: 16px;
    max-height: 16px;
}}
QProgressBar::chunk {{
    background: {_GREEN};
    border-radius: 2px;
    color: #000000;
}}
QProgressBar::chunk:disabled {{
    background: {_DIVIDER};
}}
QLabel#loading-hint {{
    color: {_TEXT_DIM};
    font-size: 14px;
    padding: 40px;
}}
QPushButton#action-btn {{
    background-color: {_CARD_BG};
    border: 1px solid {_DIVIDER};
    border-radius: 6px;
    padding: 6px 14px;
    color: {_TEXT_SECONDARY};
    font-size: 12px;
}}
QPushButton#action-btn:hover {{
    background-color: {_hover};
    border: 1px solid {_ACCENT};
    color: {_ACCENT};
}}
QPushButton#action-btn:disabled {{
    color: {_TEXT_DIM};
    border: 1px solid {_DIVIDER};
}}
QPushButton#copy-btn {{
    background-color: transparent;
    border: 1px solid {_DIVIDER};
    border-radius: 4px;
    padding: 2px 8px;
    color: {_TEXT_SECONDARY};
    font-size: 11px;
}}
QPushButton#copy-btn:hover {{
    border: 1px solid {_ACCENT};
    color: {_ACCENT};
}}
QToolTip {{
    background-color: {_SIDEBAR_BG};
    color: {_TEXT_PRIMARY};
    border: 1px solid {_DIVIDER};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}}
QTableWidget {{
    background-color: {_CARD_BG};
    border: 1px solid {_DIVIDER};
    border-radius: 6px;
    gridline-color: {_DIVIDER};
    color: {_TEXT_PRIMARY};
    font-size: 13px;
    outline: none;
}}
QTableWidget::item {{
    padding: 4px 8px;
}}
QTableWidget::item:alternate {{
    background-color: {_alt};
}}
QTableWidget::item:selected,
QTableWidget::item:alternate:selected {{
    background-color: {_ACCENT};
    color: #000000;
}}
QHeaderView::section {{
    background-color: {_SIDEBAR_BG};
    color: {_TEXT_SECONDARY};
    padding: 6px 8px;
    border: none;
    border-right: 1px solid {_DIVIDER};
    border-bottom: 1px solid {_DIVIDER};
    font-weight: 600;
    font-size: 12px;
}}
QHeaderView::section:hover {{
    color: {_ACCENT};
}}
QTabWidget#software-tabs::pane {{
    border: none;
    background: transparent;
    top: -1px;
}}
QTabBar#software-tabbar {{
    background: transparent;
}}
QTabBar#software-tabbar::tab {{
    background: {_CARD_BG};
    color: {_TEXT_SECONDARY};
    border: 1px solid {_DIVIDER};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 16px;
    margin-right: 2px;
    font-size: 12px;
    min-width: 60px;
}}
QTabBar#software-tabbar::tab:hover {{
    background: {_hover};
    color: {_TEXT_PRIMARY};
}}
QTabBar#software-tabbar::tab:selected {{
    background: {_BG};
    color: {_ACCENT};
    border-color: {_DIVIDER};
    font-weight: 600;
}}
QDialog {{
    background-color: {_BG};
    color: {_TEXT_PRIMARY};
}}
/* Settings dialog sidebar */
QWidget#settings-sidebar {{
    background-color: {_SIDEBAR_BG};
    border-right: 1px solid {_DIVIDER};
}}
QLabel#settings-title {{
    font-size: 16px;
    font-weight: 700;
    color: {_TEXT_PRIMARY};
    padding: 4px 8px;
}}
QLabel#settings-section {{
    font-size: 13px;
    font-weight: 600;
    color: {_ACCENT};
    padding-top: 8px;
}}
QListWidget#settings-nav {{
    background-color: transparent;
    border: none;
    outline: none;
    font-size: 13px;
}}
QListWidget#settings-nav::item {{
    padding: 6px 8px;
    border-radius: 4px;
    color: {_TEXT_SECONDARY};
}}
QListWidget#settings-nav::item:hover {{
    background-color: {_CARD_BG};
    color: {_TEXT_PRIMARY};
}}
QListWidget#settings-nav::item:selected {{
    background-color: {_ACCENT};
    color: #000000;
    font-weight: 600;
}}
QWidget#settings-bottombar {{
    background-color: {_SIDEBAR_BG};
    border-top: 1px solid {_DIVIDER};
}}
QComboBox {{
    background-color: {_CARD_BG};
    border: 1px solid {_DIVIDER};
    border-radius: 4px;
    padding: 4px 8px;
    color: {_TEXT_PRIMARY};
    font-size: 13px;
}}
QComboBox:hover {{
    border: 1px solid {_ACCENT};
}}
QComboBox QAbstractItemView {{
    background-color: {_CARD_BG};
    color: {_TEXT_PRIMARY};
    selection-background-color: {_ACCENT};
    selection-color: #000000;
    border: 1px solid {_DIVIDER};
}}
QFrame#tools-category {{
    background-color: {_CARD_BG};
    border-radius: 8px;
}}
QFrame#tools-sidebar {{
    border-right: 1px solid {_DIVIDER};
}}
QPushButton#tool-cat-btn {{
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 8px 10px;
    text-align: left;
    color: {_TEXT_SECONDARY};
    font-size: 13px;
    font-weight: 500;
}}
QPushButton#tool-cat-btn:hover {{
    background-color: {_hover};
    color: {_TEXT_PRIMARY};
}}
QPushButton#tool-cat-btn:checked {{
    background-color: {_hover};
    color: {_ACCENT};
    font-weight: 700;
}}
QPushButton#tool-cat-btn[cat="repair"]:checked {{ color: {_RED}; }}
QPushButton#tool-cat-btn[cat="maintenance"]:checked {{ color: {_YELLOW}; }}
QPushButton#tool-cat-btn[cat="diagnostics"]:checked {{ color: {_ACCENT}; }}
QPushButton#tool-cat-btn[cat="status"]:checked {{ color: {_GREEN}; }}
QLineEdit#tool-search {{
    background-color: {_CARD_BG};
    border: 1px solid {_DIVIDER};
    border-radius: 6px;
    padding: 8px 12px;
    color: {_TEXT_PRIMARY};
    font-size: 13px;
}}
QLineEdit#tool-search:focus {{
    border: 1px solid {_ACCENT};
}}
QFrame#tool-card {{
    background-color: {_CARD_BG};
    border: 1px solid {_DIVIDER};
    border-left: 3px solid {_DIVIDER};
    border-radius: 6px;
}}
QFrame#tool-card:hover {{
    border: 1px solid {_ACCENT};
    border-left: 3px solid {_ACCENT};
    background-color: {_hover};
}}
QFrame#tool-card:disabled {{
    color: {_TEXT_DIM};
    border: 1px solid {_DIVIDER};
    border-left: 3px solid {_DIVIDER};
}}
QFrame#tool-card[cat="repair"] {{ border-left: 3px solid {_RED}; }}
QFrame#tool-card[cat="repair"]:hover {{ border-left: 3px solid {_RED}; border-color: {_RED}; }}
QFrame#tool-card[cat="maintenance"] {{ border-left: 3px solid {_YELLOW}; }}
QFrame#tool-card[cat="maintenance"]:hover {{ border-left: 3px solid {_YELLOW}; border-color: {_YELLOW}; }}
QFrame#tool-card[cat="diagnostics"] {{ border-left: 3px solid {_ACCENT}; }}
QFrame#tool-card[cat="diagnostics"]:hover {{ border-left: 3px solid {_ACCENT}; border-color: {_ACCENT}; }}
QFrame#tool-card[cat="status"] {{ border-left: 3px solid {_GREEN}; }}
QFrame#tool-card[cat="status"]:hover {{ border-left: 3px solid {_GREEN}; border-color: {_GREEN}; }}
QLabel#tool-card-name {{
    color: {_TEXT_PRIMARY};
    font-size: 13px;
    font-weight: 700;
}}
QLabel#tool-card-desc {{
    color: {_TEXT_DIM};
    font-size: 12px;
}}
QFrame#tool-card[cat="repair"] QLabel#tool-card-desc {{ color: {_RED}; }}
QFrame#tool-card[cat="maintenance"] QLabel#tool-card-desc {{ color: {_YELLOW}; }}
QFrame#tool-card[cat="diagnostics"] QLabel#tool-card-desc {{ color: {_ACCENT}; }}
QFrame#tool-card[cat="status"] QLabel#tool-card-desc {{ color: {_GREEN}; }}
QLabel#tool-badge {{
    background-color: {_ACCENT};
    color: #000000;
    font-size: 11px;
    font-weight: 700;
    border-radius: 10px;
}}
QPushButton#tool-log-header {{
    background: transparent;
    border: none;
    border-top: 1px solid {_DIVIDER};
    padding: 8px 0;
    color: {_TEXT_SECONDARY};
    font-size: 13px;
    font-weight: 600;
    text-align: left;
}}
QPushButton#tool-log-header:hover {{
    color: {_ACCENT};
}}
QFrame#tool-log-frame {{
    background: transparent;
}}
QPlainTextEdit#tool-log {{
    background-color: #050505;
    color: #00e060;
    border: 1px solid {_DIVIDER};
    border-radius: 6px;
    font-family: Consolas, 'Cascadia Mono', 'Courier New', monospace;
    font-size: 14px;
    padding: 6px;
}}
QLabel#tool-status {{
    color: {_ACCENT};
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#tool-bottom {{
    background-color: {_CARD_BG};
    border: 1px solid {_DIVIDER};
    border-radius: 6px;
    padding: 10px 20px;
    color: {_TEXT_SECONDARY};
    font-size: 13px;
}}
QPushButton#tool-bottom:hover {{
    border: 1px solid {_ACCENT};
    color: {_ACCENT};
}}
QPushButton#tool-bottom[accent="stop"]:hover {{ border-color: {_RED}; color: {_RED}; }}
QPushButton#tool-bottom[accent="reboot"]:hover {{ border-color: {_YELLOW}; color: {_YELLOW}; }}
QMenu {{
    background-color: {_CARD_BG};
    border: 1px solid {_DIVIDER};
    border-radius: 6px;
    padding: 6px;
}}
QMenu::item {{
    background-color: transparent;
    color: {_TEXT_PRIMARY};
    padding: 10px 28px;
    border-radius: 4px;
    margin: 2px 4px;
    font-size: 14px;
    min-width: 220px;
}}
QMenu::item:selected {{
    background-color: {_ACCENT};
    color: #000000;
}}
QMenu::separator {{
    height: 1px;
    background: {_DIVIDER};
    margin: 4px 8px;
}}
"""


KEY_WIDTH = 230
KEY_WIDTH_COMPACT = 170


def set_dark_titlebar(window: QMainWindow, force_dark: bool | None = None) -> None:
    """Set the window title bar to dark or light via DWM (Windows 10 build 18985+).

    If force_dark is None, uses the current theme setting.
    """
    try:
        if force_dark is None:
            from app import _resolve_theme
            force_dark = (_resolve_theme() == "dark")
        hwnd = int(window.winId())
        value = ctypes.c_int(1 if force_dark else 0)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
            ) == 0:
                break
    except Exception:
        pass


# ---------------------------------------------------------------------------
#  Signal classes for cross-thread communication
# ---------------------------------------------------------------------------

class CollectSignals(QObject):
    """Signals for background data collection."""
    step = Signal(str, str, int, int)  # label, thread_key, completed, total
    page_ready = Signal(int)
    finished = Signal()


class SensorRefreshSignals(QObject):
    """Signals for live sensor refresh."""
    refreshed = Signal()


class ProcessRefreshSignals(QObject):
    """Signals for process list refresh."""
    refreshed = Signal()


class SpeedTestSignals(QObject):
    """Signals for network speed test."""
    progress = Signal(str)
    finished = Signal(dict)


class BufferbloatSignals(QObject):
    """Signals for bufferbloat test."""
    progress = Signal(str)
    finished = Signal(dict)


class ToolSignals(QObject):
    """Signals for streaming PowerShell tool output to the Tools page."""
    output = Signal(str)
    status = Signal(str)
    finished = Signal(int)


# ---------------------------------------------------------------------------
#  Settings dialog
# ---------------------------------------------------------------------------

_ALL_SENSOR_TYPES = [
    "Temperature", "Fan", "Power", "Clock", "Voltage", "Load",
    "Level", "Data", "Factor", "Throughput", "SmallData", "Control",
]

_ALL_HARDWARE_TYPES = [
    "CPU", "GPU", "Motherboard", "Controller", "Storage",
    "Battery", "Memory", "Network", "PSU",
]

_SENSOR_SPARK_COLORS: dict[str, str] = {
    "Temperature": "#e07b7b",
    "Clock": "#60cdff",
    "Power": "#ffd166",
    "Load": "#7fde7f",
    "Fan": "#c0c0c0",
    "Voltage": "#b388ff",
}


# ---------------------------------------------------------------------------
#  Flow layout — wraps items left-to-right, top-to-bottom (like text)
# ---------------------------------------------------------------------------
class _FlowLayout(QLayout):
    """A simple flow layout that wraps widgets like text.

    Used by the Tools page so tool cards reflow automatically when the
    window is resized, without fixed column counts.
    """

    def __init__(self, parent=None, spacing: int = 8):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._spacing = spacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        m = self.contentsMargins()
        eff_rect = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = eff_rect.x()
        y = eff_rect.y()
        for item in self._items:
            wid = item.widget()
            if wid is None:
                continue
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > eff_rect.right() and line_height > 0:
                x = eff_rect.x()
                y = y + line_height + self._spacing
                next_x = x + hint.width() + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - eff_rect.y()


# ---------------------------------------------------------------------------
#  Tool card — clickable card for the Tools page
# ---------------------------------------------------------------------------
class _ToolCard(QFrame):
    """A clickable card representing a tool on the Tools page.

    Shows the tool name (bold), description (dim), and a mode-count
    badge if the tool has multiple modes.  Emits ``clicked`` on mouse
    release (left button only) or Enter/Space key press.
    """

    clicked = Signal()

    def __init__(self, name: str, desc: str, cat_key: str,
                 mode_count: int, mode_labels: list[str] | None = None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("tool-card")
        self.setProperty("cat", cat_key)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedWidth(240)
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._name = name.lower()
        self._desc = desc.lower()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(6)
        lbl_name = QLabel(name)
        lbl_name.setObjectName("tool-card-name")
        lbl_name.setToolTip(desc)
        top.addWidget(lbl_name)
        top.addStretch()
        if mode_count > 1:
            badge = QLabel(str(mode_count))
            badge.setObjectName("tool-badge")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setFixedSize(20, 20)
            if mode_labels:
                badge.setToolTip("\n".join(mode_labels))
            top.addWidget(badge)
        layout.addLayout(top)

        lbl_desc = QLabel(desc)
        lbl_desc.setObjectName("tool-card-desc")
        lbl_desc.setWordWrap(True)
        lbl_desc.setToolTip(desc)
        layout.addWidget(lbl_desc)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class SettingsDialog(QDialog):
    """Sidebar-style settings dialog with categorized sections."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(640, 520)
        cfg = get_config()

        # -- Main layout: top (sidebar + content) + bottom (buttons) -- #
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top section: sidebar + stacked content
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setObjectName("settings-sidebar")
        sidebar.setFixedWidth(180)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(8, 12, 8, 12)
        sb_layout.setSpacing(2)

        title = QLabel("Settings")
        title.setObjectName("settings-title")
        sb_layout.addWidget(title)
        sb_layout.addSpacing(16)

        self._nav = QListWidget()
        self._nav.setObjectName("settings-nav")
        self._nav.setIconSize(QSize(16, 16))
        for label, icon in [
            ("General",        "\u2699"),
            ("Refresh",        "\u23F1"),
            ("Processes",      "\u2630"),
            ("Sensors",        "\u26C8"),
            ("Speed Test",     "\u2195"),
        ]:
            item = QListWidgetItem(f"  {icon}  {label}")
            item.setSizeHint(QSize(0, 36))
            self._nav.addItem(item)
        self._nav.setCurrentRow(0)
        sb_layout.addWidget(self._nav)
        sb_layout.addStretch()

        top.addWidget(sidebar)

        # Content area
        self._stack = QStackedWidget()
        self._stack.setObjectName("settings-content")
        self._build_general_page(cfg)
        self._build_refresh_page(cfg)
        self._build_processes_page(cfg)
        self._build_sensors_page(cfg)
        self._build_speed_test_page(cfg)
        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        top.addWidget(self._stack)

        root.addLayout(top, 1)

        # Bottom button bar
        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(12, 8, 12, 8)
        btn_bar.addStretch()
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        btn_bar.addWidget(btns)

        bottom = QWidget()
        bottom.setObjectName("settings-bottombar")
        bottom.setLayout(btn_bar)
        root.addWidget(bottom)

    # -- Page builders -- #

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("settings-section")
        return lbl

    def _wrap_page(self, content_layout: QVBoxLayout) -> QScrollArea:
        """Wrap a page layout in a scroll area."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        w = QWidget()
        w.setLayout(content_layout)
        scroll.setWidget(w)
        return scroll

    def _build_general_page(self, cfg) -> None:
        page = QVBoxLayout()
        page.setContentsMargins(24, 20, 24, 20)
        page.setSpacing(14)
        page.addWidget(self._section_label("General"))

        form = QFormLayout()
        form.setSpacing(10)

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["dark", "light", "system"])
        self._theme_combo.setCurrentText(cfg.theme)
        form.addRow("Theme:", self._theme_combo)

        self._font_combo = QComboBox()
        self._font_combo.addItem("Default", "")
        for f in QFontDatabase.families():
            self._font_combo.addItem(f, f)
        idx = self._font_combo.findData(cfg.font_family)
        self._font_combo.setCurrentIndex(idx if idx >= 0 else 0)
        form.addRow("Font family:", self._font_combo)

        self._cache_spin = QSpinBox()
        self._cache_spin.setRange(60, 86400)
        self._cache_spin.setSingleStep(60)
        self._cache_spin.setSuffix(" s")
        self._cache_spin.setValue(cfg.cache_ttl_seconds)
        form.addRow("Static cache TTL:", self._cache_spin)

        page.addLayout(form)

        self._compact_check = QCheckBox("Compact row layout (denser, smaller text)")
        self._compact_check.setChecked(cfg.compact_view)
        page.addWidget(self._compact_check)

        self._progress_check = QCheckBox("Show progress bars for usage values")
        self._progress_check.setChecked(cfg.show_progress_bars)
        page.addWidget(self._progress_check)

        page.addStretch()
        self._stack.addWidget(self._wrap_page(page))

    def _build_refresh_page(self, cfg) -> None:
        page = QVBoxLayout()
        page.setContentsMargins(24, 20, 24, 20)
        page.setSpacing(14)
        page.addWidget(self._section_label("Refresh Intervals"))

        form = QFormLayout()
        form.setSpacing(10)

        self._refresh_spin = QSpinBox()
        self._refresh_spin.setRange(500, 60000)
        self._refresh_spin.setSingleStep(500)
        self._refresh_spin.setSuffix(" ms")
        self._refresh_spin.setValue(cfg.sensor_refresh_interval_ms)
        form.addRow("Sensor refresh interval:", self._refresh_spin)

        self._proc_refresh_spin = QSpinBox()
        self._proc_refresh_spin.setRange(1000, 60000)
        self._proc_refresh_spin.setSingleStep(500)
        self._proc_refresh_spin.setSuffix(" ms")
        self._proc_refresh_spin.setValue(cfg.process_refresh_interval_ms)
        form.addRow("Process & network refresh:", self._proc_refresh_spin)

        page.addLayout(form)

        hint = QLabel("Sensor refresh updates CPU/RAM/GPU sensor values.\n"
                       "Process & network refresh updates the Processes and Network pages.")
        hint.setObjectName("update-status")
        hint.setWordWrap(True)
        page.addWidget(hint)

        page.addStretch()
        self._stack.addWidget(self._wrap_page(page))

    def _build_processes_page(self, cfg) -> None:
        page = QVBoxLayout()
        page.setContentsMargins(24, 20, 24, 20)
        page.setSpacing(14)
        page.addWidget(self._section_label("Processes"))

        form = QFormLayout()
        form.setSpacing(10)

        self._proc_top_spin = QSpinBox()
        self._proc_top_spin.setRange(10, 500)
        self._proc_top_spin.setSingleStep(10)
        self._proc_top_spin.setSuffix(" processes")
        self._proc_top_spin.setValue(cfg.process_top_n)
        form.addRow("Top N processes:", self._proc_top_spin)

        self._sparkline_spin = QSpinBox()
        self._sparkline_spin.setRange(10, 300)
        self._sparkline_spin.setSingleStep(10)
        self._sparkline_spin.setSuffix(" samples")
        self._sparkline_spin.setValue(cfg.sparkline_max_samples)
        form.addRow("Sparkline graph samples:", self._sparkline_spin)

        page.addLayout(form)

        thresh_label = QLabel("Smart Colorization Thresholds")
        thresh_label.setObjectName("settings-section")
        page.addWidget(thresh_label)

        thresh_form = QFormLayout()
        thresh_form.setSpacing(8)

        self._cpu_warn = QSpinBox()
        self._cpu_warn.setRange(1, 100)
        self._cpu_warn.setSuffix(" %")
        self._cpu_warn.setValue(int(cfg.cpu_warn_threshold))
        thresh_form.addRow("CPU warning:", self._cpu_warn)

        self._cpu_crit = QSpinBox()
        self._cpu_crit.setRange(1, 100)
        self._cpu_crit.setSuffix(" %")
        self._cpu_crit.setValue(int(cfg.cpu_crit_threshold))
        thresh_form.addRow("CPU critical:", self._cpu_crit)

        self._mem_warn = QSpinBox()
        self._mem_warn.setRange(1, 10000)
        self._mem_warn.setSuffix(" MB")
        self._mem_warn.setValue(int(cfg.mem_warn_threshold))
        thresh_form.addRow("Memory warning:", self._mem_warn)

        self._mem_crit = QSpinBox()
        self._mem_crit.setRange(1, 10000)
        self._mem_crit.setSuffix(" MB")
        self._mem_crit.setValue(int(cfg.mem_crit_threshold))
        thresh_form.addRow("Memory critical:", self._mem_crit)

        self._disk_warn = QSpinBox()
        self._disk_warn.setRange(1, 100000)
        self._disk_warn.setSuffix(" KB/s")
        self._disk_warn.setValue(int(cfg.disk_warn_threshold))
        thresh_form.addRow("Disk warning:", self._disk_warn)

        self._disk_crit = QSpinBox()
        self._disk_crit.setRange(1, 100000)
        self._disk_crit.setSuffix(" KB/s")
        self._disk_crit.setValue(int(cfg.disk_crit_threshold))
        thresh_form.addRow("Disk critical:", self._disk_crit)

        self._net_warn = QSpinBox()
        self._net_warn.setRange(1, 1000)
        self._net_warn.setSuffix(" conn")
        self._net_warn.setValue(int(cfg.net_warn_threshold))
        thresh_form.addRow("Network warning:", self._net_warn)

        self._net_crit = QSpinBox()
        self._net_crit.setRange(1, 1000)
        self._net_crit.setSuffix(" conn")
        self._net_crit.setValue(int(cfg.net_crit_threshold))
        thresh_form.addRow("Network critical:", self._net_crit)

        page.addLayout(thresh_form)

        hint = QLabel("Processes above the critical threshold appear red.\n"
                       "Processes above the warning threshold appear orange.")
        hint.setObjectName("update-status")
        hint.setWordWrap(True)
        page.addWidget(hint)

        page.addStretch()
        self._stack.addWidget(self._wrap_page(page))

    def _build_sensors_page(self, cfg) -> None:
        page = QVBoxLayout()
        page.setContentsMargins(24, 20, 24, 20)
        page.setSpacing(14)
        page.addWidget(self._section_label("LibreHardwareMonitor Sensors"))

        desc = QLabel("Enable or disable hardware types and sensor categories.\n"
                       "Disabling unused types reduces sensor collection overhead.")
        desc.setObjectName("update-status")
        desc.setWordWrap(True)
        page.addWidget(desc)

        hw_label = QLabel("Hardware Types")
        hw_label.setObjectName("settings-section")
        page.addWidget(hw_label)

        hw_grid = QGridLayout()
        hw_grid.setSpacing(6)
        self._hw_checks: dict[str, QCheckBox] = {}
        cols = 2
        for i, hw_type in enumerate(_ALL_HARDWARE_TYPES):
            cb = QCheckBox(hw_type)
            cb.setChecked(cfg.is_hardware_type_enabled(hw_type))
            self._hw_checks[hw_type] = cb
            hw_grid.addWidget(cb, i // cols, i % cols)
        page.addLayout(hw_grid)

        st_label = QLabel("Sensor Types")
        st_label.setObjectName("settings-section")
        page.addWidget(st_label)

        st_grid = QGridLayout()
        st_grid.setSpacing(6)
        self._st_checks: dict[str, QCheckBox] = {}
        for i, stype in enumerate(_ALL_SENSOR_TYPES):
            cb = QCheckBox(stype)
            cb.setChecked(cfg.is_sensor_type_enabled(stype))
            self._st_checks[stype] = cb
            st_grid.addWidget(cb, i // cols, i % cols)
        page.addLayout(st_grid)

        page.addStretch()
        self._stack.addWidget(self._wrap_page(page))

    def _build_speed_test_page(self, cfg) -> None:
        page = QVBoxLayout()
        page.setContentsMargins(24, 20, 24, 20)
        page.setSpacing(14)
        page.addWidget(self._section_label("Speed Test"))

        desc = QLabel("Configure the Cloudflare speed test parameters.\n"
                       "Larger sizes give more accurate results but take longer.")
        desc.setObjectName("update-status")
        desc.setWordWrap(True)
        page.addWidget(desc)

        form = QFormLayout()
        form.setSpacing(10)

        self._dl_spin = QSpinBox()
        self._dl_spin.setRange(1, 500)
        self._dl_spin.setSuffix(" MB")
        self._dl_spin.setValue(cfg.speed_test_download_mb)
        form.addRow("Download size:", self._dl_spin)

        self._ul_spin = QSpinBox()
        self._ul_spin.setRange(1, 500)
        self._ul_spin.setSuffix(" MB")
        self._ul_spin.setValue(cfg.speed_test_upload_mb)
        form.addRow("Upload size:", self._ul_spin)

        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(10, 600)
        self._timeout_spin.setSingleStep(10)
        self._timeout_spin.setSuffix(" s")
        self._timeout_spin.setValue(cfg.speed_test_timeout_s)
        form.addRow("Timeout:", self._timeout_spin)

        page.addLayout(form)

        warn = QLabel("Note: Cloudflare blocks exactly 100 MB downloads.\n"
                       "Keep download size below 100 MB to avoid HTTP 403 errors.")
        warn.setObjectName("update-status")
        warn.setWordWrap(True)
        page.addWidget(warn)

        page.addStretch()
        self._stack.addWidget(self._wrap_page(page))

    def _on_save(self) -> None:
        cfg = get_config()
        cfg.sensor_refresh_interval_ms = self._refresh_spin.value()
        cfg.process_refresh_interval_ms = self._proc_refresh_spin.value()
        cfg.process_top_n = self._proc_top_spin.value()
        cfg.sparkline_max_samples = self._sparkline_spin.value()
        cfg.cache_ttl_seconds = self._cache_spin.value()
        cfg.theme = self._theme_combo.currentText()
        cfg.font_family = self._font_combo.currentData()
        cfg.compact_view = self._compact_check.isChecked()
        cfg.show_progress_bars = self._progress_check.isChecked()
        cfg.enabled_hardware_types = {
            hw: cb.isChecked() for hw, cb in self._hw_checks.items()
        }
        cfg.enabled_sensor_types = [
            st for st, cb in self._st_checks.items() if cb.isChecked()
        ]
        cfg.speed_test_download_mb = self._dl_spin.value()
        cfg.speed_test_upload_mb = self._ul_spin.value()
        cfg.speed_test_timeout_s = self._timeout_spin.value()
        cfg.cpu_warn_threshold = float(self._cpu_warn.value())
        cfg.cpu_crit_threshold = float(self._cpu_crit.value())
        cfg.mem_warn_threshold = float(self._mem_warn.value())
        cfg.mem_crit_threshold = float(self._mem_crit.value())
        cfg.disk_warn_threshold = float(self._disk_warn.value())
        cfg.disk_crit_threshold = float(self._disk_crit.value())
        cfg.net_warn_threshold = int(self._net_warn.value())
        cfg.net_crit_threshold = int(self._net_crit.value())
        cfg.save()
        logger.info("Settings updated via dialog (theme=%s, compact=%s, "
                     "progress=%s, font=%s, sensor_refresh=%dms, "
                     "proc_refresh=%dms, proc_top=%d, sparkline=%d, "
                     "speed_test=%d/%dMB/%ds)",
                     cfg.theme, cfg.compact_view, cfg.show_progress_bars,
                     cfg.font_family or "default",
                     cfg.sensor_refresh_interval_ms,
                     cfg.process_refresh_interval_ms, cfg.process_top_n,
                     cfg.sparkline_max_samples,
                     cfg.speed_test_download_mb, cfg.speed_test_upload_mb,
                     cfg.speed_test_timeout_s)
        self.accept()


# ---------------------------------------------------------------------------
#  Main window
# ---------------------------------------------------------------------------

class InfoWindow(QMainWindow):
    PAGES = [
        ("OS", "Operating System"),
        ("Hardware", "Hardware"),
        ("Sensors", "Sensors"),
        ("Network", "Network Adapters"),
        ("External IP", "External IP"),
        ("Processes", "Running Processes"),
        ("Software", "Software & Startup"),
        ("Updates", "Windows Updates"),
        ("Health", "System Health"),
        ("Speed Test", "Network Speed Test"),
        ("Devices", "Connected Devices"),
        ("Diagnostics", "System Diagnostics"),
        ("Tools", "Windows Tools"),
    ]

    _SENSOR_TYPES = [
        "Temperature", "Fan", "Power", "Clock", "Voltage", "Load",
        "Level", "Data", "Factor", "Throughput", "SmallData", "Control",
    ]
    _STYPE_TO_KEY = {
        "Temperature": "temperatures", "Fan": "fans", "Power": "powers",
        "Clock": "clocks", "Voltage": "voltages", "Load": "loads",
        "Level": "levels", "Data": "data", "Factor": "factors",
        "Throughput": "throughputs", "SmallData": "smalldata",
        "Control": "controls",
    }

    def __init__(self, collector: Collector) -> None:
        super().__init__()
        self.setAutoFillBackground(True)
        self.collector = collector
        self.setWindowTitle("SysDigger  ·  Copyright (C) Stavros Antoniou")
        # App icon: shown in the title bar (top-left) and Windows taskbar.
        _icon_path = icon_path()
        if os.path.exists(_icon_path):
            self.setWindowIcon(QIcon(_icon_path))
        self.resize(1100, 780)
        self.setMinimumSize(860, 600)

        self._search_items: list[dict[str, str]] = []
        # Per-page search-item indices so a page can discard its stale
        # entries when re-rendered.  Without this, auto-refresh pages
        # (Network @ 5s, Processes @ 5s) leak ~30-50 items per rebuild,
        # growing ~36k items/hour and slowing search to a crawl.
        self._search_items_by_page: dict[int, list[int]] = {}
        self._current_page = 0
        self._pages_ready: set[int] = set()
        self._collecting = True
        self._closing = False
        self._sensor_value_labels: dict[tuple, list[QLabel]] = {}

        # Hardware page dynamic labels (updated by 2s sensor refresh)
        self._hw_cpu_usage_lbl: QLabel | None = None
        self._hw_cpu_usage_bar: QLabel | None = None
        self._hw_cpu_percore_lbl: QLabel | None = None
        self._hw_cpu_freq_lbl: QLabel | None = None
        self._hw_ram_used_lbl: QLabel | None = None
        self._hw_ram_avail_lbl: QLabel | None = None
        self._hw_ram_usage_lbl: QLabel | None = None
        self._hw_ram_usage_bar: QLabel | None = None
        self._hw_gpu_sensor_labels: list[tuple[str, str, str, QLabel]] = []
        self._sparklines: dict[str, _Sparkline] = {}
        self._sensor_minmax: dict[tuple, list[float]] = {}
        self._sensor_sparklines: dict[tuple, _Sparkline] = {}
        self._sensor_spark_data: dict[tuple, list[float]] = {}
        self._net_io_prev: tuple[int, int] | None = None
        self._net_io_time: float = 0.0
        self._net_spark_up: list[float] = []
        self._net_spark_down: list[float] = []
        self._disk_io_prev: tuple[int, int] | None = None
        self._disk_io_time: float = 0.0
        self._disk_spark_read: list[float] = []
        self._disk_spark_write: list[float] = []
        self._battery_spark: list[float] = []
        self._sensor_refreshing = False
        self._sensor_refresh_timer = None
        self._process_refresh_timer = None
        self._process_refreshing = False
        # Re-entry guard for Processes tab lazy-build: when the user
        # switches tabs we rebuild the page to construct the newly-visible
        # tab; this flag prevents infinite recursion during that rebuild.
        self._process_tab_rebuilding = False
        self._speed_testing = False
        self._bufferbloat_testing = False
        self._tool_running = False
        self._tool_proc: subprocess.Popen | None = None
        self._tool_log_path = os.path.join(
            tempfile.gettempdir(), "SA_WinTools_Active.log"
        )
        self._tools_built = False
        self._tool_cards: list[_ToolCard] = []
        self._tool_filter_cat = "all"
        self._path_select_pending: dict | None = None
        self._tool_running_mode: dict | None = None
        self._tool_running_name: str = ""
        self._tool_stopping = False
        self._tool_stopped = False
        self._pending_tool_reboot = False
        self._tool_start_time: float = 0.0

        self._build_ui()
        self._load_window_settings()
        self._show_loading_placeholders()
        # The Tools page has no collection dependency — build it immediately so
        # it is ready even before the background collection threads finish.
        self._populate_tools()
        set_dark_titlebar(self)

        self._refresh_btn.setEnabled(False)
        self._nav_buttons[0].setChecked(True)
        self._on_nav_clicked(0)

        # NOTE: _start_collection() is NOT called here.  It is called by
        # app.main() AFTER window.show() + processEvents(), so the first
        # paint (dark background + loading placeholders) is processed
        # before any collection-thread signals arrive in the event queue.
        # Qt processes paint events at low priority — if collection signals
        # are already queued when the event loop starts, they starve the
        # paint event, leaving the window white for seconds.

    # -- Native event handling --------------------------------------------- #
    def nativeEvent(self, eventType, message):
        """Intercept WM_ERASEBKGND to prevent the white flash.

        Windows sends WM_ERASEBKGND during show(), before Qt's event loop
        can process the first paint event.  The system fills the window
        with the default white background brush, causing a visible white
        flash.  Returning (True, 1) tells Windows the background is
        already erased, so Qt's QSS background-color paints dark during
        the first WM_PAINT without any preceding white erase.
        """
        if eventType == b"windows_generic_MSG":
            try:
                import ctypes.wintypes as wt
                msg = wt.MSG.from_address(int(message))
                if msg.message == 0x0014:  # WM_ERASEBKGND
                    return True, 1
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    # -- UI construction ---------------------------------------------------- #
    def _build_ui(self) -> None:
        central = QWidget()
        central.setAutoFillBackground(True)
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(12, 18, 0, 18)
        sb_layout.setSpacing(2)

        app_title = QLabel("SysDigger")
        app_title.setObjectName("app-title")
        sb_layout.addWidget(app_title)
        sb_layout.addSpacing(16)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_buttons: list[QPushButton] = []
        _nav_icon_dir = icons_dir()
        _nav_icon_dir = os.path.join(_nav_icon_dir, "nav")
        for i, (short, _) in enumerate(self.PAGES):
            btn = QPushButton(short)
            btn.setObjectName("nav-btn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # Load nav icon (icons/nav/<key>.png); key = short label lowercased
            _icon_key = short.lower().replace(" ", "_")
            _icon_path = os.path.join(_nav_icon_dir, f"{_icon_key}.png")
            if os.path.exists(_icon_path):
                btn.setIcon(QIcon(_icon_path))
                btn.setIconSize(QSize(18, 18))
            btn.clicked.connect(lambda _, idx=i: self._on_nav_clicked(idx))
            self._nav_group.addButton(btn, i)
            sb_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        sb_layout.addStretch()

        self._host_label = QLabel("")
        self._host_label.setObjectName("hostname")
        sb_layout.addWidget(self._host_label)
        sb_layout.addSpacing(12)

        self._updater = LibraryUpdater(lib_dir())
        self._updater.signals.status.connect(self._on_update_status)
        self._updater.signals.finished.connect(self._on_update_finished)

        installed_ver = self._updater.get_installed_version()
        self._update_btn = QPushButton("Update Libraries")
        self._update_btn.setObjectName("update-btn")
        self._update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_btn.clicked.connect(self._on_update_clicked)
        sb_layout.addWidget(self._update_btn)

        self._update_status = QLabel(f"Sensors: v{installed_ver}")
        self._update_status.setObjectName("update-status")
        self._update_status.setWordWrap(True)
        sb_layout.addWidget(self._update_status)

        self._copyright_label = QLabel("© 2026 Stavros Antoniou")
        self._copyright_label.setObjectName("copyright")
        self._copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb_layout.addWidget(self._copyright_label)

        root.addWidget(sidebar)

        content = QFrame()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(14)

        topbar = QHBoxLayout()
        topbar.setSpacing(16)
        self._page_title = QLabel("Operating System")
        self._page_title.setObjectName("page-title")
        topbar.addWidget(self._page_title)
        topbar.addStretch()

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("action-btn")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setToolTip("Reload all system data without restarting")
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        topbar.addWidget(self._refresh_btn)

        self._export_btn = QPushButton("Export")
        self._export_btn.setObjectName("action-btn")
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setToolTip("Export all system info to a file")
        self._export_btn.clicked.connect(self._on_export_clicked)
        topbar.addWidget(self._export_btn)

        self._log_btn = QPushButton("Log")
        self._log_btn.setObjectName("action-btn")
        self._log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._log_btn.setToolTip("Open the application log file")
        self._log_btn.clicked.connect(self._on_log_clicked)
        topbar.addWidget(self._log_btn)

        self._theme_btn = QPushButton("Theme")
        self._theme_btn.setObjectName("action-btn")
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.setToolTip("Toggle dark/light theme")
        self._theme_btn.clicked.connect(self._on_theme_toggle)
        topbar.addWidget(self._theme_btn)

        self._compact_btn = QPushButton("Compact")
        self._compact_btn.setObjectName("action-btn")
        self._compact_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._compact_btn.setCheckable(True)
        self._compact_btn.setChecked(get_config().compact_view)
        self._compact_btn.setToolTip("Toggle compact/expanded row layout")
        self._compact_btn.clicked.connect(self._on_compact_toggle)
        topbar.addWidget(self._compact_btn)

        self._settings_btn = QPushButton("Settings")
        self._settings_btn.setObjectName("action-btn")
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setToolTip("Edit application settings")
        self._settings_btn.clicked.connect(self._on_settings_clicked)
        topbar.addWidget(self._settings_btn)

        self._about_btn = QPushButton("About")
        self._about_btn.setObjectName("action-btn")
        self._about_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._about_btn.setToolTip("About SysDigger")
        self._about_btn.clicked.connect(self._on_about_clicked)
        topbar.addWidget(self._about_btn)

        self._search = QLineEdit()
        self._search.setObjectName("search")
        self._search.setPlaceholderText("Search all fields...")
        self._search.setFixedWidth(260)
        self._search.textChanged.connect(self._on_search_changed)
        topbar.addWidget(self._search)
        content_layout.addLayout(topbar)

        self._stack = QStackedWidget()
        content_layout.addWidget(self._stack)

        self._pages: list[QScrollArea] = []
        for _ in self.PAGES:
            page = self._make_scroll_page()
            self._pages.append(page)
            self._stack.addWidget(page)

        self._search_page = self._make_scroll_page()
        self._stack.addWidget(self._search_page)

        root.addWidget(content, 1)

        self._collect_signals = CollectSignals()
        self._collect_signals.step.connect(self._on_collect_step)
        self._collect_signals.page_ready.connect(self._on_page_ready)
        self._collect_signals.finished.connect(self._on_collect_finished)

        self._sensor_refresh_signals = SensorRefreshSignals()
        self._sensor_refresh_signals.refreshed.connect(self._update_sensor_values)

        self._process_refresh_signals = ProcessRefreshSignals()
        self._process_refresh_signals.refreshed.connect(self._on_process_refreshed)

        self._speed_test_signals = SpeedTestSignals()
        self._speed_test_signals.progress.connect(self._on_speed_test_progress)
        self._speed_test_signals.finished.connect(self._on_speed_test_finished)

        self._bufferbloat_signals = BufferbloatSignals()
        self._bufferbloat_signals.progress.connect(self._on_bufferbloat_progress)
        self._bufferbloat_signals.finished.connect(self._on_bufferbloat_finished)

        self._tool_signals = ToolSignals()
        self._tool_signals.output.connect(self._on_tool_output)
        self._tool_signals.status.connect(self._on_tool_status)
        self._tool_signals.finished.connect(self._on_tool_finished)

        self._status_label = QLabel("Initializing...")
        self._status_label.setMinimumWidth(360)
        self._status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        # Terminal-style progress bar (bash-like ASCII bar) in the status bar.
        # Uses block characters in a monospace font, color-coded by progress.
        # Per-thread progress tracking: each collection thread reports its own
        # (completed, total) sub-steps, and the bar shows the aggregate.
        self._thread_progress: dict[str, tuple[int, int]] = {}
        self._progress_bar = QLabel()
        self._progress_bar.setObjectName("term-bar-status")
        _pf = QFont("Consolas")
        _pf.setBold(True)
        _pf.setPointSize(10)
        self._progress_bar.setFont(_pf)
        self._refresh_dot = QLabel()
        self._refresh_dot.setObjectName("refresh-dot")
        self._refresh_dot.setFixedSize(8, 8)
        self._refresh_dot_timer = None
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        sb.addWidget(self._refresh_dot)
        sb.addWidget(self._status_label, 1)
        sb.addPermanentWidget(self._progress_bar)
        self._update_progress_bar()

    def _make_scroll_page(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(True)
        container = QWidget()
        container.setAutoFillBackground(True)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(10)
        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    # -- Card / row builders ----------------------------------------------- #
    def _make_card(self, parent_layout: QVBoxLayout, section: str,
                   rows: list[tuple[str, str]], page_idx: int,
                   value_labels: list | None = None,
                   bar_labels: list | None = None) -> None:
        cfg = get_config()
        compact = cfg.compact_view
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(
            18, 10 if compact else 14,
            18, 10 if compact else 14)
        card_layout.setSpacing(1 if compact else 3)

        title_row = QHBoxLayout()
        title = QLabel(section)
        title.setObjectName("card-title")
        title_row.addWidget(title)
        title_row.addStretch()

        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("copy-btn")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setToolTip("Copy all rows in this card")
        copy_btn.clicked.connect(
            lambda _, s=section, r=list(rows): self._copy_card_to_clipboard(s, r)
        )
        title_row.addWidget(copy_btn)
        card_layout.addLayout(title_row)

        for key, value in rows:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0 if compact else 1, 0, 0 if compact else 1)
            rl.setSpacing(8 if compact else 12)
            key_lbl = QLabel(key)
            key_lbl.setObjectName("row-key-compact" if compact else "row-key")
            key_lbl.setFixedWidth(KEY_WIDTH_COMPACT if compact else KEY_WIDTH)
            key_lbl.setWordWrap(not compact)

            # Check if this row should have a progress bar
            pct = self._extract_percentage(value) if cfg.show_progress_bars else None

            if pct is not None:
                # Row with terminal-style progress bar (bash-like ASCII bar)
                val_text = value
                val_lbl = QLabel(val_text)
                val_lbl.setObjectName("row-value-compact" if compact else "row-value")
                val_lbl.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse)
                # Build a bash-terminal-style ASCII progress bar
                bar_width = 25
                filled = int(round(pct / 100 * bar_width))
                empty = bar_width - filled
                bar_text = f"[{'█' * filled}{'░' * empty}]"
                bar_lbl = QLabel(bar_text)
                bar_lbl.setObjectName("term-bar")
                mono = QFont("Consolas")
                mono.setPointSize(10 if compact else 11)
                mono.setBold(True)
                bar_lbl.setFont(mono)
                if pct < 60:
                    bar_lbl.setStyleSheet(f"color: {_GREEN};")
                elif pct < 85:
                    bar_lbl.setStyleSheet(f"color: {_YELLOW};")
                else:
                    bar_lbl.setStyleSheet(f"color: {_RED};")
                rl.addWidget(key_lbl)
                rl.addWidget(val_lbl, 1)
                rl.addWidget(bar_lbl)

                val_lbl.setContextMenuPolicy(
                    Qt.ContextMenuPolicy.CustomContextMenu)
                val_lbl.customContextMenuRequested.connect(
                    lambda pos, vl=val_lbl, v=value, k=key,
                           s=section, r=list(rows):
                        self._show_row_copy_menu(vl, pos, v, k, s, r)
                )
                card_layout.addWidget(row)

                if value_labels is not None:
                    value_labels.append(val_lbl)
                if bar_labels is not None:
                    bar_labels.append(bar_lbl)
            else:
                # Normal row (no progress bar)
                val_lbl = QLabel(value)
                val_lbl.setObjectName("row-value-compact" if compact else "row-value"
                                      if not (key == "Error") else "error-text")
                val_lbl.setWordWrap(not compact)
                val_lbl.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                val_lbl.setContextMenuPolicy(
                    Qt.ContextMenuPolicy.CustomContextMenu
                )
                val_lbl.customContextMenuRequested.connect(
                    lambda pos, vl=val_lbl, v=value, k=key,
                           s=section, r=list(rows):
                        self._show_row_copy_menu(vl, pos, v, k, s, r)
                )
                rl.addWidget(key_lbl)
                rl.addWidget(val_lbl, 1)
                card_layout.addWidget(row)

                if value_labels is not None:
                    value_labels.append(val_lbl)
                if bar_labels is not None:
                    bar_labels.append(None)

            if page_idx >= 0:
                idx = len(self._search_items)
                self._search_items.append({
                    "page": str(page_idx),
                    "section": section,
                    "key": key,
                    "value": value,
                })
                self._search_items_by_page.setdefault(
                    page_idx, []
                ).append(idx)

        # Insert before the last stretch in the layout (if any), so cards
        # appear above a trailing stretch on pages that add one.  If there
        # is no stretch (e.g. Speed Test page with interleaved buttons, or
        # the Network Adapters tab), simply append — this avoids reversing
        # card order or inserting cards between a button and its label.
        inserted = False
        for i in range(parent_layout.count() - 1, -1, -1):
            item = parent_layout.itemAt(i)
            if item is not None and item.spacerItem() is not None:
                parent_layout.insertWidget(i, card)
                inserted = True
                break
        if not inserted:
            parent_layout.addWidget(card)

    @staticmethod
    def _extract_percentage(value: str) -> float | None:
        """Extract a percentage value from a string like '45.2%' or '45.2% (something)'.

        Returns None if the value doesn't contain a percentage.
        """
        if not isinstance(value, str) or "%" not in value:
            return None
        # Match the first percentage pattern (not preceded by minus)
        m = re.search(r'(?<![-\d])([\d.]+)%', value)
        if m:
            try:
                pct = float(m.group(1))
                if 0 <= pct <= 100:
                    return pct
            except ValueError:
                pass
        return None

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # -- Copy to clipboard -------------------------------------------------- #
    def _copy_card_to_clipboard(self, section: str,
                                rows: list[tuple[str, str]]) -> None:
        lines = [f"[{section}]"]
        for k, v in rows:
            lines.append(f"  {k}: {v}")
        QApplication.clipboard().setText("\n".join(lines))

    def _show_row_copy_menu(self, label: QLabel, pos, value: str, key: str,
                            section: str,
                            rows: list[tuple[str, str]]) -> None:
        menu = QMenu(label)
        act_val = menu.addAction("Copy Value")
        act_row = menu.addAction("Copy Row")
        act_all = menu.addAction(f"Copy All ({section})")
        chosen = menu.exec(label.mapToGlobal(pos))
        if chosen == act_val:
            QApplication.clipboard().setText(label.text())
        elif chosen == act_row:
            QApplication.clipboard().setText(f"{key}: {label.text()}")
        elif chosen == act_all:
            self._copy_card_to_clipboard(section, rows)

    # -- Table copy to clipboard ------------------------------------------- #
    @staticmethod
    def _setup_table_copy(table: QTableWidget) -> None:
        """Wire Ctrl+C and right-click Copy menu on a QTableWidget."""
        sc = QShortcut(QKeySequence.StandardKey.Copy, table)
        sc.activated.connect(lambda: InfoWindow._copy_table_selection(table))
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda pos: InfoWindow._show_table_copy_menu(table, pos)
        )

    @staticmethod
    def _copy_table_selection(table: QTableWidget) -> None:
        rows = sorted({idx.row() for idx in table.selectedIndexes()})
        if not rows:
            return
        lines = InfoWindow._extract_table_rows(table, rows)
        QApplication.clipboard().setText("\n".join(lines))

    @staticmethod
    def _extract_table_rows(table: QTableWidget, rows: list[int]) -> list[str]:
        cols = table.columnCount()
        headers = [table.horizontalHeaderItem(c).text()
                   if table.horizontalHeaderItem(c) else str(c)
                   for c in range(cols)]
        lines = ["\t".join(headers)]
        for r in rows:
            parts = []
            for c in range(cols):
                item = table.item(r, c)
                parts.append(item.text() if item else "")
            lines.append("\t".join(parts))
        return lines

    @staticmethod
    def _show_table_copy_menu(table: QTableWidget, pos) -> None:
        idx = table.indexAt(pos)
        if not idx.isValid():
            return
        if idx.row() not in {i.row() for i in table.selectedIndexes()}:
            table.selectRow(idx.row())
        menu = QMenu(table)
        n_sel = len({i.row() for i in table.selectedIndexes()})
        act_rows = menu.addAction(
            f"Copy {'row' if n_sel == 1 else f'{n_sel} rows'}")
        act_all = menu.addAction("Copy all rows")
        chosen = menu.exec(table.viewport().mapToGlobal(pos))
        if chosen == act_rows:
            InfoWindow._copy_table_selection(table)
        elif chosen == act_all:
            lines = InfoWindow._extract_table_rows(
                table, list(range(table.rowCount())))
            QApplication.clipboard().setText("\n".join(lines))

    # -- Loading placeholders + background collection ----------------------- #
    def _show_loading_placeholders(self) -> None:
        for i, page in enumerate(self._pages):
            # The Tools page is static (no collection dependency) and is
            # populated directly by _populate_tools(); never show a loading
            # placeholder there, since it would wipe the live log panel.
            if i < len(self.PAGES) and self.PAGES[i][0] == "Tools":
                continue
            layout: QVBoxLayout = page.widget().layout()
            self._clear_layout(layout)
            hint = QLabel("Collecting system information\u2026")
            hint.setObjectName("loading-hint")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.insertWidget(0, hint)
            layout.addStretch()

    def _start_collection(self) -> None:
        threading.Thread(target=self._collect_worker, daemon=True).start()

    # -- Manual refresh ----------------------------------------------------- #
    def _on_refresh_clicked(self) -> None:
        if self._collecting:
            return
        self._collecting = True
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("Refreshing...")
        self._thread_progress.clear()
        self._update_progress_bar()
        self._search.clear()
        self._search_items.clear()
        self._search_items_by_page.clear()
        self._pages_ready.clear()
        self._sensor_value_labels.clear()
        self._sensor_minmax.clear()
        self._sensor_sparklines.clear()
        self._sensor_spark_data.clear()
        self._net_io_prev = None
        self._net_io_time = 0.0
        self._net_spark_up.clear()
        self._net_spark_down.clear()
        self._disk_io_prev = None
        self._disk_io_time = 0.0
        self._disk_spark_read.clear()
        self._disk_spark_write.clear()
        self._battery_spark.clear()
        self._hw_cpu_usage_lbl = None
        self._hw_cpu_usage_bar = None
        self._hw_cpu_percore_lbl = None
        self._hw_cpu_freq_lbl = None
        self._hw_ram_used_lbl = None
        self._hw_ram_avail_lbl = None
        self._hw_ram_usage_lbl = None
        self._hw_ram_usage_bar = None
        self._sparklines.clear()
        if self._sensor_refresh_timer is not None:
            self._sensor_refresh_timer.stop()
            self._sensor_refresh_timer = None
        if self._process_refresh_timer is not None:
            self._process_refresh_timer.stop()
            self._process_refresh_timer = None
        self._show_loading_placeholders()
        self.collector.clear_cache()
        self._start_collection()

    def _collect_worker(self) -> None:
        collector = self.collector
        collector._init_wmi()

        # Prime psutil cpu_percent early — the first call per process
        # returns 0.0 and needs a delay before the second call gives a
        # real value. By priming here, collect_processes can skip the
        # 0.5s sleep (enough time passes during thread collection).
        try:
            import psutil
            for p in psutil.process_iter(["pid"]):
                try:
                    p.cpu_percent()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            collector._process_cpu_primed = True
        except Exception:
            pass

        threads: list[threading.Thread] = []
        errors: dict[str, Exception] = {}

        def _run(name: str, fn):
            try:
                fn()
            except Exception as e:
                errors[name] = e
                logger.error("Collection thread '%s' failed: %s", name, e,
                            exc_info=True)

        def _thread_a():
            collector._init_wmi()
            self._collect_signals.step.emit("Collecting OS + hardware\u2026", "os_hw", 1, 3)
            collector.collect_os()
            self._collect_signals.page_ready.emit(0)
            self._collect_signals.step.emit("Collecting hardware + sensors\u2026", "os_hw", 2, 3)
            collector.collect_hardware()
            # GPU details must run after hardware so the WMI fallback
            # can read hw_info["gpus"] when NVML is unavailable (AMD/Intel)
            collector.collect_gpu_details()
            self._collect_signals.step.emit("Hardware ready", "os_hw", 3, 3)
            self._collect_signals.page_ready.emit(1)
            self._collect_signals.page_ready.emit(2)

        def _thread_b():
            collector._init_wmi()
            self._collect_signals.step.emit("Collecting network\u2026", "net_sw", 1, 6)
            collector.collect_network()
            collector.collect_wifi_info()
            collector.collect_dns_cache()
            self._collect_signals.page_ready.emit(3)
            # Fire-and-forget: ext_ip is a slow network call (0.9s).
            # Emit page_ready(4) now so the IP page renders with a
            # placeholder, then update it when the result arrives.
            self._collect_signals.page_ready.emit(4)
            collector.collect_ext_ip()
            self._collect_signals.step.emit("Collecting software & updates\u2026", "net_sw", 2, 6)
            collector.collect_software()
            collector.collect_services()
            collector.collect_startup_impact()
            self._collect_signals.page_ready.emit(6)
            self._collect_signals.step.emit("Collecting Windows updates\u2026", "net_sw", 3, 6)
            collector.collect_updates()
            self._collect_signals.step.emit("Network & software ready", "net_sw", 4, 6)
            self._collect_signals.page_ready.emit(7)
            # Re-emit page 4 now that ext_ip has arrived
            self._collect_signals.page_ready.emit(4)
            self._collect_signals.step.emit("Network ready", "net_sw", 5, 6)
            self._collect_signals.step.emit("Software ready", "net_sw", 6, 6)

        def _thread_c():
            collector._init_wmi()
            self._collect_signals.step.emit("Collecting system health\u2026", "health_dev", 1, 4)
            collector.collect_health()
            self._collect_signals.page_ready.emit(8)
            # VPN status (cached, fast on warm start)
            collector.collect_vpn_status()
            self._collect_signals.step.emit("Collecting devices\u2026", "health_dev", 2, 4)
            # Devices (cached, fast on warm start)
            collector.collect_devices()
            collector.collect_drivers()
            self._collect_signals.step.emit("Collecting diagnostics\u2026", "health_dev", 3, 4)
            self._collect_signals.page_ready.emit(10)
            # Diagnostics (cached, fast on warm start)
            collector.collect_diagnostics()
            self._collect_signals.step.emit("Diagnostics ready", "health_dev", 4, 4)
            self._collect_signals.page_ready.emit(11)

        def _thread_d():
            # Processes don't depend on any other collector — runs in
            # parallel with A/B/C instead of waiting for them to finish.
            # cpu_percent was already primed above.
            self._collect_signals.step.emit("Collecting processes\u2026", "proc", 1, 1)
            try:
                collector.collect_processes()
            except Exception as e:
                logger.error("Process collection failed: %s", e, exc_info=True)
            self._collect_signals.page_ready.emit(5)
            self._collect_signals.page_ready.emit(9)
            self._collect_signals.step.emit("Processes ready", "proc", 1, 1)

        for name, fn in [("os_hw", _thread_a), ("net_sw", _thread_b),
                         ("health_dev", _thread_c), ("proc", _thread_d)]:
            t = threading.Thread(target=_run, args=(name, fn), daemon=True)
            threads.append(t)
            t.start()

        threads[0].join()

        self._collect_signals.step.emit("Refreshing live data\u2026", "post", 1, 2)
        try:
            collector.refresh_dynamic()
        except Exception as e:
            logger.error("Dynamic refresh failed: %s", e, exc_info=True)
        self._collect_signals.page_ready.emit(0)
        self._collect_signals.page_ready.emit(1)

        for t in threads[1:]:
            t.join()

        # Collect active connections (live, re-collected on each refresh)
        self._collect_signals.step.emit("Collecting connections\u2026", "post", 2, 2)
        try:
            collector.collect_active_connections()
        except Exception as e:
            logger.error("Active connections failed: %s", e, exc_info=True)
        self._collect_signals.page_ready.emit(3)

        self._collect_signals.finished.emit()

    def _on_collect_step(self, label: str, thread_key: str,
                        completed: int, total: int) -> None:
        self._status_label.setText(label)
        self._thread_progress[thread_key] = (completed, total)
        self._update_progress_bar()

    def _update_progress_bar(self) -> None:
        """Render the terminal-style progress bar in the status bar."""
        bar_width = 20
        done = sum(c for c, _ in self._thread_progress.values())
        total = sum(t for _, t in self._thread_progress.values())
        pct = (done / total * 100) if total > 0 else 0
        pct = max(0, min(100, pct))
        filled = int(round(pct / 100 * bar_width))
        empty = bar_width - filled
        bar_text = f"[{'█' * filled}{'░' * empty}] {int(pct):3d}%"
        self._progress_bar.setText(bar_text)
        if pct >= 100:
            color = _GREEN
        elif pct < 60:
            color = _GREEN
        elif pct < 85:
            color = _YELLOW
        else:
            color = _RED
        self._progress_bar.setStyleSheet(f"color: {color};")

    def _on_page_ready(self, page_idx: int) -> None:
        """Render a page when its data becomes available.

        Uses lazy rendering: only the page the user is currently viewing
        is rendered immediately.  Other pages are marked as "ready" and
        rendered on-demand when the user navigates to them.  This saves
        significant UI time during startup (rendering 13 pages takes
        ~500ms+ that the user never sees if they stay on page 0).
        """
        self._pages_ready.add(page_idx)
        # Tools page (12) is static — always render on first ready signal.
        if page_idx != self._current_page and page_idx != 12:
            return
        self._render_page(page_idx)

    def _discard_search_items_for_page(self, page_idx: int) -> None:
        """Remove all search items previously registered for *page_idx*.

        Search items are appended by ``_make_card`` on every render.  If a
        page re-renders (auto-refresh, manual refresh, settings/theme
        change) without first discarding the old entries, the list grows
        unbounded — ~30-50 items per Network/Processes rebuild, every 5s.
        """
        old_indices = self._search_items_by_page.pop(page_idx, None)
        if not old_indices:
            return
        # Build a set for O(1) membership test, then rebuild the list
        # without the stale entries.  Indices are unique per page and are
        # never reused between renders (a fresh list is appended each time).
        drop = set(old_indices)
        self._search_items = [
            item for i, item in enumerate(self._search_items)
            if i not in drop
        ]
        # The indices in _search_items_by_page for OTHER pages are now
        # invalidated by the compaction above; rebuild them by scanning the
        # remaining items.  This is O(N) but only runs on re-render, not
        # on every keystroke.
        new_by_page: dict[int, list[int]] = {}
        for i, item in enumerate(self._search_items):
            try:
                p = int(item.get("page", -1))
            except (TypeError, ValueError):
                continue
            new_by_page.setdefault(p, []).append(i)
        self._search_items_by_page = new_by_page

    def _render_page(self, page_idx: int) -> None:
        """Actually render a page's content (called by _on_page_ready
        and _on_nav_clicked)."""
        # Drop any search items previously registered for this page so the
        # populate call starts from a clean slate.  This prevents unbounded
        # growth on auto-refresh pages (Network/Processes rebuild every 5s).
        self._discard_search_items_for_page(page_idx)
        try:
            if page_idx == 0:
                self._populate_os()
                hostname = self.collector.data.os_info.get("Computer Name", "")
                if hostname:
                    self._host_label.setText(hostname)
            elif page_idx == 1:
                self._populate_hardware()
            elif page_idx == 2:
                self._populate_sensors()
            elif page_idx == 3:
                self._populate_network()
            elif page_idx == 4:
                self._populate_ip()
            elif page_idx == 5:
                self._populate_processes()
            elif page_idx == 6:
                self._populate_software()
            elif page_idx == 7:
                self._populate_updates()
            elif page_idx == 8:
                self._populate_health()
            elif page_idx == 9:
                self._populate_speed_test()
            elif page_idx == 10:
                self._populate_devices()
            elif page_idx == 11:
                self._populate_diagnostics()
            elif page_idx == 12:
                # Tools page is static; built once at startup. Re-render on
                # settings change is a no-op (theme/compact apply via QSS).
                if not self._tools_built:
                    self._populate_tools()
        except Exception as e:
            logger.error("Page %d render failed: %s", page_idx, e,
                        exc_info=True)
            self._render_page_error(page_idx, e)

    def _on_collect_finished(self) -> None:
        self._collecting = False
        # Mark all threads as fully complete
        for key in ("os_hw", "net_sw", "health_dev", "proc", "post"):
            self._thread_progress[key] = (1, 1)
        self._update_progress_bar()
        self._status_label.setText("Ready")
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("Refresh")
        self._start_sensor_refresh()
        self._start_process_refresh()

    def _render_page_error(self, page_idx: int, exc: Exception) -> None:
        """Render an error card on a page that failed to populate."""
        try:
            layout: QVBoxLayout = self._pages[page_idx].widget().layout()
            self._clear_layout(layout)
            page_name = self.PAGES[page_idx][1] if page_idx < len(self.PAGES) else f"Page {page_idx}"
            self._make_card(layout, page_name, [
                ("Status", "Failed to load"),
                ("Error", f"{type(exc).__name__}: {exc}"),
                ("Hint", "See app.log for details. Click Log button to open."),
            ], -1)
            layout.addStretch()
        except Exception:
            pass  # avoid recursion if even error rendering fails

    # -- Live sensor refresh ------------------------------------------------ #

    @property
    def _sensor_refresh_interval(self) -> int:
        return get_config().sensor_refresh_interval_ms

    def _start_sensor_refresh(self) -> None:
        if self._sensor_refresh_timer is not None:
            return
        from PySide6.QtCore import QTimer
        timer = QTimer(self)
        timer.timeout.connect(self._on_sensor_refresh_tick)
        timer.start(self._sensor_refresh_interval)
        self._sensor_refresh_timer = timer

    def _restart_sensor_refresh(self) -> None:
        """Restart the sensor timer with the current config interval."""
        if self._sensor_refresh_timer is not None:
            self._sensor_refresh_timer.stop()
            self._sensor_refresh_timer = None
        if not self._collecting:
            self._start_sensor_refresh()

    def _on_sensor_refresh_tick(self) -> None:
        if self._closing:
            return
        if self._sensor_refreshing:
            return
        self._sensor_refreshing = True
        self._pulse_refresh_dot()
        threading.Thread(target=self._sensor_refresh_worker, daemon=True).start()

    def _pulse_refresh_dot(self) -> None:
        self._refresh_dot.setObjectName("refresh-dot-active")
        self._refresh_dot.style().unpolish(self._refresh_dot)
        self._refresh_dot.style().polish(self._refresh_dot)
        if self._refresh_dot_timer is not None:
            self._refresh_dot_timer.stop()
        else:
            from PySide6.QtCore import QTimer
            self._refresh_dot_timer = QTimer(self)
            self._refresh_dot_timer.setSingleShot(True)
            self._refresh_dot_timer.timeout.connect(self._dim_refresh_dot)
        self._refresh_dot_timer.start(600)

    def _dim_refresh_dot(self) -> None:
        self._refresh_dot.setObjectName("refresh-dot")
        self._refresh_dot.style().unpolish(self._refresh_dot)
        self._refresh_dot.style().polish(self._refresh_dot)

    def _sensor_refresh_worker(self) -> None:
        try:
            self.collector.refresh_sensors()
        except Exception as e:
            logger.error("Sensor refresh worker failed: %s", e, exc_info=True)
        self._sensor_refresh_signals.refreshed.emit()

    def _update_sensor_values(self) -> None:
        self._sensor_refreshing = False
        if self._closing:
            return
        sensors = self.collector.data.hw_info.get("sensors", {})
        if not sensors.get("available"):
            return
        lookup: dict[tuple, str] = {}
        color_lookup: dict[tuple, str] = {}
        raw_lookup: dict[tuple, float] = {}
        for stype in self._SENSOR_TYPES:
            key = self._STYPE_TO_KEY[stype]
            for entry in sensors.get(key, []):
                source = entry.get("Source", entry.get("Category", "Other"))
                etype = entry.get("Type", "")
                name = entry.get("Name", "")
                val = entry.get("Value", 0.0)
                k = (source, etype, name)
                lookup[k] = fmt_sensor_value(etype, val)
                color_lookup[k] = self._sensor_color(etype, val)
                raw_lookup[k] = val
        for key, labels in self._sensor_value_labels.items():
            val_str = lookup.get(key)
            if val_str is None:
                continue
            color = color_lookup.get(key, _TEXT_PRIMARY)
            raw_val = raw_lookup.get(key, 0.0)
            if key in self._sensor_minmax:
                mm = self._sensor_minmax[key]
                if raw_val < mm[0]:
                    mm[0] = raw_val
                if raw_val > mm[1]:
                    mm[1] = raw_val
            else:
                self._sensor_minmax[key] = [raw_val, raw_val]
            etype = key[1]
            mm = self._sensor_minmax[key]
            tooltip = (f"Min: {fmt_sensor_value(etype, mm[0])}  |  "
                       f"Max: {fmt_sensor_value(etype, mm[1])}")
            for lbl in labels:
                if lbl.text() != val_str:
                    lbl.setText(val_str)
                if color != _TEXT_PRIMARY:
                    lbl.setStyleSheet(f"color: {color};")
                else:
                    lbl.setStyleSheet("")
                lbl.setToolTip(tooltip)

        # -- Update Hardware page CPU/RAM labels from live sensor data -- #
        self._update_hardware_labels(sensors)

    def _update_hardware_labels(self, sensors: dict) -> None:
        """Refresh the Hardware > CPU and Memory tab labels (and progress
        bars) from the freshly-collected sensor data.

        ``refresh_sensors()`` already updated ``hw_info['cpu']`` and
        ``hw_info['ram']`` — here we push those values into the live
        QLabel widgets so the Hardware page stays in sync with the 2s
        sensor refresh without a full page rebuild.
        """
        cpu = self.collector.data.hw_info.get("cpu", {})
        usage_str = cpu.get("Usage", "")
        percore_str = cpu.get("Per-core Usage", "")

        if self._hw_cpu_usage_lbl is not None and usage_str:
            self._hw_cpu_usage_lbl.setText(usage_str)
            # Update progress bar
            if self._hw_cpu_usage_bar is not None:
                pct = self._extract_percentage(usage_str)
                if pct is not None:
                    bar_width = 25
                    filled = int(round(pct / 100 * bar_width))
                    empty = bar_width - filled
                    self._hw_cpu_usage_bar.setText(
                        f"[{'█' * filled}{'░' * empty}]")
                    if pct < 60:
                        color = _GREEN
                    elif pct < 85:
                        color = _YELLOW
                    else:
                        color = _RED
                    self._hw_cpu_usage_bar.setStyleSheet(f"color: {color};")

        if self._hw_cpu_percore_lbl is not None and percore_str:
            self._hw_cpu_percore_lbl.setText(percore_str)

        freq_str = cpu.get("Current Freq", "")
        if self._hw_cpu_freq_lbl is not None and freq_str:
            self._hw_cpu_freq_lbl.setText(freq_str)

        # -- RAM -- #
        ram = self.collector.data.hw_info.get("ram", {})
        if self._hw_ram_used_lbl is not None:
            self._hw_ram_used_lbl.setText(str(ram.get("Used", "N/A")))
        if self._hw_ram_avail_lbl is not None:
            self._hw_ram_avail_lbl.setText(str(ram.get("Available", "N/A")))
        ram_usage_str = ram.get("Usage %", "")
        if self._hw_ram_usage_lbl is not None and ram_usage_str:
            self._hw_ram_usage_lbl.setText(ram_usage_str)
            if self._hw_ram_usage_bar is not None:
                pct = self._extract_percentage(ram_usage_str)
                if pct is not None:
                    bar_width = 25
                    filled = int(round(pct / 100 * bar_width))
                    empty = bar_width - filled
                    self._hw_ram_usage_bar.setText(
                        f"[{'█' * filled}{'░' * empty}]")
                    if pct < 60:
                        color = _GREEN
                    elif pct < 85:
                        color = _YELLOW
                    else:
                        color = _RED
                    self._hw_ram_usage_bar.setStyleSheet(f"color: {color};")

        # -- Sparkline graphs -- #
        sp = self._sparklines
        if "cpu_usage" in sp:
            pct = self._extract_percentage(usage_str)
            if pct is not None:
                sp["cpu_usage"].add_sample(pct)
        if "ram_usage" in sp:
            pct = self._extract_percentage(ram_usage_str)
            if pct is not None:
                sp["ram_usage"].add_sample(pct)

        # CPU + GPU temperature from LHM sensors
        cpu_temp_val: float | None = None
        gpu_temp_val: float | None = None
        gpu_util_val: float | None = None
        for entry in sensors.get("temperatures", []):
            cat = entry.get("Category", "")
            if cpu_temp_val is None and cat == "CPU" and (
                    entry.get("Name", "") == "CPU Package"
                    or cpu_temp_val is None):
                cpu_temp_val = entry.get("Value", 0.0)
            if cat == "GPU" and gpu_temp_val is None:
                gpu_temp_val = entry.get("Value", 0.0)
        for entry in sensors.get("loads", []):
            if (gpu_util_val is None
                    and entry.get("Category", "") == "GPU"
                    and entry.get("Name", "") == "GPU Core"):
                gpu_util_val = entry.get("Value", 0.0)
                break
        if "cpu_temp" in sp and cpu_temp_val is not None:
            sp["cpu_temp"].add_sample(cpu_temp_val)
        if "gpu_temp" in sp and gpu_temp_val is not None:
            sp["gpu_temp"].add_sample(gpu_temp_val)
        if "gpu_temp_2" in sp and gpu_temp_val is not None:
            sp["gpu_temp_2"].add_sample(gpu_temp_val)
        if "gpu_util" in sp and gpu_util_val is not None:
            sp["gpu_util"].add_sample(gpu_util_val)

        # GPU Live Metrics card — update labels from fresh sensor data
        # (works with any GPU vendor via LHM sensors)
        if self._hw_gpu_sensor_labels:
            gpu_lookup: dict[tuple, str] = {}
            gpu_color_lookup: dict[tuple, str] = {}
            for stype in self._SENSOR_TYPES:
                skey = self._STYPE_TO_KEY[stype]
                for entry in sensors.get(skey, []):
                    if entry.get("Category") != "GPU":
                        continue
                    src = entry.get("Source", "GPU")
                    etype = entry.get("Type", "")
                    name = entry.get("Name", "")
                    val = entry.get("Value", 0.0)
                    k = (src, etype, name)
                    gpu_lookup[k] = fmt_sensor_value(etype, val)
                    gpu_color_lookup[k] = self._sensor_color(etype, val)
            for src, stype, name, lbl in self._hw_gpu_sensor_labels:
                k = (src, stype, name)
                val_str = gpu_lookup.get(k)
                if val_str is None:
                    continue
                if lbl.text() != val_str:
                    lbl.setText(val_str)
                color = gpu_color_lookup.get(k, _TEXT_PRIMARY)
                if color != _TEXT_PRIMARY:
                    lbl.setStyleSheet(f"color: {color};")
                else:
                    lbl.setStyleSheet("")

        # Disk I/O throughput (MB/s) from psutil delta
        try:
            import time as _time_mod
            import psutil as _psutil_mod
            dio = _psutil_mod.disk_io_counters()
            now = _time_mod.time()
            if dio is not None:
                cur = (dio.read_bytes, dio.write_bytes)
                if self._disk_io_prev is not None and self._disk_io_time > 0:
                    dt = now - self._disk_io_time
                    if dt > 0:
                        read_mbps = ((cur[0] - self._disk_io_prev[0]) / dt
                                     / (1024 * 1024))
                        write_mbps = ((cur[1] - self._disk_io_prev[1]) / dt
                                      / (1024 * 1024))
                        self._disk_spark_read.append(read_mbps)
                        self._disk_spark_write.append(write_mbps)
                        max_sp = get_config().sparkline_max_samples
                        if len(self._disk_spark_read) > max_sp:
                            self._disk_spark_read.pop(0)
                        if len(self._disk_spark_write) > max_sp:
                            self._disk_spark_write.pop(0)
                        if "disk_read" in sp:
                            sp["disk_read"].add_sample(read_mbps)
                        if "disk_write" in sp:
                            sp["disk_write"].add_sample(write_mbps)
                self._disk_io_prev = cur
                self._disk_io_time = now
        except Exception:
            pass

        # Network throughput (KB/s) from psutil delta
        try:
            import time as _time_mod2
            import psutil as _psutil_mod2
            nio = _psutil_mod2.net_io_counters()
            now = _time_mod2.time()
            cur = (nio.bytes_sent, nio.bytes_recv)
            if self._net_io_prev is not None and self._net_io_time > 0:
                dt = now - self._net_io_time
                if dt > 0:
                    up_kbps = (cur[0] - self._net_io_prev[0]) / dt / 1024
                    down_kbps = (cur[1] - self._net_io_prev[1]) / dt / 1024
                    self._net_spark_up.append(up_kbps)
                    self._net_spark_down.append(down_kbps)
                    max_sp = get_config().sparkline_max_samples
                    if len(self._net_spark_up) > max_sp:
                        self._net_spark_up.pop(0)
                    if len(self._net_spark_down) > max_sp:
                        self._net_spark_down.pop(0)
                    if "net_up" in sp:
                        sp["net_up"].add_sample(up_kbps)
                    if "net_down" in sp:
                        sp["net_down"].add_sample(down_kbps)
            self._net_io_prev = cur
            self._net_io_time = now
        except Exception:
            pass

        # Battery percentage
        try:
            import psutil as _psutil_bat
            if hasattr(_psutil_bat, "sensors_battery"):
                b = _psutil_bat.sensors_battery()
                if b is not None:
                    self._battery_spark.append(b.percent)
                    max_sp = get_config().sparkline_max_samples
                    if len(self._battery_spark) > max_sp:
                        self._battery_spark.pop(0)
                    if "battery_pct" in sp:
                        sp["battery_pct"].add_sample(b.percent)
        except Exception:
            pass

        # Sensor sparklines on Sensors page (data + widgets) — all
        # chartable sensor types (Temperature, Clock, Power, Load, Fan,
        # Voltage), not just Temperature.
        max_sp = get_config().sparkline_max_samples
        for stype in self._SENSOR_TYPES:
            if stype not in _SENSOR_SPARK_COLORS:
                continue
            skey_pl = self._STYPE_TO_KEY[stype]
            for entry in sensors.get(skey_pl, []):
                src = entry.get("Source", entry.get("Category", "Other"))
                name = entry.get("Name", "")
                val = entry.get("Value", 0.0)
                skey = (src, stype, name)
                if skey not in self._sensor_spark_data:
                    self._sensor_spark_data[skey] = []
                self._sensor_spark_data[skey].append(val)
                if len(self._sensor_spark_data[skey]) > max_sp:
                    self._sensor_spark_data[skey].pop(0)
                ssp = self._sensor_sparklines.get(skey)
                if ssp is not None:
                    ssp.add_sample(val)

    # -- Page population ---------------------------------------------------- #
    @staticmethod
    def _sensor_color(stype: str, val: float) -> str:
        if stype == "Temperature":
            if val < 50:
                return _GREEN
            if val < 70:
                return _YELLOW
            return _RED
        if stype in ("Load", "Level", "Control"):
            if val < 60:
                return _GREEN
            if val < 85:
                return _YELLOW
            return _RED
        return _TEXT_PRIMARY

    # -- Process refresh ---------------------------------------------------- #

    def _process_refresh_interval(self) -> int:
        return get_config().process_refresh_interval_ms

    def _start_process_refresh(self) -> None:
        if self._process_refresh_timer is not None:
            return
        from PySide6.QtCore import QTimer
        timer = QTimer(self)
        timer.timeout.connect(self._on_process_refresh_tick)
        timer.start(self._process_refresh_interval())
        self._process_refresh_timer = timer

    def _restart_process_refresh(self) -> None:
        """Restart the process timer with the current config interval."""
        if self._process_refresh_timer is not None:
            self._process_refresh_timer.stop()
            self._process_refresh_timer = None
        if not self._collecting:
            self._start_process_refresh()

    def _on_process_refresh_tick(self) -> None:
        if self._process_refreshing:
            return
        self._process_refreshing = True
        threading.Thread(target=self._process_refresh_worker,
                         daemon=True).start()

    def _process_refresh_worker(self) -> None:
        try:
            self.collector.collect_processes()
        except Exception as e:
            logger.error("Process refresh worker failed: %s", e,
                        exc_info=True)
        try:
            self.collector.collect_active_connections()
        except Exception as e:
            logger.error("Active connections refresh failed: %s", e,
                        exc_info=True)
        self._process_refresh_signals.refreshed.emit()

    def _on_process_refreshed(self) -> None:
        self._process_refreshing = False
        if self._current_page == 5:
            # Discard stale search items before re-populating; otherwise
            # the 5s auto-refresh leaks ~200 entries per cycle.
            self._discard_search_items_for_page(5)
            self._populate_processes()
        if self._current_page == 3:
            self._discard_search_items_for_page(3)
            self._populate_network()

    # -- Speed test --------------------------------------------------------- #
    def _on_speed_test_clicked(self) -> None:
        if self._speed_testing:
            return
        self._speed_testing = True
        self._speed_test_btn.setEnabled(False)
        self._speed_test_btn.setText("Testing...")
        self._speed_test_status.setText("Running speed test...")
        threading.Thread(target=self._speed_test_worker, daemon=True).start()

    def _speed_test_worker(self) -> None:
        self._speed_test_signals.progress.emit("Downloading test data...")
        try:
            result = self.collector.run_speed_test()
        except Exception as e:
            result = {"error": str(e), "download_mbps": 0, "upload_mbps": 0}
            logger.error("Speed test worker failed: %s", e, exc_info=True)
        self._speed_test_signals.finished.emit(result)

    def _on_speed_test_progress(self, msg: str) -> None:
        self._speed_test_status.setText(msg)

    def _on_speed_test_finished(self, result: dict) -> None:
        self._speed_testing = False
        self._speed_test_btn.setEnabled(True)
        self._speed_test_btn.setText("Run Speed Test")
        if self._current_page == 9:
            self._populate_speed_test()

    # -- Bufferbloat test -------------------------------------------------- #
    def _on_bufferbloat_clicked(self) -> None:
        if self._bufferbloat_testing:
            return
        self._bufferbloat_testing = True
        self._bufferbloat_btn.setEnabled(False)
        self._bufferbloat_btn.setText("Testing...")
        self._bufferbloat_status.setText("Measuring baseline latency...")
        threading.Thread(target=self._bufferbloat_worker, daemon=True).start()

    def _bufferbloat_worker(self) -> None:
        self._bufferbloat_signals.progress.emit("Measuring baseline latency...")
        try:
            # Run the test with progress callbacks
            result = self._run_bufferbloat_with_progress()
        except Exception as e:
            result = {"error": str(e), "baseline_latency_ms": 0.0}
            logger.error("Bufferbloat worker failed: %s", e, exc_info=True)
        self._bufferbloat_signals.finished.emit(result)

    def _run_bufferbloat_with_progress(self) -> dict:
        """Run the bufferbloat test, emitting progress signals.

        Wraps the collector's run_bufferbloat_test with progress updates
        by splitting it into phases.
        """
        import statistics

        col = self.collector
        result: dict[str, Any] = {
            "baseline_latency_ms": 0.0,
            "download_latency_ms": 0.0,
            "download_bloat_ms": 0.0,
            "upload_latency_ms": 0.0,
            "upload_bloat_ms": 0.0,
            "grade": "",
            "error": "",
            "timestamp": datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"),
        }

        def _ping_latency(host="1.1.1.1", count=10):
            try:
                proc = subprocess.run(
                    ["ping", "-n", str(count), "-w", "2000", host],
                    capture_output=True, text=True, timeout=30,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                m = re.search(r"Average\s*=\s*(\d+)\s*ms", proc.stdout)
                if m:
                    return float(m.group(1))
            except Exception as e:
                logger.debug("Ping failed: %s", e)
            return None

        def _ping_in_background(host="1.1.1.1", duration_s=12.0):
            latencies = []
            deadline = time.time() + duration_s
            while time.time() < deadline:
                try:
                    proc = subprocess.run(
                        ["ping", "-n", "1", "-w", "2000", host],
                        capture_output=True, text=True, timeout=5,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    m = re.search(r"time[=<](\d+)ms", proc.stdout)
                    if m:
                        latencies.append(float(m.group(1)))
                except Exception:
                    pass
            return latencies

        # 1. Baseline
        baseline = _ping_latency(count=10)
        if baseline is None:
            result["error"] = "Could not measure baseline ping latency"
            col.data.bufferbloat_result = result
            return result
        result["baseline_latency_ms"] = round(baseline, 1)

        # 2. Download under load
        self._bufferbloat_signals.progress.emit(
            f"Testing download latency (baseline {baseline:.0f}ms)...")
        dl_latencies = []
        dl_thread = threading.Thread(
            target=lambda: dl_latencies.extend(
                _ping_in_background(duration_s=12.0)),
            daemon=True,
        )
        dl_thread.start()
        try:
            import requests as _req
            _ua = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/120.0.0.0 Safari/537.36")}
            with _req.get(
                "https://speed.cloudflare.com/__down?bytes=99000000",
                timeout=120, stream=True, headers=_ua) as resp:
                for _ in resp.iter_content(chunk_size=65536):
                    pass
        except Exception as e:
            logger.debug("Bufferbloat download load failed: %s", e)
        dl_thread.join(timeout=15)

        if dl_latencies:
            dl_avg = statistics.mean(dl_latencies)
            result["download_latency_ms"] = round(dl_avg, 1)
            result["download_bloat_ms"] = round(max(0, dl_avg - baseline), 1)
        else:
            result["download_latency_ms"] = 0.0
            result["download_bloat_ms"] = 0.0

        # 3. Upload under load
        self._bufferbloat_signals.progress.emit("Testing upload latency...")
        ul_latencies = []
        ul_thread = threading.Thread(
            target=lambda: ul_latencies.extend(
                _ping_in_background(duration_s=12.0)),
            daemon=True,
        )
        ul_thread.start()
        try:
            import requests as _req
            _ua = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/120.0.0.0 Safari/537.36")}
            with _req.post("https://speed.cloudflare.com/__up",
                           data=b"0" * 50_000_000, timeout=120, headers=_ua):
                pass
        except Exception as e:
            logger.debug("Bufferbloat upload load failed: %s", e)
        ul_thread.join(timeout=15)

        if ul_latencies:
            ul_avg = statistics.mean(ul_latencies)
            result["upload_latency_ms"] = round(ul_avg, 1)
            result["upload_bloat_ms"] = round(max(0, ul_avg - baseline), 1)
        else:
            result["upload_latency_ms"] = 0.0
            result["upload_bloat_ms"] = 0.0

        # 4. Grade
        worst = max(result["download_bloat_ms"], result["upload_bloat_ms"])
        if worst < 30:
            result["grade"] = "A"
        elif worst < 60:
            result["grade"] = "B"
        elif worst < 100:
            result["grade"] = "C"
        elif worst < 200:
            result["grade"] = "D"
        else:
            result["grade"] = "F"

        col.data.bufferbloat_result = result
        return result

    def _on_bufferbloat_progress(self, msg: str) -> None:
        self._bufferbloat_status.setText(msg)

    def _on_bufferbloat_finished(self, result: dict) -> None:
        self._bufferbloat_testing = False
        self._bufferbloat_btn.setEnabled(True)
        self._bufferbloat_btn.setText("Run Bufferbloat Test")
        if self._current_page == 9:
            self._populate_speed_test()

    # -- Windows Tools (PowerShell subprocess suite) ----------------------- #
    # All maintenance tools from the standalone "SA WinTools" PowerShell app
    # (in ``tools source/``) are surfaced here. Each tool runs its verbatim
    # PowerShell script as a hidden-window subprocess; stdout/stderr are
    # streamed live into the log panel via Qt signals.

    @property
    def _tools_page_idx(self) -> int:
        return len(self.PAGES) - 1  # "Tools" is the final nav entry

    # Category icon cache: { "repair": QPixmap, ... } — loaded once on demand.
    _category_icon_cache: dict[str, QPixmap] = {}

    @classmethod
    def _category_icon(cls, key: str) -> QPixmap | None:
        """Load and cache the category icon PNG (icons/<key>.png).

        Returns a QPixmap sized for a 20x20 label, or None if the file is
        missing (so the title still renders without an icon).
        """
        cached = cls._category_icon_cache.get(key)
        if cached is not None:
            return cached
        path = os.path.join(icons_dir(), f"{key}.png")
        if not os.path.exists(path):
            return None
        pm = QPixmap(path)
        if pm.isNull():
            return None
        cls._category_icon_cache[key] = pm
        return pm

    def _populate_tools(self) -> None:
        """Build the Tools page: category sidebar + tool card grid + log.

        Layout:
            ┌──────────────────────────────────────────────┐
            │ [Search tools...]              Status: READY │
            ├────────────┬─────────────────────────────────┤
            │  All       │  ┌──────┐ ┌──────┐ ┌──────┐    │
            │  ▸ Repair  │  │ Card │ │ Card │ │ Card │    │
            │  Maint.    │  └──────┘ └──────┘ └──────┘    │
            │  HW & Diag │  ┌──────┐ ┌──────┐              │
            │  Status    │  │ Card │ │ Card │  ...        │
            │            │  └──────┘ └──────┘              │
            ├────────────┴─────────────────────────────────┤
            │ ▾ Execution Log                               │
            │ [output lines...]                             │
            │ [Open Log] [Clear] [Stop] [Reboot]            │
            └──────────────────────────────────────────────┘

        The category sidebar filters the tool grid.  The search box
        filters by tool name/description across all categories.  Tool
        cards wrap in a FlowLayout so they reflow on window resize.
        The log panel is collapsible (click the header to toggle).
        """
        if self._tools_built:
            return
        idx = self._tools_page_idx
        page = self._pages[idx]
        page.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout: QVBoxLayout = page.widget().layout()
        self._clear_layout(layout)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(0)

        self._tool_cards: list[_ToolCard] = []
        self._tool_filter_cat: str = "all"

        # --- Top bar: search + status ---
        topbar = QHBoxLayout()
        topbar.setContentsMargins(0, 0, 0, 8)
        topbar.setSpacing(10)
        self._tool_search = QLineEdit()
        self._tool_search.setObjectName("tool-search")
        self._tool_search.setPlaceholderText("Search tools...")
        self._tool_search.setFixedWidth(260)
        self._tool_search.textChanged.connect(self._filter_tools)
        topbar.addWidget(self._tool_search)
        topbar.addStretch()
        self._tool_status_lbl = QLabel("READY")
        self._tool_status_lbl.setObjectName("tool-status")
        topbar.addWidget(self._tool_status_lbl)
        layout.addLayout(topbar)

        # --- Main split: category sidebar + tool grid ---
        split = QHBoxLayout()
        split.setSpacing(0)
        split.setContentsMargins(0, 0, 0, 0)

        # Category sidebar
        cat_frame = QFrame()
        cat_frame.setObjectName("tools-sidebar")
        cat_layout = QVBoxLayout(cat_frame)
        cat_layout.setContentsMargins(0, 0, 8, 0)
        cat_layout.setSpacing(2)

        self._tool_cat_btns: list[QPushButton] = []
        total_tools = sum(len(c["tools"]) for c in TOOL_CATEGORIES)

        btn_all = QPushButton(f"All  ({total_tools})")
        btn_all.setObjectName("tool-cat-btn")
        btn_all.setCheckable(True)
        btn_all.setChecked(True)
        btn_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_all.clicked.connect(lambda: self._set_tool_category("all"))
        cat_layout.addWidget(btn_all)
        self._tool_cat_btns.append(btn_all)

        for cat in TOOL_CATEGORIES:
            n = len(cat["tools"])
            icon_pixmap = self._category_icon(cat["key"])
            label = f"{cat['name']}  ({n})"
            btn = QPushButton(label)
            btn.setObjectName("tool-cat-btn")
            btn.setProperty("cat", cat["key"])
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if icon_pixmap is not None:
                btn.setIcon(QIcon(icon_pixmap))
                btn.setIconSize(QSize(16, 16))
            btn.clicked.connect(
                lambda _, ck=cat["key"]: self._set_tool_category(ck)
            )
            cat_layout.addWidget(btn)
            self._tool_cat_btns.append(btn)

        cat_layout.addStretch()
        split.addWidget(cat_frame)

        # Tool grid (scrollable, flow layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        grid_container = QWidget()
        self._tool_flow = _FlowLayout(grid_container, spacing=8)
        self._tool_flow.setContentsMargins(4, 4, 8, 4)
        scroll.setWidget(grid_container)
        split.addWidget(scroll, 1)

        layout.addLayout(split, 1)

        # --- Build tool cards ---
        for cat in TOOL_CATEGORIES:
            for tool in cat["tools"]:
                card = _ToolCard(
                    tool["name"], tool["desc"], cat["key"],
                    len(tool.get("modes", [])),
                    [m["label"] for m in tool.get("modes", [])],
                )
                card.clicked.connect(
                    lambda ck=cat["key"], tn=tool["name"], t=tool:
                        self._on_tool_clicked(ck, tn, t)
                )
                self._tool_cards.append(card)

        self._rebuild_tool_grid()

        # --- Collapsible log panel ---
        log_header = QPushButton("▾ Execution Log")
        log_header.setObjectName("tool-log-header")
        log_header.setCursor(Qt.CursorShape.PointingHandCursor)
        log_header.setCheckable(True)
        log_header.setChecked(True)
        log_header.clicked.connect(self._toggle_log_panel)
        layout.addWidget(log_header)
        self._tool_log_header = log_header

        log_frame = QFrame()
        log_frame.setObjectName("tool-log-frame")
        log_v = QVBoxLayout(log_frame)
        log_v.setContentsMargins(0, 4, 0, 0)
        log_v.setSpacing(4)
        self._tool_log = QPlainTextEdit()
        self._tool_log.setObjectName("tool-log")
        self._tool_log.setReadOnly(True)
        self._tool_log.setMaximumBlockCount(20000)
        self._tool_log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._tool_log.setMinimumHeight(260)
        self._tool_log.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._tool_log.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._tool_log.setPlaceholderText(
            "Select a tool above to run. Output will stream here in real time."
        )
        log_v.addWidget(self._tool_log)
        self._tool_log_frame = log_frame

        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        self._tool_log_btn = QPushButton("Open Log")
        self._tool_log_btn.setObjectName("tool-bottom")
        self._tool_log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tool_log_btn.clicked.connect(self._on_tool_open_log)
        bottom.addWidget(self._tool_log_btn)

        self._tool_clear_btn = QPushButton("Clear")
        self._tool_clear_btn.setObjectName("tool-bottom")
        self._tool_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tool_clear_btn.clicked.connect(self._on_tool_clear)
        bottom.addWidget(self._tool_clear_btn)

        self._tool_stop_btn = QPushButton("Stop")
        self._tool_stop_btn.setObjectName("tool-bottom")
        self._tool_stop_btn.setProperty("accent", "stop")
        self._tool_stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tool_stop_btn.clicked.connect(self._on_tool_stop)
        bottom.addWidget(self._tool_stop_btn)

        self._tool_reboot_btn = QPushButton("Reboot")
        self._tool_reboot_btn.setObjectName("tool-bottom")
        self._tool_reboot_btn.setProperty("accent", "reboot")
        self._tool_reboot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tool_reboot_btn.clicked.connect(self._on_tool_reboot)
        bottom.addWidget(self._tool_reboot_btn)
        bottom.addStretch()
        log_v.addLayout(bottom)
        layout.addWidget(log_frame, 1)

        self._tools_built = True
        self._tool_stopped = False
        self._pending_tool_reboot = False

    def _set_tool_category(self, cat_key: str) -> None:
        """Filter the tool grid to show only the selected category."""
        self._tool_filter_cat = cat_key
        for btn in self._tool_cat_btns:
            btn.setChecked(btn.property("cat") == cat_key or
                           (cat_key == "all" and btn.text().startswith("All")))
        self._rebuild_tool_grid()

    def _filter_tools(self) -> None:
        """Filter tool cards by search query."""
        self._rebuild_tool_grid()

    def _rebuild_tool_grid(self) -> None:
        """Re-populate the flow layout with cards matching the current
        category filter and search query."""
        # Clear existing items from the flow layout
        while self._tool_flow.count():
            item = self._tool_flow.takeAt(0)
            w = item.widget() if item else None
            if w:
                w.setParent(None)

        query = self._tool_search.text().strip().lower() if hasattr(self, "_tool_search") else ""
        cat = self._tool_filter_cat

        for card in self._tool_cards:
            cat_match = (cat == "all" or card.property("cat") == cat)
            search_match = (not query or query in card._name or query in card._desc)
            if cat_match and search_match:
                self._tool_flow.addWidget(card)
                card.setVisible(True)
            else:
                card.setParent(None)
                card.setVisible(False)

    def _toggle_log_panel(self) -> None:
        """Show/hide the log panel when the header is clicked."""
        visible = self._tool_log_header.isChecked()
        self._tool_log_header.setText(
            "▾ Execution Log" if visible else "▸ Execution Log"
        )
        self._tool_log_frame.setVisible(visible)

    def _on_tool_clicked(self, category_key: str, tool_name: str,
                        tool: dict) -> None:
        """Handle a tool button click. Single-mode tools run directly;
        multi-mode tools show a popup menu of modes."""
        if self._tool_running:
            self._tool_status_lbl.setText(
                "A tool is already running - click Stop first.")
            return
        modes = tool.get("modes", [])
        if len(modes) == 1:
            self._run_tool_mode(category_key, tool_name, modes[0])
            return
        # Multi-mode: show a popup menu of modes centered on the app window.
        menu = QMenu(tool_name, self)
        menu.setObjectName("tool-menu")
        for mode in modes:
            act = menu.addAction(mode["label"])
            act.triggered.connect(
                lambda _, ck=category_key, tn=tool_name, m=mode:
                    self._run_tool_mode(ck, tn, m)
            )
        # Center the menu on the main window
        center = self.mapToGlobal(self.rect().center())
        # Adjust so the menu's center (not top-left) lands on the window center
        menu.move(center.x() - menu.sizeHint().width() // 2,
                  center.y() - menu.sizeHint().height() // 2)
        menu.exec()

    def _run_tool_mode(self, category_key: str, tool_name: str,
                       mode: dict) -> None:
        """Collect any input, confirm if destructive, then launch the tool."""
        if self._tool_running:
            self._tool_status_lbl.setText(
                "A tool is already running - click Stop first.")
            return
        # path_select is a two-phase flow: scan -> pick -> clean. The scan
        # output streams to the log; when it finishes we parse the captured
        # rows, show a multi-select dialog, then run the cleanup script.
        if mode.get("input", {}).get("type") == "path_select":
            self._begin_path_select_flow(tool_name, mode)
            return
        # 1. Collect input (text / drive letter / hdd mode) if needed.
        subs: dict[str, str] = {}
        if mode.get("input"):
            subs = self._collect_tool_input(mode["input"])
            if subs is None:
                return  # user cancelled
        # 2. Confirm destructive operations.
        if mode.get("confirm"):
            if not self._confirm_tool(tool_name, mode["label"]):
                self._tool_status_lbl.setText("CANCELLED")
                return
        # 3. Build the final script with placeholders substituted.
        script = resolve_tool_placeholders(mode["script"])
        for token, val in subs.items():
            script = script.replace(token, val)
        # Track the running mode so Stop can decide whether to prompt.
        self._tool_running_mode = mode
        self._tool_running_name = tool_name
        label = f"{tool_name} - {mode['label']}"
        self._run_powershell_tool(label, script, mode.get("reboot", False))

    def _begin_path_select_flow(self, tool_name: str, mode: dict) -> None:
        """Phase 1 of path_select: run the scan script. When it finishes,
        :meth:`_on_tool_finished` detects the pending state, parses the
        captured output, and shows the multi-select dialog (phase 2)."""
        spec = mode["input"]
        scan_script = resolve_tool_placeholders(spec["scan_script"])
        self._path_select_pending = {
            "tool_name": tool_name,
            "mode": mode,
            "spec": spec,
        }
        # Scan phase is read-only - track the mode so Stop can check
        # _path_select_pending to know we're not yet in the destructive
        # cleanup phase.
        self._tool_running_mode = mode
        self._tool_running_name = tool_name
        scan_label = f"{tool_name} - {mode['label']} (scanning...)"
        self._run_powershell_tool(scan_label, scan_script, False)

    def _parse_scan_output(self, text: str, spec: dict) -> list[tuple]:
        """Parse the scan output captured from the log panel.

        Returns a list of ``(size_bytes, id_value, label)`` tuples where
        ``id_value`` is the value to substitute into ``__PATHS__`` (the path
        for filesystem deletions or the package FullName for Appx) and
        ``label`` is what to show in the dialog.

        For ``id_col=False`` (filesystem) the scan emits ``size\tpath`` so
        ``id_value == label == path``. For ``id_col=True`` (Appx) the scan
        emits ``size\tid\tlabel``.
        """
        id_col = spec.get("id_col", False)
        items: list[tuple] = []
        in_scan = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == "__SCAN_BEGIN__":
                in_scan = True
                continue
            if stripped == "__SCAN_END__":
                in_scan = False
                continue
            if not in_scan:
                continue
            parts = line.split("\t")
            if id_col:
                if len(parts) < 3:
                    continue
                try:
                    size = int(parts[0])
                except ValueError:
                    continue
                id_value = parts[1]
                label = "\t".join(parts[2:])
                items.append((size, id_value, label))
            else:
                if len(parts) < 2:
                    continue
                try:
                    size = int(parts[0])
                except ValueError:
                    continue
                path = "\t".join(parts[1:])
                items.append((size, path, path))
        return items

    @staticmethod
    def _is_critical_path(path: str) -> bool:
        """Return True for paths that must never be auto-deleted."""
        try:
            p = os.path.normpath(path).lower()
        except Exception:
            return True
        # Root of a drive (e.g. "c:\\") is never deletable.
        if len(p) <= 3:
            return True
        user_profile = os.environ.get("USERPROFILE", "")
        if user_profile:
            up = os.path.normpath(user_profile).lower()
            if p == up:
                return True
        critical_prefixes = (
            r"c:\windows",
            r"c:\program files",
            r"c:\program files (x86)",
            r"c:\programdata",
            r"c:\$windows.~ws",
            r"c:\$windows.~bt",
            r"c:\recovery",
        )
        for prefix in critical_prefixes:
            if p == prefix or p.startswith(prefix + os.sep):
                return True
        # Block anything Microsoft-branded in AppData to avoid nuking
        # system-critical app containers.
        if r"\microsoft" in p:
            return True
        return False

    @staticmethod
    def _fmt_item_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        if size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def _path_select_dlg(self, spec: dict,
                        items: list[tuple]) -> list[str] | None:
        """Show a modal multi-select dialog with checkboxes.

        ``items`` is the list returned by :meth:`_parse_scan_output`:
        ``(size_bytes, id_value, label)`` tuples. Returns the list of
        selected ``id_value`` strings, or None if the user cancelled.
        """
        if not items:
            QMessageBox.information(
                self, "No Items",
                "The scan did not find any selectable items."
            )
            return None
        blocklist = spec.get("blocklist", True)
        title = spec.get("label", "Select items:")
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(640)
        dlg.setMinimumHeight(480)
        # Larger-than-default font so scan results are easy to read across
        # all path_select dialogs (Disk Analyzer, Appx Manager).
        result_font = QFont()
        result_font.setPointSize(11)
        v = QVBoxLayout(dlg)
        v.setSpacing(8)
        lbl_title = QLabel(title)
        lbl_title.setFont(result_font)
        v.addWidget(lbl_title)
        if blocklist:
            lbl_note = QLabel(
                "Critical system paths are hidden (C:\\Windows, "
                "Program Files, Microsoft app containers, profile root)."
            )
            lbl_note.setFont(result_font)
            v.addWidget(lbl_note)
        lw = QListWidget()
        lw.setFont(result_font)
        lw.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        checkable = (Qt.ItemFlag.ItemIsUserCheckable
                     | Qt.ItemFlag.ItemIsEnabled)
        shown: list[tuple] = []  # (id_value, size_bytes)
        for size_bytes, id_value, label in items:
            if blocklist and self._is_critical_path(id_value):
                continue
            shown.append((id_value, size_bytes))
            size_str = self._fmt_item_size(size_bytes)
            if label == id_value:
                display = f"{size_str}  -  {id_value}"
            else:
                display = f"{size_str}  -  {label}  ({id_value})"
            item = QListWidgetItem(display)
            item.setFlags(checkable)
            item.setCheckState(Qt.CheckState.Unchecked)
            lw.addItem(item)
        if not shown:
            QMessageBox.information(
                self, "Nothing Selectable",
                "All scanned items were blocked by the critical-path filter."
            )
            return None
        v.addWidget(lw, 1)

        # Select-all / none + live total label
        btn_row = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_none = QPushButton("Select None")
        btn_all.setFont(result_font)
        btn_none.setFont(result_font)
        total_lbl = QLabel("Selected: 0  -  0 B")
        total_lbl.setFont(result_font)
        btn_all.clicked.connect(lambda: self._set_all_checks(lw, True))
        btn_none.clicked.connect(lambda: self._set_all_checks(lw, False))
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addStretch(1)
        btn_row.addWidget(total_lbl)
        v.addLayout(btn_row)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        bb.button(QDialogButtonBox.StandardButton.Ok).setFont(result_font)
        bb.button(QDialogButtonBox.StandardButton.Cancel).setFont(result_font)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)

        def _on_item_changed(*_):
            total = 0
            count = 0
            for i in range(lw.count()):
                it = lw.item(i)
                if it.checkState() == Qt.CheckState.Checked:
                    total += shown[i][1]
                    count += 1
            total_lbl.setText(
                f"Selected: {count}  -  {self._fmt_item_size(total)}"
            )
        lw.itemChanged.connect(_on_item_changed)
        lw.setFocus()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        selected: list[str] = []
        for i in range(lw.count()):
            it = lw.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                selected.append(shown[i][0])
        if not selected:
            QMessageBox.warning(
                self, "Nothing Selected",
                "Tick at least one item before proceeding."
            )
            return None
        return selected

    @staticmethod
    def _set_all_checks(lw: QListWidget, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        lw.blockSignals(True)
        for i in range(lw.count()):
            lw.item(i).setCheckState(state)
        lw.blockSignals(False)
        # Manually emit one itemChanged so the total label refreshes.
        if lw.count() > 0:
            lw.itemChanged.emit(lw.item(0))

    def _run_powershell_tool(self, label: str, script: str,
                             reboot: bool = False) -> None:
        """Launch the PowerShell script in a background thread."""
        self._tool_running = True
        self._tool_stopped = False
        self._pending_tool_reboot = reboot
        self._set_tool_buttons_enabled(False)
        self._tool_log.clear()
        # Emit a start banner to the log so the user can see what is
        # running and when it started. The banner is written here (main
        # thread) so it appears before any streamed output from the worker.
        # We also truncate the on-disk log file and write the banner to it
        # so the "Open Log" view matches the GUI log.
        self._tool_start_time = time.monotonic()
        banner_lines = [
            "",
            f"[{self._tool_ts()}] ===== STARTED: {label} =====",
            "",
        ]
        for line in banner_lines:
            self._tool_log.appendPlainText(line)
        self._tool_log.ensureCursorVisible()
        try:
            with open(self._tool_log_path, "w", encoding="utf-8") as logf:
                for line in banner_lines:
                    logf.write(line + "\n")
        except Exception:
            pass
        self._tool_status_lbl.setText(f"RUNNING: {label}")
        self._status_label.setText(f"Tools: running {label}")
        threading.Thread(
            target=self._tool_worker, args=(label, script), daemon=True
        ).start()

    @staticmethod
    def _tool_ts() -> str:
        """Timestamp string for log banners (HH:MM:SS)."""
        return datetime.datetime.now().strftime("%H:%M:%S")

    def _emit_log_line(self, line: str) -> None:
        """Append a line to the tool log and the on-disk log file.

        Used for GUI-side status banners (COMPLETED / FAILED /
        TERMINATED) that are emitted from the main thread, outside the
        streaming worker loop. The file is opened in append mode so the
        banner follows the streamed output that the worker already wrote.
        """
        if self._tools_built:
            self._tool_log.appendPlainText(line)
            self._tool_log.ensureCursorVisible()
        try:
            with open(self._tool_log_path, "a", encoding="utf-8") as logf:
                logf.write(line + "\n")
        except Exception:
            pass

    def _tool_worker(self, label: str, script: str) -> None:
        """Run the PowerShell script via a temp .ps1 file and stream output."""
        rc = -1
        script_path: str | None = None
        try:
            fd, script_path = tempfile.mkstemp(
                suffix=".ps1", prefix="satool_"
            )
            # utf-8-sig writes a BOM so Windows PowerShell 5.1 correctly
            # detects UTF-8 (box-drawing / accented chars in the scripts).
            with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
                f.write(TOOL_PREAMBLE)
                f.write("\n")
                f.write(script)
            cmd = [
                "powershell.exe", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", script_path,
            ]
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
            self._tool_proc = proc
            # Open in append mode: _run_powershell_tool already truncated
            # the file and wrote the STARTED banner to it, so the worker
            # appends streamed output after the banner (keeps the on-disk
            # log and the GUI log in sync).
            with open(self._tool_log_path, "a", encoding="utf-8") as logf:
                assert proc.stdout is not None
                for line in proc.stdout:
                    line = line.rstrip("\r\n")
                    # Preserve blank lines, headers, and `===` separators
                    # so the log keeps the script's visual structure (blank
                    # lines between steps, "SA WinTools - ..." banners, and
                    # `=====` section dividers). Earlier versions stripped
                    # these for "compactness" but that made the log a wall
                    # of text with no readable section breaks.
                    self._tool_signals.output.emit(line)
                    logf.write(line + "\n")
                    logf.flush()
            rc = proc.wait()
        except Exception as e:
            logger.error("Tool worker failed: %s", e, exc_info=True)
            err_line = f"[ERROR] {e}"
            self._tool_signals.output.emit(err_line)
            # Also persist the error to the on-disk log so "Open Log"
            # shows the same content as the GUI log.
            try:
                with open(self._tool_log_path, "a", encoding="utf-8") as logf:
                    logf.write(err_line + "\n")
            except Exception:
                pass
            rc = -1
        finally:
            self._tool_proc = None
            if script_path:
                try:
                    os.unlink(script_path)
                except OSError:
                    pass
        self._tool_signals.finished.emit(rc)

    def _on_tool_output(self, line: str) -> None:
        if self._tools_built:
            self._tool_log.appendPlainText(line)
            self._tool_log.ensureCursorVisible()

    def _on_tool_status(self, msg: str) -> None:
        if self._tools_built:
            self._tool_status_lbl.setText(msg)

    def _on_tool_finished(self, rc: int) -> None:
        # path_select phase 2: a scan just finished. Parse the captured log
        # output, show the multi-select dialog, and (if the user confirms)
        # launch the cleanup script. We keep _tool_running True so tool
        # buttons stay disabled while the dialog is up.
        if self._path_select_pending is not None and not self._tool_stopped:
            pending = self._path_select_pending
            self._path_select_pending = None
            if self._tools_built:
                self._tool_status_lbl.setText("PICKING ITEMS...")
                self._status_label.setText("Tools: awaiting selection")
            # Emit a "scan complete" banner so the user sees the scan phase
            # ended cleanly before the pick dialog appears. The cleanup
            # phase will clear the log when it starts, so this banner only
            # appears if the user cancels the dialog (leaving the scan log
            # visible as the final state).
            duration = time.monotonic() - self._tool_start_time
            self._emit_log_line("")
            self._emit_log_line(
                f"[{self._tool_ts()}] ===== SCAN COMPLETE "
                f"({duration:.1f}s, exit {rc}) - pick items to proceed ====="
            )
            items = self._parse_scan_output(
                self._tool_log.toPlainText(), pending["spec"]
            )
            if not items:
                self._tool_running = False
                self._tool_stopping = False
                self._tool_running_mode = None
                self._tool_running_name = ""
                self._set_tool_buttons_enabled(True)
                if self._tools_built:
                    self._tool_status_lbl.setText("NO ITEMS FOUND")
                    self._status_label.setText("Tools: scan found no items")
                self._emit_log_line("[!] No selectable items were found.")
                return
            selected = self._path_select_dlg(pending["spec"], items)
            if not selected:
                self._tool_running = False
                self._tool_stopping = False
                self._tool_running_mode = None
                self._tool_running_name = ""
                self._set_tool_buttons_enabled(True)
                if self._tools_built:
                    self._tool_status_lbl.setText("CANCELLED")
                    self._status_label.setText("Tools: cancelled")
                self._emit_log_line("[!] Cancelled by user - no items selected.")
                return
            # Confirm destructive op (the path_select mode already declares
            # confirm=True, but we check here so the user gets one last
            # warning before the actual deletion runs).
            if pending["mode"].get("confirm"):
                if not self._confirm_tool(pending["tool_name"],
                                          pending["mode"]["label"]):
                    self._tool_running = False
                    self._tool_stopping = False
                    self._tool_running_mode = None
                    self._tool_running_name = ""
                    self._set_tool_buttons_enabled(True)
                    if self._tools_built:
                        self._tool_status_lbl.setText("CANCELLED")
                        self._status_label.setText("Tools: cancelled")
                    self._emit_log_line("[!] Cancelled by user - no cleanup performed.")
                    return
            paths_str = "\n".join(selected)
            script = resolve_tool_placeholders(pending["spec"]["script"])
            script = script.replace("__PATHS__", paths_str)
            # Add "(cleaning...)" suffix so the STARTED banner of the cleanup
            # phase clearly distinguishes it from the scan phase.
            cleanup_label = (f"{pending['tool_name']} - "
                             f"{pending['mode']['label']} (cleaning {len(selected)} item(s)...)")
            # Mode tracking is already set from the scan phase; the cleanup
            # phase is destructive so Stop should prompt if interrupted.
            self._tool_running_mode = pending["mode"]
            self._tool_running_name = pending["tool_name"]
            # _run_powershell_tool re-sets _tool_running True and clears the
            # log so the scan output is replaced by the deletion log.
            self._run_powershell_tool(
                cleanup_label, script,
                pending["mode"].get("reboot", False)
            )
            return

        # Compute duration before resetting the start time.
        duration = (time.monotonic() - self._tool_start_time
                    if self._tool_start_time else 0.0)
        self._tool_running = False
        self._tool_stopping = False
        self._tool_running_mode = None
        self._tool_running_name = ""
        self._set_tool_buttons_enabled(True)
        if self._tools_built:
            if self._tool_stopped:
                self._tool_status_lbl.setText("TERMINATED")
                self._status_label.setText("Tools: terminated")
                self._emit_log_line("")
                self._emit_log_line(
                    f"[{self._tool_ts()}] ===== TERMINATED BY USER "
                    f"({duration:.1f}s) ====="
                )
            else:
                self._tool_status_lbl.setText("COMPLETED")
                self._status_label.setText(
                    f"Tools: completed (exit {rc})" if rc else "Tools: completed"
                )
                # End banner with exit code + duration for clear feedback.
                if rc == 0:
                    self._emit_log_line("")
                    self._emit_log_line(
                        f"[{self._tool_ts()}] ===== COMPLETED SUCCESSFULLY "
                        f"({duration:.1f}s, exit {rc}) ====="
                    )
                else:
                    self._emit_log_line("")
                    self._emit_log_line(
                        f"[{self._tool_ts()}] ===== COMPLETED WITH ERRORS "
                        f"({duration:.1f}s, exit {rc}) ====="
                    )
                if self._pending_tool_reboot:
                    self._emit_log_line("")
                    self._emit_log_line(
                        "[!] REBOOT REQUIRED for the changes to take effect."
                    )
            self._pending_tool_reboot = False
            self._tool_start_time = 0.0

    def _set_tool_buttons_enabled(self, enabled: bool) -> None:
        if not self._tools_built:
            return
        for c in self._tool_cards:
            c.setEnabled(enabled)

    def _on_tool_stop(self) -> None:
        if not self._tools_built:
            return
        # Guard against double-clicks while a stop is already in progress.
        if self._tool_stopping:
            return
        proc = self._tool_proc
        if not proc or proc.poll() is not None:
            # Process already exited (worker thread will emit finished soon).
            self._tool_stopped = True
            self._tool_stopping = False
            self._path_select_pending = None
            self._tool_running_mode = None
            self._tool_running_name = ""
            self._tool_status_lbl.setText("TERMINATED")
            self._status_label.setText("Tools: terminating...")
            return

        # Determine whether the running operation is destructive enough to
        # warrant a warning before force-stopping. The proxy is the mode's
        # `confirm` flag - modes that already prompt before running (SFC,
        # DISM, chkdsk /f or /r, Appx removal, dev cache deletion, etc.) are
        # the ones whose mid-flight termination can leave the system in an
        # inconsistent state. path_select scan phase is read-only (the
        # destructive cleanup phase only starts after _path_select_pending
        # has been cleared), so it does not prompt.
        mode = self._tool_running_mode
        in_path_select_scan = self._path_select_pending is not None
        is_destructive = (self._is_critical_stop_operation(mode)
                          and not in_path_select_scan)
        if is_destructive:
            tool_name = self._tool_running_name or "the tool"
            mode_label = mode.get("label", "this operation") if mode else "this operation"
            r = QMessageBox.warning(
                self, "Stop Critical Operation?",
                f"A critical operation is in progress:\n\n"
                f"  {tool_name} - {mode_label}\n\n"
                f"Force-stopping it now may leave the system in an "
                f"inconsistent state (incomplete repairs, broken "
                f"registrations, partial deletions). Whenever possible, "
                f"let the operation finish.\n\n"
                f"Stop it anyway?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                # User chose to let it finish - leave the tool running.
                return

        # Mark stopping state so subsequent Stop clicks are ignored and
        # _on_tool_finished shows TERMINATED instead of COMPLETED.
        self._tool_stopping = True
        self._tool_stopped = True
        self._path_select_pending = None
        self._tool_status_lbl.setText("STOPPING...")
        self._status_label.setText("Tools: stopping...")

        # Run the actual kill in a background thread so the UI stays
        # responsive during the graceful-shutdown grace period.
        threading.Thread(
            target=self._stop_tool_proc_async, args=(proc,), daemon=True
        ).start()

    # Patterns that mark a tool script as critical-to-stop. When any of
    # these substrings appear in the mode's script, stopping mid-flight can
    # leave Windows in an inconsistent state (incomplete SFC/DISM repairs,
    # partial chkdsk bad-sector recovery, broken Appx registrations,
    # half-applied registry edits, etc.). Used by _on_tool_stop to decide
    # whether to prompt before force-killing.
    _CRITICAL_SCRIPT_PATTERNS = (
        "sfc /scannow",
        "dism.exe /Online /Cleanup-Image",
        "chkdsk",
        "Optimize-Volume",
        "Remove-AppxPackage",
        "reagentc",
        # slmgr /ato (online activation) modifies the license state;
        # slmgr /dlv is read-only and is NOT matched here. The /ipk mode
        # already carries confirm=True so it is caught by the other branch.
        'slmgr.vbs" /ato',
        "powercfg /hibernate",
        "Clear-RecycleBin",
        "Stop-Service",
        "Start-Service",
        "net use * /delete",
        "w32tm /unregister",
        "w32tm /register",
        "Set-ItemProperty",
        "Remove-Item",
        "Disable-PnpDevice",
        "Enable-PnpDevice",
        "Rename-Item",
        "New-Item",  # registry key creation
    )

    @classmethod
    def _is_critical_stop_operation(cls, mode: dict | None) -> bool:
        """Return True if stopping this mode mid-flight is dangerous.

        Heuristic: a mode is critical if it carries ``confirm=True`` (already
        flagged as destructive before running) OR its script contains any of
        the :data:`_CRITICAL_SCRIPT_PATTERNS` substrings (sfc, dism, chkdsk,
        Optimize-Volume, Remove-AppxPackage, slmgr, powercfg /hibernate,
        service stop/start, registry writes, file deletions, PnP device
        enable/disable, ...). The path_select scan phase is read-only and
        is excluded by the caller via the ``_path_select_pending`` check.
        """
        if not mode:
            return False
        if mode.get("confirm"):
            return True
        script = mode.get("script", "")
        if not script:
            return False
        script_lower = script.lower()
        for pattern in cls._CRITICAL_SCRIPT_PATTERNS:
            if pattern.lower() in script_lower:
                return True
        return False

    def _stop_tool_proc_async(self, proc: subprocess.Popen) -> None:
        """Background thread: try graceful shutdown first, then force kill.

        Phase 1 sends ``taskkill /T /PID`` (no ``/F``) which posts
        ``WM_CLOSE`` to every window in the process tree. This lets
        GUI child processes (Notepad from Hosts Editor, ``mdtsched.exe``
        from Memory Diagnostic, slmgr.vbs dialogs, ...) shut down
        cleanly. PowerShell itself was launched with
        ``CREATE_NO_WINDOW`` so it has no window to receive the message
        and will not exit here - the grace period also gives the script
        a moment to reach a natural exit point if it was just about to
        finish on its own.

        Phase 2 (after the 3s grace period) sends ``taskkill /F /T``
        which forcibly terminates the whole tree, including PowerShell
        and any windowless child processes.
        """
        pid = proc.pid
        # Phase 1: graceful - WM_CLOSE to windows in the tree.
        try:
            subprocess.run(
                ["taskkill", "/T", "/PID", str(pid)],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=3,
            )
        except subprocess.TimeoutExpired:
            pass  # taskkill itself hung; fall through to force
        except Exception:
            pass  # best effort; fall through to force

        # Poll for up to 3 seconds for a graceful exit.
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            try:
                if proc.poll() is not None:
                    return  # exited gracefully
            except Exception:
                break
            time.sleep(0.1)

        # Phase 2: force kill the entire process tree.
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=5,
            )
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _on_tool_clear(self) -> None:
        if not self._tools_built:
            return
        if self._tool_running:
            self._on_tool_stop()
        self._tool_log.clear()
        # Only reset the stop flags if no tool is running.  If a tool IS
        # running, _on_tool_stop() just launched an async kill thread; the
        # _on_tool_finished handler (fired when the kill completes) needs
        # _tool_stopped to still be True to show "TERMINATED BY USER"
        # instead of "COMPLETED SUCCESSFULLY".  Resetting them here would
        # race with the async kill and produce misleading status banners.
        if not self._tool_running:
            self._tool_stopped = False
            self._tool_stopping = False
        self._path_select_pending = None
        if not self._tool_running:
            self._tool_running_mode = None
            self._tool_running_name = ""
            self._tool_start_time = 0.0
        self._tool_status_lbl.setText("READY")
        self._status_label.setText("Tools: ready")

    def _on_tool_open_log(self) -> None:
        if os.path.exists(self._tool_log_path):
            try:
                os.startfile(self._tool_log_path)
            except Exception as e:
                logger.error("Failed to open tool log: %s", e, exc_info=True)
                self._status_label.setText(f"Cannot open log: {e}")
        else:
            self._status_label.setText("No tool log yet - run a tool first.")

    def _on_tool_reboot(self) -> None:
        r = QMessageBox.question(
            self, "Confirm Reboot",
            "This will immediately restart your computer.\n\n"
            "All unsaved work will be lost.\n\nProceed with reboot?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r == QMessageBox.StandardButton.Yes:
            try:
                subprocess.Popen(
                    ["shutdown", "/r", "/f", "/t", "0"],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception as e:
                logger.error("Failed to initiate reboot: %s", e, exc_info=True)
                QMessageBox.warning(
                    self, "Reboot Failed",
                    f"Could not initiate reboot: {e}",
                )

    def _confirm_tool(self, tool_name: str, mode_label: str) -> bool:
        r = QMessageBox.question(
            self, "Confirm Tool",
            f"Run the following operation?\n\n"
            f"  {tool_name}\n  {mode_label}\n\n"
            f"This may modify your system. Proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return r == QMessageBox.StandardButton.Yes

    # -- Tool input dialogs ------------------------------------------------- #
    def _drive_list(self) -> list[tuple[str, str]]:
        """Return [(letter, display), ...] of mounted local drives via psutil."""
        drives: list[tuple[str, str]] = []
        try:
            import psutil
            for p in psutil.disk_partitions(all=False):
                if not p.device or len(p.device) < 2 or p.device[1] != ":":
                    continue
                letter = p.device[0].upper()
                try:
                    u = psutil.disk_usage(p.mountpoint)
                    total = u.total / (1024 ** 3)
                    free = u.free / (1024 ** 3)
                    label = (f"{letter}:  -  Total: {total:.0f} GB   "
                             f"Free: {free:.0f} GB")
                except Exception:
                    label = f"{letter}:  -  {p.mountpoint}"
                drives.append((letter, label))
        except Exception:
            pass
        return drives

    def _collect_tool_input(self, spec: dict) -> dict[str, str] | None:
        """Show the appropriate input dialog and return substitutions.

        Returns None if the user cancelled.
        """
        kind = spec.get("type", "")
        if kind == "text":
            return self._collect_text_input(spec)
        if kind == "drive":
            return self._collect_drive_input(spec)
        if kind == "hdd_check":
            return self._collect_hdd_check_input(spec)
        return {}

    def _collect_text_input(self, spec: dict) -> dict[str, str] | None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Input Required")
        dlg.setMinimumWidth(420)
        v = QVBoxLayout(dlg)
        v.setSpacing(10)
        v.addWidget(QLabel(spec.get("label", "Enter value:")))
        le = QLineEdit()
        le.setPlaceholderText(spec.get("placeholder", ""))
        if spec.get("maxlen"):
            le.setMaxLength(spec["maxlen"])
        v.addWidget(le)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        le.setFocus()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        text = le.text().strip()
        if not text:
            QMessageBox.warning(
                self, "Input Required",
                "Please enter a value before proceeding."
            )
            return None
        # Escape single quotes for PowerShell single-quoted string context.
        # Every tool script embeds user input inside '...' literals, so a
        # raw ' would terminate the string and allow arbitrary command
        # injection. PowerShell's only escape sequence for ' inside a
        # single-quoted string is doubling it to ''.
        safe = text.replace("'", "''")
        return {"__INPUT__": safe}

    def _collect_drive_input(self, spec: dict) -> dict[str, str] | None:
        drives = self._drive_list()
        if not drives:
            QMessageBox.information(
                self, "No Drives",
                "No accessible drives were detected."
            )
            return None
        letter = self._pick_drive_dlg(spec.get("label", "Select drive:"), drives)
        if letter is None:
            return None
        return {"__DRIVE__": letter}

    def _pick_drive_dlg(self, title: str,
                       drives: list[tuple[str, str]]) -> str | None:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(420)
        v = QVBoxLayout(dlg)
        v.setSpacing(10)
        v.addWidget(QLabel(title))
        lw = QListWidget()
        for _, label in drives:
            lw.addItem(label)
        if lw.count():
            lw.setCurrentRow(0)
        v.addWidget(lw)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        lw.setFocus()
        if dlg.exec() != QDialog.DialogCode.Accepted or lw.currentRow() < 0:
            return None
        return drives[lw.currentRow()][0]

    def _collect_hdd_check_input(self, spec: dict) -> dict[str, str] | None:
        drives = self._drive_list()
        if not drives:
            QMessageBox.information(
                self, "No Drives",
                "No accessible drives were detected."
            )
            return None
        dlg = QDialog(self)
        dlg.setWindowTitle("Check HDD - select drive and mode")
        dlg.setMinimumWidth(440)
        v = QVBoxLayout(dlg)
        v.setSpacing(10)
        v.addWidget(QLabel("1. Select drive to check:"))
        lw = QListWidget()
        for _, label in drives:
            lw.addItem(label)
        if lw.count():
            lw.setCurrentRow(0)
        v.addWidget(lw)
        v.addWidget(QLabel("2. Select chkdsk mode:"))
        modes = [
            ("Simple Information (Read-Only)", ""),
            ("Auto Fix Errors (/f)", "/f"),
            ("Full Check & Bad Sectors (/r)", "/r"),
            ("Quick Online Analysis (/scan)", "/scan"),
        ]
        radios: list[QRadioButton] = []
        for i, (label, _) in enumerate(modes):
            rb = QRadioButton(label)
            rb.setChecked(i == 0)
            radios.append(rb)
            v.addWidget(rb)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        lw.setFocus()
        if dlg.exec() != QDialog.DialogCode.Accepted or lw.currentRow() < 0:
            return None
        letter = drives[lw.currentRow()][0]
        mode_flag = ""
        for i, rb in enumerate(radios):
            if rb.isChecked():
                mode_flag = modes[i][1]
                break
        return {"__DRIVE__": letter, "__MODE__": mode_flag}

    # -- Page population ---------------------------------------------------- #
    def _populate_os(self) -> None:
        layout: QVBoxLayout = self._pages[0].widget().layout()
        self._clear_layout(layout)
        d = self.collector.data.os_info
        self._make_card(layout, "Operating System", [
            ("Operating System", str(d.get("Operating System", "N/A"))),
            ("OS Edition", str(d.get("OS Edition", "N/A"))),
            ("Version", str(d.get("Version", "N/A"))),
            ("Release ID", str(d.get("Release ID", "N/A"))),
            ("Build Number", str(d.get("Build Number", "N/A"))),
            ("Architecture (OS)", str(d.get("Architecture (OS)", "N/A"))),
            ("Architecture (Processor)", str(d.get("Architecture (Processor)", "N/A"))),
            ("Computer Name", str(d.get("Computer Name", "N/A"))),
            ("Logged-on User", str(d.get("Logged-on User", "N/A"))),
            ("Domain / Workgroup", str(d.get("Domain / Workgroup", "N/A"))),
            ("Install Date", str(d.get("Install Date", "N/A"))),
            ("Last Boot Time", str(d.get("Last Boot Time", "N/A"))),
            ("Uptime", str(d.get("Uptime", "N/A"))),
        ], 0)

    def _populate_hardware(self) -> None:
        page_container = self._pages[1].widget()
        layout: QVBoxLayout = page_container.layout()
        self._clear_layout(layout)
        self._pages[1].setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        hw = self.collector.data.hw_info
        page_idx = 1

        def _new_tab_page() -> tuple[QScrollArea, QVBoxLayout]:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            container = QWidget()
            tl = QVBoxLayout(container)
            tl.setContentsMargins(0, 0, 8, 0)
            tl.setSpacing(10)
            tl.addStretch()
            scroll.setWidget(container)
            return scroll, tl

        self._hardware_tabs = QTabWidget()
        self._hardware_tabs.setObjectName("hardware-tabs")
        self._hardware_tabs.tabBar().setObjectName("hardware-tabbar")

        cpu = hw.get("cpu", {})
        scroll, tl = _new_tab_page()
        _cpu_vlabels: list = []
        _cpu_blabels: list = []
        self._make_card(tl, "CPU", [
            ("Name", str(cpu.get("Name", "N/A"))),
            ("Physical Cores", str(cpu.get("Physical Cores", "N/A"))),
            ("Logical Cores", str(cpu.get("Logical Cores", "N/A"))),
            ("Threads", str(cpu.get("Threads", "N/A"))),
            ("Max Clock", str(cpu.get("Max Clock", "N/A"))),
            ("Current Freq", str(cpu.get("Current Freq", "N/A"))),
            ("Usage", str(cpu.get("Usage", "N/A"))),
            ("Per-core Usage", str(cpu.get("Per-core Usage", "N/A"))),
        ], page_idx, value_labels=_cpu_vlabels, bar_labels=_cpu_blabels)
        # Row 5 = Current Freq, Row 6 = Usage (has bar), Row 7 = Per-core Usage
        if len(_cpu_vlabels) > 7:
            self._hw_cpu_freq_lbl = _cpu_vlabels[5]
            self._hw_cpu_usage_lbl = _cpu_vlabels[6]
            self._hw_cpu_usage_bar = _cpu_blabels[6]
            self._hw_cpu_percore_lbl = _cpu_vlabels[7]
        _sp_max = get_config().sparkline_max_samples
        sp_cpu_usage = _Sparkline(max_samples=_sp_max, color="#60cdff", label="CPU Usage %")
        sp_cpu_temp = _Sparkline(max_samples=_sp_max, color="#e07b7b", label="CPU Temp °C")
        graph_row = QHBoxLayout()
        graph_row.addWidget(sp_cpu_usage)
        graph_row.addWidget(sp_cpu_temp)
        tl.addLayout(graph_row)
        self._sparklines["cpu_usage"] = sp_cpu_usage
        self._sparklines["cpu_temp"] = sp_cpu_temp
        self._hardware_tabs.addTab(scroll, "CPU")

        ram = hw.get("ram", {})
        ram_rows = [
            ("Total Memory", str(ram.get("Total", "N/A"))),
            ("Used", str(ram.get("Used", "N/A"))),
            ("Available", str(ram.get("Available", "N/A"))),
            ("Usage %", str(ram.get("Usage %", "N/A"))),
            ("Total Installed (slots)", str(ram.get("Total Installed", "N/A"))),
        ]
        for s in ram.get("Slots", []):
            ram_rows.append((
                f"Slot {s.get('Slot', '?')}",
                f"{s.get('Manufacturer', 'N/A')} | {s.get('Part Number', 'N/A')} | "
                f"{s.get('Capacity', 'N/A')} | {s.get('Speed', 'N/A')} | S/N: {s.get('Serial', 'N/A')}"
            ))
        scroll, tl = _new_tab_page()
        _ram_vlabels: list = []
        _ram_blabels: list = []
        self._make_card(tl, "Memory (RAM)", ram_rows, page_idx,
                       value_labels=_ram_vlabels, bar_labels=_ram_blabels)
        if len(_ram_vlabels) > 4:
            self._hw_ram_used_lbl = _ram_vlabels[1]
            self._hw_ram_avail_lbl = _ram_vlabels[2]
            self._hw_ram_usage_lbl = _ram_vlabels[3]
            self._hw_ram_usage_bar = _ram_blabels[3]
        sp_ram_usage = _Sparkline(max_samples=_sp_max, color="#60cdff", label="RAM Usage %")
        sp_gpu_temp = _Sparkline(max_samples=_sp_max, color="#e07b7b", label="GPU Temp °C")
        graph_row2 = QHBoxLayout()
        graph_row2.addWidget(sp_ram_usage)
        graph_row2.addWidget(sp_gpu_temp)
        tl.addLayout(graph_row2)
        self._sparklines["ram_usage"] = sp_ram_usage
        self._sparklines["gpu_temp"] = sp_gpu_temp
        self._hardware_tabs.addTab(scroll, "Memory")

        mb = hw.get("motherboard", {})
        scroll, tl = _new_tab_page()
        self._make_card(tl, "Motherboard", [
            ("Manufacturer", str(mb.get("Manufacturer", "N/A"))),
            ("Model", str(mb.get("Model", "N/A"))),
            ("Version", str(mb.get("Version", "N/A"))),
            ("Serial Number", str(mb.get("Serial Number", "N/A"))),
        ], page_idx)
        self._hardware_tabs.addTab(scroll, "Motherboard")

        bios = hw.get("bios", {})
        scroll, tl = _new_tab_page()
        self._make_card(tl, "BIOS", [
            ("Manufacturer", str(bios.get("Manufacturer", "N/A"))),
            ("Name", str(bios.get("Name", "N/A"))),
            ("Version", str(bios.get("Version", "N/A"))),
            ("Release Date", str(bios.get("Release Date", "N/A"))),
            ("Serial Number", str(bios.get("Serial Number", "N/A"))),
        ], page_idx)
        self._hardware_tabs.addTab(scroll, "BIOS")

        gpus = hw.get("gpus", [])
        gpu_details = self.collector.data.gpu_details
        gpu_rows: list[tuple[str, str]] = []
        for i, g in enumerate(gpus):
            prefix = "GPU" if len(gpus) == 1 else f"GPU {i + 1}"
            gpu_rows.extend([
                (f"{prefix} Name", g.get("Name", "N/A")),
                ("  Video Processor", g.get("Video Processor", "N/A")),
                ("  VRAM", g.get("VRAM", "N/A")),
                ("  Memory Type", g.get("Memory Type", "N/A")),
                ("  Driver Version", g.get("Driver Version", "N/A")),
                ("  Driver Date", g.get("Driver Date", "N/A")),
                ("  Resolution", g.get("Resolution", "N/A")),
                ("  Max Resolution", g.get("Max Resolution", "N/A")),
                ("  Color Depth", g.get("Color Depth", "N/A")),
                ("  Max Refresh Rate", g.get("Max Refresh Rate", "N/A")),
                ("  Scan Mode", g.get("Scan Mode", "N/A")),
                ("  DAC Type", g.get("DAC Type", "N/A")),
                ("  Vendor", g.get("Vendor", "N/A")),
                ("  Architecture", g.get("Architecture", "N/A")),
            ])
        if not gpu_rows:
            gpu_rows = [("GPU", "N/A")]
        scroll, tl = _new_tab_page()
        self._make_card(tl, "Graphics Adapter(s)", gpu_rows, page_idx)

        # GPU Live Metrics card — built from LHM sensor data so it works
        # with any GPU vendor (NVIDIA, AMD, Intel).  Also includes NVML
        # metrics if available (NVIDIA-only, may have extra fields).
        self._hw_gpu_sensor_labels = []
        sensors_data = hw.get("sensors", {})
        gpu_metric_rows: list[tuple[str, str]] = []
        gpu_metric_keys: list[tuple[str, str, str]] = []
        if sensors_data.get("available"):
            stype_label = {
                "Temperature": "Temp",
                "Load": "Load",
                "Fan": "Fan",
                "Clock": "Clock",
                "Power": "Power",
                "Voltage": "Voltage",
            }
            for stype in ("Temperature", "Load", "Fan", "Clock",
                          "Power", "Voltage"):
                skey = self._STYPE_TO_KEY.get(stype, "")
                if not skey:
                    continue
                for entry in sensors_data.get(skey, []):
                    if entry.get("Category") != "GPU":
                        continue
                    name = entry.get("Name", "N/A")
                    val = entry.get("Value", 0.0)
                    src = entry.get("Source", "GPU")
                    label_prefix = stype_label.get(stype, stype)
                    row_label = f"  {label_prefix}: {name}"
                    gpu_metric_rows.append(
                        (row_label, fmt_sensor_value(stype, val)))
                    gpu_metric_keys.append((src, stype, name))

        # Append NVML-only fields that LHM doesn't provide
        for gd in gpu_details or []:
            api = gd.get("API", "")
            if "NVML" not in api:
                continue
            for k, v in gd.items():
                if k in ("API", "Name", "Driver Version"):
                    continue
                if any(k.lower() in rk.lower()
                       for rk, _ in gpu_metric_rows):
                    continue
                gpu_metric_rows.append((f"  NVML: {k}", str(v)))
                gpu_metric_keys.append(("", "", ""))

        if gpu_metric_rows:
            _gpu_vlabels: list = []
            self._make_card(tl, "GPU Live Metrics", gpu_metric_rows,
                            page_idx, value_labels=_gpu_vlabels)
            for lbl, (src, stype, name) in zip(_gpu_vlabels, gpu_metric_keys):
                if stype:
                    self._hw_gpu_sensor_labels.append((src, stype, name, lbl))

        sp_gpu_util = _Sparkline(max_samples=_sp_max, color="#60cdff", label="GPU Util %")
        sp_gpu_temp2 = _Sparkline(max_samples=_sp_max, color="#e07b7b", label="GPU Temp °C")
        graph_row_gpu = QHBoxLayout()
        graph_row_gpu.addWidget(sp_gpu_util)
        graph_row_gpu.addWidget(sp_gpu_temp2)
        tl.addLayout(graph_row_gpu)
        self._sparklines["gpu_util"] = sp_gpu_util
        self._sparklines["gpu_temp_2"] = sp_gpu_temp2
        self._hardware_tabs.addTab(scroll, "GPU")

        disks = hw.get("disks", [])
        scroll, tl = _new_tab_page()
        if disks:
            for d in disks:
                self._make_card(tl, f"Disk {d.get('Index', '?')} - {d.get('Model', 'N/A')}", [
                    ("Size", d.get("Size", "N/A")),
                    ("Media Type", d.get("Media Type", "N/A")),
                    ("Interface", d.get("Interface", "N/A")),
                    ("Link Speed", d.get("Link Speed", "N/A")),
                    ("Serial", d.get("Serial", "N/A")),
                    ("Firmware", d.get("Firmware", "N/A")),
                    ("Free Space", d.get("Free", "N/A")),
                    ("Usage %", d.get("Usage %", "N/A")),
                ], page_idx)
        else:
            self._make_card(tl, "Physical Disk(s)", [("Disk", "N/A")], page_idx)

        sp_disk_read = _Sparkline(max_samples=_sp_max, color="#60cdff", label="All Disks Read MB/s")
        sp_disk_write = _Sparkline(max_samples=_sp_max, color="#90ee90", label="All Disks Write MB/s")
        sp_disk_read.set_samples(self._disk_spark_read)
        sp_disk_write.set_samples(self._disk_spark_write)
        graph_row_disk = QHBoxLayout()
        graph_row_disk.addWidget(sp_disk_read)
        graph_row_disk.addWidget(sp_disk_write)
        tl.addLayout(graph_row_disk)
        self._sparklines["disk_read"] = sp_disk_read
        self._sparklines["disk_write"] = sp_disk_write

        bench_card = QWidget()
        bench_layout = QVBoxLayout(bench_card)
        bench_layout.setContentsMargins(0, 0, 0, 0)
        bench_layout.setSpacing(8)
        bench_title = QLabel("Disk Benchmark")
        bench_title.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {_ACCENT};")
        bench_layout.addWidget(bench_title)
        bench_row = QHBoxLayout()
        drive_label = QLabel("Drive:")
        drive_combo = QComboBox()
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            if os.path.exists(f"{letter}:\\"):
                drive_combo.addItem(f"{letter}:")
        bench_row.addWidget(drive_label)
        bench_row.addWidget(drive_combo)
        size_label = QLabel("Size:")
        size_combo = QComboBox()
        for sz in ("64 MB", "128 MB", "256 MB", "512 MB", "1 GB"):
            size_combo.addItem(sz)
        size_combo.setCurrentIndex(2)
        bench_row.addWidget(size_label)
        bench_row.addWidget(size_combo)
        run_btn = QPushButton("Run Benchmark")
        run_btn.setObjectName("action-btn")
        run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        bench_row.addWidget(run_btn)
        bench_row.addStretch()
        bench_layout.addLayout(bench_row)
        bench_result = QLabel("No benchmark run yet.")
        bench_result.setStyleSheet(f"color: {_TEXT_SECONDARY}; font-size: 13px;")
        bench_layout.addWidget(bench_result)
        tl.addWidget(bench_card)

        def _run_benchmark():
            drive = drive_combo.currentText()
            size_text = size_combo.currentText()
            if "MB" in size_text:
                size_mb = int(size_text.split()[0])
            elif "GB" in size_text:
                size_mb = int(size_text.split()[0]) * 1024
            else:
                size_mb = 256
            run_btn.setEnabled(False)
            run_btn.setText("Running…")
            bench_result.setText(f"Running benchmark on {drive} ({size_mb} MB)…")

            def _worker():
                result = self.collector.run_disk_benchmark(drive, size_mb)
                msg = (f"Drive: {result.get('Drive', 'N/A')}  |  "
                       f"Write: {result.get('Write Speed (MB/s)', 0.0)} MB/s  |  "
                       f"Read: {result.get('Read Speed (MB/s)', 0.0)} MB/s  |  "
                       f"Status: {result.get('Status', 'N/A')}")
                try:
                    QMetaObject.invokeMethod(
                        bench_result, "setText", Qt.ConnectionType.QueuedConnection,
                        Qt.Q_ARG(str, msg))
                    QMetaObject.invokeMethod(
                        run_btn, "setEnabled", Qt.ConnectionType.QueuedConnection,
                        Qt.Q_ARG(bool, True))
                    QMetaObject.invokeMethod(
                        run_btn, "setText", Qt.ConnectionType.QueuedConnection,
                        Qt.Q_ARG(str, "Run Benchmark"))
                except RuntimeError:
                    pass  # Widget was deleted (page rebuilt) — ignore

            threading.Thread(target=_worker, daemon=True).start()

        run_btn.clicked.connect(_run_benchmark)
        self._hardware_tabs.addTab(scroll, "Disks")

        bat = hw.get("battery", {})
        if bat.get("Present"):
            bat_rows = [
                ("Percent", str(bat.get("Percent", "N/A"))),
                ("Plugged In", str(bat.get("Plugged In", "N/A"))),
                ("Charging", str(bat.get("Charging", "N/A"))),
                ("Time Left", str(bat.get("Time Left", "N/A"))),
                ("Design Capacity", str(bat.get("Design Capacity", "N/A"))),
                ("Full Charge Capacity", str(bat.get("Full Charge Capacity", "N/A"))),
                ("Wear %", str(bat.get("Wear %", "N/A"))),
                ("Cycle Count", str(bat.get("Cycle Count", "N/A"))),
            ]
        else:
            bat_rows = [("Battery", "Not present")]
        scroll, tl = _new_tab_page()
        self._make_card(tl, "Battery", bat_rows, page_idx)
        if bat.get("Present"):
            sp_battery = _Sparkline(max_samples=_sp_max, color="#60cdff", label="Battery %")
            sp_battery.set_samples(self._battery_spark)
            tl.addWidget(sp_battery)
            self._sparklines["battery_pct"] = sp_battery
        self._hardware_tabs.addTab(scroll, "Battery")

        layout.addWidget(self._hardware_tabs)

    def _populate_sensors(self) -> None:
        page_container = self._pages[2].widget()
        layout: QVBoxLayout = page_container.layout()
        self._sensor_value_labels.clear()
        self._sensor_minmax.clear()
        self._sensor_sparklines.clear()
        self._sensor_spark_data.clear()
        self._clear_layout(layout)
        self._pages[2].setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        sensors = self.collector.data.hw_info.get("sensors", {})
        page_idx = 2

        if not sensors.get("available"):
            hint = sensors.get("hint", "")
            self._make_card(layout, "Sensors", [
                ("Status", "Not available"),
                ("How to enable", hint),
            ], page_idx)
            layout.addStretch()
            return

        source_lbl = QLabel(f"Source: {sensors.get('source', 'N/A')}")
        source_lbl.setObjectName("update-status")
        layout.addWidget(source_lbl)

        all_sensors: list[dict[str, Any]] = []
        for stype in self._SENSOR_TYPES:
            key = self._STYPE_TO_KEY[stype]
            for entry in sensors.get(key, []):
                all_sensors.append(entry)

        components: dict[str, list[dict[str, Any]]] = {}
        for s in all_sensors:
            source = s.get("Source", s.get("Category", "Other"))
            components.setdefault(source, []).append(s)

        self._sensor_tabs = QTabWidget()
        self._sensor_tabs.setObjectName("sensor-tabs")
        self._sensor_tabs.tabBar().setObjectName("sensor-tabbar")

        for source, comp_entries in components.items():
            tab_label = source

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            tab_container = QWidget()
            tab_layout = QVBoxLayout(tab_container)
            tab_layout.setContentsMargins(0, 0, 8, 0)
            tab_layout.setSpacing(10)
            tab_layout.addStretch()
            scroll.setWidget(tab_container)

            comp_entries.sort(key=lambda e: (
                SENSOR_TYPE_ORDER.get(e.get("Type", ""), 99),
                e.get("Name", ""),
            ))

            prev_type = ""
            current_rows: list[tuple[str, str]] = []
            current_entries: list[dict] = []

            def _flush_card():
                if not current_rows:
                    return
                vlabels: list[QLabel] = []
                self._make_card(
                    tab_layout, prev_type, current_rows, page_idx, vlabels
                )
                for lbl, entry in zip(vlabels, current_entries):
                    stype = entry.get("Type", "")
                    val = entry.get("Value", 0.0)
                    color = self._sensor_color(stype, val)
                    if color != _TEXT_PRIMARY:
                        lbl.setStyleSheet(f"color: {color};")
                    key = (source, entry.get("Type", ""),
                           entry.get("Name", ""))
                    self._sensor_value_labels.setdefault(
                        key, []
                    ).append(lbl)
                    if key in self._sensor_minmax:
                        mm = self._sensor_minmax[key]
                        if val < mm[0]:
                            mm[0] = val
                        if val > mm[1]:
                            mm[1] = val
                    else:
                        self._sensor_minmax[key] = [val, val]
                    mm = self._sensor_minmax[key]
                    lbl.setToolTip(
                        f"Min: {fmt_sensor_value(stype, mm[0])}  |  "
                        f"Max: {fmt_sensor_value(stype, mm[1])}"
                    )

                if prev_type in _SENSOR_SPARK_COLORS:
                    _sp_max_s = get_config().sparkline_max_samples
                    spark_row: QHBoxLayout | None = None
                    count_in_row = 0
                    for entry in current_entries:
                        name = entry.get("Name", "N/A")
                        val = entry.get("Value", 0.0)
                        key = (source, prev_type, name)
                        sp = _Sparkline(
                            max_samples=_sp_max_s,
                            color=_SENSOR_SPARK_COLORS[prev_type],
                            label=name)
                        sp.setMinimumHeight(50)
                        if key in self._sensor_spark_data:
                            sp.set_samples(self._sensor_spark_data[key])
                        sp.add_sample(val)
                        self._sensor_sparklines[key] = sp
                        if spark_row is None:
                            spark_row = QHBoxLayout()
                        spark_row.addWidget(sp)
                        count_in_row += 1
                        if count_in_row >= 2:
                            tab_layout.insertLayout(
                                tab_layout.count() - 1, spark_row)
                            spark_row = None
                            count_in_row = 0
                    if spark_row is not None and count_in_row > 0:
                        tab_layout.insertLayout(
                            tab_layout.count() - 1, spark_row)

            for e in comp_entries:
                stype = e.get("Type", "")
                name = e.get("Name", "N/A")
                val = e.get("Value", 0.0)
                val_str = fmt_sensor_value(stype, val)

                if stype != prev_type:
                    _flush_card()
                    current_rows = []
                    current_entries = []
                    prev_type = stype

                current_rows.append((name, val_str))
                current_entries.append(e)

            _flush_card()

            self._sensor_tabs.addTab(scroll, tab_label)

        layout.addWidget(self._sensor_tabs)

    def _populate_network(self) -> None:
        layout: QVBoxLayout = self._pages[3].widget().layout()
        # Preserve selected sub-tab + scroll position across rebuilds (active
        # connections + DNS cache auto-refresh every 5s; without this the page
        # jumps back to the Adapters tab and scroll resets to top on each
        # refresh).
        prev_tab = -1
        prev_scroll = 0
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if isinstance(w, QTabWidget):
                prev_tab = w.currentIndex()
                tab_content = w.widget(prev_tab)
                if isinstance(tab_content, QScrollArea):
                    inner = tab_content.widget()
                    if inner and inner.layout():
                        for j in range(inner.layout().count()):
                            child = inner.layout().itemAt(j).widget()
                            if isinstance(child, QTableWidget):
                                prev_scroll = (
                                    child.verticalScrollBar().value())
                                break
                    if prev_scroll == 0:
                        prev_scroll = (
                            tab_content.verticalScrollBar().value())
                break
        self._clear_layout(layout)
        page_idx = 3
        data = self.collector.data
        nets = data.net_info

        tabs = QTabWidget()
        tabs.setObjectName("software-tabs")

        # -- Adapters tab -- #
        scroll1 = QScrollArea()
        scroll1.setWidgetResizable(True)
        scroll1.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll1.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        c1 = QWidget()
        t1 = QVBoxLayout(c1)
        t1.setContentsMargins(0, 0, 8, 0)
        t1.setSpacing(10)
        scroll1.setWidget(c1)

        if nets:
            for a in nets:
                self._make_card(t1, a.get("Name", "N/A"), [
                    ("Description", a.get("Description", "N/A")),
                    ("MAC Address", a.get("MAC", "N/A")),
                    ("Status", a.get("Status", "N/A")),
                    ("Link Speed", a.get("Link Speed", "N/A")),
                    ("IPv4 Address", ", ".join(a.get("IPv4", [])) or "N/A"),
                    ("IPv6 Address", ", ".join(a.get("IPv6", [])) or "N/A"),
                    ("Default Gateway", a.get("Gateway", "N/A")),
                    ("DNS Servers", a.get("DNS Servers", "N/A")),
                    ("Bytes Sent", a.get("Bytes Sent", "N/A")),
                    ("Bytes Received", a.get("Bytes Received", "N/A")),
                ], page_idx)
        else:
            self._make_card(t1, "Network Adapters",
                            [("Adapters", "None detected")], page_idx)

        sp_net_up = _Sparkline(max_samples=get_config().sparkline_max_samples,
                               color="#60cdff", label="Upload KB/s")
        sp_net_down = _Sparkline(max_samples=get_config().sparkline_max_samples,
                                 color="#90ee90", label="Download KB/s")
        sp_net_up.set_samples(self._net_spark_up)
        sp_net_down.set_samples(self._net_spark_down)
        graph_row_net = QHBoxLayout()
        graph_row_net.addWidget(sp_net_up)
        graph_row_net.addWidget(sp_net_down)
        t1.addLayout(graph_row_net)
        self._sparklines["net_up"] = sp_net_up
        self._sparklines["net_down"] = sp_net_down

        vpn = data.vpn_status
        vpn_rows: list[tuple[str, str]] = []
        vpn_rows.append(("VPN Active", "Yes" if vpn.get("Active") else "No"))
        conns = vpn.get("Connections", [])
        if conns:
            for c in conns:
                vpn_rows.append((
                    f"  {c.get('Adapter', 'VPN')}",
                    f"{c.get('Status', 'N/A')} (matched: {c.get('Matched', 'N/A')})"
                ))
        else:
            vpn_rows.append(("Connections", "None detected"))
        self._make_card(t1, "VPN Status", vpn_rows, page_idx)

        tabs.addTab(scroll1, "Adapters")

        # -- Active Connections tab -- #
        scroll2 = QScrollArea()
        scroll2.setWidgetResizable(True)
        scroll2.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll2.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        c2 = QWidget()
        t2 = QVBoxLayout(c2)
        t2.setContentsMargins(0, 0, 8, 0)
        t2.setSpacing(10)
        scroll2.setWidget(c2)

        conns_list = data.active_connections
        if conns_list:
            MAX_CONN_ROWS = 200
            shown_conns = conns_list[:MAX_CONN_ROWS]
            conn_table = QTableWidget(len(shown_conns), 6)
            conn_table.setObjectName("device-table")
            conn_table.setAlternatingRowColors(True)
            conn_table.setSelectionBehavior(
                QTableWidget.SelectionBehavior.SelectRows)
            conn_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            conn_table.verticalHeader().setVisible(False)
            conn_table.verticalHeader().setDefaultSectionSize(26)
            conn_table.setWordWrap(False)
            conn_table.setHorizontalHeaderLabels(
                ["Protocol", "Local Address", "Remote Address",
                 "State", "PID", "Process"])
            for i, c in enumerate(shown_conns):
                conn_table.setItem(i, 0, QTableWidgetItem(c.get("Protocol", "")))
                conn_table.setItem(i, 1, QTableWidgetItem(c.get("Local Address", "")))
                conn_table.setItem(i, 2, QTableWidgetItem(c.get("Remote Address", "")))
                state_item = _SelBlackItem(c.get("State", ""))
                conn_table.setItem(i, 3, state_item)
                conn_table.setItem(i, 4, QTableWidgetItem(c.get("PID", "")))
                conn_table.setItem(i, 5, QTableWidgetItem(c.get("Process", "")))
                state = c.get("State", "")
                if state == "ESTABLISHED":
                    state_item.setForeground(QColor(_GREEN))
                elif state in ("LISTEN", "BOUND"):
                    state_item.setForeground(QColor(_YELLOW))
                elif state in ("CLOSE_WAIT", "TIME_WAIT", "FIN_WAIT1",
                               "FIN_WAIT2", "CLOSING"):
                    state_item.setForeground(QColor(_RED))
            conn_table.setSortingEnabled(True)
            hdr = conn_table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
            self._setup_table_copy(conn_table)
            t2.addWidget(conn_table)
            if len(conns_list) > MAX_CONN_ROWS:
                cap_label = QLabel(
                    f"Showing {MAX_CONN_ROWS} of {len(conns_list)} connections")
                cap_label.setObjectName("update-status")
                t2.addWidget(cap_label)
        else:
            self._make_card(t2, "Active Connections",
                            [("Status", "No active connections found")], -1)
        tabs.addTab(scroll2, f"Connections ({len(conns_list)})")

        # -- Wi-Fi tab -- #
        scroll3 = QScrollArea()
        scroll3.setWidgetResizable(True)
        scroll3.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll3.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        c3 = QWidget()
        t3 = QVBoxLayout(c3)
        t3.setContentsMargins(0, 0, 8, 0)
        t3.setSpacing(10)
        scroll3.setWidget(c3)

        wifi = data.wifi_info
        if wifi:
            wifi_rows = [
                ("Name", wifi.get("Name", "N/A")),
                ("Description", wifi.get("Description", "N/A")),
                ("SSID", wifi.get("SSID", "N/A")),
                ("State", wifi.get("State", "N/A")),
                ("MAC", wifi.get("MAC", "N/A")),
                ("BSSID", wifi.get("BSSID", "N/A")),
                ("Standard", wifi.get("Standard", "N/A")),
                ("Band", wifi.get("Band", "N/A")),
                ("Channel", wifi.get("Channel", "N/A")),
                ("Signal", wifi.get("Signal", "N/A")),
                ("Authentication", wifi.get("Authentication", "N/A")),
                ("Cipher", wifi.get("Cipher", "N/A")),
                ("Receive Rate", wifi.get("Receive Rate", "N/A")),
                ("Transmit Rate", wifi.get("Transmit Rate", "N/A")),
            ]
            self._make_card(t3, "Wi-Fi Adapter", wifi_rows, page_idx)
        else:
            self._make_card(t3, "Wi-Fi Adapter",
                            [("Status", "No Wi-Fi adapter connected")], -1)
        tabs.addTab(scroll3, "Wi-Fi")

        # -- DNS Cache tab -- #
        scroll4 = QScrollArea()
        scroll4.setWidgetResizable(True)
        scroll4.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll4.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        c4 = QWidget()
        t4 = QVBoxLayout(c4)
        t4.setContentsMargins(0, 0, 8, 0)
        t4.setSpacing(10)
        scroll4.setWidget(c4)

        dns = data.dns_cache
        if dns:
            dns_table = QTableWidget(len(dns), 5)
            dns_table.setObjectName("device-table")
            dns_table.setAlternatingRowColors(True)
            dns_table.setSelectionBehavior(
                QTableWidget.SelectionBehavior.SelectRows)
            dns_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            dns_table.verticalHeader().setVisible(False)
            dns_table.verticalHeader().setDefaultSectionSize(26)
            dns_table.setWordWrap(False)
            dns_table.setHorizontalHeaderLabels(
                ["Record Name", "Type", "TTL", "Section", "Address"])
            for i, d in enumerate(dns):
                dns_table.setItem(i, 0, QTableWidgetItem(d.get("Record Name", "")))
                dns_table.setItem(i, 1, QTableWidgetItem(d.get("Type", "")))
                _ttl_str = d.get("TTL", "")
                try:
                    _ttl_val = int(_ttl_str)
                except (ValueError, TypeError):
                    _ttl_val = 0
                dns_table.setItem(i, 2, _NumericItem(str(_ttl_str), _ttl_val))
                dns_table.setItem(i, 3, QTableWidgetItem(d.get("Section", "")))
                dns_table.setItem(i, 4, QTableWidgetItem(d.get("Address", "")))
            hdr = dns_table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            dns_table.setSortingEnabled(True)
            self._setup_table_copy(dns_table)
            t4.addWidget(dns_table)
        else:
            self._make_card(t4, "DNS Cache",
                            [("Status", "No DNS cache entries found")], -1)
        tabs.addTab(scroll4, f"DNS Cache ({len(dns)})")

        if prev_tab >= 0:
            tabs.setCurrentIndex(min(prev_tab, tabs.count() - 1))
        layout.addWidget(tabs)

        if prev_scroll > 0:
            from PySide6.QtCore import QTimer

            def _restore_scroll():
                idx = tabs.currentIndex()
                if idx < 0:
                    return
                tab_content = tabs.widget(idx)
                if not isinstance(tab_content, QScrollArea):
                    return
                inner = tab_content.widget()
                if not inner or not inner.layout():
                    return
                for j in range(inner.layout().count()):
                    child = inner.layout().itemAt(j).widget()
                    if isinstance(child, QTableWidget):
                        child.verticalScrollBar().setValue(prev_scroll)
                        return
                tab_content.verticalScrollBar().setValue(prev_scroll)

            QTimer.singleShot(0, _restore_scroll)

    def _populate_ip(self) -> None:
        layout: QVBoxLayout = self._pages[4].widget().layout()
        self._clear_layout(layout)
        data = self.collector.data
        page_idx = 4
        if data.ext_ip_error:
            self._make_card(layout, "External (Public) IP", [
                ("Error", data.ext_ip_error),
                ("Last Checked", data.ext_ip_time or "N/A"),
            ], page_idx)
        else:
            rows: list[tuple[str, str]] = []
            for k in ["IP", "Hostname", "ISP / Organization", "Country",
                      "Region", "City", "Timezone", "Coordinates"]:
                if k in data.ext_ip_info:
                    rows.append((k, data.ext_ip_info[k]))
            rows.append(("Last Checked", data.ext_ip_time or "N/A"))
            self._make_card(layout, "External (Public) IP", rows, page_idx)

    def _populate_processes(self) -> None:
        layout: QVBoxLayout = self._pages[5].widget().layout()
        prev_tab = -1
        prev_scroll = 0
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if isinstance(w, QTabWidget):
                prev_tab = w.currentIndex()
                # Find scroll position of current tab's table/tree
                tab_content = w.widget(prev_tab)
                if tab_content and tab_content.layout():
                    for j in range(tab_content.layout().count()):
                        child = tab_content.layout().itemAt(j).widget()
                        if isinstance(child, (QTableWidget, QTreeWidget)):
                            prev_scroll = child.verticalScrollBar().value()
                            break
                break
        self._clear_layout(layout)
        procs = self.collector.data.processes
        if not procs:
            self._make_card(layout, "Processes", [
                ("Status", "No process data"),
            ], -1)
            layout.addStretch()
            return

        tabs = QTabWidget()
        tabs.setObjectName("software-tabs")

        # Lazy tab construction: only build the currently-visible tab to
        # avoid wasting ~40-80ms per 5s refresh building the invisible one.
        # When the user switches tabs, currentChanged triggers a full
        # rebuild which constructs the newly-visible tab.
        visible_tab = max(prev_tab, 0)

        # Thresholds for smart colorization (per-column) — read from config
        # Returns (red, orange) thresholds; above red = critical, above orange = warning
        _cfg = get_config()
        _THRESHOLDS = {
            "cpu": (_cfg.cpu_crit_threshold, _cfg.cpu_warn_threshold),
            "mem": (_cfg.mem_crit_threshold, _cfg.mem_warn_threshold),
            "disk": (_cfg.disk_crit_threshold, _cfg.disk_warn_threshold),
            "net": (_cfg.net_crit_threshold, _cfg.net_warn_threshold),
        }

        def _color_for(value: float, key: str) -> QColor | None:
            """Return a QColor based on smart thresholds, or None for normal."""
            red, orange = _THRESHOLDS[key]
            if value >= red:
                return QColor("#ef4444")   # red
            if value >= orange:
                return QColor("#f59e0b")   # amber/orange
            return None

        def _colorize_item(item, value: float, key: str) -> None:
            c = _color_for(value, key)
            if c is not None:
                item.setForeground(c)

        # -- Table view tab -- #
        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table = QTableWidget(len(procs), 6)
        table.setObjectName("proc-table")
        table.setHorizontalHeaderLabels(
            ["PID", "Name", "CPU %", "Memory", "Disk", "Network"])
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(False)

        # Lazy row population: only fill rows when the table is visible.
        # The per-row setItem loop creates ~1200 QTableWidgetItems for 200
        # processes — this is the expensive part, not the table setup.
        if visible_tab == 0:
            for i, p in enumerate(procs):
                table.setItem(i, 0, _NumericItem(str(p.get("PID", 0)), p.get("PID", 0)))
                table.setItem(i, 1, _SelBlackItem(p.get("Name", "N/A")))

                cpu_val = p.get("CPU %", 0.0)
                cpu_item = _NumericItem(f"{cpu_val:.1f}%", cpu_val)
                _colorize_item(cpu_item, cpu_val, "cpu")
                table.setItem(i, 2, cpu_item)

                mem_mb = p.get("Memory (MB)", 0)
                mem_item = _NumericItem(
                    f"{mem_mb:.1f} MB" if mem_mb else "N/A", mem_mb)
                _colorize_item(mem_item, mem_mb, "mem")
                table.setItem(i, 3, mem_item)

                disk_kb = p.get("Disk (KB/s)", 0)
                disk_item = _NumericItem(
                    f"{disk_kb:.1f} KB/s" if disk_kb else "0 KB/s", disk_kb)
                _colorize_item(disk_item, disk_kb, "disk")
                table.setItem(i, 4, disk_item)

                net_n = p.get("Network", 0)
                net_item = _NumericItem(
                    f"{net_n} conn" if net_n else "—", net_n)
                _colorize_item(net_item, net_n, "net")
                table.setItem(i, 5, net_item)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        table.setSortingEnabled(True)
        table.sortByColumn(2, Qt.SortOrder.DescendingOrder)
        self._setup_table_copy(table)
        table_layout.addWidget(table)

        count_label = QLabel(f"Top {len(procs)} processes by CPU usage  ·  "
                             f"red = critical  ·  orange = high")
        count_label.setObjectName("update-status")
        table_layout.addWidget(count_label)
        tabs.addTab(table_page, "List View")

        # -- Tree view tab -- #
        tree_page = QWidget()
        tree_layout = QVBoxLayout(tree_page)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree = QTreeWidget()
        tree.setObjectName("device-table")
        tree.setAlternatingRowColors(True)
        tree.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        tree.setHeaderLabels(["PID", "Name", "CPU %", "Memory", "Disk", "Network"])
        tree.setSortingEnabled(False)

        # Lazy item population: only build tree items when the tree tab is
        # visible. The recursive _add_children traversal + QTreeWidgetItem
        # creation for ~200 processes is the expensive part.
        if visible_tab == 1:
            proc_by_pid: dict[int, dict] = {}
            children_map: dict[int | None, list[dict]] = {}
            for p in procs:
                pid = p.get("PID")
                if pid is None:
                    continue
                proc_by_pid[pid] = p
            for p in procs:
                ppid = p.get("PPID")
                children_map.setdefault(ppid, []).append(p)

            def _make_tree_item(p: dict) -> QTreeWidgetItem:
                cpu_val = p.get("CPU %", 0.0)
                mem_mb = p.get("Memory (MB)", 0)
                disk_kb = p.get("Disk (KB/s)", 0)
                net_n = p.get("Network", 0)
                item = QTreeWidgetItem([
                    str(p.get("PID", 0)),
                    p.get("Name", "N/A"),
                    f"{cpu_val:.1f}%",
                    f"{mem_mb:.1f} MB" if mem_mb else "N/A",
                    f"{disk_kb:.1f} KB/s" if disk_kb else "0 KB/s",
                    f"{net_n} conn" if net_n else "—",
                ])
                for col, (val, key) in enumerate([
                    (cpu_val, "cpu"), (mem_mb, "mem"),
                    (disk_kb, "disk"), (net_n, "net"),
                ], start=2):
                    c = _color_for(val, key)
                    if c is not None:
                        item.setForeground(col, c)
                return item

            def _add_children(parent_item, parent_pid: int | None):
                kids = children_map.get(parent_pid, [])
                kids.sort(key=lambda x: x.get("Name", "").lower())
                for kid in kids:
                    child_item = _make_tree_item(kid)
                    parent_item.addChild(child_item)
                    _add_children(child_item, kid.get("PID"))

            # Root items: processes whose PPID is None or whose PPID is
            # not in the collected set (orphaned — e.g. PPID=0 for the
            # System Idle Process, which psutil doesn't return).
            root_items = [p for p in procs
                          if p.get("PPID") is None
                          or p.get("PPID") not in proc_by_pid]
            root_items.sort(key=lambda x: x.get("Name", "").lower())
            for r in root_items:
                top_item = _make_tree_item(r)
                tree.addTopLevelItem(top_item)
                _add_children(top_item, r.get("PID"))

            tree.expandToDepth(0)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        tree_layout.addWidget(tree)

        tree_count = QLabel(f"{len(procs)} processes (tree grouped by parent PID)  ·  "
                            f"red = critical  ·  orange = high")
        tree_count.setObjectName("update-status")
        tree_layout.addWidget(tree_count)
        tabs.addTab(tree_page, "Tree View")

        # Block signals during tab restoration so currentChanged doesn't
        # trigger a redundant rebuild.
        tabs.blockSignals(True)
        if prev_tab >= 0:
            tabs.setCurrentIndex(min(prev_tab, tabs.count() - 1))
        tabs.blockSignals(False)

        # When the user switches tabs, rebuild the page so the newly-
        # visible tab gets its rows populated.  The _process_tab_rebuilding
        # guard prevents infinite recursion: during the rebuild, this
        # handler fires again (from setCurrentIndex above, which is now
        # blocked, or from Qt internals) and returns immediately.
        def _on_proc_tab_changed(_idx: int) -> None:
            if self._process_tab_rebuilding:
                return
            self._process_tab_rebuilding = True
            try:
                self._populate_processes()
            finally:
                self._process_tab_rebuilding = False
        tabs.currentChanged.connect(_on_proc_tab_changed)

        layout.addWidget(tabs)
        if prev_scroll > 0:
            from PySide6.QtCore import QTimer
            def _restore_scroll():
                idx = tabs.currentIndex()
                if idx < 0:
                    return
                tab_content = tabs.widget(idx)
                if not (tab_content and tab_content.layout()):
                    return
                for j in range(tab_content.layout().count()):
                    child = tab_content.layout().itemAt(j).widget()
                    if isinstance(child, (QTableWidget, QTreeWidget)):
                        child.verticalScrollBar().setValue(prev_scroll)
                        break
            QTimer.singleShot(0, _restore_scroll)

    def _populate_software(self) -> None:
        page_container = self._pages[6].widget()
        layout: QVBoxLayout = page_container.layout()
        self._clear_layout(layout)
        self._pages[6].setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        tabs = QTabWidget()
        tabs.setObjectName("software-tabs")
        tabs.tabBar().setObjectName("software-tabbar")

        # -- Startup programs tab -- #
        startup = self.collector.data.startup_programs
        scroll1 = QScrollArea()
        scroll1.setWidgetResizable(True)
        scroll1.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll1.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        c1 = QWidget()
        t1 = QVBoxLayout(c1)
        t1.setContentsMargins(0, 0, 8, 0)
        t1.setSpacing(10)
        t1.addStretch()
        scroll1.setWidget(c1)

        if startup:
            st_rows = [(p.get("Name", "N/A"), f"{p.get('Command', 'N/A')}  [{p.get('Source', 'N/A')}]")
                       for p in startup]
            self._make_card(t1, "Startup Programs", st_rows, 6)
        else:
            self._make_card(t1, "Startup Programs",
                            [("Status", "No startup programs found")], -1)
        tabs.addTab(scroll1, f"Startup ({len(startup)})")

        # -- Installed programs tab -- #
        installed = self.collector.data.installed_programs
        scroll2 = QScrollArea()
        scroll2.setWidgetResizable(True)
        scroll2.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll2.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        c2 = QWidget()
        t2 = QVBoxLayout(c2)
        t2.setContentsMargins(0, 0, 8, 0)
        t2.setSpacing(10)
        scroll2.setWidget(c2)

        if installed:
            table = QTableWidget(len(installed), 4)
            table.setObjectName("installed-table")
            table.setHorizontalHeaderLabels(
                ["Name", "Version", "Publisher", "Install Date"])
            table.setAlternatingRowColors(True)
            table.setSelectionBehavior(
                QTableWidget.SelectionBehavior.SelectRows)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.verticalHeader().setVisible(False)

            for i, prog in enumerate(installed):
                table.setItem(i, 0, QTableWidgetItem(prog.get("Name", "N/A")))
                table.setItem(i, 1, QTableWidgetItem(prog.get("Version", "N/A")))
                table.setItem(i, 2, QTableWidgetItem(prog.get("Publisher", "N/A")))
                table.setItem(i, 3, QTableWidgetItem(prog.get("Install Date", "N/A")))

            table.setSortingEnabled(True)

            header = table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            self._setup_table_copy(table)
            t2.addWidget(table)
        else:
            self._make_card(t2, "Installed Programs",
                            [("Status", "No installed programs found")], -1)
        tabs.addTab(scroll2, f"Installed ({len(installed)})")

        # -- Services tab -- #
        services = self.collector.data.services_info
        scroll3 = QScrollArea()
        scroll3.setWidgetResizable(True)
        scroll3.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll3.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        c3 = QWidget()
        t3 = QVBoxLayout(c3)
        t3.setContentsMargins(0, 0, 8, 0)
        t3.setSpacing(10)
        scroll3.setWidget(c3)

        if services:
            svc_table = QTableWidget(len(services), 5)
            svc_table.setObjectName("device-table")
            svc_table.setAlternatingRowColors(True)
            svc_table.setSelectionBehavior(
                QTableWidget.SelectionBehavior.SelectRows)
            svc_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            svc_table.verticalHeader().setVisible(False)
            svc_table.verticalHeader().setDefaultSectionSize(26)
            svc_table.setWordWrap(False)
            svc_table.setHorizontalHeaderLabels(
                ["Name", "Display Name", "State", "Start Type", "Log On As"])
            for i, svc in enumerate(services):
                svc_table.setItem(i, 0, QTableWidgetItem(svc.get("Name", "")))
                svc_table.setItem(i, 1, QTableWidgetItem(svc.get("Display Name", "")))
                state_item = _SelBlackItem(svc.get("State", ""))
                svc_table.setItem(i, 2, state_item)
                svc_table.setItem(i, 3, QTableWidgetItem(svc.get("Start Type", "")))
                svc_table.setItem(i, 4, QTableWidgetItem(svc.get("Log On As", "")))
                # Color-code State
                if state_item:
                    state = svc.get("State", "")
                    if state == "Running":
                        state_item.setForeground(QColor(_GREEN))
                    elif state == "Stopped":
                        state_item.setForeground(QColor(_RED))
                    else:
                        state_item.setForeground(QColor(_YELLOW))
            svc_table.setSortingEnabled(True)
            hdr = svc_table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            self._setup_table_copy(svc_table)
            t3.addWidget(svc_table)
        else:
            self._make_card(t3, "Windows Services",
                            [("Status", "No services found")], -1)
        tabs.addTab(scroll3, f"Services ({len(services)})")

        # -- Startup Impact tab -- #
        scroll4 = QScrollArea()
        scroll4.setWidgetResizable(True)
        scroll4.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll4.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        c4 = QWidget()
        t4 = QVBoxLayout(c4)
        t4.setContentsMargins(0, 0, 8, 0)
        t4.setSpacing(10)
        scroll4.setWidget(c4)

        impact = self.collector.data.startup_impact
        if impact:
            self._make_card(t4, "Boot Performance", [
                ("Last Boot Duration", f"{impact.get('Last Boot Duration (s)', 'N/A')} s"),
                ("Startup Programs Count", str(impact.get("Startup Programs Count", 0))),
            ], -1)

            boot_history = impact.get("Boot History", [])
            if boot_history:
                bh_table = QTableWidget(len(boot_history), 2)
                bh_table.setObjectName("device-table")
                bh_table.setAlternatingRowColors(True)
                bh_table.setSelectionBehavior(
                    QTableWidget.SelectionBehavior.SelectRows)
                bh_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                bh_table.verticalHeader().setVisible(False)
                bh_table.verticalHeader().setDefaultSectionSize(26)
                bh_table.setWordWrap(False)
                bh_table.setHorizontalHeaderLabels(
                    ["Boot Time", "Duration (s)"])
                for i, bh in enumerate(boot_history):
                    bh_table.setItem(i, 0, QTableWidgetItem(
                        bh.get("Boot Time", "")))
                    dur = bh.get("Duration (s)", "")
                    try:
                        dval = float(dur)
                    except (ValueError, TypeError):
                        dval = 0.0
                    dur_item = _NumericItem(dur, dval)
                    bh_table.setItem(i, 1, dur_item)
                    if dval > 120:
                        dur_item.setForeground(QColor(_RED))
                    elif dval > 60:
                        dur_item.setForeground(QColor(_YELLOW))
                    else:
                        dur_item.setForeground(QColor(_GREEN))
                hdr = bh_table.horizontalHeader()
                hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
                bh_table.setSortingEnabled(True)
                self._setup_table_copy(bh_table)
                t4.addWidget(bh_table)

            top_startup = impact.get("Top Startup Programs", [])
            if top_startup:
                su_table = QTableWidget(len(top_startup), 3)
                su_table.setObjectName("device-table")
                su_table.setAlternatingRowColors(True)
                su_table.setSelectionBehavior(
                    QTableWidget.SelectionBehavior.SelectRows)
                su_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                su_table.verticalHeader().setVisible(False)
                su_table.verticalHeader().setDefaultSectionSize(26)
                su_table.setWordWrap(False)
                su_table.setHorizontalHeaderLabels(
                    ["Name", "Source", "Command"])
                for i, sp in enumerate(top_startup):
                    su_table.setItem(i, 0, QTableWidgetItem(
                        sp.get("Name", "")))
                    su_table.setItem(i, 1, QTableWidgetItem(
                        sp.get("Source", "")))
                    su_table.setItem(i, 2, QTableWidgetItem(
                        sp.get("Command", "")))
                hdr = su_table.horizontalHeader()
                hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
                hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
                hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
                su_table.setSortingEnabled(True)
                self._setup_table_copy(su_table)
                t4.addWidget(su_table)
        else:
            self._make_card(t4, "Startup Impact",
                            [("Status", "No startup impact data")], -1)
        tabs.addTab(scroll4, "Startup Impact")

        layout.addWidget(tabs)

    def _populate_updates(self) -> None:
        layout: QVBoxLayout = self._pages[7].widget().layout()
        self._clear_layout(layout)
        updates = self.collector.data.update_history
        if not updates:
            self._make_card(layout, "Windows Updates", [
                ("Status", "No updates found"),
            ], -1)
            layout.addStretch()
            return

        table = QTableWidget(len(updates), 4)
        table.setObjectName("updates-table")
        table.setHorizontalHeaderLabels(
            ["KB", "Description", "Installed On", "Installed By"])
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)

        for i, u in enumerate(updates):
            table.setItem(i, 0, QTableWidgetItem(u.get("KB", "N/A")))
            table.setItem(i, 1, QTableWidgetItem(u.get("Description", "N/A")))
            table.setItem(i, 2, QTableWidgetItem(u.get("Installed On", "N/A")))
            table.setItem(i, 3, QTableWidgetItem(u.get("Installed By", "N/A")))

        table.setSortingEnabled(True)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self._setup_table_copy(table)
        layout.addWidget(table)

        count_label = QLabel(f"{len(updates)} updates installed")
        count_label.setObjectName("update-status")
        layout.addWidget(count_label)

    def _populate_health(self) -> None:
        layout: QVBoxLayout = self._pages[8].widget().layout()
        self._clear_layout(layout)
        health = self.collector.data.health_info
        page_idx = 8
        # Insert the bottom stretch BEFORE any _make_card call so the
        # insertWidget(count-1, card) logic in _make_card places each new
        # card just above the stretch (preserving caller-declared order).
        # Without this, cards are inserted before the LAST card (which is
        # the previous card, not a stretch), reversing the order.
        layout.addStretch()

        # -- Disk SMART -- #
        disk_smart = health.get("disk_smart", [])
        if disk_smart:
            smart_rows = [
                (d.get("Model", "N/A"),
                 f"Status: {d.get('Status', 'N/A')}  |  Health: {d.get('Health', 'N/A')}  |  "
                 f"Size: {d.get('Size', 'N/A')}")
                for d in disk_smart
            ]
            self._make_card(layout, "Disk Health (S.M.A.R.T.)",
                            smart_rows, page_idx)
        else:
            self._make_card(layout, "Disk Health (S.M.A.R.T.)",
                            [("Status", "No disk health data available")],
                            page_idx)

        # -- Windows Defender -- #
        defender = health.get("defender", {})
        if defender.get("Available"):
            def_rows = [
                ("Product", defender.get("Product", "N/A")),
                ("Real-time Protection",
                 defender.get("Real-time Protection", "N/A")),
                ("Antivirus", defender.get("Antivirus Enabled", "N/A")),
                ("Antispyware", defender.get("Antispyware Enabled", "N/A")),
                ("Signature Age", defender.get("Signature Age", "N/A")),
                ("Last Quick Scan", defender.get("Last Quick Scan", "N/A")),
                ("Last Full Scan", defender.get("Last Full Scan", "N/A")),
            ]
            if "Enabled" in defender:
                def_rows.insert(1, ("Enabled", defender["Enabled"]))
        else:
            def_rows = [("Status", "Windows Defender not available")]
        self._make_card(layout, "Windows Defender", def_rows, page_idx)

        # -- Firewall -- #
        firewall = health.get("firewall", [])
        if firewall:
            fw_rows = [(f.get("Profile", "N/A"), f.get("Status", "N/A")) for f in firewall]
        else:
            fw_rows = [("Status", "No firewall data available")]
        self._make_card(layout, "Firewall Status", fw_rows, page_idx)

        # -- Windows Activation -- #
        activation = health.get("activation", {})
        if activation.get("Available"):
            act_rows = [
                ("Status", activation.get("Status", "N/A")),
                ("Edition", activation.get("Edition", "N/A")),
                ("Product Key", activation.get("Product Key", "N/A")),
                ("Grace Period (days)",
                 activation.get("Grace Period (days)", "N/A")),
            ]
        else:
            act_rows = [("Status", activation.get("Status",
                        "Activation info not available"))]
        self._make_card(layout, "Windows Activation", act_rows, page_idx)

    def _populate_speed_test(self) -> None:
        layout: QVBoxLayout = self._pages[9].widget().layout()
        self._clear_layout(layout)

        self._speed_test_btn = QPushButton("Run Speed Test")
        self._speed_test_btn.setObjectName("action-btn")
        self._speed_test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._speed_test_btn.clicked.connect(self._on_speed_test_clicked)
        if self._speed_testing:
            self._speed_test_btn.setEnabled(False)
            self._speed_test_btn.setText("Testing...")
        layout.addWidget(self._speed_test_btn)

        self._speed_test_status = QLabel(
            "Testing..." if self._speed_testing
            else "Click button to run a speed test")
        self._speed_test_status.setObjectName("update-status")
        layout.addWidget(self._speed_test_status)

        result = self.collector.data.speed_test_result
        if result and (result.get("download_mbps") or result.get("upload_mbps")
                       or result.get("error")):
            # Server + user location card
            loc_rows: list[tuple[str, str]] = []
            if result.get("server_colo"):
                loc_rows.append(("Server (Cloudflare Colo)",
                                result["server_colo"]))
            if result.get("server_location"):
                loc_rows.append(("Server Location",
                                result["server_location"]))
            if result.get("user_location"):
                loc_rows.append(("Your Location",
                                result["user_location"]))
            if result.get("user_ip"):
                loc_rows.append(("Your IP", result["user_ip"]))
            if loc_rows:
                self._make_card(layout, "Test Server", loc_rows, 9)

            # Results card
            rows: list[tuple[str, str]] = []
            # Download section — always show if the test was attempted
            if result.get("download_bytes", 0) > 0:
                rows.append(("Download Speed",
                             f"{result['download_mbps']:.2f} Mbps"))
                rows.append(("Download Data",
                             f"{result.get('download_bytes', 0) / 1_000_000:.1f} MB"))
                rows.append(("Download Time",
                             f"{result.get('download_time_s', 0):.2f}s"))
            elif result.get("error"):
                rows.append(("Download Speed", "Failed"))
            # Upload section — always show if the test was attempted
            if result.get("upload_bytes", 0) > 0:
                rows.append(("Upload Speed",
                             f"{result['upload_mbps']:.2f} Mbps"))
                rows.append(("Upload Data",
                             f"{result.get('upload_bytes', 0) / 1_000_000:.1f} MB"))
                rows.append(("Upload Time",
                             f"{result.get('upload_time_s', 0):.2f}s"))
            elif result.get("error"):
                rows.append(("Upload Speed", "Failed"))
            if result.get("timestamp"):
                rows.append(("Test Run", result["timestamp"]))
            if result.get("error"):
                rows.append(("Error", result["error"]))
            self._make_card(layout, "Speed Test Results", rows, 9)
        else:
            self._make_card(layout, "Speed Test Results", [
                ("Status", "No test run yet"),
                ("Info", "Downloads 99 MB / uploads 50 MB via Cloudflare"),
                ("Server", "Closest Cloudflare data center (auto-detected)"),
            ], 9)

        # -- Bufferbloat test -- #
        self._bufferbloat_btn = QPushButton("Run Bufferbloat Test")
        self._bufferbloat_btn.setObjectName("action-btn")
        self._bufferbloat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bufferbloat_btn.clicked.connect(self._on_bufferbloat_clicked)
        if self._bufferbloat_testing:
            self._bufferbloat_btn.setEnabled(False)
            self._bufferbloat_btn.setText("Testing...")
        layout.addWidget(self._bufferbloat_btn)

        self._bufferbloat_status = QLabel(
            "Testing..." if self._bufferbloat_testing
            else "Measures latency increase under download/upload load")
        self._bufferbloat_status.setObjectName("update-status")
        layout.addWidget(self._bufferbloat_status)

        bb = self.collector.data.bufferbloat_result
        if bb and (bb.get("baseline_latency_ms") or bb.get("error")):
            bb_rows: list[tuple[str, str]] = []
            if bb.get("baseline_latency_ms"):
                bb_rows.append(("Baseline Latency",
                                f"{bb['baseline_latency_ms']:.1f} ms"))
                bb_rows.append(("Latency Under Download",
                                f"{bb['download_latency_ms']:.1f} ms"))
                bb_rows.append(("Download Bloat",
                                f"{bb['download_bloat_ms']:.1f} ms"))
                bb_rows.append(("Latency Under Upload",
                                f"{bb['upload_latency_ms']:.1f} ms"))
                bb_rows.append(("Upload Bloat",
                                f"{bb['upload_bloat_ms']:.1f} ms"))
                if bb.get("grade"):
                    bb_rows.append(("Grade", bb["grade"]))
            if bb.get("error"):
                bb_rows.append(("Error", bb["error"]))
            if bb.get("timestamp"):
                bb_rows.append(("Test Run", bb["timestamp"]))
            self._make_card(layout, "Bufferbloat Results", bb_rows, 9)
        else:
            self._make_card(layout, "Bufferbloat Results", [
                ("Status", "No test run yet"),
                ("Info", "Measures ping latency increase when the connection "
                         "is saturated with download/upload traffic"),
                ("Grading", "A (<30ms)  B (<60ms)  C (<100ms)  "
                            "D (<200ms)  F (>=200ms)"),
            ], 9)

        layout.addStretch()

    def _populate_devices(self) -> None:
        """Populate the Devices page with USB, Bluetooth, Printers, Audio sub-tabs."""
        page_container = self._pages[10].widget()
        layout: QVBoxLayout = page_container.layout()
        self._clear_layout(layout)
        page_idx = 10

        # Disable page-level scrolling — QTableWidget has its own scrollbar
        self._pages[10].setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        dev = self.collector.data.devices_info

        tabs = QTabWidget()
        tabs.setObjectName("hardware-tabs")
        tabs.tabBar().setObjectName("hardware-tabbar")

        def _new_tab_page() -> tuple[QWidget, QVBoxLayout]:
            """Plain container — no scroll area wrapper needed."""
            container = QWidget()
            tl = QVBoxLayout(container)
            tl.setContentsMargins(0, 0, 0, 0)
            tl.setSpacing(0)
            return container, tl

        # USB devices
        tab, tl = _new_tab_page()
        usb_list = dev.get("usb", [])
        if usb_list:
            self._make_device_table(tl, "USB Devices", usb_list, page_idx,
                                    ["Name", "Vendor ID", "Product ID",
                                     "Manufacturer", "Status", "Device ID"])
        else:
            self._make_card(tl, "USB Devices",
                            [("Status", "No USB devices detected")], page_idx)
        tabs.addTab(tab, f"USB ({len(usb_list)})")

        # Bluetooth devices
        tab, tl = _new_tab_page()
        bt_list = dev.get("bluetooth", [])
        if bt_list:
            self._make_device_table(tl, "Bluetooth Devices", bt_list, page_idx,
                                    ["Name", "Description", "Manufacturer",
                                     "Status", "Device ID"])
        else:
            self._make_card(tl, "Bluetooth Devices",
                            [("Status", "No Bluetooth devices detected")],
                            page_idx)
        tabs.addTab(tab, f"Bluetooth ({len(bt_list)})")

        # Printers
        tab, tl = _new_tab_page()
        prn_list = dev.get("printers", [])
        if prn_list:
            self._make_device_table(tl, "Printers", prn_list, page_idx,
                                    ["Name", "Driver", "Port", "Default",
                                     "Shared", "Status", "Print Processor"])
        else:
            self._make_card(tl, "Printers",
                            [("Status", "No printers installed")], page_idx)
        tabs.addTab(tab, f"Printers ({len(prn_list)})")

        # Audio devices
        tab, tl = _new_tab_page()
        aud_list = dev.get("audio", [])
        if aud_list:
            self._make_device_table(tl, "Audio Devices", aud_list, page_idx,
                                    ["Name", "Manufacturer", "ProductName",
                                     "Status", "Device ID"])
        else:
            self._make_card(tl, "Audio Devices",
                            [("Status", "No audio devices detected")],
                            page_idx)
        tabs.addTab(tab, f"Audio ({len(aud_list)})")

        # Drivers
        tab, tl = _new_tab_page()
        drv_list = self.collector.data.drivers_info
        if drv_list:
            self._make_device_table(tl, "Drivers", drv_list, page_idx,
                                    ["Device Name", "Driver Version",
                                     "Driver Date", "Provider",
                                     "Device Class"])
        else:
            self._make_card(tl, "Drivers",
                            [("Status", "No driver info available")], page_idx)
        tabs.addTab(tab, f"Drivers ({len(drv_list)})")

        # Tabs fill the entire page (stretch=1, no trailing stretch)
        layout.addWidget(tabs, 1)

    def _make_device_table(self, parent_layout: QVBoxLayout, title: str,
                           devices: list[dict], page_idx: int,
                           columns: list[str]) -> None:
        """Create a QTableWidget for device lists.

        All columns use Stretch mode so the table fills the available width
        without horizontal scrolling. Tooltips show the full untruncated text.
        The table fills its parent layout (stretch=1) and uses its built-in
        scrollbar for vertical overflow when there are many rows.
        """
        table = QTableWidget(len(devices), len(columns))
        table.setObjectName("device-table")
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(26)
        table.setWordWrap(False)
        table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        for col, header in enumerate(columns):
            table.setHorizontalHeaderItem(col, QTableWidgetItem(header))

        for row, dev in enumerate(devices):
            for col, key in enumerate(columns):
                val = dev.get(key, "N/A")
                if key == "Status" and val == "OK":
                    item = _SelBlackItem(str(val))
                    item.setForeground(QColor(_GREEN))
                elif key == "Status" and val not in ("OK", "N/A"):
                    item = _SelBlackItem(str(val))
                    item.setForeground(QColor(_YELLOW))
                else:
                    item = QTableWidgetItem(str(val))
                item.setToolTip(str(val))
                table.setItem(row, col, item)

        table.setSortingEnabled(True)

        # Resize columns to fit content; horizontal scrollbar appears only
        # when content exceeds viewport width (e.g. long Device IDs)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)

        # Index for search — only Name + Status to avoid index bloat
        # (was: rows × all_keys ≈ 600 entries/tab; now: rows × 2 ≈ 200/tab)
        if page_idx >= 0:
            for dev in devices:
                name = dev.get("Name", "Device")
                idx = len(self._search_items)
                self._search_items.append({
                    "page": str(page_idx),
                    "section": title,
                    "key": f"{name} Name",
                    "value": str(name),
                })
                self._search_items_by_page.setdefault(
                    page_idx, []).append(idx)
                status = dev.get("Status")
                if status is not None:
                    idx = len(self._search_items)
                    self._search_items.append({
                        "page": str(page_idx),
                        "section": title,
                        "key": f"{name} Status",
                        "value": str(status),
                    })
                    self._search_items_by_page.setdefault(
                        page_idx, []).append(idx)

        # Table fills the tab (stretch=1)
        self._setup_table_copy(table)
        parent_layout.addWidget(table, 1)

    def _populate_diagnostics(self) -> None:
        """Populate the Diagnostics page with Event Log, Power Plan, DirectX sub-tabs."""
        page_container = self._pages[11].widget()
        layout: QVBoxLayout = page_container.layout()
        self._clear_layout(layout)
        page_idx = 11

        # Disable page-level scrolling — tabs handle their own scrolling
        self._pages[11].setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        diag = self.collector.data.diagnostics_info

        tabs = QTabWidget()
        tabs.setObjectName("hardware-tabs")
        tabs.tabBar().setObjectName("hardware-tabbar")

        def _new_plain_tab() -> tuple[QWidget, QVBoxLayout]:
            """Plain container for tables — no scroll area wrapper."""
            container = QWidget()
            tl = QVBoxLayout(container)
            tl.setContentsMargins(0, 0, 0, 0)
            tl.setSpacing(0)
            return container, tl

        def _new_scroll_tab() -> tuple[QScrollArea, QVBoxLayout]:
            """Scroll area for card-based tabs."""
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            container = QWidget()
            tl = QVBoxLayout(container)
            tl.setContentsMargins(0, 0, 8, 0)
            tl.setSpacing(10)
            tl.addStretch()
            scroll.setWidget(container)
            return scroll, tl

        # Event Log helper — builds a table tab for a list of events
        def _build_event_tab(events: list, title: str) -> None:
            tab, tl = _new_plain_tab()
            if events:
                MAX_EVENT_ROWS = 500
                shown = events[:MAX_EVENT_ROWS]
                table = QTableWidget(len(shown), 5)
                table.setObjectName("device-table")
                table.setAlternatingRowColors(True)
                table.setSelectionBehavior(
                    QTableWidget.SelectionBehavior.SelectRows)
                table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                table.verticalHeader().setVisible(False)
                table.verticalHeader().setDefaultSectionSize(26)
                table.setWordWrap(False)
                table.setHorizontalScrollBarPolicy(
                    Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                headers = ["Level", "Time", "Source", "Event ID", "Message"]
                for col, header_text in enumerate(headers):
                    table.setHorizontalHeaderItem(col, QTableWidgetItem(header_text))
                for row, evt in enumerate(shown):
                    vals = [evt.get("Level", ""),
                            evt.get("Time", ""), evt.get("Source", ""),
                            evt.get("Event ID", ""), evt.get("Message", "")]
                    for col, val in enumerate(vals):
                        if col == 0:  # Level column
                            if val == "Error":
                                item = _SelBlackItem(str(val))
                                item.setForeground(QColor(_RED))
                            elif val == "Warning":
                                item = _SelBlackItem(str(val))
                                item.setForeground(QColor(_YELLOW))
                            else:
                                item = QTableWidgetItem(str(val))
                        else:
                            item = QTableWidgetItem(str(val))
                        item.setToolTip(str(val))
                        table.setItem(row, col, item)
                table.setSortingEnabled(True)
                hdr = table.horizontalHeader()
                hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
                hdr.setStretchLastSection(True)
                self._setup_table_copy(table)
                tl.addWidget(table, 1)

                if len(events) > MAX_EVENT_ROWS:
                    cap_label = QLabel(
                        f"Showing {MAX_EVENT_ROWS} of {len(events)} entries "
                        f"(most recent)")
                    cap_label.setObjectName("update-status")
                    tl.addWidget(cap_label)

                # Index for search
                for evt in shown[:50]:
                    if page_idx >= 0:
                        idx = len(self._search_items)
                        self._search_items.append({
                            "page": str(page_idx),
                            "section": title,
                            "key": f"{evt.get('Source', 'Event')} {evt.get('Event ID', '')}",
                            "value": evt.get("Message", ""),
                        })
                        self._search_items_by_page.setdefault(
                            page_idx, []).append(idx)
            else:
                self._make_card(tl, title,
                                [("Status", "No recent errors/warnings")],
                                page_idx)
            tabs.addTab(tab, f"{title} ({len(events)})")

        _build_event_tab(diag.get("event_log_system", []), "System Events")
        _build_event_tab(diag.get("event_log_application", []),
                         "Application Events")

        # BSOD / Crash History — table + crash dump settings card
        scroll, tl = _new_scroll_tab()
        bsod_list = diag.get("bsod_history", [])
        if bsod_list:
            bsod_table = QTableWidget(len(bsod_list), 4)
            bsod_table.setObjectName("device-table")
            bsod_table.setAlternatingRowColors(True)
            bsod_table.setSelectionBehavior(
                QTableWidget.SelectionBehavior.SelectRows)
            bsod_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            bsod_table.verticalHeader().setVisible(False)
            bsod_table.verticalHeader().setDefaultSectionSize(26)
            bsod_table.setWordWrap(False)
            bsod_table.setHorizontalHeaderLabels(
                ["Time", "BugCheck Code", "Parameters", "Message"])
            for i, crash in enumerate(bsod_list):
                vals = [crash.get("Time", ""),
                        crash.get("BugCheck Code", ""),
                        crash.get("Parameters", ""),
                        crash.get("Message", "")]
                for col, val in enumerate(vals):
                    if col == 1:  # BugCheck Code column
                        if val and val not in ("(minidump file)",
                                               "(full dump)"):
                            item = _SelBlackItem(str(val))
                            item.setForeground(QColor(_RED))
                        else:
                            item = QTableWidgetItem(str(val))
                    else:
                        item = QTableWidgetItem(str(val))
                    item.setToolTip(str(val))
                    bsod_table.setItem(i, col, item)
            bsod_table.setSortingEnabled(True)
            hdr = bsod_table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
            self._setup_table_copy(bsod_table)
            tl.addWidget(bsod_table)
        else:
            self._make_card(tl, "BSOD / Crash History",
                            [("Status", "No crashes recorded")],
                            page_idx)

        # Crash dump settings card
        cd = diag.get("crash_dump_settings", {})
        if cd:
            cd_rows = [(k, str(v)) for k, v in cd.items()]
            self._make_card(tl, "Crash Dump Settings", cd_rows, page_idx)
        tabs.addTab(scroll, f"BSOD ({len(bsod_list)})")

        # Power Plan — scroll area with cards
        scroll, tl = _new_scroll_tab()
        pp = diag.get("power_plan", {})
        if pp:
            rows = [(k, str(v)) for k, v in pp.items()]
            self._make_card(tl, "Power Plan", rows, page_idx)
        else:
            self._make_card(tl, "Power Plan",
                            [("Status", "No power plan info available")],
                            page_idx)
        tabs.addTab(scroll, "Power Plan")

        # DirectX / OpenGL — scroll area with cards
        scroll, tl = _new_scroll_tab()
        dx = diag.get("directx", {})
        if dx:
            rows = [(k, str(v)) for k, v in dx.items()]
            self._make_card(tl, "DirectX / OpenGL / Vulkan", rows, page_idx)
        else:
            self._make_card(tl, "DirectX / OpenGL / Vulkan",
                            [("Status", "No graphics API info available")],
                            page_idx)
        tabs.addTab(scroll, "Graphics API")

        # System Restore Points — table
        tab, tl = _new_plain_tab()
        rp_list = diag.get("restore_points", [])
        if rp_list:
            rp_table = QTableWidget(len(rp_list), 3)
            rp_table.setObjectName("device-table")
            rp_table.setAlternatingRowColors(True)
            rp_table.setSelectionBehavior(
                QTableWidget.SelectionBehavior.SelectRows)
            rp_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            rp_table.verticalHeader().setVisible(False)
            rp_table.verticalHeader().setDefaultSectionSize(26)
            rp_table.setWordWrap(False)
            rp_table.setHorizontalHeaderLabels(
                ["Creation Time", "Description", "Sequence #"])
            for i, rp in enumerate(rp_list):
                rp_table.setItem(i, 0, QTableWidgetItem(rp.get("Creation Time", "")))
                rp_table.setItem(i, 1, QTableWidgetItem(rp.get("Description", "")))
                rp_table.setItem(i, 2, QTableWidgetItem(rp.get("Sequence #", "")))
            rp_table.setSortingEnabled(True)
            hdr = rp_table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            self._setup_table_copy(rp_table)
            tl.addWidget(rp_table, 1)
        else:
            self._make_card(tl, "System Restore Points",
                            [("Status", "No restore points found")],
                            page_idx)
        tabs.addTab(tab, f"Restore Points ({len(rp_list)})")

        # Environment Variables — table
        tab, tl = _new_plain_tab()
        env = diag.get("environment", {})
        if env:
            env_table = QTableWidget(len(env), 2)
            env_table.setObjectName("device-table")
            env_table.setAlternatingRowColors(True)
            env_table.setSelectionBehavior(
                QTableWidget.SelectionBehavior.SelectRows)
            env_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            env_table.verticalHeader().setVisible(False)
            env_table.verticalHeader().setDefaultSectionSize(26)
            env_table.setWordWrap(False)
            env_table.setHorizontalHeaderLabels(["Variable", "Value"])
            for i, (k, v) in enumerate(env.items()):
                item_k = QTableWidgetItem(k)
                item_v = QTableWidgetItem(str(v))
                item_v.setToolTip(str(v))
                env_table.setItem(i, 0, item_k)
                env_table.setItem(i, 1, item_v)
            env_table.setSortingEnabled(True)
            hdr = env_table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            self._setup_table_copy(env_table)
            tl.addWidget(env_table, 1)
        else:
            self._make_card(tl, "Environment Variables",
                            [("Status", "No environment variables found")],
                            page_idx)
        tabs.addTab(tab, f"Environment ({len(env)})")

        # PATH entries — table
        tab, tl = _new_plain_tab()
        path_list = diag.get("path_entries", [])
        if path_list:
            path_table = QTableWidget(len(path_list), 3)
            path_table.setObjectName("device-table")
            path_table.setAlternatingRowColors(True)
            path_table.setSelectionBehavior(
                QTableWidget.SelectionBehavior.SelectRows)
            path_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            path_table.verticalHeader().setVisible(False)
            path_table.verticalHeader().setDefaultSectionSize(26)
            path_table.setWordWrap(False)
            path_table.setHorizontalHeaderLabels(["Source", "#", "Path"])
            for i, pe in enumerate(path_list):
                _idx_str = pe.get("Index", "")
                try:
                    _idx_val = int(_idx_str)
                except (ValueError, TypeError):
                    _idx_val = 0
                item_idx = _NumericItem(str(_idx_str), _idx_val)
                item_path = QTableWidgetItem(pe.get("Path", ""))
                item_path.setToolTip(pe.get("Path", ""))
                # Color-code source
                item_src = _SelBlackItem(pe.get("Source", ""))
                src = pe.get("Source", "")
                if src == "System":
                    item_src.setForeground(QColor(_YELLOW))
                elif src == "User":
                    item_src.setForeground(QColor(_GREEN))
                path_table.setItem(i, 0, item_src)
                path_table.setItem(i, 1, item_idx)
                path_table.setItem(i, 2, item_path)
            hdr = path_table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            path_table.setSortingEnabled(True)
            self._setup_table_copy(path_table)
            tl.addWidget(path_table, 1)
        else:
            self._make_card(tl, "PATH Entries",
                            [("Status", "No PATH entries found")],
                            page_idx)
        tabs.addTab(tab, f"PATH ({len(path_list)})")

        # Tabs fill the entire page (stretch=1, no trailing stretch)
        layout.addWidget(tabs, 1)

    # -- Navigation --------------------------------------------------------- #
    def _on_nav_clicked(self, idx: int) -> None:
        self._current_page = idx
        if self._search.text().strip():
            self._search.clear()
        self._page_title.setText(self.PAGES[idx][1])
        self._stack.setCurrentIndex(idx)
        if idx == 12:
            self._render_page(idx)
        elif idx in self._pages_ready:
            self._render_page(idx)

    # -- Library update ----------------------------------------------------- #
    def _on_update_clicked(self) -> None:
        self._update_btn.setEnabled(False)
        self._update_btn.setText("Updating...")
        self._update_status.setObjectName("update-status")
        self._update_status.setText("Starting update...")
        self._update_status.style().unpolish(self._update_status)
        self._update_status.style().polish(self._update_status)
        self._updater.run_update()

    def _on_update_status(self, message: str, kind: str) -> None:
        obj_name = "update-status"
        if kind == "success":
            obj_name = "update-status-success"
        elif kind == "error":
            obj_name = "update-status-error"
        self._update_status.setObjectName(obj_name)
        self._update_status.setText(message)
        self._update_status.style().unpolish(self._update_status)
        self._update_status.style().polish(self._update_status)

    def _on_update_finished(self, success: bool, message: str) -> None:
        self._update_btn.setEnabled(True)
        self._update_btn.setText("Update Libraries")
        kind = "success" if success else "error"
        self._on_update_status(message, kind)

    # -- Export ------------------------------------------------------------- #
    def _on_log_clicked(self) -> None:
        """Open app.log in the default text editor."""
        log_path = os.path.join(data_dir(), "app.log")
        if not os.path.exists(log_path):
            self._status_label.setText("No log file exists yet.")
            return
        try:
            os.startfile(log_path)
            logger.info("Opened log file: %s", log_path)
        except Exception as e:
            logger.error("Failed to open log file: %s", e, exc_info=True)
            self._status_label.setText(f"Cannot open log: {e}")

    def _on_settings_clicked(self) -> None:
        """Open the Settings dialog."""
        dlg = SettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            cfg = reload_config()
            logger.info("Settings changed, applying (theme=%s, compact=%s, "
                        "progress=%s, font=%s, sensor_refresh=%dms, "
                        "proc_refresh=%dms, proc_top=%d, sparkline=%d, "
                        "speed_test=%d/%dMB/%ds)",
                        cfg.theme, cfg.compact_view, cfg.show_progress_bars,
                        cfg.font_family or "default",
                        cfg.sensor_refresh_interval_ms,
                        cfg.process_refresh_interval_ms, cfg.process_top_n,
                        cfg.sparkline_max_samples,
                        cfg.speed_test_download_mb, cfg.speed_test_upload_mb,
                        cfg.speed_test_timeout_s)
            self._restart_sensor_refresh()
            self._restart_process_refresh()

            # Re-apply theme and font
            from app import _resolve_theme
            theme = _resolve_theme()
            QApplication.instance().setStyleSheet(build_qss(theme))

            app_inst = QApplication.instance()
            if app_inst:
                font = app_inst.font()
                if cfg.font_family:
                    font.setFamily(cfg.font_family)
                app_inst.setFont(font)

            # Update toggle buttons to reflect config
            self._compact_btn.setChecked(cfg.compact_view)

            # Re-render only the current page; mark others as dirty
            # so they rebuild on-demand when navigated to.
            self._pages_ready.clear()
            # Re-add pages that already have data so navigation re-renders them.
            for i in range(12):
                self._pages_ready.add(i)
            self._pages_ready.discard(self._current_page)
            if self._current_page >= 0:
                try:
                    self._render_page(self._current_page)
                except Exception as e:
                    logger.error("Page %d re-render failed: %s",
                                self._current_page, e, exc_info=True)

            self._status_label.setText(
                "Settings applied. Changes are live.")

    def _on_about_clicked(self) -> None:
        """Show the About dialog."""
        dlg = QDialog(self)
        dlg.setWindowTitle("About SysDigger")
        dlg.setMinimumWidth(520)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(14)
        layout.setContentsMargins(28, 24, 28, 20)

        title = QLabel("SysDigger")
        title.setStyleSheet(f"font-size: 26px; font-weight: 700; color: {_ACCENT};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        ver = QLabel("Version 4.17")
        ver.setStyleSheet("font-size: 13px; font-weight: 600;")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ver)

        copy = QLabel("© 2026 Stavros Antoniou · All Rights Reserved")
        copy.setStyleSheet("font-size: 12px;")
        copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(copy)

        license_note = QLabel("Proprietary software — unauthorized copying, modification, "
                               "or distribution is prohibited. See LICENSE file for details.")
        license_note.setStyleSheet("font-size: 11px;")
        license_note.setWordWrap(True)
        license_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(license_note)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {_DIVIDER};")
        layout.addWidget(sep)

        desc = QLabel(
            "SysDigger is a Windows system information and diagnostics viewer. "
            "It gathers hardware, operating system, network, software, and "
            "diagnostic data into a single Fluent-style interface.\n\n"
            "Key features:\n"
            "  •  Hardware — CPU, GPU, memory, motherboard, storage, battery "
            "health, live sensor refresh (temperatures, fan speeds, voltages, "
            "usage), sparkline graphs (CPU/RAM usage + CPU/GPU temp)\n"
            "  •  Operating System — edition, build, uptime, activation status\n"
            "  •  Network — adapters, active TCP/UDP connections (live), "
            "Wi-Fi signal info, DNS cache viewer, external IP, speed test, "
            "bufferbloat grade\n"
            "  •  Software — installed programs, services, startup items + "
            "boot impact analysis, Windows updates\n"
            "  •  Processes — list view (sortable) + tree view (parent-child "
            "hierarchy), top 200 by CPU usage\n"
            "  •  Devices — device manager, signed drivers\n"
            "  •  Health — Windows Defender, activation, battery wear\n"
            "  •  Diagnostics — event logs, BSOD history, crash dumps, restore "
            "points, environment variables, PATH entries, DirectX/D3D feature "
            "levels\n"
            "  •  Tools — 28 integrated system utilities (flush DNS, disk "
            "cleanup, SFC/DISM, HID services, MTP/Android USB repair, disk "
            "status/online, memory diagnostic, hosts file editor, Windows "
            "Update trigger, UEFI BIOS reboot, etc.)\n"
            "  •  Disk Analyzer — large file scan, top folders, recursive "
            "folder size map, duplicate file finder, and scan-then-pick "
            "cleanup of biggest AppData folders or user profile files (you "
            "choose what to delete)\n"
            "  •  Appx Manager — uninstall largest Appx packages by size\n"
            "  •  Dev Cache Cleaner — clear npm / pip caches and leftover "
            "updater folders (LM Studio, Vortex, RSI Launcher, uv)\n"
            "  •  Hibernate Manager — toggle hibernation to free hiberfil.sys\n"
            "  •  UEFI BIOS Reboot — restart the PC directly into UEFI "
            "firmware settings (BIOS) without spamming the BIOS hotkey\n"
            "  •  Disk benchmark — sequential read/write speed test\n"
            "  •  Exports — JSON, Text, and HTML reports\n"
            "  •  Copy selected rows to clipboard from any table (Ctrl+C or "
            "right-click)\n"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; line-height: 1.5;")
        desc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(desc)

        tp_sep = QFrame()
        tp_sep.setFrameShape(QFrame.Shape.HLine)
        tp_sep.setStyleSheet(f"color: {_DIVIDER};")
        layout.addWidget(tp_sep)

        tp_title = QLabel("Third-Party Components")
        tp_title.setStyleSheet("font-size: 13px; font-weight: 600;")
        layout.addWidget(tp_title)

        tp = QLabel(
            "Hardware sensors: LibreHardwareMonitorLib (MPL-2.0) — "
            "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor\n"
            "Motherboard/CPU kernel driver: PawnIO (GPL-2.0+ with "
            "DeviceIoControl exception) — "
            "https://github.com/namazso/PawnIO\n"
            "PawnIO installer is downloaded at runtime from the official "
            "source and removed on exit — not bundled with SysDigger.\n"
            "Full third-party notices: see THIRD-PARTY-NOTICES file."
        )
        tp.setWordWrap(True)
        tp.setStyleSheet("font-size: 11px; line-height: 1.5;")
        tp.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(tp)

        layout.addStretch()

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)

        dlg.exec()

    def _on_theme_toggle(self) -> None:
        """Quick toggle between dark and light themes."""
        cfg = get_config()
        from app import _resolve_theme
        current = _resolve_theme()
        new_theme = "light" if current == "dark" else "dark"
        cfg.theme = new_theme
        cfg.save()
        QApplication.instance().setStyleSheet(build_qss(new_theme))
        # Re-apply dark/light titlebar
        set_dark_titlebar(self, force_dark=(new_theme == "dark"))
        # Re-render current page so inline stylesheets pick up new theme colors.
        # Mark all pages as dirty so they rebuild on navigation.
        self._pages_ready.clear()
        for i in range(12):
            self._pages_ready.add(i)
        self._pages_ready.discard(self._current_page)
        if self._current_page >= 0:
            try:
                self._render_page(self._current_page)
            except Exception as e:
                logger.error("Page %d re-render failed: %s",
                             self._current_page, e, exc_info=True)
        logger.info("Theme toggled to %s", new_theme)
        self._status_label.setText(f"Theme: {new_theme}")

    def _on_compact_toggle(self) -> None:
        """Toggle compact/expanded view."""
        cfg = get_config()
        cfg.compact_view = self._compact_btn.isChecked()
        cfg.save()
        logger.info("Compact view: %s", cfg.compact_view)
        # Re-render current page
        try:
            self._on_page_ready(self._current_page)
        except Exception as e:
            logger.error("Page re-render failed: %s", e, exc_info=True)
        self._status_label.setText(
            f"View: {'Compact' if cfg.compact_view else 'Expanded'}")

    def _on_export_clicked(self) -> None:
        if self._collecting:
            self._status_label.setText("Wait for collection to finish before exporting.")
            return
        formats = "JSON (*.json);;Text (*.txt);;HTML (*.html)"
        default_name = f"system_info_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export System Information", default_name, formats
        )
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".json":
                self._export_json(path)
            elif ext == ".html":
                self._export_html(path)
            else:
                self._export_text(path)
            self._status_label.setText(f"Exported to {path}")
        except Exception as e:
            logger.error("Export failed: %s", e, exc_info=True)
            self._status_label.setText(f"Export failed: {e}")

    def _export_json(self, path: str) -> None:
        data = self.collector.data
        export = {
            "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "os": data.os_info,
            "hardware": {k: v for k, v in data.hw_info.items() if k != "sensors"},
            "sensors": {
                "available": data.hw_info.get("sensors", {}).get("available", False),
                "source": data.hw_info.get("sensors", {}).get("source", "N/A"),
                "data": {
                    stype: data.hw_info.get("sensors", {}).get(
                        self._STYPE_TO_KEY.get(stype, ""), []
                    )
                    for stype in self._SENSOR_TYPES
                },
            },
            "network": data.net_info,
            "external_ip": data.ext_ip_info,
            "external_ip_error": data.ext_ip_error,
            "external_ip_time": data.ext_ip_time,
            "processes": data.processes,
            "startup_programs": data.startup_programs,
            "installed_programs": data.installed_programs,
            "updates": data.update_history,
            "health": data.health_info,
            "speed_test": data.speed_test_result,
            "bufferbloat": data.bufferbloat_result,
            "gpu_details": data.gpu_details,
            "devices": data.devices_info,
            "diagnostics": data.diagnostics_info,
            "vpn_status": data.vpn_status,
            "services": data.services_info,
            "drivers": data.drivers_info,
            "active_connections": data.active_connections,
            "wifi_info": data.wifi_info,
            "dns_cache": data.dns_cache,
            "disk_benchmark": data.disk_benchmark,
            "startup_impact": data.startup_impact,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(export, f, indent=2, default=str, ensure_ascii=False)

    def _iter_export_sections(self):
        data = self.collector.data

        yield ("Operating System", [(k, v) for k, v in data.os_info.items()])

        hw = data.hw_info
        if "cpu" in hw:
            yield ("CPU", [(k, v) for k, v in hw["cpu"].items()])

        if "ram" in hw:
            ram = hw["ram"]
            ram_rows = [(k, ram[k]) for k in ("Total", "Used", "Available",
                                              "Usage %", "Total Installed") if k in ram]
            for slot in ram.get("Slots", []):
                ram_rows.append((
                    f"Slot {slot.get('Slot', '?')}",
                    f"{slot.get('Manufacturer', 'N/A')} | {slot.get('Part Number', 'N/A')} | "
                    f"{slot.get('Capacity', 'N/A')} | {slot.get('Speed', 'N/A')} | S/N: {slot.get('Serial', 'N/A')}"
                ))
            yield ("Memory (RAM)", ram_rows)

        if "motherboard" in hw:
            yield ("Motherboard", [(k, v) for k, v in hw["motherboard"].items()])

        if "bios" in hw:
            yield ("BIOS", [(k, v) for k, v in hw["bios"].items()])

        gpus = hw.get("gpus", [])
        for i, g in enumerate(gpus):
            prefix = "GPU" if len(gpus) == 1 else f"GPU {i + 1}"
            yield (prefix, [(k, v) for k, v in g.items()])

        for d in hw.get("disks", []):
            yield (f"Disk {d.get('Index', '?')} - {d.get('Model', 'N/A')}",
                   [(k, d.get(k, "N/A")) for k in ("Size", "Media Type", "Interface",
                                                    "Link Speed", "Serial", "Firmware",
                                                    "Free", "Usage %")])

        bat = hw.get("battery", {})
        if bat.get("Present"):
            yield ("Battery", [(k, bat.get(k, "N/A"))
                               for k in ("Percent", "Plugged In", "Charging", "Time Left",
                                         "Design Capacity", "Full Charge Capacity",
                                         "Wear %", "Cycle Count")])
        else:
            yield ("Battery", [("Status", "Not present")])

        sensors = hw.get("sensors", {})
        if sensors.get("available"):
            sensor_rows: list[tuple[str, str]] = []
            for stype in self._SENSOR_TYPES:
                skey = self._STYPE_TO_KEY[stype]
                for e in sorted(sensors.get(skey, []),
                                key=lambda x: (x.get("Source", ""), x.get("Name", ""))):
                    val_str = fmt_sensor_value(stype, e.get("Value", 0.0))
                    sensor_rows.append((f"{stype} - {e.get('Source', '?')} / {e.get('Name', '?')}",
                                        val_str))
            yield (f"Sensors ({sensors.get('source', 'N/A')})", sensor_rows)

        for i, a in enumerate(data.net_info or []):
            net_rows = []
            for k, v in a.items():
                if isinstance(v, list):
                    v = ", ".join(v) if v else "N/A"
                net_rows.append((k, v))
            yield (f"Network Adapter {i + 1}: {a.get('Name', 'N/A')}", net_rows)

        if data.ext_ip_error:
            ip_rows = [("Error", data.ext_ip_error)]
        else:
            ip_rows = [(k, v) for k, v in data.ext_ip_info.items()]
        ip_rows.append(("Last Checked", data.ext_ip_time or "N/A"))
        yield ("External (Public) IP", ip_rows)

        if data.processes:
            yield ("Top Processes", [
                (str(p.get("PID", 0)),
                 f"{p.get('Name', 'N/A')} | CPU: {p.get('CPU %', 0.0):.1f}% | Mem: {p.get('Memory (MB)', 0):.1f}MB")
                for p in data.processes[:20]
            ])

        if data.startup_programs:
            yield ("Startup Programs", [
                (p.get("Name", "N/A"),
                 f"{p.get('Command', 'N/A')} [{p.get('Source', 'N/A')}]")
                for p in data.startup_programs
            ])

        if data.installed_programs:
            yield (f"Installed Programs ({len(data.installed_programs)})",
                   [(p.get("Name", "N/A"),
                     f"v{p.get('Version', 'N/A')} | {p.get('Publisher', 'N/A')} | {p.get('Install Date', 'N/A')}")
                    for p in data.installed_programs])

        if data.update_history:
            yield (f"Windows Updates ({len(data.update_history)})",
                   [(u.get("KB", "N/A"),
                     f"{u.get('Description', 'N/A')} | {u.get('Installed On', 'N/A')} | {u.get('Installed By', 'N/A')}")
                    for u in data.update_history])

        if data.services_info:
            yield (f"Windows Services ({len(data.services_info)})",
                   [(svc.get("Name", "N/A"),
                     f"{svc.get('Display Name', '')} | {svc.get('State', '')} | {svc.get('Start Type', '')}")
                    for svc in data.services_info[:50]])

        if data.drivers_info:
            yield (f"Drivers ({len(data.drivers_info)})",
                   [(drv.get("Device Name", "N/A"),
                     f"v{drv.get('Driver Version', '')} | {drv.get('Provider', '')} | {drv.get('Device Class', '')}")
                    for drv in data.drivers_info[:50]])

        if data.health_info:
            for d in data.health_info.get("disk_smart", []):
                yield (f"Disk Health: {d.get('Model', 'N/A')}", [
                    ("Status", d.get("Status", "N/A")),
                    ("Health", d.get("Health", "N/A")),
                    ("Size", d.get("Size", "N/A")),
                ])
            defender = data.health_info.get("defender", {})
            if defender.get("Available"):
                yield ("Windows Defender",
                       [(k, v) for k, v in defender.items() if k != "Available"])
            for fw in data.health_info.get("firewall", []):
                yield (f"Firewall: {fw.get('Profile', 'N/A')}",
                       [("Status", fw.get("Status", "N/A"))])
            activation = data.health_info.get("activation", {})
            if activation.get("Available"):
                yield ("Windows Activation", [
                    ("Status", activation.get("Status", "N/A")),
                    ("Edition", activation.get("Edition", "N/A")),
                    ("Product Key", activation.get("Product Key", "N/A")),
                    ("Grace Period (days)", activation.get("Grace Period (days)", "N/A")),
                ])

        if data.speed_test_result:
            st = data.speed_test_result
            st_rows: list[tuple[str, str]] = []
            if st.get("download_mbps"):
                st_rows.append(("Download", f"{st['download_mbps']:.2f} Mbps"))
            if st.get("upload_mbps"):
                st_rows.append(("Upload", f"{st['upload_mbps']:.2f} Mbps"))
            if st.get("timestamp"):
                st_rows.append(("Test Run", st["timestamp"]))
            if st.get("error"):
                st_rows.append(("Error", st["error"]))
            if st_rows:
                yield ("Speed Test", st_rows)

        if data.bufferbloat_result:
            bb = data.bufferbloat_result
            bb_rows: list[tuple[str, str]] = []
            if bb.get("baseline_latency_ms"):
                bb_rows.append(("Baseline Latency", f"{bb['baseline_latency_ms']:.1f} ms"))
                bb_rows.append(("Download Bloat", f"{bb['download_bloat_ms']:.1f} ms"))
                bb_rows.append(("Upload Bloat", f"{bb['upload_bloat_ms']:.1f} ms"))
                if bb.get("grade"):
                    bb_rows.append(("Grade", bb["grade"]))
            if bb.get("error"):
                bb_rows.append(("Error", bb["error"]))
            if bb.get("timestamp"):
                bb_rows.append(("Test Run", bb["timestamp"]))
            if bb_rows:
                yield ("Bufferbloat Test", bb_rows)

        for i, g in enumerate(data.gpu_details or []):
            yield (f"GPU {i + 1} Details", [(k, str(v)) for k, v in g.items()])

        if data.devices_info:
            for d in data.devices_info.get("usb", [])[:20]:
                yield (f"USB: {d.get('Name', 'N/A')}", [
                    ("Vendor ID", d.get("Vendor ID", "N/A")),
                    ("Product ID", d.get("Product ID", "N/A")),
                    ("Manufacturer", d.get("Manufacturer", "N/A")),
                    ("Status", d.get("Status", "N/A")),
                ])
            for d in data.devices_info.get("bluetooth", [])[:20]:
                yield (f"BT: {d.get('Name', 'N/A')}", [
                    ("Status", d.get("Status", "N/A")),
                    ("Manufacturer", d.get("Manufacturer", "N/A")),
                ])
            for d in data.devices_info.get("printers", []):
                yield (f"Printer: {d.get('Name', 'N/A')}", [
                    ("Driver", d.get("Driver", "N/A")),
                    ("Port", d.get("Port", "N/A")),
                    ("Default", d.get("Default", "N/A")),
                    ("Status", d.get("Status", "N/A")),
                ])
            for d in data.devices_info.get("audio", []):
                yield (f"Audio: {d.get('Name', 'N/A')}", [
                    ("Manufacturer", d.get("Manufacturer", "N/A")),
                    ("Status", d.get("Status", "N/A")),
                ])

        if data.diagnostics_info:
            sys_events = data.diagnostics_info.get("event_log_system", [])[:20]
            if sys_events:
                yield ("System Event Log (recent)", [
                    (f"{e.get('Time', '')} {e.get('Level', '')} {e.get('Source', '')}",
                     f"ID={e.get('Event ID', '')} {e.get('Message', '')}")
                    for e in sys_events
                ])
            app_events = data.diagnostics_info.get("event_log_application", [])[:20]
            if app_events:
                yield ("Application Event Log (recent)", [
                    (f"{e.get('Time', '')} {e.get('Level', '')} {e.get('Source', '')}",
                     f"ID={e.get('Event ID', '')} {e.get('Message', '')}")
                    for e in app_events
                ])
            pp = data.diagnostics_info.get("power_plan", {})
            if pp:
                yield ("Power Plan", [(k, str(v)) for k, v in pp.items()])
            dx = data.diagnostics_info.get("directx", {})
            if dx:
                yield ("DirectX / OpenGL", [(k, str(v)) for k, v in dx.items()])
            bsod_list = data.diagnostics_info.get("bsod_history", [])
            if bsod_list:
                yield (f"BSOD / Crash History ({len(bsod_list)})", [
                    (f"{c.get('Time', '')} {c.get('BugCheck Code', '')}",
                     f"{c.get('Parameters', '')} | {c.get('Message', '')}")
                    for c in bsod_list[:30]
                ])
            cd = data.diagnostics_info.get("crash_dump_settings", {})
            if cd:
                yield ("Crash Dump Settings", [(k, str(v)) for k, v in cd.items()])
            rp_list = data.diagnostics_info.get("restore_points", [])
            if rp_list:
                yield (f"System Restore Points ({len(rp_list)})", [
                    (rp.get("Creation Time", ""),
                     f"{rp.get('Description', '')} (Seq #{rp.get('Sequence #', '')})")
                    for rp in rp_list
                ])
            env = data.diagnostics_info.get("environment", {})
            if env:
                yield (f"Environment Variables ({len(env)})",
                       [(k, str(v)) for k, v in env.items()])
            path_list = data.diagnostics_info.get("path_entries", [])
            if path_list:
                yield (f"PATH Entries ({len(path_list)})", [
                    (f"[{pe.get('Source', '')}] #{pe.get('Index', '')}", pe.get("Path", ""))
                    for pe in path_list
                ])

        if data.vpn_status:
            vpn_rows = [("VPN Active", "Yes" if data.vpn_status.get("Active") else "No")]
            for c in data.vpn_status.get("Connections", []):
                vpn_rows.append((c.get("Adapter", "N/A"),
                                 f"{c.get('Status', 'N/A')} ({c.get('Matched', 'N/A')})"))
            yield ("VPN Status", vpn_rows)

        if data.active_connections:
            yield (f"Active Connections ({len(data.active_connections)})", [
                (c.get("Protocol", ""),
                 f"{c.get('Local Address', 'N/A')} -> {c.get('Remote Address', 'N/A')} | "
                 f"{c.get('State', 'N/A')} | PID={c.get('PID', 'N/A')} {c.get('Process', '')}")
                for c in data.active_connections[:50]
            ])

        if data.wifi_info:
            yield ("Wi-Fi Adapter", [(k, v) for k, v in data.wifi_info.items()])

        if data.dns_cache:
            yield (f"DNS Cache ({len(data.dns_cache)})", [
                (d.get("Record Name", ""),
                 f"Type={d.get('Type', 'N/A')} TTL={d.get('TTL', 'N/A')} {d.get('Address', 'N/A')}")
                for d in data.dns_cache[:50]
            ])

        if data.disk_benchmark:
            yield ("Disk Benchmark", [(k, str(v)) for k, v in data.disk_benchmark.items()])

        if data.startup_impact:
            si = data.startup_impact
            si_rows = [("Last Boot Duration", f"{si.get('Last Boot Duration (s)', 'N/A')} s"),
                       ("Startup Programs Count", str(si.get("Startup Programs Count", 0)))]
            for bh in si.get("Boot History", [])[:10]:
                si_rows.append((bh.get("Boot Time", ""),
                                f"Duration={bh.get('Duration (s)', 'N/A')}s"))
            yield ("Startup Impact", si_rows)

    def _export_text(self, path: str) -> None:
        lines: list[str] = []
        lines.append("Windows System Information")
        lines.append(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 60)
        lines.append("")
        for title, rows in self._iter_export_sections():
            lines.append(f"[{title}]")
            for k, v in rows:
                lines.append(f"  {k}: {v}")
            lines.append("")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _export_html(self, path: str) -> None:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        def _esc(s: Any) -> str:
            return (str(s).replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;").replace('"', "&quot;"))

        def _card(title: str, rows: list[tuple[str, str]]) -> str:
            body = "".join(
                f"<tr><td class='k'>{_esc(k)}</td><td class='v'>{_esc(v)}</td></tr>"
                for k, v in rows
            )
            return (f"<div class='card'><h2>{_esc(title)}</h2>"
                    f"<table>{body}</table></div>")

        sections = [f"<h1>Windows System Information</h1>",
                    f"<p class='meta'>Generated: {_esc(ts)}</p>"]
        for title, rows in self._iter_export_sections():
            sections.append(_card(title, rows))

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Windows System Information</title>
<style>
  body {{ background: #1c1c1c; color: #fff; font-family: 'Segoe UI', Arial, sans-serif; margin: 24px; }}
  h1 {{ color: #60cdff; font-size: 24px; margin-bottom: 4px; }}
  .meta {{ color: #9a9a9a; font-size: 13px; margin-bottom: 20px; }}
  .card {{ background: #2d2d2d; border-radius: 8px; padding: 18px 14px; margin-bottom: 14px; }}
  .card h2 {{ color: #60cdff; font-size: 14px; margin: 0 0 10px 0; }}
  table {{ border-collapse: collapse; width: 100%; }}
  td {{ padding: 3px 0; font-size: 14px; vertical-align: top; }}
  td.k {{ color: #9a9a9a; width: 230px; padding-right: 12px; }}
  td.v {{ color: #fff; }}
</style>
</head>
<body>
{"".join(sections)}
</body>
</html>"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    # -- Search ------------------------------------------------------------- #
    _MAX_RESULTS = 200

    def _on_search_changed(self, text: str) -> None:
        query = text.strip().lower()
        if not query:
            self._stack.setCurrentIndex(self._current_page)
            self._page_title.setText(self.PAGES[self._current_page][1])
            return

        if self._collecting:
            return

        tokens = list(dict.fromkeys(t for t in query.split() if len(t) >= 2))

        layout: QVBoxLayout = self._search_page.widget().layout()
        self._clear_layout(layout)
        layout.addStretch()

        if not tokens:
            hint = QLabel("Keep typing\u2026")
            hint.setObjectName("no-results")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.insertWidget(0, hint)
            self._page_title.setText("Search")
            self._stack.setCurrentIndex(len(self.PAGES))
            return

        total = len(self._search_items)

        token_counts: dict[str, int] = {}
        for tok in tokens:
            cnt = 0
            for item in self._search_items:
                if (tok in item["section"].lower()
                        or tok in item["key"].lower()
                        or tok in item["value"].lower()):
                    cnt += 1
            token_counts[tok] = cnt

        effective = [
            tok for tok in tokens
            if token_counts[tok] <= total * 0.25 or len(tokens) == 1
        ]
        if not effective:
            effective = tokens

        matches: list[dict[str, str]] = []
        for item in self._search_items:
            sec_l = item["section"].lower()
            key_l = item["key"].lower()
            val_l = item["value"].lower()
            if any(tok in sec_l or tok in key_l or tok in val_l for tok in effective):
                matches.append(item)

        total_matches = len(matches)
        skipped = [tok for tok in tokens if tok not in effective]
        shown = matches[: self._MAX_RESULTS]
        truncated = total_matches - len(shown)

        title = f"Search Results ({total_matches})"
        if skipped:
            title += f"  \u2014  ignored: {', '.join(skipped)}"
        self._page_title.setText(title)

        if not shown:
            label = QLabel(f"No results for \u201c{text.strip()}\u201d")
            label.setObjectName("no-results")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.insertWidget(0, label)
        else:
            sections: dict[str, list[tuple[str, str]]] = {}
            for item in shown:
                sections.setdefault(item["section"], []).append(
                    (item["key"], item["value"])
                )
            for section, rows in sections.items():
                self._make_card(layout, section, rows, -1)
            if truncated > 0:
                note = QLabel(
                    f"Showing {len(shown)} of {total_matches} results. "
                    f"Refine your search to see more."
                )
                note.setObjectName("no-results")
                note.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.insertWidget(0, note)

        self._stack.setCurrentIndex(len(self.PAGES))

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._search.clear()
            self._search.clearFocus()
        else:
            super().keyPressEvent(event)

    # -- Window settings persistence ---------------------------------------- #
    def _load_window_settings(self) -> None:
        cfg = get_config()
        geo_b64 = cfg.window_geometry
        if geo_b64:
            try:
                geo_bytes = base64.b64decode(geo_b64)
                self.restoreGeometry(QByteArray(geo_bytes))
                logger.debug("Window geometry restored from config.json")
            except Exception as e:
                logger.warning("Failed to restore window geometry: %s", e)

    def _save_window_settings(self) -> None:
        try:
            geo_bytes = bytes(self.saveGeometry())
            geo_b64 = base64.b64encode(geo_bytes).decode("ascii")
            cfg = get_config()
            cfg.window_geometry = geo_b64
            cfg.save()
        except Exception as e:
            logger.warning("Failed to save window settings: %s", e)

    def closeEvent(self, event) -> None:
        self._closing = True
        self._save_window_settings()
        # Terminate any running tool subprocess before exiting.
        if self._tool_running:
            proc = self._tool_proc
            if proc and proc.poll() is None:
                try:
                    # Force-kill the whole process tree.  A timeout guards
                    # against taskkill itself hanging (zombie process,
                    # stuck kernel driver) and locking the window open.
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        timeout=5,
                    )
                except subprocess.TimeoutExpired:
                    logger.warning("taskkill timed out closing tool subprocess")
                except Exception:
                    pass
        if self._sensor_refresh_timer is not None:
            self._sensor_refresh_timer.stop()
            self._sensor_refresh_timer = None
        if self._process_refresh_timer is not None:
            self._process_refresh_timer.stop()
            self._process_refresh_timer = None
        if self._refresh_dot_timer is not None:
            self._refresh_dot_timer.stop()
            self._refresh_dot_timer = None
        # Uninstall the PawnIO driver (portable mode — nothing left behind).
        lhm_proc = getattr(self.collector, "_lhm_process", None)
        if lhm_proc is not None:
            progress = QProgressDialog(
                "Uninstalling PawnIO driver…", None, 0, 0, self
            )
            progress.setWindowTitle("SysDigger")
            progress.setCancelButton(None)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.show()
            QApplication.processEvents()
            try:
                lhm_proc.stop()
            except Exception:
                pass
            progress.close()
        # Release cached PDH query handles (AMD per-core freq).
        try:
            self.collector.close()
        except Exception:
            pass
        super().closeEvent(event)
