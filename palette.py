"""
ThisIsPixel - Embedded Color Selector & Palette Panel
=====================================================
All-in-one color dock:

1. Interactive Saturation/Value area and rainbow Hue bar.
2. Live preview, hex editor (RRGGBB / AARRGGBB) and RGB readout.
3. 8-column swatch grid with Palette / Recent tabs.
4. Import & export of GIMP (.gpl) and JASC (.pal) palettes.
5. Signals keep the document palette and canvas radial menu in sync:
   - ``palette_changed(list[QColor])`` whenever the saved palette changes,
   - ``recent_colors_changed(list[QColor])`` for the radial menu.
"""

from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QPointF, QRectF
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QBrush,
    QPixmap,
    QLinearGradient,
    QMouseEvent,
)
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QScrollArea,
    QMenu,
    QFileDialog,
    QButtonGroup,
    QMessageBox,
    QFrame,
)

# Standard 32-color default palette (DawnBringer-like 32)
DEFAULT_PALETTE_32: List[str] = [
    "#000000", "#222034", "#45283c", "#663931", "#8f563b", "#df7126", "#d9a066", "#eec39a",
    "#fbf236", "#99e550", "#6abe30", "#37946e", "#4b692f", "#524b24", "#323c39", "#3f3f74",
    "#306082", "#5b6ee1", "#639bff", "#5fcde4", "#cbdbfc", "#ffffff", "#9badb7", "#847e87",
    "#696a6a", "#595652", "#76428a", "#ac3232", "#d95763", "#d77bba", "#8f974a", "#8a6f30",
]

MAX_RECENT_COLORS = 10


class SaturationValueArea(QWidget):
    """2D saturation (X) / value (Y) picker."""

    sv_changed = pyqtSignal(float, float)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(160, 110)
        self.setMaximumHeight(130)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self.hue: float = 0.0
        self.saturation: float = 1.0
        self.val: float = 1.0
        self.is_dragging: bool = False

    def set_hsv(self, h: float, s: float, v: float) -> None:
        self.hue = max(0.0, min(359.0, h))
        self.saturation = max(0.0, min(1.0, s))
        self.val = max(0.0, min(1.0, v))
        self.update()

    def set_hue(self, h: float) -> None:
        self.hue = max(0.0, min(359.0, h))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width, height = self.width(), self.height()

        base_color = QColor.fromHsvF(self.hue / 360.0, 1.0, 1.0)
        h_grad = QLinearGradient(0, 0, width, 0)
        h_grad.setColorAt(0.0, QColor(255, 255, 255))
        h_grad.setColorAt(1.0, base_color)
        painter.fillRect(0, 0, width, height, QBrush(h_grad))

        v_grad = QLinearGradient(0, 0, 0, height)
        v_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        v_grad.setColorAt(1.0, QColor(0, 0, 0, 255))
        painter.fillRect(0, 0, width, height, QBrush(v_grad))

        painter.setPen(QPen(QColor("#333333"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(0, 0, width - 1, height - 1)

        cx = self.saturation * (width - 1)
        cy = (1.0 - self.val) * (height - 1)
        painter.setPen(QPen(QColor(0, 0, 0, 200), 2))
        painter.drawEllipse(QPointF(cx, cy), 5, 5)
        painter.setPen(QPen(QColor(255, 255, 255, 240), 1.5))
        painter.drawEllipse(QPointF(cx, cy), 4, 4)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self._update_from_pos(event.pos())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.is_dragging:
            self._update_from_pos(event.pos())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            # Re-emit once so the final color is committed to the recent list.
            self.sv_changed.emit(self.saturation, self.val)

    def _update_from_pos(self, pos: QPoint) -> None:
        width = max(1, self.width() - 1)
        height = max(1, self.height() - 1)
        self.saturation = max(0.0, min(1.0, pos.x() / width))
        self.val = max(0.0, min(1.0, 1.0 - (pos.y() / height)))
        self.update()
        self.sv_changed.emit(self.saturation, self.val)


class HueBar(QWidget):
    """Horizontal rainbow bar for hue selection (0..359)."""

    hue_changed = pyqtSignal(float)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(15)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hue: float = 0.0
        self.is_dragging: bool = False

    def set_hue(self, h: float) -> None:
        self.hue = max(0.0, min(359.0, h))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        width, height = self.width(), self.height()

        grad = QLinearGradient(0, 0, width, 0)
        steps = 12
        for i in range(steps + 1):
            t = i / steps
            grad.setColorAt(t, QColor.fromHsvF(0.0 if t >= 1.0 else t, 1.0, 1.0))
        painter.fillRect(0, 0, width, height, QBrush(grad))

        painter.setPen(QPen(QColor("#333333"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(0, 0, width - 1, height - 1)

        hx = (self.hue / 359.0) * (width - 1)
        painter.setPen(QPen(QColor("#000000"), 2))
        painter.drawLine(int(hx), 0, int(hx), height - 1)
        painter.setPen(QPen(QColor("#ffffff"), 1.5))
        painter.drawLine(int(hx), 1, int(hx), height - 2)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self._update_from_pos(event.pos())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.is_dragging:
            self._update_from_pos(event.pos())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            self.hue_changed.emit(self.hue)

    def _update_from_pos(self, pos: QPoint) -> None:
        width = max(1, self.width() - 1)
        self.hue = max(0.0, min(359.0, (pos.x() / width) * 359.0))
        self.update()
        self.hue_changed.emit(self.hue)


class ColorSwatch(QWidget):
    """18x18 color swatch with left click select / right click menu."""

    clicked = pyqtSignal(QColor)
    right_clicked = pyqtSignal(QColor, QPoint)

    def __init__(self, color: QColor, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.color = QColor(color)
        self.setFixedSize(18, 18)
        self.setToolTip(f"{self.color.name().upper()}\n(Left click: select, Right click: options)")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QBrush(self.color))
        painter.setPen(QPen(QColor("#363636"), 1))
        painter.drawRoundedRect(QRectF(1, 1, 16, 16), 3, 3)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.color)
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(self.color, event.globalPosition().toPoint())


class PalettePanel(QWidget):
    """Embedded color selector + palette manager."""

    color_changed = pyqtSignal(QColor)
    palette_changed = pyqtSignal(list)
    recent_colors_changed = pyqtSignal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.active_color: QColor = QColor("#000000")
        self.palette_colors: List[QColor] = [QColor(h) for h in DEFAULT_PALETTE_32]
        self.recent_colors: List[QColor] = [QColor(h) for h in DEFAULT_PALETTE_32[:8]]
        self.showing_recent: bool = False

        self._init_ui()
        self._rebuild_grid()
        self.set_active_color(self.active_color, add_recent=False)

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        selector_container = QFrame()
        selector_container.setStyleSheet(
            "QFrame { background-color: #1e1e1e; border: 1px solid #333333; border-radius: 4px; padding: 4px; }"
        )
        sel_layout = QVBoxLayout(selector_container)
        sel_layout.setContentsMargins(4, 4, 4, 4)
        sel_layout.setSpacing(6)

        self.sv_area = SaturationValueArea()
        self.sv_area.sv_changed.connect(self._on_sv_changed)
        sel_layout.addWidget(self.sv_area)

        self.hue_bar = HueBar()
        self.hue_bar.hue_changed.connect(self._on_hue_changed)
        sel_layout.addWidget(self.hue_bar)
        main_layout.addWidget(selector_container)

        info_bar = QHBoxLayout()
        info_bar.setSpacing(6)

        self.color_preview = QLabel()
        self.color_preview.setFixedSize(36, 26)
        self.color_preview.setStyleSheet("border: 1px solid #404040; border-radius: 4px;")
        info_bar.addWidget(self.color_preview)

        self.hex_input = QLineEdit("#000000")
        self.hex_input.setMaxLength(9)
        self.hex_input.setFixedWidth(78)
        self.hex_input.setToolTip("Hex color: RRGGBB or AARRGGBB, then press Enter")
        self.hex_input.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; font-weight: bold; text-align: center;"
        )
        self.hex_input.returnPressed.connect(self._on_hex_submitted)
        info_bar.addWidget(self.hex_input)

        self.rgb_label = QLabel("R:0 G:0 B:0")
        self.rgb_label.setStyleSheet("font-size: 10px; color: #888888; font-family: monospace;")
        info_bar.addWidget(self.rgb_label)
        info_bar.addStretch()
        main_layout.addLayout(info_bar)

        toggle_layout = QHBoxLayout()
        toggle_layout.setSpacing(4)
        self.btn_tab_palette = QPushButton("Palette (32)")
        self.btn_tab_palette.setCheckable(True)
        self.btn_tab_palette.setChecked(True)
        self.btn_tab_recent = QPushButton("Recent (10)")
        self.btn_tab_recent.setCheckable(True)

        tab_group = QButtonGroup(self)
        tab_group.setExclusive(True)
        tab_group.addButton(self.btn_tab_palette)
        tab_group.addButton(self.btn_tab_recent)

        self.btn_tab_palette.clicked.connect(lambda: self._set_mode(False))
        self.btn_tab_recent.clicked.connect(lambda: self._set_mode(True))
        toggle_layout.addWidget(self.btn_tab_palette)
        toggle_layout.addWidget(self.btn_tab_recent)
        main_layout.addLayout(toggle_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            "QScrollArea { border: 1px solid #333333; background: #1b1b1b; border-radius: 4px; }"
        )
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(6, 6, 6, 6)
        self.grid_layout.setSpacing(3)
        self.scroll_area.setWidget(self.grid_container)
        main_layout.addWidget(self.scroll_area, 1)

        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(4)
        self.btn_add_swatch = QPushButton("+ Swatch")
        self.btn_add_swatch.setToolTip("Add the active color to the palette")
        self.btn_add_swatch.clicked.connect(self._add_current_color_to_palette)
        self.btn_load_palette = QPushButton("Load")
        self.btn_load_palette.setToolTip("Load a .gpl or .pal palette file")
        self.btn_load_palette.clicked.connect(self._load_palette_dialog)
        self.btn_save_palette = QPushButton("Save")
        self.btn_save_palette.setToolTip("Save the palette as .gpl or .pal")
        self.btn_save_palette.clicked.connect(self._save_palette_dialog)
        btn_bar.addWidget(self.btn_add_swatch)
        btn_bar.addWidget(self.btn_load_palette)
        btn_bar.addWidget(self.btn_save_palette)
        main_layout.addLayout(btn_bar)

    # ------------------------------------------------------------------ #
    # Palette state
    # ------------------------------------------------------------------ #
    def palette(self) -> List[QColor]:
        return [QColor(c) for c in self.palette_colors]

    def set_palette(self, colors: List[QColor]) -> None:
        """Replaces the working palette (used when a project is loaded)."""
        valid = [QColor(c) for c in colors if QColor(c).isValid()]
        if not valid:
            return
        self.palette_colors = valid
        self._rebuild_grid()
        self.palette_changed.emit(self.palette())

    def _emit_palette_changed(self) -> None:
        self.palette_changed.emit(self.palette())

    def _set_mode(self, showing_recent: bool) -> None:
        self.showing_recent = showing_recent
        self._rebuild_grid()

    def _rebuild_grid(self) -> None:
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        colors = self.recent_colors if self.showing_recent else self.palette_colors
        columns = 8
        for idx, color in enumerate(colors):
            swatch = ColorSwatch(color)
            swatch.clicked.connect(self.set_active_color)
            swatch.right_clicked.connect(self._on_swatch_context_menu)
            self.grid_layout.addWidget(swatch, idx // columns, idx % columns)

        self.btn_tab_palette.setText(f"Palette ({len(self.palette_colors)})")
        self.btn_tab_recent.setText(f"Recent ({len(self.recent_colors)})")

    # ------------------------------------------------------------------ #
    # Color picker
    # ------------------------------------------------------------------ #
    def _on_sv_changed(self, s: float, v: float) -> None:
        color = QColor.fromHsvF(self.hue_bar.hue / 360.0, s, v)
        self._update_color_internal(
            color, update_sv=False, update_hue=False, add_recent=not self.sv_area.is_dragging
        )

    def _on_hue_changed(self, h: float) -> None:
        self.sv_area.set_hue(h)
        color = QColor.fromHsvF(h / 360.0, self.sv_area.saturation, self.sv_area.val)
        self._update_color_internal(
            color, update_sv=False, update_hue=False, add_recent=not self.hue_bar.is_dragging
        )

    def _on_hex_submitted(self) -> None:
        text = self.hex_input.text().strip()
        if not text.startswith("#"):
            text = "#" + text
        color = QColor(text)
        if color.isValid():
            self.set_active_color(color)
        else:
            self.hex_input.setText(self.active_color.name().upper())

    def _update_color_internal(
        self,
        color: QColor,
        update_sv: bool = True,
        update_hue: bool = True,
        add_recent: bool = True,
    ) -> None:
        if not color.isValid():
            return
        self.active_color = QColor(color)

        pixmap = QPixmap(36, 26)
        pixmap.fill(self.active_color)
        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor("#404040"), 1))
        painter.drawRect(0, 0, 35, 25)
        painter.end()
        self.color_preview.setPixmap(pixmap)

        hex_str = self.active_color.name().upper()
        if self.active_color.alpha() < 255:
            hex_str = self.active_color.name(QColor.NameFormat.HexArgb).upper()
        if self.hex_input.text().upper() != hex_str:
            self.hex_input.setText(hex_str)
        self.rgb_label.setText(
            f"R:{self.active_color.red()} G:{self.active_color.green()} "
            f"B:{self.active_color.blue()} A:{self.active_color.alpha()}"
        )

        hue = max(0.0, self.active_color.hueF()) * 360.0
        saturation = self.active_color.saturationF()
        value = self.active_color.valueF()

        if update_hue and self.active_color.saturation() > 0:
            self.hue_bar.set_hue(hue)
            self.sv_area.set_hue(hue)
        if update_sv:
            self.sv_area.set_hsv(self.hue_bar.hue, saturation, value)

        if add_recent:
            self._add_recent_color(self.active_color)

        self.color_changed.emit(self.active_color)

    def _add_recent_color(self, color: QColor) -> None:
        opaque = QColor(color)
        opaque.setAlpha(255)
        if opaque not in self.recent_colors:
            self.recent_colors.insert(0, opaque)
            del self.recent_colors[MAX_RECENT_COLORS:]
            self.recent_colors_changed.emit([QColor(c) for c in self.recent_colors])
            if self.showing_recent:
                self._rebuild_grid()
            else:
                self.btn_tab_recent.setText(f"Recent ({len(self.recent_colors)})")

    def set_active_color(self, color: QColor, add_recent: bool = True) -> None:
        """Sets the active color and syncs the picker (used by swatches/eyedropper)."""
        self._update_color_internal(color, update_sv=True, update_hue=True, add_recent=add_recent)

    def _add_current_color_to_palette(self) -> None:
        color = QColor(self.active_color)
        if color not in self.palette_colors:
            self.palette_colors.append(color)
            self._rebuild_grid()
            self._emit_palette_changed()

    def _on_swatch_context_menu(self, color: QColor, global_pos: QPoint) -> None:
        menu = QMenu(self)
        action_replace = menu.addAction("Replace with Current Color")
        action_delete = menu.addAction("Delete Swatch")
        menu.addSeparator()
        action_use = menu.addAction("Use as Active Color")

        action = menu.exec(global_pos)
        if action == action_use:
            self.set_active_color(color)
        elif action == action_replace:
            if self.showing_recent:
                for idx, existing in enumerate(self.recent_colors):
                    if existing == color:
                        replacement = QColor(self.active_color)
                        replacement.setAlpha(255)
                        self.recent_colors[idx] = replacement
                        self.recent_colors_changed.emit([QColor(c) for c in self.recent_colors])
                        break
            else:
                for idx, existing in enumerate(self.palette_colors):
                    if existing == color:
                        self.palette_colors[idx] = QColor(self.active_color)
                        self._emit_palette_changed()
                        break
            self._rebuild_grid()
        elif action == action_delete:
            if self.showing_recent:
                if color in self.recent_colors:
                    self.recent_colors.remove(color)
                    self.recent_colors_changed.emit([QColor(c) for c in self.recent_colors])
                    self._rebuild_grid()
            elif color in self.palette_colors and len(self.palette_colors) > 1:
                self.palette_colors.remove(color)
                self._rebuild_grid()
                self._emit_palette_changed()

    # ------------------------------------------------------------------ #
    # Palette file I/O
    # ------------------------------------------------------------------ #
    def _load_palette_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Palette File", "", "Palette Files (*.gpl *.pal);;All Files (*)"
        )
        if not path:
            return

        loaded_colors: List[QColor] = []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                lines = [line.strip() for line in handle.readlines()]

            if path.lower().endswith(".gpl"):
                for line in lines:
                    if not line or line.startswith("#") or line.startswith("GIMP") or ":" in line:
                        continue
                    parts = line.split()
                    if len(parts) >= 3 and all(part.isdigit() for part in parts[:3]):
                        loaded_colors.append(
                            QColor(int(parts[0]), int(parts[1]), int(parts[2]))
                        )
            elif path.lower().endswith(".pal"):
                data_lines = [line for line in lines if line and not line.startswith("#")]
                if len(data_lines) >= 3 and data_lines[0].upper() == "JASC-PAL":
                    count = int(data_lines[2])
                    for line in data_lines[3 : 3 + count]:
                        parts = line.split()
                        if len(parts) >= 3:
                            loaded_colors.append(
                                QColor(int(parts[0]), int(parts[1]), int(parts[2]))
                            )

            if not loaded_colors:
                QMessageBox.warning(
                    self, "Palette Load Failed", "No colors were found in the selected file."
                )
                return

            self.palette_colors = loaded_colors
            self.set_active_color(self.palette_colors[0])
            self._rebuild_grid()
            self._emit_palette_changed()
            QMessageBox.information(
                self, "Palette Loaded", f"Successfully loaded {len(loaded_colors)} colors."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Load Failed", f"Error loading palette file:\n{exc}")

    def _save_palette_dialog(self) -> None:
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Palette File",
            "my_palette.gpl",
            "GPL Palette (*.gpl);;JASC Palette (*.pal)",
        )
        if not path:
            return

        lower = path.lower()
        if not (lower.endswith(".gpl") or lower.endswith(".pal")):
            path += ".pal" if "JASC" in (selected_filter or "") else ".gpl"
            lower = path.lower()

        try:
            if lower.endswith(".gpl"):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("GIMP Palette\nName: ThisIsPixel Palette\nColumns: 8\n#\n")
                    for color in self.palette_colors:
                        handle.write(
                            f"{color.red():3d} {color.green():3d} {color.blue():3d}  {color.name()}\n"
                        )
            else:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(f"JASC-PAL\n0100\n{len(self.palette_colors)}\n")
                    for color in self.palette_colors:
                        handle.write(f"{color.red()} {color.green()} {color.blue()}\n")
            QMessageBox.information(self, "Palette Saved", f"Palette saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", f"Error saving palette file:\n{exc}")
