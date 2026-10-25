"""
ThisIsPixel - Layers Dock Panel
===============================
Layer management built on Qt's Model/View architecture:

- ``LayerListModel`` exposes the active frame's layers plus thumbnail cache.
- ``LayerItemDelegate`` renders a 32x32 thumbnail, name, opacity and clickable
  Eye / Lock buttons on every row.
- ``LayersPanel`` provides undoable actions: add, duplicate, delete, move,
  merge down, rename, opacity, visibility and lock.

Every structural action is a QUndoCommand (see commands.py), so Ctrl+Z works
consistently across the whole document.
"""

from typing import List, Optional

from PyQt6.QtCore import (
    Qt,
    QAbstractListModel,
    QModelIndex,
    QSize,
    QRect,
    QRectF,
    QEvent,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QPixmap,
    QPainter,
    QPen,
    QBrush,
    QColor,
    QMouseEvent,
    QUndoStack,
)
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListView,
    QPushButton,
    QSlider,
    QLabel,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QMenu,
    QInputDialog,
    QMessageBox,
)

from commands import (
    AddLayerCommand,
    DuplicateLayerCommand,
    MergeDownCommand,
    MoveLayerCommand,
    RemoveLayerCommand,
    RenameLayerCommand,
    SetLayerLockedCommand,
    SetLayerOpacityCommand,
    SetLayerVisibleCommand,
)
from models import Layer, Project


class LayerListModel(QAbstractListModel):
    """List model binding the active frame's layers to the QListView."""

    NameRole = Qt.ItemDataRole.UserRole + 1
    VisibleRole = Qt.ItemDataRole.UserRole + 2
    LockedRole = Qt.ItemDataRole.UserRole + 3
    OpacityRole = Qt.ItemDataRole.UserRole + 4

    def __init__(self, project: Project, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project = project

    @property
    def layers(self) -> List[Layer]:
        return self.project.active_frame.layers

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.layers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.layers)):
            return None

        layer = self.layers[index.row()]

        if role in (Qt.ItemDataRole.DisplayRole, self.NameRole):
            return layer.name
        if role == Qt.ItemDataRole.DecorationRole:
            return QPixmap.fromImage(layer.thumbnail(32))
        if role == self.VisibleRole:
            return layer.visible
        if role == self.LockedRole:
            return layer.locked
        if role == self.OpacityRole:
            return int(round(layer.opacity * 100))
        if role == Qt.ItemDataRole.SizeHintRole:
            return QSize(200, 46)
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{layer.name}\nOpacity: {int(layer.opacity * 100)}%"
        return None

    def refresh(self) -> None:
        """Resets the model so every row is repainted from the domain objects."""
        self.beginResetModel()
        self.endResetModel()


class LayerItemDelegate(QStyledItemDelegate):
    """Row renderer with clickable Eye/Lock hotspots."""

    def __init__(self, panel: "LayersPanel", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.panel = panel

    @staticmethod
    def _hotspots(option: QStyleOptionViewItem) -> tuple:
        row_rect = option.rect.adjusted(2, 2, -2, -2)
        eye_rect = QRect(
            row_rect.right() - 48, row_rect.top() + (row_rect.height() - 24) // 2, 22, 24
        )
        lock_rect = QRect(
            row_rect.right() - 24, row_rect.top() + (row_rect.height() - 24) // 2, 22, 24
        )
        return row_rect, eye_rect, lock_rect

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        row_rect, eye_rect, lock_rect = self._hotspots(option)

        if option.state & QStyle.StateFlag.State_Selected:
            painter.setBrush(QBrush(QColor("#243b57")))
            painter.setPen(QPen(QColor("#3a78c4"), 1))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setBrush(QBrush(QColor("#2c2c2c")))
            painter.setPen(QPen(QColor("#3a3a3a"), 1))
        else:
            painter.setBrush(QBrush(QColor("#222222")))
            painter.setPen(QPen(QColor("#2b2b2b"), 1))
        painter.drawRoundedRect(QRectF(row_rect), 4, 4)

        thumb: Optional[QPixmap] = index.data(Qt.ItemDataRole.DecorationRole)
        thumb_x = row_rect.left() + 6
        thumb_y = row_rect.top() + (row_rect.height() - 32) // 2
        if thumb:
            painter.drawPixmap(thumb_x, thumb_y, thumb)

        name = index.data(LayerListModel.NameRole) or "Layer"
        opacity = index.data(LayerListModel.OpacityRole)
        visible = index.data(LayerListModel.VisibleRole)
        locked = index.data(LayerListModel.LockedRole)

        text_x = thumb_x + 38
        text_y = row_rect.top() + 18
        painter.setPen(QColor("#ffffff" if visible else "#777777"))
        font = painter.font()
        font.setBold(index.row() == self.panel.project.active_layer_idx)
        painter.setFont(font)
        painter.drawText(text_x, text_y, str(name))

        subtext = f"{opacity}%" + ("  •  Locked" if locked else "")
        painter.setPen(QColor("#888888"))
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(text_x, text_y + 15, subtext)

        painter.setBrush(QBrush(QColor("#2a2a2a")))
        painter.setPen(QPen(QColor("#363636"), 1))
        painter.drawRoundedRect(QRectF(eye_rect), 4, 4)
        painter.drawRoundedRect(QRectF(lock_rect), 4, 4)

        painter.setPen(QColor("#3a78c4" if visible else "#666666"))
        painter.drawText(eye_rect, Qt.AlignmentFlag.AlignCenter, "👁" if visible else "🚫")
        painter.setPen(QColor("#c77838" if locked else "#666666"))
        painter.drawText(lock_rect, Qt.AlignmentFlag.AlignCenter, "🔒" if locked else "🔓")

        painter.restore()

    def editorEvent(
        self,
        event: QEvent,
        model: QAbstractListModel,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> bool:
        if event.type() == QEvent.Type.MouseButtonRelease and isinstance(event, QMouseEvent):
            if event.button() == Qt.MouseButton.LeftButton:
                row = index.row()
                _, eye_rect, lock_rect = self._hotspots(option)
                pos = event.pos()
                if eye_rect.contains(pos):
                    self.panel.toggle_visibility(row)
                    return True
                if lock_rect.contains(pos):
                    self.panel.toggle_lock(row)
                    return True
        return super().editorEvent(event, model, option, index)


class LayersPanel(QWidget):
    """Layers management dock panel with undoable actions."""

    layers_changed = pyqtSignal()

    def __init__(
        self,
        project: Project,
        undo_stack: QUndoStack,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.project = project
        self.undo_stack = undo_stack
        self._syncing = False
        self._init_ui()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        opacity_box = QHBoxLayout()
        opacity_box.setSpacing(6)
        lbl_opacity = QLabel("Opacity:")
        lbl_opacity.setStyleSheet("color: #888888; font-weight: 500;")
        opacity_box.addWidget(lbl_opacity)

        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(0, 100)
        self.slider_opacity.setValue(100)

        self.spin_opacity = QSpinBox()
        self.spin_opacity.setRange(0, 100)
        self.spin_opacity.setValue(100)
        self.spin_opacity.setSuffix("%")
        self.spin_opacity.setFixedWidth(58)

        self.slider_opacity.valueChanged.connect(self.spin_opacity.setValue)
        self.spin_opacity.valueChanged.connect(self._on_opacity_changed)

        opacity_box.addWidget(self.slider_opacity)
        opacity_box.addWidget(self.spin_opacity)
        layout.addLayout(opacity_box)

        self.model = LayerListModel(self.project, self)
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(LayerItemDelegate(self, self.view))
        self.view.setMouseTracking(True)
        self.view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.clicked.connect(self._on_layer_selected)
        self.view.doubleClicked.connect(self._on_rename_requested)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.view, 1)

        btn_row1 = QHBoxLayout()
        btn_row1.setSpacing(5)
        self.btn_new = QPushButton("+ New")
        self.btn_new.setToolTip("Add a new layer on top")
        self.btn_new.clicked.connect(self._on_new_layer)
        self.btn_dup = QPushButton("Duplicate")
        self.btn_dup.setToolTip("Duplicate the active layer")
        self.btn_dup.clicked.connect(self._on_duplicate_layer)
        self.btn_del = QPushButton("Delete")
        self.btn_del.setToolTip("Delete the active layer")
        self.btn_del.clicked.connect(self._on_delete_layer)
        btn_row1.addWidget(self.btn_new)
        btn_row1.addWidget(self.btn_dup)
        btn_row1.addWidget(self.btn_del)
        layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        btn_row2.setSpacing(5)
        self.btn_up = QPushButton("▲ Up")
        self.btn_up.setToolTip("Move layer up (towards foreground)")
        self.btn_up.clicked.connect(self._on_move_up)
        self.btn_down = QPushButton("▼ Down")
        self.btn_down.setToolTip("Move layer down (towards background)")
        self.btn_down.clicked.connect(self._on_move_down)
        self.btn_merge = QPushButton("Merge")
        self.btn_merge.setToolTip("Merge the active layer into the layer below")
        self.btn_merge.clicked.connect(self._on_merge_down)
        btn_row2.addWidget(self.btn_up)
        btn_row2.addWidget(self.btn_down)
        btn_row2.addWidget(self.btn_merge)
        layout.addLayout(btn_row2)

        self._sync_selection()

    # ------------------------------------------------------------------ #
    # Sync helpers
    # ------------------------------------------------------------------ #
    def _sync_selection(self) -> None:
        """Mirrors the document's active layer into the view and opacity widgets."""
        self.project.normalize_indices()
        idx = self.project.active_layer_idx
        self._syncing = True
        try:
            model_idx = self.model.index(idx, 0)
            if model_idx.isValid():
                self.view.setCurrentIndex(model_idx)
            layer = self.project.active_layer
            value = int(round(layer.opacity * 100))
            self.slider_opacity.blockSignals(True)
            self.spin_opacity.blockSignals(True)
            self.slider_opacity.setValue(value)
            self.spin_opacity.setValue(value)
            self.slider_opacity.blockSignals(False)
            self.spin_opacity.blockSignals(False)
        finally:
            self._syncing = False
        self._update_button_states()

    def _update_button_states(self) -> None:
        count = len(self.project.active_frame.layers)
        index = self.project.active_layer_idx
        has_previous = index > 0
        has_next = index < count - 1
        self.btn_del.setEnabled(count > 1)
        self.btn_merge.setEnabled(count > 1 and has_next)
        self.btn_up.setEnabled(has_previous)
        self.btn_down.setEnabled(has_next)
        self.btn_dup.setEnabled(count >= 1)
        self.btn_new.setEnabled(True)

    def set_project(self, project: Project) -> None:
        self.project = project
        self.model.project = project
        self.refresh()

    def refresh(self) -> None:
        """Refreshes the layer list and selection state."""
        self.model.refresh()
        self._sync_selection()

    # ------------------------------------------------------------------ #
    # Actions (undoable)
    # ------------------------------------------------------------------ #
    def toggle_visibility(self, row: int) -> None:
        layers = self.project.active_frame.layers
        if 0 <= row < len(layers):
            self.undo_stack.push(
                SetLayerVisibleCommand(
                    self.project,
                    self.project.active_frame_idx,
                    row,
                    not layers[row].visible,
                )
            )
            self.layers_changed.emit()

    def toggle_lock(self, row: int) -> None:
        layers = self.project.active_frame.layers
        if 0 <= row < len(layers):
            self.undo_stack.push(
                SetLayerLockedCommand(
                    self.project,
                    self.project.active_frame_idx,
                    row,
                    not layers[row].locked,
                )
            )
            self.layers_changed.emit()

    def _on_layer_selected(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        self.project.set_active_layer(index.row())
        self._sync_selection()
        self.layers_changed.emit()

    def _on_opacity_changed(self, val: int) -> None:
        if self._syncing:
            return
        layer = self.project.active_layer
        old = layer.opacity
        new = val / 100.0
        if abs(old - new) < 1e-6:
            return
        self.undo_stack.push(
            SetLayerOpacityCommand(
                self.project,
                self.project.active_frame_idx,
                self.project.active_layer_idx,
                old,
                new,
            )
        )

    def _on_new_layer(self) -> None:
        self.undo_stack.push(
            AddLayerCommand(self.project, self.project.active_frame_idx, index=0)
        )
        self.layers_changed.emit()

    def _on_duplicate_layer(self) -> None:
        self.undo_stack.push(
            DuplicateLayerCommand(
                self.project,
                self.project.active_frame_idx,
                self.project.active_layer_idx,
            )
        )
        self.layers_changed.emit()

    def _on_delete_layer(self) -> None:
        count = len(self.project.active_frame.layers)
        if count <= 1:
            QMessageBox.information(self, "Delete Layer", "A project needs at least one layer.")
            return
        self.undo_stack.push(
            RemoveLayerCommand(
                self.project,
                self.project.active_frame_idx,
                self.project.active_layer_idx,
            )
        )
        self.layers_changed.emit()

    def _on_move_up(self) -> None:
        current = self.project.active_layer_idx
        if current > 0:
            self.undo_stack.push(
                MoveLayerCommand(
                    self.project,
                    self.project.active_frame_idx,
                    current,
                    current - 1,
                )
            )
            self.layers_changed.emit()

    def _on_move_down(self) -> None:
        current = self.project.active_layer_idx
        if current < len(self.project.active_frame.layers) - 1:
            self.undo_stack.push(
                MoveLayerCommand(
                    self.project,
                    self.project.active_frame_idx,
                    current,
                    current + 1,
                )
            )
            self.layers_changed.emit()

    def _on_merge_down(self) -> None:
        current = self.project.active_layer_idx
        if current < len(self.project.active_frame.layers) - 1:
            self.undo_stack.push(
                MergeDownCommand(
                    self.project,
                    self.project.active_frame_idx,
                    current,
                )
            )
            self.layers_changed.emit()

    def _on_rename_requested(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        layers = self.project.active_frame.layers
        if not (0 <= index.row() < len(layers)):
            return
        current = layers[index.row()].name
        name, accepted = QInputDialog.getText(self, "Rename Layer", "Layer name:", text=current)
        name = name.strip()
        if accepted and name and name != current:
            self.undo_stack.push(
                RenameLayerCommand(
                    self.project,
                    self.project.active_frame_idx,
                    index.row(),
                    name,
                )
            )
            self.layers_changed.emit()

    def _on_context_menu(self, pos) -> None:
        index = self.view.indexAt(pos)
        row = index.row() if index.isValid() else self.project.active_layer_idx
        layers = self.project.active_frame.layers
        if not (0 <= row < len(layers)):
            return
        if index.isValid() and row != self.project.active_layer_idx:
            self.project.set_active_layer(row)
            self._sync_selection()

        menu = QMenu(self)
        action_rename = menu.addAction("Rename Layer...")
        action_duplicate = menu.addAction("Duplicate")
        action_delete = menu.addAction("Delete")
        menu.addSeparator()
        action_merge = menu.addAction("Merge Down")
        action_merge.setEnabled(len(layers) > 1 and row < len(layers) - 1)
        action_delete.setEnabled(len(layers) > 1)

        chosen = menu.exec(self.view.viewport().mapToGlobal(pos))
        if chosen == action_rename:
            self._on_rename_requested(self.model.index(row, 0))
        elif chosen == action_duplicate:
            self._on_duplicate_layer()
        elif chosen == action_delete:
            self._on_delete_layer()
        elif chosen == action_merge:
            self._on_merge_down()
