"""
ThisIsPixel - Drawing Tools & Tool Options Bar
==============================================
This module implements:
1. Tool Enumeration (9 tools):
   - Pencil (B): freehand drawing with brush size + opacity (source-over blending).
   - Eraser (E): erase pixels back to transparent.
   - Line (L): exact 1px straight line with live preview.
   - Rectangle (U): bounding rectangle (outline or filled).
   - Ellipse (O): bounding ellipse (outline or filled).
   - Bucket Fill (G): scanline flood fill with color tolerance.
   - Eyedropper (I / Alt+Click): sample a color.
   - Marquee (M): rectangular selection (move / copy / cut / paste).
   - Spray (S): random pixel scatter with density.
2. ToolOptionsBar: slim horizontal parameter options bar mounted above the canvas.
3. Procedural vector icon generator (no external asset dependencies).

All rasterization helpers are pure functions so they can be unit-tested without
a QApplication.
"""

import math
import random
from enum import Enum
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal, QRect
from PyQt6.QtGui import QColor, QPixmap, QPainter, QPen, QBrush, QIcon
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QCheckBox,
    QFrame,
)


class ToolType(Enum):
    """Complete enumeration of supported drawing and selection tools."""

    PENCIL = "Pencil"
    ERASER = "Eraser"
    LINE = "Line"
    RECTANGLE = "Rectangle"
    ELLIPSE = "Ellipse"
    BUCKET = "Bucket"
    EYEDROPPER = "Eyedropper"
    MARQUEE = "Marquee"
    SPRAY = "Spray"


#: Shortcut key per tool (single letter, matching the Tools menu actions).
TOOL_SHORTCUTS = {
    ToolType.PENCIL: "B",
    ToolType.ERASER: "E",
    ToolType.LINE: "L",
    ToolType.RECTANGLE: "U",
    ToolType.ELLIPSE: "O",
    ToolType.BUCKET: "G",
    ToolType.EYEDROPPER: "I",
    ToolType.MARQUEE: "M",
    ToolType.SPRAY: "S",
}


def create_tool_icon(tool: ToolType) -> QIcon:
    """Generates a 24x24 procedural vector QIcon using QPainter."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor("#cccccc"), 2)
    painter.setPen(pen)

    if tool == ToolType.PENCIL:
        pen.setColor(QColor("#3a78c4"))
        painter.setPen(pen)
        painter.drawLine(5, 19, 18, 6)
        painter.drawLine(18, 6, 19, 5)
        painter.drawLine(5, 19, 3, 21)

    elif tool == ToolType.ERASER:
        painter.setBrush(QBrush(QColor("#d9534f")))
        pen.setColor(QColor("#ffffff"))
        painter.setPen(pen)
        painter.drawRoundedRect(5, 7, 14, 10, 2, 2)

    elif tool == ToolType.LINE:
        pen.setColor(QColor("#e0e0e0"))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawLine(4, 20, 20, 4)

    elif tool == ToolType.RECTANGLE:
        pen.setColor(QColor("#e0e0e0"))
        painter.setPen(pen)
        painter.drawRect(5, 5, 14, 14)

    elif tool == ToolType.ELLIPSE:
        pen.setColor(QColor("#e0e0e0"))
        painter.setPen(pen)
        painter.drawEllipse(4, 4, 16, 16)

    elif tool == ToolType.BUCKET:
        pen.setColor(QColor("#c77838"))
        painter.setPen(pen)
        painter.drawRect(6, 8, 10, 10)
        painter.setBrush(QBrush(QColor("#c77838")))
        painter.drawEllipse(16, 16, 4, 4)

    elif tool == ToolType.EYEDROPPER:
        pen.setColor(QColor("#5cb85c"))
        painter.setPen(pen)
        painter.drawLine(6, 18, 16, 8)
        painter.drawEllipse(15, 6, 4, 4)

    elif tool == ToolType.MARQUEE:
        pen.setColor(QColor("#5bc0de"))
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(4, 4, 16, 16)

    elif tool == ToolType.SPRAY:
        painter.setBrush(QBrush(QColor("#b085f5")))
        painter.setPen(Qt.PenStyle.NoPen)
        coords = [(12, 12), (9, 8), (15, 7), (8, 14), (16, 15), (12, 6), (17, 11), (6, 11)]
        for cx, cy in coords:
            painter.drawEllipse(cx, cy, 2, 2)

    painter.end()
    return QIcon(pixmap)


# --- Geometry & Rasterization Algorithms ---

def bresenham_line(x0: int, y0: int, x1: int, y1: int) -> List[Tuple[int, int]]:
    """Bresenham's line algorithm returning every discrete pixel of the segment."""
    points: List[Tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return points


def get_brush_pixels(
    cx: int, cy: int, size: int, bounds_w: int, bounds_h: int
) -> List[Tuple[int, int]]:
    """Calculates all pixel coordinates covered by a square brush around (cx, cy)."""
    size = max(1, int(size))
    pixels: List[Tuple[int, int]] = []
    start = -(size // 2)
    for dy in range(start, start + size):
        py = cy + dy
        if not (0 <= py < bounds_h):
            continue
        for dx in range(start, start + size):
            px = cx + dx
            if 0 <= px < bounds_w:
                pixels.append((px, py))
    return pixels


def get_rectangle_pixels(
    x0: int, y0: int, x1: int, y1: int, filled: bool, bounds_w: int, bounds_h: int
) -> List[Tuple[int, int]]:
    """Generates discrete pixel coordinates for a bounding rectangle (outline or filled)."""
    min_x, max_x = min(x0, x1), max(x0, x1)
    min_y, max_y = min(y0, y1), max(y0, y1)
    pixels: List[Tuple[int, int]] = []

    for y in range(min_y, max_y + 1):
        if not (0 <= y < bounds_h):
            continue
        for x in range(min_x, max_x + 1):
            if not (0 <= x < bounds_w):
                continue
            if filled or x == min_x or x == max_x or y == min_y or y == max_y:
                pixels.append((x, y))
    return pixels


def _ellipse_spans(
    min_x: int, max_x: int, min_y: int, max_y: int
) -> List[Tuple[int, int, int]]:
    """
    Returns (y, left_x, right_x) spans of a pixel-perfect filled ellipse.

    The span based approach guarantees a connected, 1px outline when only the
    left/right edges of every row are kept.
    """
    rx = (max_x - min_x) / 2.0
    ry = (max_y - min_y) / 2.0
    cx = min_x + rx
    cy = min_y + ry

    if rx <= 0 or ry <= 0:
        return [(min_y, min_x, min_x)]

    spans: List[Tuple[int, int, int]] = []
    for y in range(min_y, max_y + 1):
        # Normalised distance of the row centre; clamp for numeric safety.
        ny = (y - cy) / ry
        inside = 1.0 - ny * ny
        if inside < 0.0:
            continue
        half = rx * math.sqrt(inside)
        left = int(round(cx - half))
        right = int(round(cx + half))
        left = max(min_x, min(max_x, left))
        right = max(min_x, min(max_x, right))
        spans.append((y, left, right))
    return spans


def get_ellipse_pixels(
    x0: int, y0: int, x1: int, y1: int, filled: bool, bounds_w: int, bounds_h: int
) -> List[Tuple[int, int]]:
    """Generates discrete pixel coordinates for a bounding ellipse (outline or filled)."""
    min_x, max_x = min(x0, x1), max(x0, x1)
    min_y, max_y = min(y0, y1), max(y0, y1)
    spans = _ellipse_spans(min_x, max_x, min_y, max_y)
    pixels: List[Tuple[int, int]] = []

    for index, (y, left, right) in enumerate(spans):
        if not (0 <= y < bounds_h):
            continue
        if filled:
            for x in range(left, right + 1):
                if 0 <= x < bounds_w:
                    pixels.append((x, y))
            continue

        # Top and bottom caps are drawn as full horizontal runs.
        if index in (0, len(spans) - 1):
            for x in range(left, right + 1):
                if 0 <= x < bounds_w:
                    pixels.append((x, y))
            continue

        if 0 <= left < bounds_w:
            pixels.append((left, y))
        if right != left and 0 <= right < bounds_w:
            pixels.append((right, y))

        # Connect the edge of this row to the previous row so the outline stays
        # continuous even for very flat ellipses.
        prev_y, prev_left, prev_right = spans[index - 1]
        if 0 <= prev_y < bounds_h:
            for x in range(min(left, prev_left) + 1, max(left, prev_left)):
                if 0 <= x < bounds_w:
                    pixels.append((x, y))
            for x in range(min(right, prev_right) + 1, max(right, prev_right)):
                if 0 <= x < bounds_w:
                    pixels.append((x, y))

    # De-duplicate while preserving deterministic order.
    return list(dict.fromkeys(pixels))


def _pixel_buffer(image):
    """
    Returns (words, stride) memoryview over an ARGB32 image for fast pixel access.

    Returns (None, 0) when the buffer cannot be exposed (fallback callers then use
    QImage.pixel()/setPixel()).
    """
    try:
        ptr = image.bits()
        ptr.setsize(image.sizeInBytes())
        words = memoryview(ptr).cast("I")
        return words, image.bytesPerLine() // 4
    except Exception:  # pragma: no cover - defensive, platform specific
        return None, 0


def flood_fill_scanline(
    image,
    start_x: int,
    start_y: int,
    fill_color: QColor,
    tolerance: int = 0,
    clip_rect: Optional[QRect] = None,
) -> None:
    """
    Scanline flood fill with per-channel color tolerance.

    Uses a direct ARGB32 buffer for speed (pure Python fallback available) and
    optionally restricts the fill to ``clip_rect`` (used by the marquee tool).
    """
    width, height = image.width(), image.height()
    if not (0 <= start_x < width and 0 <= start_y < height):
        return

    left, top, right, bottom = 0, 0, width - 1, height - 1
    if clip_rect is not None:
        left = max(0, clip_rect.left())
        top = max(0, clip_rect.top())
        right = min(width - 1, clip_rect.right())
        bottom = min(height - 1, clip_rect.bottom())
        if not (left <= start_x <= right and top <= start_y <= bottom):
            return

    words, stride = _pixel_buffer(image)
    if words is None:
        _flood_fill_slow(image, start_x, start_y, fill_color, tolerance, left, top, right, bottom)
        return

    target = words[start_y * stride + start_x]
    fill = fill_color.rgba()
    if target == fill and tolerance <= 0:
        return

    target_a = (target >> 24) & 0xFF
    target_r = (target >> 16) & 0xFF
    target_g = (target >> 8) & 0xFF
    target_b = target & 0xFF
    limit = max(0, int(tolerance)) * 4

    def matches(pixel: int) -> bool:
        if tolerance <= 0:
            return pixel == target
        return (
            abs(((pixel >> 24) & 0xFF) - target_a)
            + abs(((pixel >> 16) & 0xFF) - target_r)
            + abs(((pixel >> 8) & 0xFF) - target_g)
            + abs((pixel & 0xFF) - target_b)
        ) <= limit

    visited = bytearray(width * height)
    stack: List[Tuple[int, int]] = [(start_x, start_y)]

    while stack:
        x, y = stack.pop()
        row = y * stride
        base = y * width
        if visited[base + x]:
            continue

        # Move to the left-most match of this span.
        xl = x
        while xl > left:
            if visited[base + xl - 1] or not matches(words[row + xl - 1]):
                break
            xl -= 1

        span_up = False
        span_down = False
        xr = xl
        while xr <= right:
            index = base + xr
            if visited[index] or not matches(words[row + xr]):
                break
            words[row + xr] = fill
            visited[index] = 1

            if y > top:
                up_index = index - width
                if not visited[up_index] and matches(words[row - stride + xr]):
                    if not span_up:
                        stack.append((xr, y - 1))
                        span_up = True
                else:
                    span_up = False
            if y < bottom:
                down_index = index + width
                if not visited[down_index] and matches(words[row + stride + xr]):
                    if not span_down:
                        stack.append((xr, y + 1))
                        span_down = True
                else:
                    span_down = False
            xr += 1


def _flood_fill_slow(
    image, start_x, start_y, fill_color, tolerance, left, top, right, bottom
) -> None:
    """Fallback flood fill using QImage.pixel()/setPixel() (safe on any platform)."""
    target = image.pixel(start_x, start_y)
    fill = fill_color.rgba()
    if target == fill and tolerance <= 0:
        return

    target_a = (target >> 24) & 0xFF
    target_r = (target >> 16) & 0xFF
    target_g = (target >> 8) & 0xFF
    target_b = target & 0xFF
    limit = max(0, int(tolerance)) * 4

    def matches(pixel: int) -> bool:
        if tolerance <= 0:
            return pixel == target
        return (
            abs(((pixel >> 24) & 0xFF) - target_a)
            + abs(((pixel >> 16) & 0xFF) - target_r)
            + abs(((pixel >> 8) & 0xFF) - target_g)
            + abs((pixel & 0xFF) - target_b)
        ) <= limit

    width = image.width()
    visited = set()
    stack = [(start_x, start_y)]
    while stack:
        x, y = stack.pop()
        if (x, y) in visited:
            continue
        if not matches(image.pixel(x, y)):
            continue
        xl = x
        while xl > left and (xl - 1, y) not in visited and matches(image.pixel(xl - 1, y)):
            xl -= 1
        while xl <= right and (xl, y) not in visited and matches(image.pixel(xl, y)):
            visited.add((xl, y))
            image.setPixel(xl, y, fill)
            if y > top and (xl, y - 1) not in visited and matches(image.pixel(xl, y - 1)):
                stack.append((xl, y - 1))
            if y < bottom and (xl, y + 1) not in visited and matches(image.pixel(xl, y + 1)):
                stack.append((xl, y + 1))
            xl += 1


def get_spray_pixels(
    cx: int, cy: int, radius: int, density: int, bounds_w: int, bounds_h: int
) -> List[Tuple[int, int]]:
    """Generates random spray pixel coordinates distributed within a circle."""
    pixels: List[Tuple[int, int]] = []
    radius = max(1, int(radius))
    for _ in range(max(0, int(density))):
        r = random.uniform(0, radius)
        theta = random.uniform(0, 2 * math.pi)
        px = int(round(cx + r * math.cos(theta)))
        py = int(round(cy + r * math.sin(theta)))
        if 0 <= px < bounds_w and 0 <= py < bounds_h:
            pixels.append((px, py))
    return pixels


def create_app_icon() -> QIcon:
    """Builds the application icon procedurally (64x64 pixel-art motif)."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.fillRect(0, 0, size, size, QColor("#1b1b1b"))
    painter.fillRect(4, 4, 56, 56, QColor("#232323"))
    colors = ["#3a78c4", "#5fcde4", "#fbf236", "#df7126", "#d95763"]
    cell = 8
    for row in range(4):
        for col in range(4):
            painter.fillRect(16 + col * cell, 16 + row * cell, cell, cell, QColor(colors[(row + col) % len(colors)]))
    painter.setPen(QPen(QColor("#dcdcdc"), 2))
    painter.drawRect(5, 5, 53, 53)
    painter.end()
    return QIcon(pixmap)


class ToolOptionsBar(QWidget):
    """
    Slim horizontal Tool Options Bar mounted directly above the canvas.
    Controls adapt to the active tool.
    """

    options_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(34)
        self.setObjectName("toolOptionsBar")

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 0, 10, 0)
        self.layout.setSpacing(10)

        # Default parameters
        self.brush_size: int = 1
        self.brush_opacity: float = 1.0
        self.fill_tolerance: int = 0
        self.shape_filled: bool = False
        self.spray_density: int = 6

        # Active tool indicator label
        self.label_tool_title = QLabel("Pencil")
        self.label_tool_title.setStyleSheet("font-weight: 600; color: #3a78c4; font-size: 11px;")
        self.layout.addWidget(self.label_tool_title)

        self.layout.addWidget(self._make_separator())

        # Size slider & spinbox
        self.label_size = QLabel("Size:")
        self.label_size.setStyleSheet("color: #888888; font-size: 11px;")
        self.slider_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_size.setRange(1, 32)
        self.slider_size.setValue(1)
        self.slider_size.setFixedWidth(80)
        self.spin_size = QSpinBox()
        self.spin_size.setRange(1, 32)
        self.spin_size.setValue(1)
        self.spin_size.setFixedWidth(46)

        self.slider_size.valueChanged.connect(self.spin_size.setValue)
        self.spin_size.valueChanged.connect(self._on_size_changed)

        self.layout.addWidget(self.label_size)
        self.layout.addWidget(self.slider_size)
        self.layout.addWidget(self.spin_size)

        # Opacity slider & spinbox
        self.label_opacity = QLabel("Opacity:")
        self.label_opacity.setStyleSheet("color: #888888; font-size: 11px;")
        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(5, 100)
        self.slider_opacity.setValue(100)
        self.slider_opacity.setFixedWidth(80)
        self.spin_opacity = QSpinBox()
        self.spin_opacity.setRange(5, 100)
        self.spin_opacity.setValue(100)
        self.spin_opacity.setSuffix("%")
        self.spin_opacity.setFixedWidth(56)

        self.slider_opacity.valueChanged.connect(self.spin_opacity.setValue)
        self.spin_opacity.valueChanged.connect(self._on_opacity_changed)

        self.layout.addWidget(self.label_opacity)
        self.layout.addWidget(self.slider_opacity)
        self.layout.addWidget(self.spin_opacity)

        # Bucket tolerance slider & spinbox
        self.label_tolerance = QLabel("Tolerance:")
        self.label_tolerance.setStyleSheet("color: #888888; font-size: 11px;")
        self.slider_tolerance = QSlider(Qt.Orientation.Horizontal)
        self.slider_tolerance.setRange(0, 255)
        self.slider_tolerance.setValue(0)
        self.slider_tolerance.setFixedWidth(80)
        self.spin_tolerance = QSpinBox()
        self.spin_tolerance.setRange(0, 255)
        self.spin_tolerance.setValue(0)
        self.spin_tolerance.setFixedWidth(50)

        self.slider_tolerance.valueChanged.connect(self.spin_tolerance.setValue)
        self.spin_tolerance.valueChanged.connect(self._on_tolerance_changed)

        self.layout.addWidget(self.label_tolerance)
        self.layout.addWidget(self.slider_tolerance)
        self.layout.addWidget(self.spin_tolerance)

        # Shape filled checkbox
        self.check_filled = QCheckBox("Filled")
        self.check_filled.setStyleSheet("font-size: 11px;")
        self.check_filled.toggled.connect(self._on_filled_toggled)
        self.layout.addWidget(self.check_filled)

        # Spray density spinbox
        self.label_spray = QLabel("Density:")
        self.label_spray.setStyleSheet("color: #888888; font-size: 11px;")
        self.spin_spray = QSpinBox()
        self.spin_spray.setRange(1, 30)
        self.spin_spray.setValue(6)
        self.spin_spray.setFixedWidth(46)
        self.spin_spray.valueChanged.connect(self._on_spray_density_changed)
        self.layout.addWidget(self.label_spray)
        self.layout.addWidget(self.spin_spray)

        self.layout.addStretch()

        self.update_for_tool(ToolType.PENCIL)

    def _make_separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet("background-color: #333333; margin: 4px 2px;")
        line.setFixedWidth(1)
        return line

    def update_for_tool(self, tool: ToolType) -> None:
        """Adapts visibility of controls based on the active tool."""
        self.label_tool_title.setText(tool.value)

        show_size = tool in (ToolType.PENCIL, ToolType.ERASER, ToolType.SPRAY)
        show_opacity = tool in (ToolType.PENCIL, ToolType.SPRAY)
        show_tolerance = tool == ToolType.BUCKET
        show_filled = tool in (ToolType.RECTANGLE, ToolType.ELLIPSE)
        show_spray = tool == ToolType.SPRAY

        for widget in (self.label_size, self.slider_size, self.spin_size):
            widget.setVisible(show_size)
        for widget in (self.label_opacity, self.slider_opacity, self.spin_opacity):
            widget.setVisible(show_opacity)
        for widget in (self.label_tolerance, self.slider_tolerance, self.spin_tolerance):
            widget.setVisible(show_tolerance)
        self.check_filled.setVisible(show_filled)
        self.label_spray.setVisible(show_spray)
        self.spin_spray.setVisible(show_spray)

    def _on_size_changed(self, val: int) -> None:
        self.brush_size = val
        self.slider_size.blockSignals(True)
        self.slider_size.setValue(val)
        self.slider_size.blockSignals(False)
        self.options_changed.emit()

    def _on_opacity_changed(self, val: int) -> None:
        self.brush_opacity = val / 100.0
        self.slider_opacity.blockSignals(True)
        self.slider_opacity.setValue(val)
        self.slider_opacity.blockSignals(False)
        self.options_changed.emit()

    def _on_tolerance_changed(self, val: int) -> None:
        self.fill_tolerance = val
        self.slider_tolerance.blockSignals(True)
        self.slider_tolerance.setValue(val)
        self.slider_tolerance.blockSignals(False)
        self.options_changed.emit()

    def _on_filled_toggled(self, checked: bool) -> None:
        self.shape_filled = checked
        self.options_changed.emit()

    def _on_spray_density_changed(self, val: int) -> None:
        self.spray_density = val
        self.options_changed.emit()
