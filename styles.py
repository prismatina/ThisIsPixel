"""
ThisIsPixel - Style & Theme Engine
===================================
Professional dark theme engine adopting modern digital art studio aesthetics:
- Base background: #1b1b1b
- Panel background: #232323
- Button background: #2d2d2d (hover #383838, pressed #1f1f1f)
- Subtle borders: #333333
- Muted accent highlight: #3a78c4 (subtle slate blue) and #c77838 (subtle warm amber)
- Minimum 4px border-radius on buttons and inputs for a clean, non-generic finish.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import QApplication

# Color Palette Constants
COLOR_BASE = "#1b1b1b"           # Main workspace and window background
COLOR_PANEL = "#232323"          # Dock panels and sidebar background
COLOR_PANEL_ALT = "#1e1e1e"      # Containers, table backgrounds, and headers
COLOR_SURFACE = "#282828"        # Card and row surface background
COLOR_BORDER = "#333333"         # Subtle borders and dividers
COLOR_BORDER_LIGHT = "#404040"   # Hover borders
COLOR_TEXT = "#dcdcdc"           # Primary readable text
COLOR_TEXT_MUTED = "#888888"     # Secondary subtle text
COLOR_ACCENT = "#3a78c4"         # Muted elegant accent blue
COLOR_ACCENT_HOVER = "#498adb"   # Hover state for accent
COLOR_ACCENT_MUTED = "#264873"   # Deep accent fill for checked state
COLOR_BTN = "#2d2d2d"            # Button default fill
COLOR_BTN_HOVER = "#383838"      # Button hover fill
COLOR_BTN_PRESSED = "#202020"    # Button pressed fill

DARK_THEME_QSS = f"""
/* =========================================================================
   MODERN STUDIO DARK THEME - ThisIsPixel
   ========================================================================= */

QMainWindow {{
    background-color: {COLOR_BASE};
}}

QWidget {{
    color: {COLOR_TEXT};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 12px;
}}

/* Tooltips */
QToolTip {{
    background-color: {COLOR_SURFACE};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    padding: 5px 8px;
    border-radius: 4px;
    font-size: 11px;
}}

/* Menu Bar & Menus */
QMenuBar {{
    background-color: {COLOR_PANEL};
    color: {COLOR_TEXT};
    border-bottom: 1px solid {COLOR_BORDER};
    padding: 2px 6px;
    font-size: 12px;
}}

QMenuBar::item {{
    background: transparent;
    padding: 5px 9px;
    border-radius: 4px;
}}

QMenuBar::item:selected {{
    background-color: {COLOR_BTN_HOVER};
}}

QMenu {{
    background-color: {COLOR_PANEL};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 4px 0px;
}}

QMenu::item {{
    padding: 6px 26px 6px 22px;
}}

QMenu::item:selected {{
    background-color: {COLOR_ACCENT_MUTED};
    color: #ffffff;
}}

QMenu::separator {{
    height: 1px;
    background-color: {COLOR_BORDER};
    margin: 4px 8px;
}}

/* Dock Widgets */
QDockWidget {{
    font-weight: 600;
    font-size: 11px;
    titlebar-close-icon: url(none);
    titlebar-normal-icon: url(none);
}}

QDockWidget::title {{
    background-color: {COLOR_PANEL_ALT};
    color: {COLOR_TEXT_MUTED};
    padding: 6px 10px;
    border-top: 1px solid {COLOR_BORDER};
    border-bottom: 1px solid {COLOR_BORDER};
    text-align: left;
    font-size: 11px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}

QDockWidget::close-button, QDockWidget::float-button {{
    border: none;
    background: transparent;
    padding: 2px;
    subcontrol-position: top right;
    subcontrol-origin: margin;
    position: absolute;
    top: 2px; bottom: 2px;
    width: 18px;
}}

QDockWidget::close-button {{
    right: 6px;
}}

QDockWidget::float-button {{
    right: 26px;
}}

QDockWidget::close-button:hover, QDockWidget::float-button:hover {{
    background-color: {COLOR_BTN_HOVER};
    border-radius: 3px;
}}

/* Push Buttons */
QPushButton {{
    background-color: {COLOR_BTN};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 5px 12px;
    font-size: 12px;
    min-height: 18px;
}}

QPushButton:hover {{
    background-color: {COLOR_BTN_HOVER};
    border-color: {COLOR_BORDER_LIGHT};
    color: #ffffff;
}}

QPushButton:pressed {{
    background-color: {COLOR_BTN_PRESSED};
    border-color: {COLOR_BORDER};
}}

QPushButton:checked {{
    background-color: {COLOR_ACCENT_MUTED};
    border: 1px solid {COLOR_ACCENT};
    color: #ffffff;
    font-weight: 600;
}}

QPushButton:disabled {{
    background-color: {COLOR_PANEL_ALT};
    color: {COLOR_TEXT_MUTED};
    border-color: {COLOR_BORDER};
}}

/* Tool Buttons */
QToolButton {{
    background-color: {COLOR_BTN};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 4px;
    margin: 1px;
}}

QToolButton:hover {{
    background-color: {COLOR_BTN_HOVER};
    border-color: {COLOR_BORDER_LIGHT};
}}

QToolButton:pressed {{
    background-color: {COLOR_BTN_PRESSED};
    border-color: {COLOR_BORDER};
}}

QToolButton:checked {{
    background-color: {COLOR_ACCENT_MUTED};
    border: 1px solid {COLOR_ACCENT};
}}

/* Tool Options Slim Header Bar */
#toolOptionsBar {{
    background-color: {COLOR_PANEL};
    border-bottom: 1px solid {COLOR_BORDER};
    min-height: 32px;
    max-height: 34px;
}}

/* Line Edits & Spinboxes */
QLineEdit, QSpinBox {{
    background-color: {COLOR_BASE};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 3px 6px;
    min-height: 20px;
    selection-background-color: {COLOR_ACCENT};
    selection-color: #ffffff;
}}

QLineEdit:focus, QSpinBox:focus {{
    border-color: {COLOR_ACCENT};
}}

/* Combo Box */
QComboBox {{
    background-color: {COLOR_BTN};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 3px 8px;
    min-height: 20px;
}}

QComboBox:hover {{
    border-color: {COLOR_BORDER_LIGHT};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 18px;
    border-left: 1px solid {COLOR_BORDER};
}}

QComboBox QAbstractItemView {{
    background-color: {COLOR_PANEL};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    selection-background-color: {COLOR_ACCENT};
    selection-color: #ffffff;
    padding: 2px;
}}

/* Sliders */
QSlider::groove:horizontal {{
    border: 1px solid {COLOR_BORDER};
    height: 4px;
    background: {COLOR_BASE};
    border-radius: 2px;
}}

QSlider::sub-page:horizontal {{
    background: {COLOR_ACCENT};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: #d4d4d4;
    border: 1px solid {COLOR_BORDER};
    width: 12px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 6px;
}}

QSlider::handle:horizontal:hover {{
    background: #ffffff;
    border-color: {COLOR_ACCENT};
}}

/* Checkboxes (native Fusion tick is kept so checked state is always visible) */
QCheckBox {{
    spacing: 6px;
    color: {COLOR_TEXT};
}}

QCheckBox:disabled {{
    color: {COLOR_TEXT_MUTED};
}}

/* Dialogs */
QDialog {{
    background-color: {COLOR_PANEL};
}}

QDialog QLabel {{
    color: {COLOR_TEXT};
}}

QMessageBox {{
    background-color: {COLOR_PANEL};
}}

QInputDialog {{
    background-color: {COLOR_PANEL};
}}

/* List Views & Tables */
QListView, QTableWidget {{
    background-color: {COLOR_BASE};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    gridline-color: {COLOR_BORDER};
    outline: none;
}}

QListView::item {{
    border-radius: 3px;
    margin: 1px 2px;
}}

QListView::item:hover, QTableWidget::item:hover {{
    background-color: {COLOR_BTN};
}}

QListView::item:selected, QTableWidget::item:selected {{
    background-color: {COLOR_ACCENT_MUTED};
    color: #ffffff;
    border-left: 2px solid {COLOR_ACCENT};
}}

/* ScrollBars */
QScrollBar:vertical {{
    background-color: transparent;
    width: 8px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background-color: #383838;
    min-height: 24px;
    border-radius: 4px;
    margin: 1px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: #4c4c4c;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    background: transparent;
}}

QScrollBar:horizontal {{
    background-color: transparent;
    height: 8px;
    margin: 0px;
}}

QScrollBar::handle:horizontal {{
    background-color: #383838;
    min-width: 24px;
    border-radius: 4px;
    margin: 1px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: #4c4c4c;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
    background: transparent;
}}

/* Multi-Segment Status Bar */
QStatusBar {{
    background-color: {COLOR_PANEL_ALT};
    color: {COLOR_TEXT_MUTED};
    border-top: 1px solid {COLOR_BORDER};
    padding: 1px 6px;
    font-size: 11px;
}}

QStatusBar QLabel {{
    background: transparent;
    color: {COLOR_TEXT_MUTED};
    padding: 2px 10px;
    border-right: 1px solid {COLOR_BORDER};
    font-size: 11px;
    font-family: Consolas, "Segoe UI Mono", monospace;
}}

QStatusBar QLabel:last-child {{
    border-right: none;
}}

/* Dock Tab Stacking */
QTabWidget::pane {{
    border: 1px solid {COLOR_BORDER};
    background-color: {COLOR_PANEL};
    border-radius: 4px;
}}

QTabBar::tab {{
    background-color: {COLOR_BASE};
    color: {COLOR_TEXT_MUTED};
    padding: 5px 12px;
    border: 1px solid {COLOR_BORDER};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background-color: {COLOR_PANEL};
    color: #ffffff;
    border-top: 2px solid {COLOR_ACCENT};
}}

QTabBar::tab:hover:!selected {{
    background-color: {COLOR_BTN_HOVER};
    color: {COLOR_TEXT};
}}
"""


def setup_hidpi_support() -> None:
    """Enables HiDPI scaling attributes before QApplication initialization."""
    if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    if hasattr(Qt.HighDpiScaleFactorRoundingPolicy, "PassThrough"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )


def _build_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLOR_BASE))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLOR_TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLOR_PANEL))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLOR_PANEL_ALT))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(COLOR_SURFACE))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(COLOR_TEXT))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLOR_TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLOR_BTN))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLOR_TEXT))
    palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLOR_ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(COLOR_TEXT_MUTED))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(COLOR_TEXT_MUTED))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(COLOR_TEXT_MUTED)
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(COLOR_TEXT_MUTED)
    )
    return palette


def apply_theme(app: QApplication, theme: str = "dark") -> None:
    """
    Applies the application theme.

    :param app: Active QApplication instance.
    :param theme: ``"dark"`` for the studio dark theme, ``"fusion"`` for the
        default Fusion look with the same dark color palette.
    """
    app.setStyle("Fusion")
    app.setPalette(_build_palette())
    app.setStyleSheet(DARK_THEME_QSS if theme == "dark" else "")


def apply_dark_theme(app: QApplication) -> None:
    """Backwards compatible helper applying the default dark theme."""
    apply_theme(app, "dark")
