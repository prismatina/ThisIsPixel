"""
ThisIsPixel - Pixel Art Editor
==============================
Main window, menus, workspace docking and application lifecycle.

Architecture
------------
* ``Project`` is the single source of truth. Every document mutation calls
  :meth:`Project.notify`, which invokes ``MainWindow._on_document_changed``.
  All docks refresh from that one choke point (no stale panels).
* Structural edits and pixel strokes are QUndoCommands on one shared stack, so
  undo/redo covers layers, frames, opacity, visibility, lock, merge, move,
  drawing, fill, paste, delete and selection moves.
* The window prevents data loss: close/new/open ask to save, autosave writes a
  recovery file, and a recovery prompt appears when an autosave is found.
"""

import os
import sys
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QSize, QTimer, QStandardPaths, QEvent
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QImage,
    QKeySequence,
    QPainter,
    QUndoStack,
)
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QDockWidget,
    QFileDialog,
    QGridLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from canvas import CanvasView
from app_settings import create_settings
from dialogs import NewProjectDialog, PreferencesDialog, WelcomeDialog
from layers import LayersPanel
from models import Project
from palette import PalettePanel
from styles import apply_theme, setup_hidpi_support
from timeline import TimelinePanel
from tools import TOOL_SHORTCUTS, ToolOptionsBar, ToolType, create_app_icon, create_tool_icon
from version import APP_VERSION

APP_NAME = "ThisIsPixel"
MAX_RECENT_FILES = 8

TOOL_KEYS = {
    Qt.Key.Key_B: ToolType.PENCIL,
    Qt.Key.Key_E: ToolType.ERASER,
    Qt.Key.Key_L: ToolType.LINE,
    Qt.Key.Key_U: ToolType.RECTANGLE,
    Qt.Key.Key_O: ToolType.ELLIPSE,
    Qt.Key.Key_G: ToolType.BUCKET,
    Qt.Key.Key_I: ToolType.EYEDROPPER,
    Qt.Key.Key_M: ToolType.MARQUEE,
    Qt.Key.Key_S: ToolType.SPRAY,
}


class ToolboxWidget(QWidget):
    """Compact 2-column toolbox sidebar (nine tools, clustered at the top)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedWidth(78)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(6, 6, 6, 6)
        self.main_layout.setSpacing(6)

        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(3)
        self.main_layout.addLayout(self.grid)
        self.main_layout.addStretch()


class MainWindow(QMainWindow):
    """Main application window with a dock-based pixel art workspace."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Untitled.pxp - ThisIsPixel")
        self.resize(1280, 820)
        self.setMinimumSize(980, 640)
        self.setWindowIcon(create_app_icon())

        self.settings = create_settings()

        # ---- document --------------------------------------------------- #
        default_w = int(self.settings.value("default_width", 32))
        default_h = int(self.settings.value("default_height", 32))
        self.project = Project(width=default_w, height=default_h)
        self.undo_stack = QUndoStack(self)
        self._non_command_dirty = False
        self._refreshing = False
        self._first_show = True

        # ---- central workspace ------------------------------------------ #
        self.tool_options_bar = ToolOptionsBar(self)
        self.tool_options_bar.options_changed.connect(self._on_tool_options_changed)

        self.canvas_view = CanvasView(self.project, self.undo_stack, self.tool_options_bar, self)

        central_container = QWidget(self)
        central_layout = QVBoxLayout(central_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.tool_options_bar)
        central_layout.addWidget(self.canvas_view, 1)
        self.setCentralWidget(central_container)

        # ---- dock panels ------------------------------------------------- #
        self.toolbox_widget = ToolboxWidget(self)
        self.palette_panel = PalettePanel(self)
        self.layers_panel = LayersPanel(self.project, self.undo_stack, self)
        self.timeline_panel = TimelinePanel(self.project, self.undo_stack, self)

        self._init_docks()
        self._init_toolbox_buttons()
        self._init_menu_bar()
        self._init_status_bar()
        self._init_autosave()
        self._connect_signals()
        self._restore_layout()

        # Seed the document palette from the palette panel default.
        self.project.palette = self.palette_panel.palette()
        self.canvas_view.set_recent_colors(self.palette_panel.recent_colors)
        self.canvas_view.set_color(self.palette_panel.active_color)

        self._prune_recent_files()
        self._apply_preferences(initial=True)
        self._update_window_title()
        self._update_status_bar()

        # Every document mutation now funnels through one refresh path.
        self.project.change_callback = self._on_document_changed

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def _init_docks(self) -> None:
        self.setDockOptions(
            QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.GroupedDragging
        )

        self.dock_tools = QDockWidget("Tools", self)
        self.dock_tools.setObjectName("dockTools")
        self.dock_tools.setWidget(self.toolbox_widget)
        self.dock_tools.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock_tools)

        self.dock_palette = QDockWidget("Color Palette", self)
        self.dock_palette.setObjectName("dockColorPalette")
        self.dock_palette.setWidget(self.palette_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_palette)

        self.dock_layers = QDockWidget("Layers", self)
        self.dock_layers.setObjectName("dockLayers")
        self.dock_layers.setWidget(self.layers_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_layers)

        self.dock_timeline = QDockWidget("Animation Timeline", self)
        self.dock_timeline.setObjectName("dockTimeline")
        self.dock_timeline.setWidget(self.timeline_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock_timeline)

        self.resizeDocks([self.dock_palette, self.dock_layers], [420, 300], Qt.Orientation.Vertical)
        self.resizeDocks([self.dock_tools], [84], Qt.Orientation.Horizontal)

    def _init_toolbox_buttons(self) -> None:
        self.tool_button_group = QButtonGroup(self)
        self.tool_button_group.setExclusive(True)
        self.tool_buttons: Dict[ToolType, QToolButton] = {}

        tooltips = {
            ToolType.PENCIL: "Pencil - draw with the active color",
            ToolType.ERASER: "Eraser - erase pixels to transparent",
            ToolType.LINE: "Straight line - 1px line with live preview",
            ToolType.RECTANGLE: "Rectangle - outline or filled",
            ToolType.ELLIPSE: "Ellipse - outline or filled",
            ToolType.BUCKET: "Bucket fill - flood fill with tolerance",
            ToolType.EYEDROPPER: "Eyedropper - pick a color from the canvas",
            ToolType.MARQUEE: "Marquee - select, move, copy, cut and paste",
            ToolType.SPRAY: "Spray - random pixel scatter with density",
        }

        for idx, tool_type in enumerate(ToolType):
            letter = TOOL_SHORTCUTS.get(tool_type, "")
            btn = QToolButton(self)
            btn.setIcon(create_tool_icon(tool_type))
            btn.setIconSize(QSize(20, 20))
            btn.setFixedSize(32, 32)
            btn.setToolTip(f"{tooltips[tool_type]} [{letter}]")
            btn.setCheckable(True)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, t=tool_type: self._select_tool_by_type(t))
            self.tool_button_group.addButton(btn)
            self.tool_buttons[tool_type] = btn
            self.toolbox_widget.grid.addWidget(btn, idx // 2, idx % 2)

        self.tool_buttons[ToolType.PENCIL].setChecked(True)

    # ------------------------------------------------------------------ #
    # Menus
    # ------------------------------------------------------------------ #
    def _init_menu_bar(self) -> None:
        mb = self.menuBar()

        # ---- File ------------------------------------------------------- #
        menu_file = mb.addMenu("&File")

        act_new = QAction("&New Project...", self)
        act_new.setShortcut(QKeySequence.StandardKey.New)
        act_new.triggered.connect(self._on_new_project)
        menu_file.addAction(act_new)

        act_open = QAction("&Open Project...", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self._on_open_project)
        menu_file.addAction(act_open)

        self.menu_recent = menu_file.addMenu("Recent Files")
        self._update_recent_files_menu()

        menu_file.addSeparator()

        act_save = QAction("&Save Project", self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self._on_save_project)
        menu_file.addAction(act_save)

        act_save_as = QAction("Save &As...", self)
        act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        act_save_as.triggered.connect(self._on_save_project_as)
        menu_file.addAction(act_save_as)

        menu_file.addSeparator()

        act_export = QAction("&Export PNG...", self)
        act_export.setShortcut(QKeySequence("Ctrl+E"))
        act_export.triggered.connect(self._on_export_png)
        menu_file.addAction(act_export)

        act_sheet = QAction("Export Sprite &Sheet...", self)
        act_sheet.setShortcut(QKeySequence("Ctrl+Shift+E"))
        act_sheet.triggered.connect(self._on_export_sprite_sheet)
        menu_file.addAction(act_sheet)

        menu_file.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        # ---- Edit ------------------------------------------------------- #
        menu_edit = mb.addMenu("&Edit")

        self.act_undo = QAction("&Undo", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.triggered.connect(self.undo_stack.undo)
        self.act_undo.setEnabled(False)
        self.undo_stack.canUndoChanged.connect(self.act_undo.setEnabled)
        menu_edit.addAction(self.act_undo)

        self.act_redo = QAction("&Redo", self)
        self.act_redo.setShortcuts([QKeySequence.StandardKey.Redo, QKeySequence("Ctrl+Shift+Z")])
        self.act_redo.triggered.connect(self.undo_stack.redo)
        self.act_redo.setEnabled(False)
        self.undo_stack.canRedoChanged.connect(self.act_redo.setEnabled)
        menu_edit.addAction(self.act_redo)

        menu_edit.addSeparator()

        act_cut = QAction("Cu&t", self)
        act_cut.setShortcut(QKeySequence.StandardKey.Cut)
        act_cut.triggered.connect(self.canvas_view.cut_selection)
        menu_edit.addAction(act_cut)

        act_copy = QAction("&Copy", self)
        act_copy.setShortcut(QKeySequence.StandardKey.Copy)
        act_copy.triggered.connect(self.canvas_view.copy_selection)
        menu_edit.addAction(act_copy)

        act_paste = QAction("&Paste", self)
        act_paste.setShortcut(QKeySequence.StandardKey.Paste)
        act_paste.triggered.connect(self.canvas_view.paste_clipboard)
        menu_edit.addAction(act_paste)

        menu_edit.addSeparator()

        act_select_all = QAction("Select &All", self)
        act_select_all.setShortcut(QKeySequence.StandardKey.SelectAll)
        act_select_all.triggered.connect(self.canvas_view.select_all)
        menu_edit.addAction(act_select_all)

        act_deselect = QAction("&Deselect", self)
        act_deselect.setShortcut(QKeySequence("Ctrl+D"))
        act_deselect.triggered.connect(self.canvas_view.clear_selection)
        menu_edit.addAction(act_deselect)

        act_delete_sel = QAction("Delete Selection Content", self)
        act_delete_sel.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        act_delete_sel.triggered.connect(self.canvas_view.delete_selection)
        menu_edit.addAction(act_delete_sel)

        menu_edit.addSeparator()

        act_clear = QAction("Clear Current Layer", self)
        act_clear.triggered.connect(self._on_clear_layer)
        menu_edit.addAction(act_clear)

        menu_edit.addSeparator()

        act_prefs = QAction("&Preferences...", self)
        act_prefs.setShortcut(QKeySequence("Ctrl+,"))
        act_prefs.triggered.connect(self._open_preferences)
        menu_edit.addAction(act_prefs)

        # ---- Tools ------------------------------------------------------ #
        menu_tools = mb.addMenu("&Tools")
        self.tool_action_group = QActionGroup(self)
        self.tool_action_group.setExclusive(True)
        self.tool_actions: Dict[ToolType, QAction] = {}

        for tool_type in ToolType:
            letter = TOOL_SHORTCUTS.get(tool_type, "")
            act = QAction(f"{tool_type.value}\t{letter}" if letter else tool_type.value, self)
            act.setCheckable(True)
            act.setChecked(tool_type == ToolType.PENCIL)
            act.triggered.connect(lambda _, t=tool_type: self._select_tool_by_type(t))
            self.tool_action_group.addAction(act)
            menu_tools.addAction(act)
            self.tool_actions[tool_type] = act

        # ---- View ------------------------------------------------------- #
        menu_view = mb.addMenu("&View")

        act_zoom_in = QAction("Zoom &In", self)
        act_zoom_in.setShortcut(QKeySequence("Ctrl++"))
        act_zoom_in.triggered.connect(self.canvas_view.zoom_in)
        menu_view.addAction(act_zoom_in)

        act_zoom_out = QAction("Zoom &Out", self)
        act_zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        act_zoom_out.triggered.connect(self.canvas_view.zoom_out)
        menu_view.addAction(act_zoom_out)

        act_fit = QAction("Zoom to &Fit", self)
        act_fit.setShortcut(QKeySequence("Ctrl+0"))
        act_fit.triggered.connect(self.canvas_view.zoom_to_fit)
        menu_view.addAction(act_fit)

        menu_view.addSeparator()

        self.act_pixel_grid = QAction("Show &Pixel Grid", self, checkable=True)
        self.act_pixel_grid.setChecked(True)
        self.act_pixel_grid.toggled.connect(self.canvas_view.set_pixel_grid)
        menu_view.addAction(self.act_pixel_grid)

        self.act_tile_grid = QAction("Show &Tile Grid", self, checkable=True)
        self.act_tile_grid.setChecked(False)
        self.act_tile_grid.toggled.connect(self.canvas_view.set_tile_grid)
        menu_view.addAction(self.act_tile_grid)

        self.act_onion = QAction("Toggle &Onion Skin", self, checkable=True)
        self.act_onion.setChecked(False)
        self.act_onion.toggled.connect(self._on_onion_action_toggled)
        menu_view.addAction(self.act_onion)

        # ---- Animation --------------------------------------------------- #
        menu_anim = mb.addMenu("&Animation")

        act_play = QAction("Play / Pause", self)
        act_play.setShortcut(QKeySequence("Ctrl+Space"))
        act_play.triggered.connect(self.timeline_panel.toggle_playback)
        menu_anim.addAction(act_play)

        act_prev = QAction("Previous Frame", self)
        act_prev.setShortcut(QKeySequence("Ctrl+Left"))
        act_prev.triggered.connect(lambda: self._step_frame(-1))
        menu_anim.addAction(act_prev)

        act_next = QAction("Next Frame", self)
        act_next.setShortcut(QKeySequence("Ctrl+Right"))
        act_next.triggered.connect(lambda: self._step_frame(1))
        menu_anim.addAction(act_next)

        menu_anim.addSeparator()

        act_add_frame = QAction("Add Frame", self)
        act_add_frame.triggered.connect(self.timeline_panel._on_add_frame)
        menu_anim.addAction(act_add_frame)

        act_dup_frame = QAction("Duplicate Frame", self)
        act_dup_frame.triggered.connect(self.timeline_panel._on_duplicate_frame)
        menu_anim.addAction(act_dup_frame)

        act_del_frame = QAction("Delete Frame", self)
        act_del_frame.triggered.connect(self.timeline_panel._on_delete_frame)
        menu_anim.addAction(act_del_frame)

        # ---- Window ------------------------------------------------------ #
        menu_window = mb.addMenu("&Window")
        menu_window.addAction(self.dock_tools.toggleViewAction())
        menu_window.addAction(self.dock_palette.toggleViewAction())
        menu_window.addAction(self.dock_layers.toggleViewAction())
        menu_window.addAction(self.dock_timeline.toggleViewAction())
        menu_window.addSeparator()

        act_reset_layout = QAction("Reset Layout to Default", self)
        act_reset_layout.triggered.connect(self._reset_layout_to_default)
        menu_window.addAction(act_reset_layout)

        # ---- Help -------------------------------------------------------- #
        menu_help = mb.addMenu("&Help")
        act_guide = QAction("Panduan && Tips", self)
        act_guide.setShortcut(QKeySequence("F1"))
        act_guide.triggered.connect(self._show_guide)
        menu_help.addAction(act_guide)
        menu_help.addSeparator()

        act_about = QAction("About ThisIsPixel", self)
        act_about.triggered.connect(self._on_about)
        menu_help.addAction(act_about)

    # ------------------------------------------------------------------ #
    # Status bar / autosave
    # ------------------------------------------------------------------ #
    def _init_status_bar(self) -> None:
        sb = self.statusBar()

        self.status_cursor = QLabel("X: --  Y: --")
        self.status_cursor.setMinimumWidth(120)
        sb.addPermanentWidget(self.status_cursor)

        self.status_tool = QLabel("Tool: Pencil")
        self.status_tool.setMinimumWidth(200)
        sb.addPermanentWidget(self.status_tool)

        self.status_canvas = QLabel("32x32 px  |  Zoom: 1600%")
        self.status_canvas.setMinimumWidth(190)
        sb.addPermanentWidget(self.status_canvas)

        self.status_file = QLabel("Untitled.pxp")
        self.status_file.setMinimumWidth(220)
        sb.addPermanentWidget(self.status_file)

    def _init_autosave(self) -> None:
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self._on_autosave_tick)

    # ------------------------------------------------------------------ #
    # Signals
    # ------------------------------------------------------------------ #
    def _connect_signals(self) -> None:
        self.palette_panel.color_changed.connect(self.canvas_view.set_color)
        self.palette_panel.palette_changed.connect(self._on_palette_changed)
        self.palette_panel.recent_colors_changed.connect(self.canvas_view.set_recent_colors)

        self.canvas_view.color_picked.connect(self.palette_panel.set_active_color)
        self.canvas_view.cursor_moved.connect(self._on_cursor_moved)
        self.canvas_view.zoom_changed.connect(self._on_zoom_changed)
        self.canvas_view.canvas_modified.connect(self._on_canvas_modified)
        self.canvas_view.tool_changed.connect(self._on_canvas_tool_changed)
        self.canvas_view.status_message.connect(self._on_status_message)

        self.layers_panel.layers_changed.connect(self._on_layers_changed)
        self.timeline_panel.frame_changed.connect(self._on_frame_changed)
        self.timeline_panel.onion_skin_toggled.connect(self._on_onion_timeline_toggled)

        self.undo_stack.cleanChanged.connect(lambda _: self._update_window_title())

    # ------------------------------------------------------------------ #
    # Central refresh path
    # ------------------------------------------------------------------ #
    def _on_document_changed(self) -> None:
        """Single refresh entry point used by every document mutation."""
        if self._refreshing:
            return
        self._refreshing = True
        try:
            self.layers_panel.refresh()
            self.timeline_panel.refresh_document()
            self.canvas_view.refresh()
        finally:
            self._refreshing = False
        self._update_status_bar()
        self._update_window_title()

    # ------------------------------------------------------------------ #
    # Tool selection
    # ------------------------------------------------------------------ #
    def _select_tool_by_type(self, tool_type: ToolType) -> None:
        self.canvas_view.set_tool(tool_type)

    def _on_canvas_tool_changed(self, tool_type: ToolType) -> None:
        button = self.tool_buttons.get(tool_type)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        action = self.tool_actions.get(tool_type)
        if action is not None and not action.isChecked():
            action.setChecked(True)
        self._update_status_bar()

    def _on_tool_options_changed(self) -> None:
        self._update_status_bar()

    def keyPressEvent(self, event) -> None:
        """Single-letter tool shortcuts (text widgets consume their own keys)."""
        if event.modifiers() == Qt.KeyboardModifier.NoModifier:
            tool = TOOL_KEYS.get(event.key())
            if tool is not None:
                self._select_tool_by_type(tool)
                event.accept()
                return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event) -> bool:
        """Global tool shortcuts that never steal keystrokes from text fields."""
        if (
            event.type() == QEvent.Type.KeyPress
            and self.isActiveWindow()
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
            and QApplication.activeModalWidget() is None
        ):
            focus = QApplication.focusWidget()
            owns_focus = focus is None or focus.window() is self
            is_text = isinstance(focus, (QLineEdit, QAbstractSpinBox))
            if owns_focus and not is_text:
                tool = TOOL_KEYS.get(event.key())
                if tool is not None:
                    self._select_tool_by_type(tool)
                    return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------ #
    # Status / title
    # ------------------------------------------------------------------ #
    def _on_cursor_moved(self, x: int, y: int) -> None:
        if x >= 0 and y >= 0:
            self.status_cursor.setText(f"X: {x:02d}  Y: {y:02d}")
        else:
            self.status_cursor.setText("X: --  Y: --")

    def _on_zoom_changed(self, zoom_pct: int) -> None:
        self._update_status_bar()

    def _on_status_message(self, message: str) -> None:
        self.statusBar().showMessage(message, 4000)

    def _on_canvas_modified(self) -> None:
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        tool = self.canvas_view.current_tool
        size = self.tool_options_bar.brush_size
        opacity = int(round(self.tool_options_bar.brush_opacity * 100))
        if tool == ToolType.BUCKET:
            detail = f"tolerance {self.tool_options_bar.fill_tolerance}"
        elif tool in (ToolType.RECTANGLE, ToolType.ELLIPSE):
            detail = "filled" if self.tool_options_bar.shape_filled else "outline"
        elif tool == ToolType.SPRAY:
            detail = f"{size}px, density {self.tool_options_bar.spray_density}"
        else:
            detail = f"{size}px, {opacity}%"
        self.status_tool.setText(f"Tool: {tool.value} ({detail})")

        w, h = self.project.width, self.project.height
        zoom = int(round(self.canvas_view.zoom_factor * 100))
        self.status_canvas.setText(f"{w}x{h} px  |  Zoom: {zoom}%")

    def _is_dirty(self) -> bool:
        return self._non_command_dirty or not self.undo_stack.isClean()

    def _update_window_title(self) -> None:
        name = self.project.display_name
        mark = " *" if self._is_dirty() else ""
        self.setWindowTitle(f"{name}{mark} - ThisIsPixel")
        self.status_file.setText(f"{name}{mark}")

    # ------------------------------------------------------------------ #
    # Palette
    # ------------------------------------------------------------------ #
    def _on_palette_changed(self, colors: List[QColor]) -> None:
        self.project.palette = [QColor(c) for c in colors]
        self._non_command_dirty = True
        self._update_window_title()

    def _sync_palette_to_project(self) -> None:
        self.project.palette = [QColor(c) for c in self.palette_panel.palette()]

    # ------------------------------------------------------------------ #
    # Frame / onion skin
    # ------------------------------------------------------------------ #
    def _on_frame_changed(self, frame_idx: int) -> None:
        self.layers_panel.refresh()
        self.canvas_view.refresh()
        self._update_status_bar()
        self._update_window_title()

    def _on_layers_changed(self) -> None:
        self.canvas_view.refresh()
        self._update_status_bar()
        self._update_window_title()

    def _step_frame(self, direction: int) -> None:
        total = len(self.project.frames)
        if total <= 1:
            return
        self.timeline_panel.stop_playback()
        new_idx = (self.project.active_frame_idx + direction) % total
        self.project.set_active_frame(new_idx)
        self.timeline_panel.sync_selection()
        self._on_frame_changed(new_idx)

    def _on_onion_action_toggled(self, checked: bool) -> None:
        self.canvas_view.set_onion_skin(checked)
        self.timeline_panel.set_onion_skin_state(checked)
        self.canvas_view.refresh()

    def _on_onion_timeline_toggled(self, checked: bool) -> None:
        self.canvas_view.set_onion_skin(checked)
        if self.act_onion.isChecked() != checked:
            self.act_onion.blockSignals(True)
            self.act_onion.setChecked(checked)
            self.act_onion.blockSignals(False)
        self.canvas_view.refresh()

    # ------------------------------------------------------------------ #
    # Project lifecycle
    # ------------------------------------------------------------------ #
    def _maybe_save(self) -> bool:
        """Returns True when it is safe to discard the current document."""
        if not self._is_dirty():
            return True
        reply = QMessageBox.warning(
            self,
            "Unsaved Changes",
            f"Save changes to {self.project.display_name} before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if reply == QMessageBox.StandardButton.Save:
            return self._on_save_project()
        return reply == QMessageBox.StandardButton.Discard

    def _adopt_project(self, project: Project, recent_path: Optional[str] = None) -> None:
        self.project.change_callback = None
        self.project = project
        self.undo_stack.clear()
        self._non_command_dirty = False
        self._rebind_project()
        if recent_path:
            self._add_recent_file(recent_path)
        self._update_window_title()
        self._update_status_bar()

    def _rebind_project(self) -> None:
        """Rebinds every view to the current document and resyncs palette/state."""
        self.project.change_callback = self._on_document_changed

        self.canvas_view.set_project(self.project)
        self.layers_panel.set_project(self.project)
        self.timeline_panel.set_project(self.project)

        self.palette_panel.blockSignals(True)
        try:
            if self.project.palette:
                self.palette_panel.set_palette(self.project.palette)
            self.project.palette = self.palette_panel.palette()
        finally:
            self.palette_panel.blockSignals(False)

        self.canvas_view.set_recent_colors(self.palette_panel.recent_colors)
        self.canvas_view.set_color(self.palette_panel.active_color)

        onion = self.act_onion.isChecked()
        self.timeline_panel.set_onion_skin_state(onion)
        self.canvas_view.set_onion_skin(onion)

        self._apply_zoom_preference()

    def _on_new_project(self) -> None:
        if not self._maybe_save():
            return
        dlg = NewProjectDialog(self)
        if not dlg.exec():
            return
        project = Project(width=dlg.canvas_width, height=dlg.canvas_height)
        project.palette = [QColor(c) for c in self.palette_panel.palette()]
        self._discard_autosave()
        self._adopt_project(project)

    def _on_open_project(self) -> None:
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open ThisIsPixel Project",
            "",
            "ThisIsPixel Project (*.pxp);;All Files (*)",
        )
        if path:
            self._load_project(path)

    def _load_project(self, path: str, add_recent: bool = True) -> bool:
        if not os.path.exists(path):
            QMessageBox.warning(self, "Open Failed", f"File not found:\n{path}")
            self._remove_recent_file(path)
            return False
        try:
            project = Project.load_from_file(path)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            QMessageBox.critical(
                self, "Open Failed", f"Could not open the project file:\n{exc}"
            )
            return False

        self._discard_autosave()
        self._adopt_project(project, recent_path=path if add_recent else None)
        self.statusBar().showMessage(f"Opened {os.path.basename(path)}", 4000)
        return True

    def _save_to(self, path: str) -> bool:
        if not path.lower().endswith(".pxp"):
            path += ".pxp"
        self._sync_palette_to_project()
        try:
            self.project.save_to_file(path)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            QMessageBox.critical(self, "Save Failed", f"Could not save the project:\n{exc}")
            return False

        self.undo_stack.setClean()
        self._non_command_dirty = False
        self._discard_autosave()
        self._add_recent_file(path)
        self._update_window_title()
        self.statusBar().showMessage(f"Saved to {os.path.basename(path)}", 4000)
        return True

    def _on_save_project(self) -> bool:
        if not self.project.file_path:
            return self._on_save_project_as()
        return self._save_to(self.project.file_path)

    def _on_save_project_as(self) -> bool:
        suggested = self.project.file_path or f"{os.path.splitext(self.project.display_name)[0]}.pxp"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save ThisIsPixel Project", suggested, "ThisIsPixel Project (*.pxp)"
        )
        if not path:
            return False
        return self._save_to(path)

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    def _ask_export_scale(self) -> Optional[int]:
        default = int(self.settings.value("default_export_scale", 8))
        scales = [1, 2, 4, 8, 16, 32]
        items = [
            f"{scale}x  ({self.project.width * scale} x {self.project.height * scale} px)"
            for scale in scales
        ]
        current = scales.index(default) if default in scales else 3
        item, ok = QInputDialog.getItem(
            self, "Export Scale", "Scale factor (nearest neighbour):", items, current, False
        )
        if not ok:
            return None
        return scales[items.index(item)]

    def _on_export_png(self) -> None:
        scale = self._ask_export_scale()
        if scale is None:
            return

        suggested = f"{os.path.splitext(self.project.display_name)[0]}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PNG Image", suggested, "PNG Image (*.png)"
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"

        composite = self.project.active_frame.composite(use_cache=False)
        target_w = self.project.width * scale
        target_h = self.project.height * scale
        scaled = composite.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        if scaled.save(path, "PNG"):
            self.statusBar().showMessage(
                f"Exported {target_w}x{target_h} px to {os.path.basename(path)}", 5000
            )
        else:
            QMessageBox.critical(self, "Export Failed", "The PNG file could not be written.")

    def _on_export_sprite_sheet(self) -> None:
        scale = self._ask_export_scale()
        if scale is None:
            return

        count = len(self.project.frames)
        sheet_w = self.project.width * scale * count
        sheet_h = self.project.height * scale
        if sheet_w > 32768 or sheet_h > 32768:
            QMessageBox.warning(
                self,
                "Sprite Sheet Too Large",
                f"The resulting sheet would be {sheet_w}x{sheet_h} px.\n"
                "Choose a smaller scale or fewer frames.",
            )
            return

        suggested = f"{os.path.splitext(self.project.display_name)[0]}_sheet.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Sprite Sheet", suggested, "PNG Image (*.png)"
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"

        sheet = QImage(sheet_w, sheet_h, QImage.Format.Format_ARGB32)
        sheet.fill(QColor(0, 0, 0, 0))
        painter = QPainter(sheet)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        for index, frame in enumerate(self.project.frames):
            frame_img = frame.composite(use_cache=False).scaled(
                self.project.width * scale,
                self.project.height * scale,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            painter.drawImage(index * self.project.width * scale, 0, frame_img)
        painter.end()

        if sheet.save(path, "PNG"):
            self.statusBar().showMessage(
                f"Exported {count}-frame sheet ({sheet_w}x{sheet_h} px)", 5000
            )
        else:
            QMessageBox.critical(self, "Export Failed", "The sprite sheet could not be written.")

    # ------------------------------------------------------------------ #
    # Edit helpers
    # ------------------------------------------------------------------ #
    def _on_clear_layer(self) -> None:
        reply = QMessageBox.question(
            self,
            "Clear Current Layer",
            "Clear every pixel on the active layer? This can be undone with Ctrl+Z.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.canvas_view.clear_active_layer()

    def _open_preferences(self) -> None:
        dlg = PreferencesDialog(self)
        dlg.settings_saved.connect(self._on_preferences_saved)
        dlg.exec()

    def _on_preferences_saved(self) -> None:
        self._apply_preferences(initial=False)

    def _apply_preferences(self, initial: bool) -> None:
        app = QApplication.instance()
        if app is not None:
            theme = str(self.settings.value("theme", "dark"))
            apply_theme(app, theme)

        pixel_grid = self.settings.value("show_pixel_grid", True, type=bool)
        tile_grid = self.settings.value("show_tile_grid", False, type=bool)
        tile_size = int(self.settings.value("tile_size", 8))

        self.act_pixel_grid.blockSignals(True)
        self.act_pixel_grid.setChecked(pixel_grid)
        self.act_pixel_grid.blockSignals(False)
        self.canvas_view.set_pixel_grid(pixel_grid)

        self.act_tile_grid.blockSignals(True)
        self.act_tile_grid.setChecked(tile_grid)
        self.act_tile_grid.blockSignals(False)
        self.canvas_view.set_tile_grid(tile_grid)
        self.canvas_view.set_tile_size(tile_size)

        interval = int(self.settings.value("autosave_interval", 5))
        self.autosave_timer.stop()
        if interval > 0:
            self.autosave_timer.start(max(1, interval) * 60_000)

        if not initial:
            self._apply_zoom_preference()
            self._update_status_bar()

    def _apply_zoom_preference(self) -> None:
        default_zoom = int(self.settings.value("default_zoom", 0))
        autofit = self.settings.value("autofit_on_open", True, type=bool)
        if default_zoom > 0:
            self.canvas_view.set_zoom(default_zoom / 100.0)
        elif autofit:
            self.canvas_view.zoom_to_fit()
        else:
            self.canvas_view.set_zoom(16.0)

    # ------------------------------------------------------------------ #
    # Autosave / recovery
    # ------------------------------------------------------------------ #
    def _autosave_path(self) -> str:
        if self.project.file_path:
            return self.project.file_path + ".autosave"
        base = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
        if not base:
            base = os.path.expanduser("~")
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, "untitled.pxp.autosave")

    def _on_autosave_tick(self) -> None:
        if not self._is_dirty():
            return
        path = self._autosave_path()
        try:
            self._sync_palette_to_project()
            self.project.save_copy(path)
            self.settings.setValue("autosave_path", path)
            self.statusBar().showMessage("Autosave written", 2500)
        except Exception:  # noqa: BLE001 - autosave must never interrupt drawing
            pass

    def _discard_autosave(self) -> None:
        path = str(self.settings.value("autosave_path", "") or "")
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        self.settings.remove("autosave_path")

    def check_autosave_recovery(self) -> bool:
        """Offers to restore a previous autosave (called once at startup).

        Returns True when a recovered document became the active project.
        """
        path = str(self.settings.value("autosave_path", "") or "")
        if not path:
            return False
        if not os.path.exists(path):
            self.settings.remove("autosave_path")
            return False

        reply = QMessageBox.question(
            self,
            "Recover Autosaved Work",
            f"An autosaved session was found:\n{path}\n\nRecover it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self._load_project(path, add_recent=False):
                self.project.file_path = None
                self.project.is_modified = True
                self._non_command_dirty = True
                self._update_window_title()
                self.statusBar().showMessage("Recovered autosaved project", 5000)
                return True
            return False
        self._discard_autosave()
        return False

    # ------------------------------------------------------------------ #
    # First-run guide / command-line startup
    # ------------------------------------------------------------------ #
    def _show_guide(self) -> None:
        """Help > Panduan & Tips (also F1)."""
        WelcomeDialog(self, first_run=False).exec()

    def show_welcome_if_needed(self) -> None:
        """Shows the Indonesian quick-start guide on the first launch only."""
        if os.environ.get("THISISPIXEL_SKIP_WELCOME"):
            return
        if not self.settings.value("show_welcome", True, type=bool):
            return

        dialog = WelcomeDialog(self, first_run=True)
        dialog.exec()
        if dialog.should_skip_next_time():
            self.settings.setValue("show_welcome", False)
            self.settings.sync()

    def startup(self, project_path: str = "") -> None:
        """Runs after the window is visible: recovery, file argument, guide."""
        recovered = self.check_autosave_recovery()
        if project_path:
            self._load_project(project_path)
            return
        if not recovered:
            self.show_welcome_if_needed()

    # ------------------------------------------------------------------ #
    # Recent files
    # ------------------------------------------------------------------ #
    def _recent_files(self) -> List[str]:
        value = self.settings.value("recent_files", [], type=list)
        return [str(p) for p in value] if isinstance(value, list) else []

    def _save_recent_files(self, files: List[str]) -> None:
        self.settings.setValue("recent_files", files[:MAX_RECENT_FILES])
        self._update_recent_files_menu()

    def _add_recent_file(self, path: str) -> None:
        path = os.path.abspath(path)
        recent = [p for p in self._recent_files() if os.path.normcase(p) != os.path.normcase(path)]
        recent.insert(0, path)
        self._save_recent_files(recent)

    def _remove_recent_file(self, path: str) -> None:
        recent = [
            p for p in self._recent_files() if os.path.normcase(p) != os.path.normcase(os.path.abspath(path))
        ]
        self._save_recent_files(recent)

    def _prune_recent_files(self) -> None:
        recent = [p for p in self._recent_files() if os.path.exists(p)]
        self._save_recent_files(recent)

    def _update_recent_files_menu(self) -> None:
        self.menu_recent.clear()
        recent = self._recent_files()
        if not recent:
            act = self.menu_recent.addAction("(No recent files)")
            act.setEnabled(False)
            return

        for path in recent:
            act = self.menu_recent.addAction(os.path.basename(path))
            act.setToolTip(path)
            act.triggered.connect(lambda _, p=path: self._open_recent_file(p))

        self.menu_recent.addSeparator()
        act_clear = self.menu_recent.addAction("Clear Recent Files")
        act_clear.triggered.connect(lambda: self._save_recent_files([]))

    def _open_recent_file(self, path: str) -> None:
        if not os.path.exists(path):
            QMessageBox.warning(self, "File Missing", f"The file no longer exists:\n{path}")
            self._remove_recent_file(path)
            return
        if not self._maybe_save():
            return
        self._load_project(path)

    # ------------------------------------------------------------------ #
    # Window state / about
    # ------------------------------------------------------------------ #
    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About ThisIsPixel",
            f"<b>ThisIsPixel</b> {APP_VERSION} - Pixel Art Studio<br><br>"
            "Features:<br>"
            "&bull; 9 tools: pencil, eraser, line, rectangle, ellipse, bucket,<br>"
            "&nbsp;&nbsp;eyedropper, marquee, spray<br>"
            "&bull; Multi-layer and multi-frame animation with onion skin<br>"
            "&bull; Palette import/export (.gpl, .pal) saved inside .pxp<br>"
            "&bull; Unlimited undo/redo for pixels and structure<br>"
            "&bull; Selection move, copy, cut and paste<br>"
            "&bull; PNG and sprite-sheet export (1x - 32x, nearest neighbour)<br>"
            "&bull; Autosave and crash recovery<br><br>"
            "Press <b>F1</b> for the Indonesian quick-start guide.<br>"
            "Press <b>Ctrl+,</b> to review all shortcuts.",
        )

    def _restore_layout(self) -> None:
        geo = self.settings.value("window_geometry")
        state = self.settings.value("window_state")
        if geo:
            self.restoreGeometry(geo)
        if state:
            self.restoreState(state)

    def _reset_layout_to_default(self) -> None:
        for dock, area in (
            (self.dock_tools, Qt.DockWidgetArea.LeftDockWidgetArea),
            (self.dock_palette, Qt.DockWidgetArea.RightDockWidgetArea),
            (self.dock_layers, Qt.DockWidgetArea.RightDockWidgetArea),
            (self.dock_timeline, Qt.DockWidgetArea.BottomDockWidgetArea),
        ):
            dock.setFloating(False)
            self.addDockWidget(area, dock)
            dock.show()
        self.resizeDocks(
            [self.dock_palette, self.dock_layers], [420, 300], Qt.Orientation.Vertical
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            QTimer.singleShot(0, self._apply_zoom_preference)

    def closeEvent(self, event) -> None:
        if not self._maybe_save():
            event.ignore()
            return

        self._discard_autosave()
        self.timeline_panel.stop_playback()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.settings.setValue("window_geometry", self.saveGeometry())
        self.settings.setValue("window_state", self.saveState())
        self.settings.sync()
        event.accept()


def main() -> None:
    """Application entry point."""
    setup_hidpi_support()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(create_app_icon())

    settings = create_settings()
    apply_theme(app, str(settings.value("theme", "dark")))

    window = MainWindow()
    window.show()

    # Windows "Open with" / file association passes the project path as argv[1].
    startup_file = ""
    for argument in sys.argv[1:]:
        if os.path.isfile(argument):
            startup_file = os.path.abspath(argument)
            break

    QTimer.singleShot(0, lambda: window.startup(startup_file))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
