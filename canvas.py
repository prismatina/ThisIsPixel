"""
ThisIsPixel - Canvas Viewport, Selection & Radial Menu
======================================================
Advanced graphics canvas built on QGraphicsView + QGraphicsScene:

1. Smooth zoom (Ctrl+Wheel / menu) and pan (Space+Drag / Middle Mouse).
2. Cached compositing with optional onion skinning (ghosts rendered *behind*
   the active frame).
3. Pixel grid (auto-hidden when zoomed far out) and configurable tile grid.
4. Navigator mini-map with a red viewport indicator; click/drag to navigate.
5. Rectangular marquee selection with:
   - move selected pixels by dragging inside the selection,
   - Copy / Cut / Paste (system clipboard + internal pixel-exact buffer),
   - Delete selection content,
   - all pixel edits clipped to the active selection when one exists.
6. Source-over alpha blending for pencil/spray opacity.
7. Radial palette menu on right click with recent colors.
8. Pixel edits are stored as DrawStrokeCommand on the shared QUndoStack.
"""

import math
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QPoint, QRect
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QPixmap,
    QImage,
    QMouseEvent,
    QWheelEvent,
    QKeyEvent,
    QTransform,
    QUndoStack,
    QGuiApplication,
)
from PyQt6.QtWidgets import (
    QWidget,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
    QStyleOptionGraphicsItem,
)

from models import Project, DrawStrokeCommand
from tools import (
    ToolType,
    ToolOptionsBar,
    bresenham_line,
    get_brush_pixels,
    get_rectangle_pixels,
    get_ellipse_pixels,
    flood_fill_scanline,
    get_spray_pixels,
    create_tool_icon,
)

MIN_ZOOM = 0.05
MAX_ZOOM = 32.0
PIXEL_GRID_MIN_ZOOM = 4.0


class RadialPopupWidget(QWidget):
    """
    Radial palette menu with 8 tool slots and 8 recent color slots.

    Emits ``tool_selected`` / ``color_selected`` and closes itself.
    """

    tool_selected = pyqtSignal(ToolType)
    color_selected = pyqtSignal(QColor)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(240, 240)

        self.tools: List[ToolType] = [
            ToolType.PENCIL,
            ToolType.ERASER,
            ToolType.LINE,
            ToolType.RECTANGLE,
            ToolType.ELLIPSE,
            ToolType.BUCKET,
            ToolType.SPRAY,
            ToolType.EYEDROPPER,
        ]
        self.recent_colors: List[QColor] = []
        self.hovered_tool_idx: int = -1
        self.hovered_color_idx: int = -1
        self._icons = {tool: create_tool_icon(tool) for tool in self.tools}

    def set_recent_colors(self, colors: List[QColor]) -> None:
        # De-duplicate while preserving order.
        unique: List[QColor] = []
        for color in colors:
            if color.isValid() and color not in unique:
                unique.append(color)
        self.recent_colors = unique[:8]
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx, cy = 120, 120

        painter.setBrush(QBrush(QColor(30, 30, 30, 235)))
        painter.setPen(QPen(QColor("#3e3e42"), 2))
        painter.drawEllipse(10, 10, 220, 220)

        painter.setBrush(QBrush(QColor(45, 45, 48, 245)))
        painter.setPen(QPen(QColor("#007acc"), 1))
        painter.drawEllipse(cx - 30, cy - 30, 60, 60)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(QRectF(cx - 30, cy - 10, 60, 20), Qt.AlignmentFlag.AlignCenter, "TOOLS")

        radius_tools = 65
        for i, tool in enumerate(self.tools):
            angle = i * (2 * math.pi / len(self.tools)) - math.pi / 2
            tx = cx + radius_tools * math.cos(angle)
            ty = cy + radius_tools * math.sin(angle)
            is_hover = i == self.hovered_tool_idx
            painter.setBrush(QBrush(QColor("#007acc" if is_hover else "#3a3a3d")))
            painter.setPen(QPen(QColor("#007acc" if is_hover else "#555558"), 1))
            painter.drawEllipse(QPointF(tx, ty), 16, 16)
            pix = self._icons[tool].pixmap(18, 18)
            painter.drawPixmap(int(tx - 9), int(ty - 9), pix)

        radius_colors = 95
        for i, color in enumerate(self.recent_colors):
            angle = i * (2 * math.pi / 8) - math.pi / 2
            tx = cx + radius_colors * math.cos(angle)
            ty = cy + radius_colors * math.sin(angle)
            is_hover = i == self.hovered_color_idx
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor("#ffffff" if is_hover else "#222222"), 2 if is_hover else 1))
            painter.drawEllipse(QPointF(tx, ty), 10, 10)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        dx = pos.x() - 120
        dy = pos.y() - 120
        dist = math.hypot(dx, dy)

        self.hovered_tool_idx = -1
        self.hovered_color_idx = -1

        if 50 <= dist <= 80:
            angle = (math.atan2(dy, dx) + math.pi / 2) % (2 * math.pi)
            idx = int(round(angle / (2 * math.pi / len(self.tools)))) % len(self.tools)
            self.hovered_tool_idx = idx
        elif 82 <= dist <= 110 and self.recent_colors:
            angle = (math.atan2(dy, dx) + math.pi / 2) % (2 * math.pi)
            count = len(self.recent_colors)
            idx = int(round(angle / (2 * math.pi / 8))) % count
            self.hovered_color_idx = idx

        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self.hovered_tool_idx >= 0:
                self.tool_selected.emit(self.tools[self.hovered_tool_idx])
                self.close()
            elif 0 <= self.hovered_color_idx < len(self.recent_colors):
                self.color_selected.emit(self.recent_colors[self.hovered_color_idx])
                self.close()
            else:
                self.close()
        elif event.button() == Qt.MouseButton.RightButton:
            self.close()


class CanvasGraphicsItem(QGraphicsItem):
    """Renders checkerboard, composite, previews, selection, and grids."""

    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        self.show_pixel_grid: bool = True
        self.show_tile_grid: bool = False
        self.tile_size: int = 8
        self.onion_skin: bool = False
        self.zoom_factor: float = 1.0
        self.live_editing: bool = False

        self.preview_pixels: List[Tuple[int, int]] = []
        self.preview_color: QColor = QColor(0, 0, 0, 255)
        self.selection_rect: Optional[QRect] = None

        # Floating buffer drawn while the user drags a selection.
        self.floating_image: Optional[QImage] = None
        self.floating_pos: QPoint = QPoint(0, 0)

        self.checker_pixmap = self._create_checkerboard()

    def refresh_geometry(self) -> None:
        """Notifies the scene that boundingRect() changed (project resize/reload)."""
        self.prepareGeometryChange()
        self.update()

    def _create_checkerboard(self) -> QPixmap:
        pix = QPixmap(16, 16)
        painter = QPainter(pix)
        painter.fillRect(0, 0, 8, 8, QColor("#FFFFFF"))
        painter.fillRect(8, 0, 8, 8, QColor("#E0E0E0"))
        painter.fillRect(0, 8, 8, 8, QColor("#E0E0E0"))
        painter.fillRect(8, 8, 8, 8, QColor("#FFFFFF"))
        painter.end()
        return pix

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.project.width, self.project.height)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        width, height = self.project.width, self.project.height

        painter.fillRect(QRectF(0, 0, width, height), QBrush(self.checker_pixmap))

        composite = self.project.render_composite(
            onion_skin=self.onion_skin, use_cache=not self.live_editing
        )
        painter.drawImage(0, 0, composite)

        if self.floating_image is not None:
            painter.drawImage(self.floating_pos, self.floating_image)

        if self.preview_pixels:
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self.preview_color))
            for px, py in self.preview_pixels:
                if 0 <= px < width and 0 <= py < height:
                    painter.drawRect(px, py, 1, 1)
            painter.restore()

        if self.selection_rect is not None and not self.selection_rect.isEmpty():
            painter.save()
            dash_pen = QPen(QColor("#00d2d3"), 1)
            dash_pen.setCosmetic(True)
            dash_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(dash_pen)
            painter.setBrush(QBrush(QColor(0, 210, 211, 35)))
            painter.drawRect(QRectF(self.selection_rect))
            painter.restore()

        if self.show_pixel_grid and self.zoom_factor >= PIXEL_GRID_MIN_ZOOM:
            grid_pen = QPen(QColor(160, 160, 160, 80), 1)
            grid_pen.setCosmetic(True)
            painter.setPen(grid_pen)
            for x in range(1, width):
                painter.drawLine(QPointF(x, 0), QPointF(x, height))
            for y in range(1, height):
                painter.drawLine(QPointF(0, y), QPointF(width, y))

        if self.show_tile_grid and self.tile_size > 0:
            tile_pen = QPen(QColor(0, 122, 204, 190), 1)
            tile_pen.setCosmetic(True)
            painter.setPen(tile_pen)
            for x in range(self.tile_size, width, self.tile_size):
                painter.drawLine(QPointF(x, 0), QPointF(x, height))
            for y in range(self.tile_size, height, self.tile_size):
                painter.drawLine(QPointF(0, y), QPointF(width, y))

        border_pen = QPen(QColor(70, 70, 70), 1)
        border_pen.setCosmetic(True)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(0, 0, width, height))


class NavigatorMiniMap(QWidget):
    """Mini-map with a red viewport indicator; click/drag to navigate."""

    navigate = pyqtSignal(float, float)  # normalized canvas coordinates

    def __init__(self, project: Project, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project = project
        self.setFixedSize(140, 140)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.visible_norm_rect: QRectF = QRectF(0, 0, 1, 1)
        self._thumb_rect: QRectF = QRectF(0, 0, 1, 1)
        self._checker = self._create_checkerboard()

    def _create_checkerboard(self) -> QPixmap:
        pix = QPixmap(16, 16)
        painter = QPainter(pix)
        painter.fillRect(0, 0, 8, 8, QColor("#2b2b2b"))
        painter.fillRect(8, 0, 8, 8, QColor("#1f1f1f"))
        painter.fillRect(0, 8, 8, 8, QColor("#1f1f1f"))
        painter.fillRect(8, 8, 8, 8, QColor("#2b2b2b"))
        painter.end()
        return pix

    def set_viewport_rect(self, norm_rect: QRectF) -> None:
        self.visible_norm_rect = norm_rect
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        painter.fillRect(self.rect(), QColor("#1e1e1e"))

        comp = self.project.active_frame.composite()
        scaled = comp.scaled(
            self.width() - 4,
            self.height() - 4,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        offset_x = (self.width() - scaled.width()) / 2
        offset_y = (self.height() - scaled.height()) / 2

        painter.fillRect(
            QRectF(offset_x, offset_y, scaled.width(), scaled.height()),
            QBrush(self._checker),
        )
        painter.drawImage(int(offset_x), int(offset_y), scaled)
        self._thumb_rect = QRectF(offset_x, offset_y, scaled.width(), scaled.height())

        rect = self.visible_norm_rect
        vx = offset_x + rect.x() * scaled.width()
        vy = offset_y + rect.y() * scaled.height()
        vw = max(4.0, rect.width() * scaled.width())
        vh = max(4.0, rect.height() * scaled.height())
        painter.setPen(QPen(QColor("#ff4757"), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(vx, vy, vw, vh))

        painter.setPen(QPen(QColor("#3e3e42"), 1))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def _emit_navigation(self, pos: QPoint) -> None:
        rect = self._thumb_rect
        if rect.width() <= 0 or rect.height() <= 0:
            return
        nx = (pos.x() - rect.x()) / rect.width()
        ny = (pos.y() - rect.y()) / rect.height()
        self.navigate.emit(max(0.0, min(1.0, nx)), max(0.0, min(1.0, ny)))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._emit_navigation(event.pos())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._emit_navigation(event.pos())


class CanvasView(QGraphicsView):
    """Main canvas viewport: panning, zooming, drawing, selection and undo."""

    cursor_moved = pyqtSignal(int, int)
    zoom_changed = pyqtSignal(int)
    color_picked = pyqtSignal(QColor)
    canvas_modified = pyqtSignal()
    tool_changed = pyqtSignal(ToolType)
    status_message = pyqtSignal(str)

    def __init__(
        self,
        project: Project,
        undo_stack: QUndoStack,
        tool_options: ToolOptionsBar,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.project = project
        self.undo_stack = undo_stack
        self.tool_options = tool_options

        self.current_tool: ToolType = ToolType.PENCIL
        self.active_color: QColor = QColor(0, 0, 0, 255)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setSceneRect(-4000, -4000, 8000, 8000)

        self.canvas_item = CanvasGraphicsItem(self.project)
        self.scene.addItem(self.canvas_item)

        self.setBackgroundBrush(QBrush(QColor("#181920")))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Interaction state
        self.is_panning = False
        self.space_pressed = False
        self.pan_start_pos = QPoint()
        self.pan_start_center = QPointF()

        self.is_drawing = False
        self.is_selecting = False
        self.selection_start: Optional[Tuple[int, int]] = None
        self.stroke_start_pixel: Optional[Tuple[int, int]] = None
        self.last_pixel_pos: Optional[Tuple[int, int]] = None
        self.before_stroke_image: Optional[QImage] = None
        self._stroke_frame_idx: int = 0
        self._stroke_layer_idx: int = 0

        # Selection move state
        self._moving_selection = False
        self._move_before_image: Optional[QImage] = None
        self._move_buffer: Optional[QImage] = None
        self._move_origin: QPoint = QPoint()
        self._move_delta: QPoint = QPoint()
        self._move_start_pixel: Optional[Tuple[int, int]] = None

        # Internal pixel clipboard (kept in sync with the system clipboard).
        self.clipboard_image: Optional[QImage] = None

        self.mini_map = NavigatorMiniMap(self.project, self)
        self.mini_map.navigate.connect(self._center_on_normalized)
        self.mini_map.move(10, 10)

        self.radial_menu = RadialPopupWidget(self)
        self.radial_menu.tool_selected.connect(self.set_tool)
        self.radial_menu.color_selected.connect(self.set_color)
        self.set_recent_colors([self.active_color])

        self.zoom_factor: float = 16.0
        self._apply_zoom()
        self.centerOn(self.canvas_item)
        self._update_cursor()

    # ------------------------------------------------------------------ #
    # Project / view state
    # ------------------------------------------------------------------ #
    def set_project(self, project: Project) -> None:
        """Rebinds the canvas to a new/reloaded document."""
        self.project = project
        self.canvas_item.project = project
        self.canvas_item.refresh_geometry()
        self.mini_map.project = project
        self.clear_selection()
        self.canvas_item.preview_pixels = []
        self.canvas_item.floating_image = None
        self.canvas_item.live_editing = False
        self.is_drawing = False
        self.is_selecting = False
        self._moving_selection = False
        self.before_stroke_image = None
        self._move_before_image = None
        self._move_buffer = None
        self.clipboard_image = None
        self.zoom_to_fit()
        self.refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.mini_map.move(self.width() - self.mini_map.width() - 15, 15)
        self._update_mini_map_viewport()

    def _apply_zoom(self) -> None:
        transform = QTransform()
        transform.scale(self.zoom_factor, self.zoom_factor)
        self.setTransform(transform)
        self.canvas_item.zoom_factor = self.zoom_factor
        self.canvas_item.update()
        self.zoom_changed.emit(int(round(self.zoom_factor * 100)))
        self._update_mini_map_viewport()

    def reset_zoom(self) -> None:
        """Resets the view to fit the whole canvas inside the viewport."""
        self.zoom_to_fit()

    def zoom_to_fit(self, margin: float = 0.9) -> None:
        viewport = self.viewport().size()
        if viewport.width() <= 0 or viewport.height() <= 0:
            return
        width = max(1, self.project.width)
        height = max(1, self.project.height)
        factor = min(viewport.width() / width, viewport.height() / height) * margin
        factor = max(MIN_ZOOM, min(MAX_ZOOM, factor))
        if factor >= 8.0:
            factor = float(int(factor))
        self.zoom_factor = factor
        self._apply_zoom()
        self.centerOn(QPointF(width / 2.0, height / 2.0))

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom_factor * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom_factor / 1.25)

    def set_zoom(self, new_factor: float) -> None:
        clamped = max(MIN_ZOOM, min(MAX_ZOOM, new_factor))
        if clamped >= 8.0:
            clamped = float(round(clamped))
        if abs(clamped - self.zoom_factor) < 1e-6:
            return
        self.zoom_factor = clamped
        self._apply_zoom()

    def _update_mini_map_viewport(self) -> None:
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        width = float(max(1, self.project.width))
        height = float(max(1, self.project.height))
        norm = QRectF(
            visible.x() / width,
            visible.y() / height,
            visible.width() / width,
            visible.height() / height,
        )
        # Clamp so the indicator never leaves the thumbnail.
        left = max(0.0, min(1.0, norm.x()))
        top = max(0.0, min(1.0, norm.y()))
        right = max(0.0, min(1.0, norm.x() + norm.width()))
        bottom = max(0.0, min(1.0, norm.y() + norm.height()))
        self.mini_map.set_viewport_rect(QRectF(left, top, max(0.0, right - left), max(0.0, bottom - top)))

    def _center_on_normalized(self, nx: float, ny: float) -> None:
        self.centerOn(QPointF(nx * self.project.width, ny * self.project.height))
        self._update_mini_map_viewport()

    def _update_cursor(self) -> None:
        if self.is_panning:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self.space_pressed:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif self.current_tool in (ToolType.EYEDROPPER,):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    # ------------------------------------------------------------------ #
    # Tools / options
    # ------------------------------------------------------------------ #
    def set_tool(self, tool: ToolType) -> None:
        self.current_tool = tool
        self._update_cursor()
        self.tool_options.update_for_tool(tool)
        self.tool_changed.emit(tool)

    def set_color(self, color: QColor) -> None:
        if not color.isValid():
            return
        self.active_color = QColor(color)

    def set_recent_colors(self, colors: List[QColor]) -> None:
        self.radial_menu.set_recent_colors(colors)

    def set_pixel_grid(self, visible: bool) -> None:
        self.canvas_item.show_pixel_grid = visible
        self.canvas_item.update()

    def set_tile_grid(self, visible: bool) -> None:
        self.canvas_item.show_tile_grid = visible
        self.canvas_item.update()

    def set_tile_size(self, size: int) -> None:
        self.canvas_item.tile_size = max(1, int(size))
        self.canvas_item.update()

    def set_onion_skin(self, active: bool) -> None:
        self.canvas_item.onion_skin = active
        self.project.invalidate_cache()
        self.canvas_item.update()

    # Compatibility aliases used by the menu wiring.
    def toggle_pixel_grid(self, visible: bool) -> None:
        self.set_pixel_grid(visible)

    def toggle_tile_grid(self, visible: bool) -> None:
        self.set_tile_grid(visible)

    def toggle_onion_skin(self, active: bool) -> None:
        self.set_onion_skin(active)

    # ------------------------------------------------------------------ #
    # Selection helpers
    # ------------------------------------------------------------------ #
    def has_selection(self) -> bool:
        rect = self.canvas_item.selection_rect
        return rect is not None and not rect.isEmpty()

    def selection_rect(self) -> Optional[QRect]:
        rect = self.canvas_item.selection_rect
        if rect is None or rect.isEmpty():
            return None
        return rect.intersected(QRect(0, 0, self.project.width, self.project.height))

    def clear_selection(self) -> None:
        self.canvas_item.selection_rect = None
        self.canvas_item.update()

    def select_all(self) -> None:
        self.canvas_item.selection_rect = QRect(0, 0, self.project.width, self.project.height)
        self.canvas_item.update()

    def _allowed(self, x: int, y: int) -> bool:
        """True when (x, y) is inside the active selection (or no selection)."""
        rect = self.selection_rect()
        if rect is None:
            return True
        return rect.contains(x, y)

    def copy_selection(self) -> bool:
        rect = self.selection_rect()
        if rect is None:
            self.status_message.emit("Nothing selected - use the Marquee tool (M) first")
            return False
        image = self.project.active_layer.image.copy(rect)
        self.clipboard_image = image
        QGuiApplication.clipboard().setImage(image)
        self.status_message.emit(f"Copied {rect.width()}x{rect.height()} px")
        return True

    def cut_selection(self) -> bool:
        if not self.copy_selection():
            return False
        self.delete_selection()
        self.status_message.emit("Cut selection")
        return True

    def paste_clipboard(self) -> bool:
        image = None
        if self.clipboard_image is not None:
            image = self.clipboard_image
        else:
            system_image = QGuiApplication.clipboard().image()
            if not system_image.isNull():
                image = system_image.convertToFormat(QImage.Format.Format_ARGB32)
        if image is None or image.isNull():
            self.status_message.emit("Clipboard is empty")
            return False

        layer = self.project.active_layer
        if layer.locked or not layer.visible:
            self.status_message.emit("Layer is locked or hidden")
            return False

        rect = self.selection_rect()
        target = rect.topLeft() if rect is not None else QPoint(0, 0)
        self._stroke_frame_idx = self.project.active_frame_idx
        self._stroke_layer_idx = self.project.active_layer_idx
        before = layer.image.copy()
        painter = QPainter(layer.image)
        painter.drawImage(target, image)
        painter.end()
        after = layer.image.copy()
        self._push_pixel_command(before, after, "Paste")

        pasted = QRect(target, image.size())
        clipped = pasted.intersected(QRect(0, 0, self.project.width, self.project.height))
        if not clipped.isEmpty():
            self.canvas_item.selection_rect = clipped
        self.status_message.emit(f"Pasted {image.width()}x{image.height()} px")
        return True

    def delete_selection(self) -> bool:
        rect = self.selection_rect()
        if rect is None:
            return False
        layer = self.project.active_layer
        if layer.locked or not layer.visible:
            self.status_message.emit("Layer is locked or hidden")
            return False

        self._stroke_frame_idx = self.project.active_frame_idx
        self._stroke_layer_idx = self.project.active_layer_idx
        before = layer.image.copy()
        painter = QPainter(layer.image)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(rect, Qt.GlobalColor.transparent)
        painter.end()
        after = layer.image.copy()
        self._push_pixel_command(before, after, "Delete Selection")
        return True

    def clear_active_layer(self) -> bool:
        """Clears every pixel of the active layer as a single undoable step."""
        layer = self.project.active_layer
        if layer.locked or not layer.visible:
            self.status_message.emit("Layer is locked or hidden")
            return False

        self._stroke_frame_idx = self.project.active_frame_idx
        self._stroke_layer_idx = self.project.active_layer_idx
        before = layer.image.copy()
        layer.image.fill(QColor(0, 0, 0, 0))
        after = layer.image.copy()
        self._push_pixel_command(before, after, "Clear Layer")
        self.status_message.emit("Layer cleared (Ctrl+Z to undo)")
        return True

    def _push_pixel_command(
        self,
        before: QImage,
        after: QImage,
        text: str,
        frame_idx: Optional[int] = None,
        layer_idx: Optional[int] = None,
    ) -> None:
        if before == after:
            return
        frame_idx = self._stroke_frame_idx if frame_idx is None else frame_idx
        layer_idx = self._stroke_layer_idx if layer_idx is None else layer_idx
        command = DrawStrokeCommand(
            self.project,
            frame_idx,
            layer_idx,
            before,
            after,
            text=text,
        )
        self.undo_stack.push(command)
        if 0 <= frame_idx < len(self.project.frames):
            self.project.frames[frame_idx].touch()
        self.canvas_item.live_editing = False
        self.canvas_item.update()
        self.mini_map.update()
        self.canvas_modified.emit()

    # ------------------------------------------------------------------ #
    # Mouse / keyboard
    # ------------------------------------------------------------------ #
    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)
            self._update_mini_map_viewport()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.space_pressed = True
            self._update_cursor()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            if self._moving_selection:
                self._cancel_selection_move()
            else:
                self.clear_selection()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.space_pressed = False
            self._update_cursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event) -> None:
        self.space_pressed = False
        self.is_panning = False
        self._update_cursor()
        super().focusOutEvent(event)

    def _scene_pos_to_pixel(self, scene_pos: QPointF) -> Optional[Tuple[int, int]]:
        x = int(math.floor(scene_pos.x()))
        y = int(math.floor(scene_pos.y()))
        if 0 <= x < self.project.width and 0 <= y < self.project.height:
            return x, y
        return None

    def _clamped_pixel(self, event: QMouseEvent) -> Tuple[int, int]:
        scene_pos = self.mapToScene(event.pos())
        px = max(0, min(self.project.width - 1, int(math.floor(scene_pos.x()))))
        py = max(0, min(self.project.height - 1, int(math.floor(scene_pos.y()))))
        return px, py

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # 1. Panning
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self.space_pressed
        ):
            self.is_panning = True
            self.pan_start_pos = event.pos()
            self.pan_start_center = self.mapToScene(self.viewport().rect().center())
            self._update_cursor()
            event.accept()
            return

        # 2. Radial menu
        if event.button() == Qt.MouseButton.RightButton:
            colors = [self.active_color] + list(self.radial_menu.recent_colors)
            colors += list(self.project.palette)
            self.radial_menu.set_recent_colors(colors)
            target = event.globalPosition().toPoint() - QPoint(120, 120)
            screen = self.screen()
            if screen is not None:
                available = screen.availableGeometry()
                target.setX(
                    max(available.left(), min(target.x(), available.right() - 240))
                )
                target.setY(
                    max(available.top(), min(target.y(), available.bottom() - 240))
                )
            self.radial_menu.move(target)
            self.radial_menu.show()
            event.accept()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        # 3. Eyedropper (tool or Alt+Click)
        if event.modifiers() & Qt.KeyboardModifier.AltModifier or self.current_tool == ToolType.EYEDROPPER:
            scene_pos = self.mapToScene(event.pos())
            pixel = self._scene_pos_to_pixel(scene_pos)
            if pixel:
                px, py = pixel
                layer_color = self.project.active_layer.image.pixelColor(px, py)
                if layer_color.alpha() == 0:
                    layer_color = self.project.active_frame.composite().pixelColor(px, py)
                picked = QColor(layer_color)
                picked.setAlpha(255)
                self.active_color = picked
                self.color_picked.emit(picked)
            return

        # 4. Marquee selection / selection move
        if self.current_tool == ToolType.MARQUEE:
            px, py = self._clamped_pixel(event)
            rect = self.selection_rect()
            if rect is not None and rect.contains(px, py):
                self._begin_selection_move(px, py)
            else:
                self.is_selecting = True
                self.selection_start = (px, py)
                self.canvas_item.selection_rect = QRect(px, py, 1, 1)
                self.canvas_item.update()
            return

        layer = self.project.active_layer
        if layer.locked or not layer.visible:
            self.status_message.emit("Layer is locked or hidden")
            return

        scene_pos = self.mapToScene(event.pos())
        pixel = self._scene_pos_to_pixel(scene_pos)
        if not pixel:
            return

        px, py = pixel
        self._stroke_frame_idx = self.project.active_frame_idx
        self._stroke_layer_idx = self.project.active_layer_idx
        self.is_drawing = True
        self.stroke_start_pixel = (px, py)
        self.last_pixel_pos = (px, py)
        self.before_stroke_image = layer.image.copy()
        self.canvas_item.live_editing = True

        if self.current_tool == ToolType.BUCKET:
            if not self._allowed(px, py):
                self.is_drawing = False
                self.before_stroke_image = None
                self.canvas_item.live_editing = False
                return
            flood_fill_scanline(
                layer.image,
                px,
                py,
                self.active_color,
                self.tool_options.fill_tolerance,
                self.selection_rect(),
            )
            self.project.active_frame.touch()
            self._commit_stroke("Bucket Fill")
            self.is_drawing = False
            self.stroke_start_pixel = None
            self.last_pixel_pos = None
            return

        if self.current_tool in (ToolType.PENCIL, ToolType.ERASER, ToolType.SPRAY):
            self._apply_brush_at(px, py)
        elif self.current_tool in (ToolType.LINE, ToolType.RECTANGLE, ToolType.ELLIPSE):
            self.canvas_item.preview_pixels = [(px, py)] if self._allowed(px, py) else []
            self.canvas_item.preview_color = self.active_color

        self.canvas_item.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.is_panning:
            delta = event.pos() - self.pan_start_pos
            dx = delta.x() / self.zoom_factor
            dy = delta.y() / self.zoom_factor
            self.centerOn(self.pan_start_center - QPointF(dx, dy))
            self._update_mini_map_viewport()
            return

        if self._moving_selection:
            px, py = self._clamped_pixel(event)
            sx, sy = self._move_start_pixel or (px, py)
            self._move_delta = QPoint(px - sx, py - sy)
            self.canvas_item.floating_pos = self._move_origin + self._move_delta
            self.canvas_item.update()
            self.cursor_moved.emit(px, py)
            return

        if self.is_selecting and self.selection_start:
            px, py = self._clamped_pixel(event)
            sx, sy = self.selection_start
            self.canvas_item.selection_rect = QRect(
                min(sx, px), min(sy, py), abs(px - sx) + 1, abs(py - sy) + 1
            )
            self.canvas_item.update()
            self.cursor_moved.emit(px, py)
            return

        scene_pos = self.mapToScene(event.pos())
        pixel = self._scene_pos_to_pixel(scene_pos)

        if not pixel:
            self.cursor_moved.emit(-1, -1)
            return

        px, py = pixel
        self.cursor_moved.emit(px, py)

        if not (self.is_drawing and self.stroke_start_pixel):
            return

        if self.current_tool in (ToolType.PENCIL, ToolType.ERASER, ToolType.SPRAY):
            if self.last_pixel_pos:
                for lx, ly in bresenham_line(self.last_pixel_pos[0], self.last_pixel_pos[1], px, py):
                    self._apply_brush_at(lx, ly)
            else:
                self._apply_brush_at(px, py)
            self.last_pixel_pos = (px, py)
            self.project.active_frame.touch()
            self.canvas_item.update()

        elif self.current_tool == ToolType.LINE:
            sx, sy = self.stroke_start_pixel
            points = bresenham_line(sx, sy, px, py)
            self.canvas_item.preview_pixels = [p for p in points if self._allowed(*p)]
            self.canvas_item.preview_color = self.active_color
            self.canvas_item.update()

        elif self.current_tool == ToolType.RECTANGLE:
            sx, sy = self.stroke_start_pixel
            points = get_rectangle_pixels(
                sx,
                sy,
                px,
                py,
                self.tool_options.shape_filled,
                self.project.width,
                self.project.height,
            )
            self.canvas_item.preview_pixels = [p for p in points if self._allowed(*p)]
            self.canvas_item.preview_color = self.active_color
            self.canvas_item.update()

        elif self.current_tool == ToolType.ELLIPSE:
            sx, sy = self.stroke_start_pixel
            points = get_ellipse_pixels(
                sx,
                sy,
                px,
                py,
                self.tool_options.shape_filled,
                self.project.width,
                self.project.height,
            )
            self.canvas_item.preview_pixels = [p for p in points if self._allowed(*p)]
            self.canvas_item.preview_color = self.active_color
            self.canvas_item.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.is_panning:
            self.is_panning = False
            self._update_cursor()
            return

        if self._moving_selection:
            self._finish_selection_move()
            return

        if self.is_selecting:
            self.is_selecting = False
            rect = self.canvas_item.selection_rect
            if rect is not None and (rect.width() <= 1 and rect.height() <= 1):
                self.clear_selection()
            return

        if event.button() == Qt.MouseButton.LeftButton and self.is_drawing:
            if self.current_tool in (ToolType.LINE, ToolType.RECTANGLE, ToolType.ELLIPSE):
                layer = self.project.active_layer
                for px, py in self.canvas_item.preview_pixels:
                    if self._allowed(px, py):
                        self._blend_pixel(layer.image, px, py, self.active_color, 1.0)
                self.canvas_item.preview_pixels = []
                self.project.active_frame.touch()

            self._commit_stroke(f"{self.current_tool.value} Stroke")
            self.is_drawing = False
            self.stroke_start_pixel = None
            self.last_pixel_pos = None
            self.canvas_item.update()
            return

        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------ #
    # Selection move
    # ------------------------------------------------------------------ #
    def _begin_selection_move(self, px: int, py: int) -> None:
        rect = self.selection_rect()
        layer = self.project.active_layer
        if rect is None:
            return
        if layer.locked or not layer.visible:
            self.status_message.emit("Layer is locked or hidden")
            return

        self._move_before_image = layer.image.copy()
        self._move_buffer = layer.image.copy(rect)
        self._move_origin = rect.topLeft()
        self._move_start_pixel = (px, py)
        self._move_delta = QPoint(0, 0)
        self._moving_selection = True
        self._stroke_frame_idx = self.project.active_frame_idx
        self._stroke_layer_idx = self.project.active_layer_idx
        self.canvas_item.live_editing = True

        # Clear the source region so the drag preview looks correct.
        painter = QPainter(layer.image)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(rect, Qt.GlobalColor.transparent)
        painter.end()
        self.project.active_frame.touch()

        self.canvas_item.floating_image = self._move_buffer
        self.canvas_item.floating_pos = self._move_origin
        self.canvas_item.update()

    def _finish_selection_move(self) -> None:
        self._moving_selection = False
        self.canvas_item.floating_image = None
        layer = self.project.active_layer
        before = self._move_before_image
        buffer = self._move_buffer
        if before is None or buffer is None:
            self.canvas_item.update()
            return

        if self._move_delta.isNull():
            layer.image = before
            layer.touch()
            self.canvas_item.live_editing = False
            self.canvas_item.update()
            self._reset_move_state()
            return

        layer.image = before.copy()
        source = self.selection_rect()
        target = self._move_origin + self._move_delta
        painter = QPainter(layer.image)
        if source is not None:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(source, Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.drawImage(target, buffer)
        painter.end()
        after = layer.image.copy()

        moved = QRect(target, buffer.size()).intersected(
            QRect(0, 0, self.project.width, self.project.height)
        )
        self.canvas_item.selection_rect = None if moved.isEmpty() else moved
        self._push_pixel_command(before, after, "Move Selection")
        self._reset_move_state()
        self.canvas_item.floating_image = None
        self.canvas_item.update()

    def _cancel_selection_move(self) -> None:
        layer = self.project.active_layer
        if self._move_before_image is not None:
            layer.image = self._move_before_image
            layer.touch()
        self._reset_move_state()
        self.canvas_item.floating_image = None
        self.canvas_item.live_editing = False
        self.canvas_item.update()
        self.status_message.emit("Selection move cancelled")

    def _reset_move_state(self) -> None:
        self._moving_selection = False
        self._move_before_image = None
        self._move_buffer = None
        self._move_start_pixel = None
        self._move_delta = QPoint(0, 0)
        self.canvas_item.live_editing = False

    # ------------------------------------------------------------------ #
    # Pixel painting
    # ------------------------------------------------------------------ #
    def _blend_pixel(self, image: QImage, x: int, y: int, color: QColor, opacity: float) -> None:
        """Source-over blend of ``color`` onto one pixel (non-premultiplied ARGB32)."""
        if not (0 <= x < image.width() and 0 <= y < image.height()):
            return
        source_alpha = (color.alpha() * max(0.0, min(1.0, opacity))) / 255.0
        if source_alpha <= 0.0:
            return
        if source_alpha >= 0.999:
            image.setPixel(x, y, color.rgba())
            return

        dest = image.pixel(x, y)
        da = (dest >> 24) & 0xFF
        sa = int(round(source_alpha * 255))
        out_a = sa + (da * (255 - sa)) // 255
        if out_a <= 0:
            image.setPixel(x, y, 0)
            return
        dr = (dest >> 16) & 0xFF
        dg = (dest >> 8) & 0xFF
        db = dest & 0xFF
        sr = color.red()
        sg = color.green()
        sb = color.blue()
        out_r = (sr * sa + (dr * da * (255 - sa)) // 255) // out_a
        out_g = (sg * sa + (dg * da * (255 - sa)) // 255) // out_a
        out_b = (sb * sa + (db * da * (255 - sa)) // 255) // out_a
        image.setPixel(x, y, (out_a << 24) | (out_r << 16) | (out_g << 8) | out_b)

    def _apply_brush_at(self, cx: int, cy: int) -> None:
        """Applies the active brush at (cx, cy), respecting selection + lock state."""
        layer = self.project.active_layer
        size = self.tool_options.brush_size
        opacity = self.tool_options.brush_opacity
        pixels = get_brush_pixels(cx, cy, size, self.project.width, self.project.height)

        if self.current_tool == ToolType.PENCIL:
            for px, py in pixels:
                if self._allowed(px, py):
                    self._blend_pixel(layer.image, px, py, self.active_color, opacity)

        elif self.current_tool == ToolType.ERASER:
            for px, py in pixels:
                if self._allowed(px, py):
                    layer.image.setPixel(px, py, 0)

        elif self.current_tool == ToolType.SPRAY:
            for px, py in get_spray_pixels(
                cx,
                cy,
                radius=max(1, size),
                density=self.tool_options.spray_density,
                bounds_w=self.project.width,
                bounds_h=self.project.height,
            ):
                if self._allowed(px, py):
                    self._blend_pixel(layer.image, px, py, self.active_color, opacity)

    def _commit_stroke(self, text: str) -> None:
        """Pushes the stroke to the undo stack; the command triggers a UI refresh."""
        if self.before_stroke_image is None:
            self.canvas_item.live_editing = False
            return

        frame_idx = self._stroke_frame_idx
        layer_idx = self._stroke_layer_idx
        if not (0 <= frame_idx < len(self.project.frames)):
            self.canvas_item.live_editing = False
            self.before_stroke_image = None
            return
        frame = self.project.frames[frame_idx]
        if not (0 <= layer_idx < len(frame.layers)):
            self.canvas_item.live_editing = False
            self.before_stroke_image = None
            return
        layer = frame.layers[layer_idx]
        after = layer.image.copy()
        before = self.before_stroke_image
        self.before_stroke_image = None
        self.canvas_item.live_editing = False

        if before == after:
            self.canvas_item.update()
            return

        command = DrawStrokeCommand(
            self.project,
            frame_idx,
            layer_idx,
            before,
            after,
            text=text,
        )
        self.undo_stack.push(command)
        frame.touch()
        self.canvas_item.update()
        self.mini_map.update()
        self.canvas_modified.emit()

    def refresh(self) -> None:
        """Refreshes canvas rendering, mini-map and viewport indicator."""
        self.canvas_item.update()
        self.mini_map.update()
        self._update_mini_map_viewport()
