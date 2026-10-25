"""
ThisIsPixel - Data Models, Rendering Cache & Undo Engine
========================================================
Core document model:

- Layer: single ARGB32 image channel with visibility, lock, opacity and a
  revision counter used for thumbnail caching.
- Frame: stack of layers belonging to one animation frame. Layer index 0 is the
  foreground layer (top of the stack).
- Project: document (frames, indices, palette, file path, dirty flag) with
  cached compositing and safe .pxp serialization.
- DrawStrokeCommand: pixel-level undo command.

Every document mutation goes through ``Project.notify()`` which bumps the
document revision, marks the document dirty and invokes the registered change
callback. That single choke point keeps every dock in sync (see main.py).
"""

import json
import os
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QUndoCommand

IMAGE_FORMAT = QImage.Format.Format_ARGB32
PROJECT_VERSION = "2.1"
SUPPORTED_VERSIONS = {"2.0", "2.1"}
MIN_CANVAS = 1
MAX_CANVAS = 4096


# --------------------------------------------------------------------------- #
# Image helpers
# --------------------------------------------------------------------------- #
def image_to_base64(img: QImage) -> str:
    """Encodes a QImage into a base64 PNG string."""
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buffer, "PNG")
    buffer.close()
    return byte_array.toBase64().data().decode("ascii")


def base64_to_image(b64_str: str) -> QImage:
    """Decodes a base64 PNG string back into a QImage."""
    byte_array = QByteArray.fromBase64(b64_str.encode("ascii"))
    img = QImage()
    img.loadFromData(byte_array, "PNG")
    return img


def create_layer_image(width: int, height: int) -> QImage:
    """Creates a transparent ARGB32 image."""
    image = QImage(width, height, IMAGE_FORMAT)
    image.fill(QColor(0, 0, 0, 0))
    return image


def _normalized_image(image: QImage, width: int, height: int) -> QImage:
    """Guarantees an image matches the document dimensions (defensive on load)."""
    if image.isNull():
        return create_layer_image(width, height)
    if image.width() == width and image.height() == height:
        if image.format() != IMAGE_FORMAT:
            image = image.convertToFormat(IMAGE_FORMAT)
        return image
    result = create_layer_image(width, height)
    painter = QPainter(result)
    painter.drawImage(0, 0, image)
    painter.end()
    return result


# --------------------------------------------------------------------------- #
# Layer
# --------------------------------------------------------------------------- #
class Layer:
    """
    Represents a single drawing layer within an animation frame.

    Stacking order: ``Frame.layers[0]`` is the top-most (foreground) layer in
    both the viewport and the layers UI list.
    """

    def __init__(self, width: int, height: int, name: str = "Layer 1"):
        self.name: str = name
        self.visible: bool = True
        self.locked: bool = False
        self.opacity: float = 1.0  # 0.0 .. 1.0
        self.image: QImage = create_layer_image(width, height)
        self.revision: int = 0
        self._thumb_key: Optional[tuple] = None
        self._thumb: Optional[QImage] = None

    # -- cache ------------------------------------------------------------- #
    def touch(self) -> None:
        """Marks the pixel data as changed (invalidates cached thumbnails)."""
        self.revision += 1

    def clone(self, name: Optional[str] = None) -> "Layer":
        """Creates a deep copy of the layer including pixel data and flags."""
        new_layer = Layer(self.image.width(), self.image.height(), name or self.name)
        new_layer.visible = self.visible
        new_layer.locked = self.locked
        new_layer.opacity = self.opacity
        new_layer.image = self.image.copy()
        return new_layer

    def thumbnail(self, size: int = 32) -> QImage:
        """Returns a cached, aspect-preserving thumbnail image."""
        key = (self.revision, size)
        if self._thumb_key == key and self._thumb is not None:
            return self._thumb
        thumb = create_layer_image(size, size)
        scaled = self.image.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        painter = QPainter(thumb)
        painter.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
        painter.end()
        self._thumb_key = key
        self._thumb = thumb
        return thumb

    # -- serialization ----------------------------------------------------- #
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "visible": self.visible,
            "locked": self.locked,
            "opacity": self.opacity,
            "image_b64": image_to_base64(self.image),
        }

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], width: Optional[int] = None, height: Optional[int] = None
    ) -> "Layer":
        img = base64_to_image(data.get("image_b64", ""))
        target_w = int(width) if width is not None else max(1, img.width())
        target_h = int(height) if height is not None else max(1, img.height())
        img = _normalized_image(img, target_w, target_h)
        return cls._from_image(
            img,
            str(data.get("name", "Layer")),
            bool(data.get("visible", True)),
            bool(data.get("locked", False)),
            float(data.get("opacity", 1.0)),
        )

    @classmethod
    def _from_image(cls, img, name, visible, locked, opacity) -> "Layer":
        layer = cls.__new__(cls)
        layer.name = name
        layer.visible = visible
        layer.locked = locked
        layer.opacity = max(0.0, min(1.0, opacity))
        layer.image = img
        layer.revision = 0
        layer._thumb_key = None
        layer._thumb = None
        return layer


# --------------------------------------------------------------------------- #
# Frame
# --------------------------------------------------------------------------- #
class Frame:
    """Represents a single animation frame containing a stack of layers."""

    def __init__(self, width: int, height: int, with_default_layer: bool = True):
        self.width = width
        self.height = height
        self.layers: List[Layer] = [Layer(width, height, "Layer 1")] if with_default_layer else []
        self.revision: int = 0
        self._cache_key: Optional[tuple] = None
        self._cache_image: Optional[QImage] = None
        self._thumb_key: Optional[tuple] = None
        self._thumb: Optional[QImage] = None

    def touch(self) -> None:
        """Invalidates the composite and thumbnail caches for this frame."""
        self.revision += 1

    def clone(self) -> "Frame":
        """Creates a deep copy of the frame and all of its layers."""
        new_frame = Frame(self.width, self.height, with_default_layer=False)
        new_frame.layers = [layer.clone() for layer in self.layers]
        return new_frame

    def composite(self, use_cache: bool = True) -> QImage:
        """
        Renders all visible layers from bottom to top into an ARGB32 image.

        Because ``layers[0]`` is the top-most layer, rendering walks the list in
        reverse order. The result is cached keyed by layer revisions/flags.
        """
        key = (
            self.revision,
            tuple((id(layer), layer.visible, layer.opacity, layer.revision) for layer in self.layers),
            self.width,
            self.height,
        )
        if use_cache and self._cache_key == key and self._cache_image is not None:
            return self._cache_image

        result = create_layer_image(self.width, self.height)
        painter = QPainter(result)
        for layer in reversed(self.layers):
            if layer.visible and layer.opacity > 0.0:
                painter.setOpacity(layer.opacity)
                painter.drawImage(0, 0, layer.image)
        painter.end()

        if use_cache:
            self._cache_key = key
            self._cache_image = result
        return result

    def thumbnail(self, size: int = 36) -> QImage:
        """Returns a cached composite thumbnail for the timeline filmstrip."""
        key = (self.revision, size, tuple((id(l), l.visible, l.opacity, l.revision) for l in self.layers))
        if self._thumb_key == key and self._thumb is not None:
            return self._thumb
        comp = self.composite()
        thumb = create_layer_image(size, size)
        scaled = comp.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        painter = QPainter(thumb)
        painter.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
        painter.end()
        self._thumb_key = key
        self._thumb = thumb
        return thumb

    def to_dict(self) -> Dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "layers": [layer.to_dict() for layer in self.layers],
        }

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], width: Optional[int] = None, height: Optional[int] = None
    ) -> "Frame":
        fw = int(width if width is not None else data.get("width", 1))
        fh = int(height if height is not None else data.get("height", 1))
        frame = cls(fw, fh, with_default_layer=False)
        for l_data in data.get("layers", []):
            frame.layers.append(Layer.from_dict(l_data, fw, fh))
        if not frame.layers:
            frame.layers = [Layer(fw, fh, "Layer 1")]
        return frame


# --------------------------------------------------------------------------- #
# Project
# --------------------------------------------------------------------------- #
class Project:
    """
    Main document. Owns frames, active indices, palette and file state.

    ``change_callback`` is invoked through :meth:`notify` after every committed
    document mutation so the UI can refresh from a single place.
    """

    def __init__(self, width: int = 32, height: int = 32):
        self.width: int = max(MIN_CANVAS, min(MAX_CANVAS, int(width)))
        self.height: int = max(MIN_CANVAS, min(MAX_CANVAS, int(height)))
        self.frames: List[Frame] = [Frame(self.width, self.height)]
        self.active_frame_idx: int = 0
        self.active_layer_idx: int = 0
        self.palette: List[QColor] = []
        self.file_path: Optional[str] = None
        self.is_modified: bool = False
        self.revision: int = 0
        self.change_callback: Optional[Callable[[], None]] = None
        self._cache_key: Optional[tuple] = None
        self._cache_image: Optional[QImage] = None

    # -- document state ---------------------------------------------------- #
    def touch(self) -> None:
        """Marks the document as modified and invalidates composite caches."""
        self.revision += 1
        self.is_modified = True

    def notify(self) -> None:
        """Marks the document dirty, then notifies the UI."""
        self.touch()
        if self.change_callback is not None:
            self.change_callback()

    def invalidate_cache(self) -> None:
        """Drops cached composites (used by view toggles such as onion skin)."""
        self._cache_key = None
        self._cache_image = None

    def normalize_indices(self) -> None:
        """Clamps both active indices and writes them back to the document."""
        self.active_frame_idx = max(0, min(self.active_frame_idx, len(self.frames) - 1))
        layers = self.active_frame.layers
        self.active_layer_idx = max(0, min(self.active_layer_idx, len(layers) - 1))

    @property
    def active_frame(self) -> Frame:
        idx = max(0, min(self.active_frame_idx, len(self.frames) - 1))
        return self.frames[idx]

    @property
    def active_layer(self) -> Layer:
        frame = self.active_frame
        idx = max(0, min(self.active_layer_idx, len(frame.layers) - 1))
        return frame.layers[idx]

    @property
    def display_name(self) -> str:
        return os.path.basename(self.file_path) if self.file_path else "Untitled.pxp"

    def set_active_frame(self, idx: int) -> None:
        """Switches frame (selection change only - does not mark the file dirty)."""
        if 0 <= idx < len(self.frames):
            self.active_frame_idx = idx
            self.normalize_indices()

    def set_active_layer(self, idx: int, frame_idx: Optional[int] = None) -> None:
        """Switches active layer within a frame."""
        if frame_idx is not None:
            self.set_active_frame(frame_idx)
        layers = self.active_frame.layers
        if 0 <= idx < len(layers):
            self.active_layer_idx = idx

    # -- layer operations (callers are responsible for project.notify()) --- #
    def _next_layer_name(self) -> str:
        existing = set()
        for layer in self.active_frame.layers:
            existing.add(layer.name)
        number = len(self.active_frame.layers) + 1
        while f"Layer {number}" in existing:
            number += 1
        return f"Layer {number}"

    def add_layer(self, name: Optional[str] = None, index: int = 0) -> Layer:
        frame = self.active_frame
        layer = Layer(self.width, self.height, name or self._next_layer_name())
        index = max(0, min(index, len(frame.layers)))
        frame.layers.insert(index, layer)
        frame.touch()
        self.active_layer_idx = index
        return layer

    def remove_layer(self, idx: int) -> Optional[Layer]:
        frame = self.active_frame
        if len(frame.layers) <= 1 or not (0 <= idx < len(frame.layers)):
            return None
        layer = frame.layers.pop(idx)
        frame.touch()
        self.active_layer_idx = max(0, min(self.active_layer_idx, len(frame.layers) - 1))
        return layer

    def duplicate_layer(self, idx: int) -> Optional[Layer]:
        frame = self.active_frame
        if not (0 <= idx < len(frame.layers)):
            return None
        duplicate = frame.layers[idx].clone(f"{frame.layers[idx].name} Copy")
        frame.layers.insert(idx, duplicate)
        frame.touch()
        self.active_layer_idx = idx
        return duplicate

    def move_layer(self, from_idx: int, to_idx: int) -> bool:
        frame = self.active_frame
        if not (0 <= from_idx < len(frame.layers) and 0 <= to_idx < len(frame.layers)):
            return False
        if from_idx == to_idx:
            return False
        layer = frame.layers.pop(from_idx)
        frame.layers.insert(to_idx, layer)
        frame.touch()
        self.active_layer_idx = to_idx
        return True

    def merge_down(self, idx: int, bake_opacity: bool = True) -> bool:
        """
        Merges the layer at ``idx`` into the layer directly below it (``idx+1``).

        The result is flattened so it looks identical to the composite of both
        layers: bottom opacity is baked into the merged pixels and the resulting
        layer opacity is reset to 1.0.
        """
        frame = self.active_frame
        if not (0 <= idx < len(frame.layers) - 1):
            return False

        top = frame.layers[idx]
        bottom = frame.layers[idx + 1]

        result = create_layer_image(self.width, self.height)
        painter = QPainter(result)
        painter.setOpacity(bottom.opacity if bake_opacity else 1.0)
        painter.drawImage(0, 0, bottom.image)
        if top.visible and top.opacity > 0:
            painter.setOpacity(top.opacity)
            painter.drawImage(0, 0, top.image)
        painter.end()

        bottom.image = result
        bottom.opacity = 1.0
        bottom.touch()
        frame.layers.pop(idx)
        frame.touch()
        self.active_layer_idx = min(idx, len(frame.layers) - 1)
        return True

    # -- frame operations -------------------------------------------------- #
    def add_frame(self, frame: Optional[Frame] = None) -> Frame:
        new_frame = frame or Frame(self.width, self.height)
        self.frames.append(new_frame)
        self.active_frame_idx = len(self.frames) - 1
        self.normalize_indices()
        return new_frame

    def insert_frame(self, index: int, frame: Frame) -> None:
        index = max(0, min(index, len(self.frames)))
        self.frames.insert(index, frame)
        self.active_frame_idx = index
        self.normalize_indices()

    def duplicate_frame(self, idx: int) -> Optional[Frame]:
        if not (0 <= idx < len(self.frames)):
            return None
        clone = self.frames[idx].clone()
        self.frames.insert(idx + 1, clone)
        self.active_frame_idx = idx + 1
        self.normalize_indices()
        return clone

    def remove_frame(self, idx: int) -> Optional[Frame]:
        if len(self.frames) <= 1 or not (0 <= idx < len(self.frames)):
            return None
        frame = self.frames.pop(idx)
        self.active_frame_idx = max(0, min(self.active_frame_idx, len(self.frames) - 1))
        self.normalize_indices()
        return frame

    def move_frame(self, from_idx: int, to_idx: int) -> bool:
        if not (0 <= from_idx < len(self.frames) and 0 <= to_idx < len(self.frames)):
            return False
        if from_idx == to_idx:
            return False
        frame = self.frames.pop(from_idx)
        self.frames.insert(to_idx, frame)
        self.active_frame_idx = to_idx
        self.normalize_indices()
        return True

    # -- rendering --------------------------------------------------------- #
    def render_composite(self, onion_skin: bool = False, use_cache: bool = True) -> QImage:
        """
        Renders the active frame, optionally with onion skinning.

        Ghost frames are composited *behind* the active frame:
        - previous frame: 30% opacity
        - next frame: 15% opacity
        """
        key = (self.revision, self.active_frame_idx, bool(onion_skin), self.width, self.height)
        if use_cache and self._cache_key == key and self._cache_image is not None:
            return self._cache_image

        result = create_layer_image(self.width, self.height)
        painter = QPainter(result)
        current = self.active_frame_idx

        # Ghosts are painted first so they always stay behind the artwork.
        if onion_skin and current > 0:
            painter.setOpacity(0.30)
            painter.drawImage(0, 0, self.frames[current - 1].composite(use_cache=use_cache))

        painter.setOpacity(1.0)
        painter.drawImage(0, 0, self.active_frame.composite(use_cache=use_cache))

        if onion_skin and current + 1 < len(self.frames):
            painter.setOpacity(0.15)
            painter.drawImage(0, 0, self.frames[current + 1].composite(use_cache=use_cache))

        painter.end()

        if use_cache:
            self._cache_key = key
            self._cache_image = result
        return result

    # -- persistence ------------------------------------------------------- #
    def to_data(self) -> Dict[str, Any]:
        """Returns the serializable document dictionary."""
        self.normalize_indices()
        return {
            "version": PROJECT_VERSION,
            "width": self.width,
            "height": self.height,
            "active_frame_idx": self.active_frame_idx,
            "active_layer_idx": self.active_layer_idx,
            "palette": [c.name(QColor.NameFormat.HexArgb) for c in self.palette],
            "frames": [f.to_dict() for f in self.frames],
        }

    def _write_json(self, file_path: str) -> None:
        data = self.to_data()
        temp_path = f"{file_path}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, separators=(",", ":"))
            os.replace(temp_path, file_path)
        except Exception:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass
            raise

    def save_copy(self, file_path: str) -> None:
        """Writes a snapshot (used by autosave) without changing document state."""
        self._write_json(file_path)

    def save_to_file(self, file_path: str) -> None:
        """
        Saves the document as JSON (.pxp) using an atomic replace.

        Raises OSError/ValueError on failure so the UI can report the problem.
        """
        self._write_json(file_path)
        self.file_path = os.path.abspath(file_path)
        self.is_modified = False

    @classmethod
    def load_from_file(cls, file_path: str) -> "Project":
        """Loads and validates a .pxp project file."""
        with open(file_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        if not isinstance(data, dict):
            raise ValueError("Project file is not a valid ThisIsPixel document.")

        version = str(data.get("version", "2.0"))
        if version not in SUPPORTED_VERSIONS:
            raise ValueError(f"Unsupported project version: {version}")

        width = int(data.get("width", 0))
        height = int(data.get("height", 0))
        if not (MIN_CANVAS <= width <= MAX_CANVAS and MIN_CANVAS <= height <= MAX_CANVAS):
            raise ValueError(f"Invalid canvas dimensions: {width}x{height}")

        frames_data = data.get("frames") or []
        if not isinstance(frames_data, list) or not frames_data:
            raise ValueError("Project file does not contain any animation frame.")

        project = cls(width, height)
        project.frames = [Frame.from_dict(item, width, height) for item in frames_data]
        project.active_frame_idx = int(data.get("active_frame_idx", 0))
        project.active_layer_idx = int(data.get("active_layer_idx", 0))
        project.normalize_indices()

        palette: List[QColor] = []
        for text in data.get("palette", []) or []:
            color = QColor(text)
            if color.isValid():
                palette.append(color)
        project.palette = palette

        project.file_path = os.path.abspath(file_path)
        project.is_modified = False
        return project


# --------------------------------------------------------------------------- #
# Undo command (pixel snapshots)
# --------------------------------------------------------------------------- #
class DrawStrokeCommand(QUndoCommand):
    """
    Undo/redo for pixel drawing operations.

    Stores before/after snapshots of one layer inside one frame. Frame/layer
    indices (not object references) are stored so undo keeps working even after
    structural edits earlier in the undo history.
    """

    def __init__(
        self,
        project: Project,
        frame_idx: int,
        layer_idx: int,
        before_image: QImage,
        after_image: QImage,
        text: str = "Drawing Stroke",
    ):
        super().__init__(text)
        self.project = project
        self.frame_idx = frame_idx
        self.layer_idx = layer_idx
        self.before_image = before_image.copy()
        self.after_image = after_image.copy()

    def _target(self):
        if not (0 <= self.frame_idx < len(self.project.frames)):
            return None, None
        frame = self.project.frames[self.frame_idx]
        if not (0 <= self.layer_idx < len(frame.layers)):
            return None, None
        return frame, frame.layers[self.layer_idx]

    def _apply(self, image: QImage) -> None:
        frame, layer = self._target()
        if frame is None or layer is None:
            return
        layer.image = image.copy()
        layer.touch()
        frame.touch()
        self.project.set_active_frame(self.frame_idx)
        self.project.set_active_layer(self.layer_idx)
        self.project.notify()

    def undo(self) -> None:
        self._apply(self.before_image)

    def redo(self) -> None:
        self._apply(self.after_image)
