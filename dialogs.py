"""
ThisIsPixel - Dialogs & Preferences
===================================
1. PreferencesDialog: theme, default zoom, autosave, default canvas, grid
   defaults, tile size, default export scale and a shortcut reference.
2. NewProjectDialog: canvas dimensions with presets and remembered size.

Settings persist through QSettings ("ThisIsPixel", "EditorSettings").
"""

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QLabel,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)

from app_settings import create_settings
from version import APP_VERSION


SHORTCUT_REFERENCE = [
    ("Pencil Tool", "B"),
    ("Eraser Tool", "E"),
    ("Straight Line Tool", "L"),
    ("Rectangle Tool", "U"),
    ("Ellipse Tool", "O"),
    ("Bucket Fill", "G"),
    ("Eyedropper", "I / Alt+Click"),
    ("Marquee Selection", "M"),
    ("Spray", "S"),
    ("Deselect", "Esc / Ctrl+D"),
    ("Select All", "Ctrl+A"),
    ("Delete Selection", "Delete / Backspace"),
    ("Copy / Cut / Paste", "Ctrl+C / Ctrl+X / Ctrl+V"),
    ("Zoom In / Out", "Ctrl + / Ctrl - / Ctrl+Wheel"),
    ("Zoom to Fit", "Ctrl+0"),
    ("Pan Canvas", "Space + Drag / Middle Click"),
    ("Radial Menu", "Right Click"),
    ("Undo / Redo", "Ctrl+Z / Ctrl+Y"),
    ("New Project", "Ctrl+N"),
    ("Open Project (.pxp)", "Ctrl+O"),
    ("Save Project", "Ctrl+S"),
    ("Save As", "Ctrl+Shift+S"),
    ("Export PNG", "Ctrl+E"),
    ("Export Sprite Sheet", "Ctrl+Shift+E"),
    ("Preferences", "Ctrl+,"),
]


class PreferencesDialog(QDialog):
    """Application preferences."""

    settings_saved = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Preferences - ThisIsPixel")
        self.resize(560, 480)
        self.settings = create_settings()
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()

        # --- General --------------------------------------------------- #
        tab_general = QWidget()
        gen_layout = QVBoxLayout(tab_general)

        gen_layout.addWidget(QLabel("Visual Theme:"))
        self.combo_theme = QComboBox()
        self.combo_theme.addItem("Dark Modern (Default)", "dark")
        self.combo_theme.addItem("Classic Fusion", "fusion")
        theme = str(self.settings.value("theme", "dark"))
        self.combo_theme.setCurrentIndex(max(0, self.combo_theme.findData(theme)))
        gen_layout.addWidget(self.combo_theme)

        gen_layout.addWidget(QLabel("Initial zoom for new projects (0 = fit to window):"))
        self.spin_zoom = QSpinBox()
        self.spin_zoom.setRange(0, 3200)
        self.spin_zoom.setSingleStep(100)
        self.spin_zoom.setSpecialValueText("Fit to window")
        self.spin_zoom.setValue(int(self.settings.value("default_zoom", 0)))
        gen_layout.addWidget(self.spin_zoom)

        gen_layout.addWidget(QLabel("Autosave interval (minutes, 0 = disabled):"))
        self.spin_autosave = QSpinBox()
        self.spin_autosave.setRange(0, 60)
        self.spin_autosave.setValue(int(self.settings.value("autosave_interval", 5)))
        gen_layout.addWidget(self.spin_autosave)
        hint = QLabel(
            "Autosave writes a copy next to the current project: <i>name.pxp.autosave</i>"
        )
        hint.setStyleSheet("color: #888888; font-size: 10px;")
        hint.setWordWrap(True)
        gen_layout.addWidget(hint)
        gen_layout.addStretch()
        self.tab_widget.addTab(tab_general, "General")

        # --- Canvas ---------------------------------------------------- #
        tab_canvas = QWidget()
        can_layout = QVBoxLayout(tab_canvas)

        can_layout.addWidget(QLabel("Default canvas size for new projects:"))
        size_layout = QHBoxLayout()
        self.spin_w = QSpinBox()
        self.spin_w.setRange(1, 4096)
        self.spin_w.setValue(int(self.settings.value("default_width", 32)))
        self.spin_h = QSpinBox()
        self.spin_h.setRange(1, 4096)
        self.spin_h.setValue(int(self.settings.value("default_height", 32)))
        size_layout.addWidget(QLabel("Width:"))
        size_layout.addWidget(self.spin_w)
        size_layout.addWidget(QLabel("Height:"))
        size_layout.addWidget(self.spin_h)
        can_layout.addLayout(size_layout)

        self.check_pixel_grid = QCheckBox("Show pixel grid by default")
        self.check_pixel_grid.setChecked(
            self.settings.value("show_pixel_grid", True, type=bool)
        )
        can_layout.addWidget(self.check_pixel_grid)

        self.check_tile_grid = QCheckBox("Show tile grid by default")
        self.check_tile_grid.setChecked(
            self.settings.value("show_tile_grid", False, type=bool)
        )
        can_layout.addWidget(self.check_tile_grid)

        tile_layout = QHBoxLayout()
        tile_layout.addWidget(QLabel("Tile grid size (px):"))
        self.spin_tile = QSpinBox()
        self.spin_tile.setRange(2, 256)
        self.spin_tile.setValue(int(self.settings.value("tile_size", 8)))
        tile_layout.addWidget(self.spin_tile)
        can_layout.addLayout(tile_layout)

        self.check_autofit = QCheckBox("Fit canvas to window when opening a project")
        self.check_autofit.setChecked(
            self.settings.value("autofit_on_open", True, type=bool)
        )
        can_layout.addWidget(self.check_autofit)
        can_layout.addStretch()
        self.tab_widget.addTab(tab_canvas, "Canvas")

        # --- Shortcuts -------------------------------------------------- #
        tab_shortcuts = QWidget()
        sc_layout = QVBoxLayout(tab_shortcuts)
        table_sc = QTableWidget()
        table_sc.setColumnCount(2)
        table_sc.setHorizontalHeaderLabels(["Action / Tool", "Shortcut Key"])
        table_sc.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table_sc.setRowCount(len(SHORTCUT_REFERENCE))
        for row, (action, key) in enumerate(SHORTCUT_REFERENCE):
            table_sc.setItem(row, 0, QTableWidgetItem(action))
            table_sc.setItem(row, 1, QTableWidgetItem(key))
        table_sc.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        sc_layout.addWidget(table_sc)
        self.tab_widget.addTab(tab_shortcuts, "Shortcuts")

        # --- Files ------------------------------------------------------ #
        tab_files = QWidget()
        file_layout = QVBoxLayout(tab_files)

        file_layout.addWidget(QLabel("Default export scale:"))
        self.combo_export_scale = QComboBox()
        for scale in (1, 2, 4, 8, 16, 32):
            self.combo_export_scale.addItem(f"{scale}x", scale)
        self.combo_export_scale.setCurrentIndex(
            max(0, self.combo_export_scale.findData(
                int(self.settings.value("default_export_scale", 8))
            ))
        )
        file_layout.addWidget(self.combo_export_scale)
        info = QLabel(
            "PNG exports always use nearest-neighbour scaling so pixels stay crisp."
        )
        info.setStyleSheet("color: #888888; font-size: 10px;")
        info.setWordWrap(True)
        file_layout.addWidget(info)
        file_layout.addStretch()
        self.tab_widget.addTab(tab_files, "Files")

        layout.addWidget(self.tab_widget)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_save = QPushButton("Save")
        btn_cancel = QPushButton("Cancel")
        btn_save.clicked.connect(self._save_settings)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)

    def _save_settings(self) -> None:
        self.settings.setValue("theme", self.combo_theme.currentData())
        self.settings.setValue("default_zoom", self.spin_zoom.value())
        self.settings.setValue("autosave_interval", self.spin_autosave.value())
        self.settings.setValue("default_width", self.spin_w.value())
        self.settings.setValue("default_height", self.spin_h.value())
        self.settings.setValue("show_pixel_grid", self.check_pixel_grid.isChecked())
        self.settings.setValue("show_tile_grid", self.check_tile_grid.isChecked())
        self.settings.setValue("tile_size", self.spin_tile.value())
        self.settings.setValue("autofit_on_open", self.check_autofit.isChecked())
        self.settings.setValue("default_export_scale", self.combo_export_scale.currentData())
        self.settings.sync()
        self.settings_saved.emit()
        self.accept()


class NewProjectDialog(QDialog):
    """New document dialog with presets and remembered dimensions."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("New Project - ThisIsPixel")
        self.resize(340, 240)
        self.settings = create_settings()
        self.canvas_width = int(self.settings.value("last_width", 32))
        self.canvas_height = int(self.settings.value("last_height", 32))
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Canvas dimensions (1 - 4096 px):"))

        size_layout = QHBoxLayout()
        self.spin_w = QSpinBox()
        self.spin_w.setRange(1, 4096)
        self.spin_w.setValue(max(1, min(4096, self.canvas_width)))
        self.spin_h = QSpinBox()
        self.spin_h.setRange(1, 4096)
        self.spin_h.setValue(max(1, min(4096, self.canvas_height)))
        size_layout.addWidget(QLabel("Width:"))
        size_layout.addWidget(self.spin_w)
        size_layout.addWidget(QLabel("Height:"))
        size_layout.addWidget(self.spin_h)
        layout.addLayout(size_layout)

        layout.addWidget(QLabel("Standard presets:"))
        preset_layout = QHBoxLayout()
        for size in (16, 32, 64, 128, 256):
            button = QPushButton(f"{size}²")
            button.clicked.connect(lambda _, value=size: self._set_preset(value))
            preset_layout.addWidget(button)
        layout.addLayout(preset_layout)

        layout.addStretch()

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Create Canvas")
        btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(self._accept_values)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_ok)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)

    def _set_preset(self, size: int) -> None:
        self.spin_w.setValue(size)
        self.spin_h.setValue(size)

    def _accept_values(self) -> None:
        self.canvas_width = self.spin_w.value()
        self.canvas_height = self.spin_h.value()
        self.settings.setValue("last_width", self.canvas_width)
        self.settings.setValue("last_height", self.canvas_height)
        self.accept()


class WelcomeDialog(QDialog):
    """Friendly first-run guide (Indonesian) written for non-technical users."""

    def __init__(self, parent: Optional[QWidget] = None, first_run: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Panduan & Tips - ThisIsPixel")
        self.setMinimumSize(560, 470)
        self._first_run = first_run
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        title = QLabel(f"Selamat datang di <b>ThisIsPixel {APP_VERSION}</b>")
        title.setStyleSheet("font-size: 16px; color: #ffffff;")
        layout.addWidget(title)

        intro = QLabel(
            "Editor pixel art dan animasi sprite yang ringan. Semua yang Anda gambar "
            "disimpan di komputer Anda sendiri."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #b8b8b8;")
        layout.addWidget(intro)

        guide = QLabel(
            "<p style='margin-top:6px'><b>Langkah cepat</b></p>"
            "<ol style='margin-top:2px; margin-left:-18px'>"
            "<li><b>Pilih alat</b> di panel kiri (Pensil, Penghapus, Garis, Persegi, "
            "Elips, Ember, Pipet, Seleksi, Semprot).</li>"
            "<li><b>Klik atau seret</b> di kanvas untuk menggambar. "
            "Ukuran kuas diatur di bar atas.</li>"
            "<li><b>Ctrl+Z</b> membatalkan, <b>Ctrl+Shift+Z</b> mengulangi.</li>"
            "<li><b>Layer</b> ada di kanan, <b>frame animasi</b> di bawah. "
            "Aktifkan <i>Onion Skin</i> untuk melihat frame sebelumnya.</li>"
            "<li><b>Ctrl+S</b> menyimpan proyek <b>.pxp</b> (bisa diedit lagi).</li>"
            "<li><b>Ctrl+E</b> mengekspor gambar <b>PNG</b>, "
            "<b>Ctrl+Shift+E</b> mengekspor sprite sheet.</li>"
            "</ol>"
            "<p><b>Tenang, pekerjaan Anda aman.</b> Autosave berjalan berkala dan "
            "bila aplikasi tertutup mendadak, Anda akan ditawari pemulihan saat "
            "dibuka kembali.</p>"
            "<p style='color:#9a9a9a'>Panduan ini bisa dibuka lagi dari menu "
            "<b>Help &rsaquo; Panduan &amp; Tips</b>.</p>"
        )
        guide.setWordWrap(True)
        guide.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(guide, 1)

        self.check_skip = QCheckBox("Jangan tampilkan panduan ini lagi")
        self.check_skip.setChecked(True)
        self.check_skip.setVisible(self._first_run)
        layout.addWidget(self.check_skip)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_start = QPushButton("Mulai Menggambar")
        btn_start.setDefault(True)
        btn_start.clicked.connect(self.accept)
        buttons.addWidget(btn_start)
        layout.addLayout(buttons)

    def should_skip_next_time(self) -> bool:
        """True when the user asked not to see the guide on startup again."""
        return self._first_run and self.check_skip.isChecked()
