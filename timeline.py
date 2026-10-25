"""
ThisIsPixel - Animation Timeline Dock Panel
===========================================
Horizontal filmstrip timeline:

- Each column is a frame with a cached composite thumbnail.
- Playback (Play/Pause, FPS 1-30, Loop) driven by a QTimer.
- Onion skin toggle (previous frame 30%, next frame 15%, rendered behind).
- Undoable frame operations: add, duplicate, delete, move left/right.
- FPS and loop state persist through QSettings.
"""

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize, QRectF
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QIcon, QUndoStack
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QSlider,
    QLabel,
    QCheckBox,
    QSpinBox,
)

from commands import (
    AddFrameCommand,
    DuplicateFrameCommand,
    MoveFrameCommand,
    RemoveFrameCommand,
)
from models import Project
from app_settings import create_settings


class TimelinePanel(QWidget):
    """Animation timeline dock panel."""

    frame_changed = pyqtSignal(int)
    onion_skin_toggled = pyqtSignal(bool)

    def __init__(
        self,
        project: Project,
        undo_stack: QUndoStack,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.project = project
        self.undo_stack = undo_stack
        self.settings = create_settings()

        self.is_playing: bool = False
        self.fps: int = int(self.settings.value("fps", 12, type=int))
        self.fps = max(1, min(30, self.fps))
        self.loop: bool = self.settings.value("loop", True, type=bool)
        self.onion_skin: bool = False
        self._frame_fingerprint: tuple = ()

        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self._on_playback_tick)

        self._init_ui()
        self.refresh()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        ctrl_bar = QHBoxLayout()
        ctrl_bar.setSpacing(8)

        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setToolTip("Start / pause animation playback")
        self.btn_play.setFixedWidth(74)
        self.btn_play.clicked.connect(self.toggle_playback)
        ctrl_bar.addWidget(self.btn_play)

        lbl_fps = QLabel("FPS:")
        lbl_fps.setStyleSheet("color: #888888; font-weight: 500;")
        ctrl_bar.addWidget(lbl_fps)

        self.slider_fps = QSlider(Qt.Orientation.Horizontal)
        self.slider_fps.setRange(1, 30)
        self.slider_fps.setValue(self.fps)
        self.slider_fps.setFixedWidth(80)

        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(1, 30)
        self.spin_fps.setValue(self.fps)
        self.spin_fps.setFixedWidth(48)

        self.slider_fps.valueChanged.connect(self.spin_fps.setValue)
        self.spin_fps.valueChanged.connect(self._on_fps_changed)
        ctrl_bar.addWidget(self.slider_fps)
        ctrl_bar.addWidget(self.spin_fps)

        self.check_loop = QCheckBox("Loop")
        self.check_loop.setChecked(self.loop)
        self.check_loop.toggled.connect(self._on_loop_toggled)
        ctrl_bar.addWidget(self.check_loop)

        self.check_onion = QCheckBox("Onion Skin")
        self.check_onion.setToolTip("Ghost previous frame (30%) and next frame (15%)")
        self.check_onion.toggled.connect(self._on_onion_toggled)
        ctrl_bar.addWidget(self.check_onion)

        ctrl_bar.addStretch()

        self.btn_move_left = QPushButton("◀")
        self.btn_move_left.setToolTip("Move active frame left")
        self.btn_move_left.setFixedWidth(28)
        self.btn_move_left.clicked.connect(lambda: self._move_frame(-1))

        self.btn_move_right = QPushButton("▶")
        self.btn_move_right.setToolTip("Move active frame right")
        self.btn_move_right.setFixedWidth(28)
        self.btn_move_right.clicked.connect(lambda: self._move_frame(1))

        self.btn_add_frame = QPushButton("+ Frame")
        self.btn_add_frame.setToolTip("Add a new empty frame")
        self.btn_add_frame.clicked.connect(self._on_add_frame)

        self.btn_dup_frame = QPushButton("Duplicate")
        self.btn_dup_frame.setToolTip("Duplicate the active frame")
        self.btn_dup_frame.clicked.connect(self._on_duplicate_frame)

        self.btn_del_frame = QPushButton("Delete")
        self.btn_del_frame.setToolTip("Delete the active frame")
        self.btn_del_frame.clicked.connect(self._on_delete_frame)

        ctrl_bar.addWidget(self.btn_move_left)
        ctrl_bar.addWidget(self.btn_move_right)
        ctrl_bar.addWidget(self.btn_add_frame)
        ctrl_bar.addWidget(self.btn_dup_frame)
        ctrl_bar.addWidget(self.btn_del_frame)

        layout.addLayout(ctrl_bar)

        self.table_frames = QTableWidget(1, 1)
        self.table_frames.setFixedHeight(78)
        self.table_frames.verticalHeader().setVisible(False)
        self.table_frames.horizontalHeader().setVisible(False)
        self.table_frames.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_frames.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectColumns)
        self.table_frames.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_frames.cellClicked.connect(self._on_cell_clicked)
        self.table_frames.setIconSize(QSize(36, 36))
        self.table_frames.setStyleSheet(
            "QTableWidget { background-color: #1b1b1b; border: 1px solid #333333; border-radius: 4px; }"
            "QTableWidget::item { padding: 4px; border: 1px solid transparent; border-radius: 4px; }"
            "QTableWidget::item:selected { background-color: #243b57; border: 1px solid #3a78c4; }"
        )
        layout.addWidget(self.table_frames)

    # ------------------------------------------------------------------ #
    # Refresh / sync
    # ------------------------------------------------------------------ #
    def set_project(self, project: Project) -> None:
        self.project = project
        self.stop_playback()
        self.refresh()

    def refresh(self) -> None:
        """Rebuilds the filmstrip using cached frame thumbnails."""
        total = len(self.project.frames)
        self._frame_fingerprint = tuple(id(frame) for frame in self.project.frames)
        self.table_frames.setColumnCount(total)
        self.table_frames.setRowHeight(0, 70)

        for i, frame in enumerate(self.project.frames):
            self.table_frames.setColumnWidth(i, 68)
            thumb = QPixmap(36, 36)
            thumb.fill(Qt.GlobalColor.transparent)
            painter = QPainter(thumb)
            painter.drawImage(0, 0, frame.thumbnail(36))
            painter.setPen(QPen(QColor("#3a3a3a"), 1))
            painter.drawRoundedRect(QRectF(0, 0, 35, 35), 3, 3)
            painter.end()

            item = QTableWidgetItem(f"#{i + 1}")
            item.setIcon(QIcon(thumb))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            item.setToolTip(f"Frame {i + 1}")
            self.table_frames.setItem(0, i, item)

        self._sync_selection()
        self._update_button_states()

    def refresh_document(self) -> None:
        """Rebuilds the filmstrip when frames changed, else refreshes one thumb."""
        fingerprint = tuple(id(frame) for frame in self.project.frames)
        if (
            self.table_frames.columnCount() != len(self.project.frames)
            or fingerprint != self._frame_fingerprint
        ):
            self.refresh()
            return
        self.refresh_active_frame()
        self._sync_selection()
        self._update_button_states()

    def refresh_active_frame(self) -> None:
        """Updates only the thumbnail of the active frame (cheap during drawing)."""
        index = self.project.active_frame_idx
        if not (0 <= index < self.table_frames.columnCount()):
            return
        frame = self.project.frames[index]
        thumb = QPixmap(36, 36)
        thumb.fill(Qt.GlobalColor.transparent)
        painter = QPainter(thumb)
        painter.drawImage(0, 0, frame.thumbnail(36))
        painter.setPen(QPen(QColor("#3a3a3a"), 1))
        painter.drawRoundedRect(QRectF(0, 0, 35, 35), 3, 3)
        painter.end()
        item = self.table_frames.item(0, index)
        if item is not None:
            item.setIcon(QIcon(thumb))

    def sync_selection(self) -> None:
        """Selects the active frame column without emitting click events."""
        self._sync_selection()

    def _sync_selection(self) -> None:
        active = self.project.active_frame_idx
        if 0 <= active < self.table_frames.columnCount():
            self.table_frames.blockSignals(True)
            self.table_frames.setCurrentCell(0, active)
            self.table_frames.blockSignals(False)

    def _update_button_states(self) -> None:
        total = len(self.project.frames)
        active = self.project.active_frame_idx
        self.btn_del_frame.setEnabled(total > 1)
        self.btn_move_left.setEnabled(active > 0)
        self.btn_move_right.setEnabled(active < total - 1)
        self.btn_play.setEnabled(total > 1)

    # ------------------------------------------------------------------ #
    # Playback
    # ------------------------------------------------------------------ #
    def _on_fps_changed(self, fps: int) -> None:
        self.fps = max(1, fps)
        self.settings.setValue("fps", self.fps)
        if self.is_playing:
            self.playback_timer.setInterval(max(10, 1000 // self.fps))

    def _on_loop_toggled(self, checked: bool) -> None:
        self.loop = checked
        self.settings.setValue("loop", checked)

    def _on_onion_toggled(self, checked: bool) -> None:
        self.onion_skin = checked
        self.onion_skin_toggled.emit(checked)

    def set_onion_skin_state(self, active: bool) -> None:
        """Syncs the checkbox (external View menu toggle) without recursion."""
        self.onion_skin = active
        self.check_onion.blockSignals(True)
        self.check_onion.setChecked(active)
        self.check_onion.blockSignals(False)

    def toggle_playback(self) -> None:
        if len(self.project.frames) <= 1:
            return
        if self.is_playing:
            self.stop_playback()
        else:
            self.playback_timer.start(max(10, 1000 // self.fps))
            self.is_playing = True
            self.btn_play.setText("⏸ Pause")

    def stop_playback(self) -> None:
        self.playback_timer.stop()
        self.is_playing = False
        if hasattr(self, "btn_play"):
            self.btn_play.setText("▶ Play")

    def _on_playback_tick(self) -> None:
        total = len(self.project.frames)
        if total <= 1:
            self.stop_playback()
            return

        next_idx = self.project.active_frame_idx + 1
        if next_idx >= total:
            if self.loop:
                next_idx = 0
            else:
                self.stop_playback()
                return

        self.project.set_active_frame(next_idx)
        self._sync_selection()
        self._update_button_states()
        self.frame_changed.emit(next_idx)

    # ------------------------------------------------------------------ #
    # Frame operations (undoable)
    # ------------------------------------------------------------------ #
    def _on_cell_clicked(self, row: int, col: int) -> None:
        if 0 <= col < len(self.project.frames):
            self.project.set_active_frame(col)
            self._sync_selection()
            self._update_button_states()
            self.frame_changed.emit(col)

    def _on_add_frame(self) -> None:
        self.stop_playback()
        self.undo_stack.push(
            AddFrameCommand(self.project, index=len(self.project.frames))
        )
        self.refresh()
        self.frame_changed.emit(self.project.active_frame_idx)

    def _on_duplicate_frame(self) -> None:
        self.stop_playback()
        self.undo_stack.push(
            DuplicateFrameCommand(self.project, self.project.active_frame_idx)
        )
        self.refresh()
        self.frame_changed.emit(self.project.active_frame_idx)

    def _on_delete_frame(self) -> None:
        if len(self.project.frames) <= 1:
            return
        self.stop_playback()
        self.undo_stack.push(
            RemoveFrameCommand(self.project, self.project.active_frame_idx)
        )
        self.refresh()
        self.frame_changed.emit(self.project.active_frame_idx)

    def _move_frame(self, direction: int) -> None:
        current = self.project.active_frame_idx
        target = current + direction
        if 0 <= target < len(self.project.frames):
            self.undo_stack.push(MoveFrameCommand(self.project, current, target))
            self.refresh()
            self.frame_changed.emit(self.project.active_frame_idx)
