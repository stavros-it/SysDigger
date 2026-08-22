"""Launch mode picker dialog shown at app startup.

Presents a small QDialog with two buttons:
  - Normal Mode — full app: loads LibreHardwareMonitorLib (.NET DLLs) +
    PawnIO kernel driver for live CPU/GPU/motherboard sensors.
  - Fast Mode — skips LHM / pythonnet / .NET runtime / PawnIO entirely.
    Hardware/Sensors pages degrade to WMI fallback or "N/A". All other
    pages (OS, Network, Processes, Software, Devices, Diagnostics, Tools)
    work fully. Saves ~3-6 seconds on startup.

This module MUST NOT import `collectors` or `sensors` — those trigger
pythonnet + .NET CLR initialization at import time, which defeats the
purpose of fast mode. Only PySide6 + stdlib imports are allowed here.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
)


# Return values for show_launch_menu()
MODE_NORMAL = "normal"
MODE_FAST = "fast"
MODE_CANCEL = "cancel"


def _theme_palette_is_dark(app) -> bool:
    """Detect whether the QApplication's current palette is dark-themed."""
    pal = app.palette()
    bg = pal.color(QPalette.ColorRole.Window)
    return bg.lightness() < 128


def show_launch_menu(app) -> str:
    """Show the launch mode picker. Returns MODE_NORMAL / MODE_FAST / MODE_CANCEL.

    The dialog blocks (modal exec) until the user picks a mode or closes.
    """
    dark = _theme_palette_is_dark(app)
    if dark:
        bg = "#1c1c1c"
        card_bg = "#2d2d2d"
        accent = "#60cdff"
        text_primary = "#ffffff"
        text_secondary = "#9a9a9a"
        divider = "#3a3a3a"
        hover = "#3a3a3a"
    else:
        bg = "#f5f5f5"
        card_bg = "#ffffff"
        accent = "#0078d4"
        text_primary = "#1a1a1a"
        text_secondary = "#666666"
        divider = "#d0d0d0"
        hover = "#e0e0e0"

    dlg = QDialog()
    dlg.setWindowTitle("SysDigger — Launch Mode")
    dlg.setMinimumWidth(460)
    dlg.setStyleSheet(f"""
        QDialog {{
            background-color: {bg};
        }}
        QLabel {{
            color: {text_primary};
            background: transparent;
        }}
        QLabel#subtitle {{
            color: {text_secondary};
        }}
        QLabel#mode-title {{
            color: {text_primary};
            font-size: 15px;
            font-weight: 600;
        }}
        QLabel#mode-desc {{
            color: {text_secondary};
            font-size: 11px;
        }}
        QLabel#mode-tag {{
            color: {accent};
            font-size: 10px;
            font-weight: 600;
        }}
        QFrame#card {{
            background-color: {card_bg};
            border: 1px solid {divider};
            border-radius: 8px;
        }}
        QFrame#card:hover {{
            border: 1px solid {accent};
            background-color: {hover};
        }}
        QPushButton#pick {{
            background-color: {accent};
            color: #ffffff;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#pick:hover {{
            background-color: {accent};
            opacity: 0.9;
        }}
        QPushButton#quit {{
            background-color: transparent;
            color: {text_secondary};
            border: 1px solid {divider};
            border-radius: 6px;
            padding: 6px 14px;
            font-size: 11px;
        }}
        QPushButton#quit:hover {{
            border: 1px solid {text_secondary};
            color: {text_primary};
        }}
    """)

    result = {"mode": MODE_CANCEL}

    v = QVBoxLayout(dlg)
    v.setSpacing(14)
    v.setContentsMargins(24, 20, 24, 18)

    # Title
    title = QLabel("SysDigger")
    title.setStyleSheet(
        f"font-size: 22px; font-weight: 700; color: {accent}; "
        "background: transparent;"
    )
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    v.addWidget(title)

    subtitle = QLabel("Choose how to launch the app")
    subtitle.setObjectName("subtitle")
    subtitle.setStyleSheet("font-size: 12px; background: transparent;")
    subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
    v.addWidget(subtitle)

    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(f"color: {divider}; background: transparent;")
    v.addWidget(sep)

    def _make_card(tag: str, title_text: str, desc: str, mode: str) -> None:
        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setSpacing(4)
        cl.setContentsMargins(16, 12, 16, 12)

        tag_lbl = QLabel(tag)
        tag_lbl.setObjectName("mode-tag")
        tag_lbl.setStyleSheet("background: transparent;")
        cl.addWidget(tag_lbl)

        t = QLabel(title_text)
        t.setObjectName("mode-title")
        t.setStyleSheet("background: transparent;")
        cl.addWidget(t)

        d = QLabel(desc)
        d.setObjectName("mode-desc")
        d.setWordWrap(True)
        d.setStyleSheet("background: transparent;")
        cl.addWidget(d)

        btn = QPushButton("Launch")
        btn.setObjectName("pick")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def _pick(_checked: bool = False, m: str = mode) -> None:
            result["mode"] = m
            dlg.accept()

        btn.clicked.connect(_pick)
        cl.addWidget(btn)

        v.addWidget(card)

    _make_card(
        "FULL EXPERIENCE",
        "Normal Mode",
        "Loads LibreHardwareMonitorLib + PawnIO driver for live "
        "CPU/GPU/motherboard sensors (temperatures, fan speeds, "
        "voltages, clocks). All 14 pages fully functional. "
        "Startup takes ~3-6 seconds longer for driver install.",
        MODE_NORMAL,
    )

    _make_card(
        "FASTER STARTUP",
        "Fast Mode",
        "Skips LHM / pythonnet / .NET / PawnIO entirely. All pages "
        "work except Hardware/Sensors (show WMI fallback or 'N/A'). "
        "OS, Network, Processes, Software, Devices, Diagnostics, "
        "Tools — all fully functional. Saves ~3-6 seconds on startup.",
        MODE_FAST,
    )

    v.addStretch()

    # Bottom row: Quit button
    bottom = QHBoxLayout()
    bottom.addStretch()
    quit_btn = QPushButton("Quit")
    quit_btn.setObjectName("quit")
    quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    quit_btn.clicked.connect(dlg.reject)
    bottom.addWidget(quit_btn)
    v.addLayout(bottom)

    dlg.exec()
    return result["mode"]
