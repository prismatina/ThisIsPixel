"""
Generate the ThisIsPixel application icon (PNG + multi-size ICO).

Usage::

    python make_icon.py

Both files are written to ``asset/`` and are used by PyInstaller (see
``main.spec`` / ``main_onedir.spec``) and by the NSIS installer. The ICO
contains PNG-compressed images at 16, 24, 32, 48, 64, 128 and 256 px so
Explorer, the taskbar, the Start Menu and the installer all stay sharp.

The runtime icon itself is generated procedurally in ``tools.create_app_icon``
so the application has no hard dependency on these files.
"""

import os
import struct

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen

SIZE = 256
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "asset")
COLORS = ["#3a78c4", "#5fcde4", "#fbf236", "#df7126", "#d95763"]


def build_icon_image(size: int = SIZE) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor("#1b1b1b"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    inset = max(1, size // 16)
    painter.fillRect(
        QRect(inset, inset, size - inset * 2, size - inset * 2), QColor("#232323")
    )

    cell = size // 8
    origin = size // 4
    for row in range(4):
        for col in range(4):
            painter.fillRect(
                QRect(origin + col * cell, origin + row * cell, cell, cell),
                QColor(COLORS[(row + col) % len(COLORS)]),
            )

    painter.setPen(QPen(QColor("#dcdcdc"), max(1, size // 42)))
    painter.drawRect(
        QRect(inset + 1, inset + 1, size - inset * 2 - 2, size - inset * 2 - 2)
    )
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Qt could not encode the icon as PNG")
    buffer.close()
    return bytes(data)


def write_ico(image: QImage, path: str, sizes=ICON_SIZES) -> None:
    """Writes a PNG-compressed multi-resolution ICO without extra libraries."""
    frames = []
    for size in sizes:
        scaled = image.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        frames.append((size, png_bytes(scaled)))

    header = struct.pack("<HHH", 0, 1, len(frames))
    entries = b""
    payload = b""
    offset = 6 + 16 * len(frames)

    for size, blob in frames:
        width = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", width, width, 0, 0, 1, 32, len(blob), offset
        )
        payload += blob
        offset += len(blob)

    with open(path, "wb") as handle:
        handle.write(header + entries + payload)


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    image = build_icon_image()
    png_path = os.path.join(OUTPUT_DIR, "thisispixel.png")
    ico_path = os.path.join(OUTPUT_DIR, "thisispixel.ico")

    if not image.save(png_path, "PNG"):
        raise SystemExit(f"Could not write {png_path}")
    write_ico(image, ico_path)

    print(f"Wrote {png_path}")
    print(f"Wrote {ico_path} ({len(ICON_SIZES)} sizes)")


if __name__ == "__main__":
    main()
