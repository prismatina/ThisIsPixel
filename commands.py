"""
ThisIsPixel - Document Command Layer
====================================
All structural document edits (layers, frames, opacity, visibility, lock,
rename, merge, move) are expressed as QUndoCommand objects so that:

1. The Undo/Redo history stays consistent with the document.
2. Every mutation funnels through ``Project.notify()`` -> one UI refresh path.
3. Commands reference frames/layers by index or object identity, so they keep
   working after the history is rewound.

Pixel-level edits (strokes, fill, paste, clear, selection move) use
``DrawStrokeCommand`` from models.py which stores before/after snapshots.
"""

from typing import Optional

from PyQt6.QtGui import QUndoCommand

from models import Frame, Layer, Project


class DocumentCommand(QUndoCommand):
    """Base class that verifies indices and notifies the document once."""

    def __init__(self, project: Project, text: str):
        super().__init__(text)
        self.project = project

    def commit(self) -> None:
        self.project.notify()

    @staticmethod
    def frame_at(project: Project, frame_idx: int) -> Optional[Frame]:
        if 0 <= frame_idx < len(project.frames):
            return project.frames[frame_idx]
        return None


# --------------------------------------------------------------------------- #
# Layer commands
# --------------------------------------------------------------------------- #
class AddLayerCommand(DocumentCommand):
    def __init__(self, project: Project, frame_idx: int, index: int = 0, name: Optional[str] = None):
        super().__init__(project, "Add Layer")
        self.frame_idx = frame_idx
        self.index = index
        frame = self.frame_at(project, frame_idx)
        self.layer = Layer(project.width, project.height, name or "Layer")
        self._created = False
        if frame is not None and name is None:
            existing = {layer.name for layer in frame.layers}
            number = len(frame.layers) + 1
            while f"Layer {number}" in existing:
                number += 1
            self.layer.name = f"Layer {number}"

    def redo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None:
            return
        self.project.set_active_frame(self.frame_idx)
        self.index = max(0, min(self.index, len(frame.layers)))
        frame.layers.insert(self.index, self.layer)
        frame.touch()
        self.project.active_layer_idx = self.index
        self._created = True
        self.commit()

    def undo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or not self._created:
            return
        try:
            frame.layers.remove(self.layer)
        except ValueError:
            return
        frame.touch()
        self.project.normalize_indices()
        self.commit()


class RemoveLayerCommand(DocumentCommand):
    def __init__(self, project: Project, frame_idx: int, layer_idx: int):
        super().__init__(project, "Delete Layer")
        self.frame_idx = frame_idx
        frame = self.frame_at(project, frame_idx)
        self.layer = frame.layers[layer_idx] if frame and 0 <= layer_idx < len(frame.layers) else None
        self.index = layer_idx
        self._removed = False

    def redo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or self.layer is None or len(frame.layers) <= 1:
            return
        if self.layer not in frame.layers:
            return
        self.project.set_active_frame(self.frame_idx)
        self.index = frame.layers.index(self.layer)
        frame.layers.remove(self.layer)
        frame.touch()
        self.project.active_layer_idx = max(0, min(self.index, len(frame.layers) - 1))
        self._removed = True
        self.commit()

    def undo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or self.layer is None:
            return
        if self.layer in frame.layers:
            return
        index = max(0, min(self.index, len(frame.layers)))
        frame.layers.insert(index, self.layer)
        frame.touch()
        self.project.active_layer_idx = index
        self.commit()


class DuplicateLayerCommand(DocumentCommand):
    def __init__(self, project: Project, frame_idx: int, layer_idx: int):
        super().__init__(project, "Duplicate Layer")
        self.frame_idx = frame_idx
        frame = self.frame_at(project, frame_idx)
        source = frame.layers[layer_idx] if frame and 0 <= layer_idx < len(frame.layers) else None
        self.duplicate = source.clone(f"{source.name} Copy") if source else None
        self.index = layer_idx
        self._inserted = False

    def redo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or self.duplicate is None:
            return
        if self.duplicate in frame.layers:
            return
        self.project.set_active_frame(self.frame_idx)
        index = max(0, min(self.index, len(frame.layers)))
        frame.layers.insert(index, self.duplicate)
        frame.touch()
        self.project.active_layer_idx = index
        self._inserted = True
        self.commit()

    def undo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or self.duplicate is None or not self._inserted:
            return
        try:
            frame.layers.remove(self.duplicate)
        except ValueError:
            return
        frame.touch()
        self.project.normalize_indices()
        self.commit()


class MoveLayerCommand(DocumentCommand):
    def __init__(self, project: Project, frame_idx: int, from_idx: int, to_idx: int):
        super().__init__(project, "Move Layer")
        self.frame_idx = frame_idx
        self.from_idx = from_idx
        self.to_idx = to_idx

    def _move(self, src: int, dst: int) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or not (0 <= src < len(frame.layers) and 0 <= dst < len(frame.layers)):
            return
        self.project.set_active_frame(self.frame_idx)
        layer = frame.layers.pop(src)
        frame.layers.insert(dst, layer)
        frame.touch()
        self.project.active_layer_idx = dst
        self.commit()

    def redo(self) -> None:
        self._move(self.from_idx, self.to_idx)

    def undo(self) -> None:
        self._move(self.to_idx, self.from_idx)


class MergeDownCommand(DocumentCommand):
    def __init__(self, project: Project, frame_idx: int, layer_idx: int):
        super().__init__(project, "Merge Down")
        self.frame_idx = frame_idx
        frame = self.frame_at(project, frame_idx)
        self.layer_idx = layer_idx
        if frame is not None and 0 <= layer_idx < len(frame.layers) - 1:
            self.top: Optional[Layer] = frame.layers[layer_idx]
            self.bottom: Optional[Layer] = frame.layers[layer_idx + 1]
            self.bottom_image = self.bottom.image.copy()
            self.bottom_opacity = self.bottom.opacity
        else:
            self.top = None
            self.bottom = None
            self.bottom_image = None
            self.bottom_opacity = 1.0
        self._merged = False

    def redo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or self.top is None or self.bottom is None:
            return
        if self.top not in frame.layers or self.bottom not in frame.layers:
            return
        index = frame.layers.index(self.top)
        self.project.set_active_frame(self.frame_idx)
        if not self.project.merge_down(index):
            return
        self._merged = True
        self.commit()

    def undo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or self.bottom is None or self.top is None or not self._merged:
            return
        self.bottom.image = self.bottom_image.copy()
        self.bottom.opacity = self.bottom_opacity
        self.bottom.touch()
        if self.top not in frame.layers:
            index = max(0, min(self.layer_idx, len(frame.layers)))
            frame.layers.insert(index, self.top)
        frame.touch()
        self.project.active_layer_idx = self.layer_idx
        self._merged = False
        self.commit()


class SetLayerOpacityCommand(DocumentCommand):
    """Opacity change; consecutive drags merge into a single undo step."""

    def __init__(self, project: Project, frame_idx: int, layer_idx: int, old: float, new: float):
        super().__init__(project, "Change Layer Opacity")
        self.frame_idx = frame_idx
        self.layer_idx = layer_idx
        self.old = old
        self.new = new

    def id(self) -> int:
        return 0x1000 + (self.frame_idx * 1000) + self.layer_idx

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not isinstance(other, SetLayerOpacityCommand):
            return False
        if (self.frame_idx, self.layer_idx) != (other.frame_idx, other.layer_idx):
            return False
        if abs(self.new - other.old) > 1e-6:
            return False
        self.new = other.new
        return True

    def redo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or not (0 <= self.layer_idx < len(frame.layers)):
            return
        frame.layers[self.layer_idx].opacity = self.new
        frame.touch()
        self.commit()

    def undo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or not (0 <= self.layer_idx < len(frame.layers)):
            return
        frame.layers[self.layer_idx].opacity = self.old
        frame.touch()
        self.commit()


class SetLayerVisibleCommand(DocumentCommand):
    def __init__(self, project: Project, frame_idx: int, layer_idx: int, visible: bool):
        super().__init__(project, "Show Layer" if visible else "Hide Layer")
        self.frame_idx = frame_idx
        self.layer_idx = layer_idx
        self.visible = visible

    def redo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or not (0 <= self.layer_idx < len(frame.layers)):
            return
        frame.layers[self.layer_idx].visible = self.visible
        frame.touch()
        self.commit()

    def undo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or not (0 <= self.layer_idx < len(frame.layers)):
            return
        frame.layers[self.layer_idx].visible = not self.visible
        frame.touch()
        self.commit()


class SetLayerLockedCommand(DocumentCommand):
    def __init__(self, project: Project, frame_idx: int, layer_idx: int, locked: bool):
        super().__init__(project, "Lock Layer" if locked else "Unlock Layer")
        self.frame_idx = frame_idx
        self.layer_idx = layer_idx
        self.locked = locked

    def redo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or not (0 <= self.layer_idx < len(frame.layers)):
            return
        frame.layers[self.layer_idx].locked = self.locked
        frame.touch()
        self.commit()

    def undo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or not (0 <= self.layer_idx < len(frame.layers)):
            return
        frame.layers[self.layer_idx].locked = not self.locked
        frame.touch()
        self.commit()


class RenameLayerCommand(DocumentCommand):
    def __init__(self, project: Project, frame_idx: int, layer_idx: int, name: str):
        super().__init__(project, "Rename Layer")
        self.frame_idx = frame_idx
        self.layer_idx = layer_idx
        frame = self.frame_at(project, frame_idx)
        self.old_name = (
            frame.layers[layer_idx].name if frame and 0 <= layer_idx < len(frame.layers) else "Layer"
        )
        self.new_name = name

    def redo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or not (0 <= self.layer_idx < len(frame.layers)):
            return
        frame.layers[self.layer_idx].name = self.new_name
        frame.touch()
        self.commit()

    def undo(self) -> None:
        frame = self.frame_at(self.project, self.frame_idx)
        if frame is None or not (0 <= self.layer_idx < len(frame.layers)):
            return
        frame.layers[self.layer_idx].name = self.old_name
        frame.touch()
        self.commit()


# --------------------------------------------------------------------------- #
# Frame commands
# --------------------------------------------------------------------------- #
class AddFrameCommand(DocumentCommand):
    def __init__(self, project: Project, index: Optional[int] = None, frame: Optional[Frame] = None):
        super().__init__(project, "Add Frame")
        self.frame = frame or Frame(project.width, project.height)
        self.index = len(project.frames) if index is None else index
        self._inserted = False

    def redo(self) -> None:
        if self.frame in self.project.frames:
            return
        index = max(0, min(self.index, len(self.project.frames)))
        self.project.frames.insert(index, self.frame)
        self.project.active_frame_idx = index
        self.project.normalize_indices()
        self._inserted = True
        self.commit()

    def undo(self) -> None:
        if not self._inserted or self.frame not in self.project.frames:
            return
        index = self.project.frames.index(self.frame)
        self.project.frames.remove(self.frame)
        self.project.active_frame_idx = max(0, min(index, len(self.project.frames) - 1))
        self.project.normalize_indices()
        self.commit()


class DuplicateFrameCommand(DocumentCommand):
    def __init__(self, project: Project, frame_idx: int):
        super().__init__(project, "Duplicate Frame")
        self.frame_idx = frame_idx
        source = project.frames[frame_idx] if 0 <= frame_idx < len(project.frames) else None
        self.frame = source.clone() if source else None
        self._inserted = False

    def redo(self) -> None:
        if self.frame is None or self.frame in self.project.frames:
            return
        index = max(0, min(self.frame_idx + 1, len(self.project.frames)))
        self.project.frames.insert(index, self.frame)
        self.project.active_frame_idx = index
        self.project.normalize_indices()
        self._inserted = True
        self.commit()

    def undo(self) -> None:
        if self.frame is None or not self._inserted or self.frame not in self.project.frames:
            return
        index = self.project.frames.index(self.frame)
        self.project.frames.remove(self.frame)
        self.project.active_frame_idx = max(0, min(index, len(self.project.frames) - 1))
        self.project.normalize_indices()
        self.commit()


class RemoveFrameCommand(DocumentCommand):
    def __init__(self, project: Project, frame_idx: int):
        super().__init__(project, "Delete Frame")
        self.frame_idx = frame_idx
        self.frame = project.frames[frame_idx] if 0 <= frame_idx < len(project.frames) else None
        self._removed = False

    def redo(self) -> None:
        if self.frame is None or len(self.project.frames) <= 1:
            return
        if self.frame not in self.project.frames:
            return
        index = self.project.frames.index(self.frame)
        self.project.frames.remove(self.frame)
        self.project.active_frame_idx = max(0, min(index, len(self.project.frames) - 1))
        self.project.normalize_indices()
        self._removed = True
        self.commit()

    def undo(self) -> None:
        if self.frame is None or not self._removed or self.frame in self.project.frames:
            return
        index = max(0, min(self.frame_idx, len(self.project.frames)))
        self.project.frames.insert(index, self.frame)
        self.project.active_frame_idx = index
        self.project.normalize_indices()
        self.commit()


class MoveFrameCommand(DocumentCommand):
    def __init__(self, project: Project, from_idx: int, to_idx: int):
        super().__init__(project, "Move Frame")
        self.from_idx = from_idx
        self.to_idx = to_idx

    def _move(self, src: int, dst: int) -> None:
        if not (0 <= src < len(self.project.frames) and 0 <= dst < len(self.project.frames)):
            return
        frame = self.project.frames.pop(src)
        self.project.frames.insert(dst, frame)
        self.project.active_frame_idx = dst
        self.project.normalize_indices()
        self.commit()

    def redo(self) -> None:
        self._move(self.from_idx, self.to_idx)

    def undo(self) -> None:
        self._move(self.to_idx, self.from_idx)
