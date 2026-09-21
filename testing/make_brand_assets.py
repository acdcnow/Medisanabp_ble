"""Generate the HACS brand assets for the Medisanabp BLE integration.

Home Assistant serves ``custom_components/<domain>/brand/<name>`` for the eight
supported names (icon.png, icon@2x.png, logo.png, logo@2x.png and their dark_*
variants); HACS validation is satisfied by ``brand/icon.png``. The images are a
flat heart on transparent background, rendered analytically (3x supersampled)
so no image library is needed:

    python testing/make_brand_assets.py
"""

from __future__ import annotations

import pathlib
import struct
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRAND = ROOT / "custom_components" / "medisanabp_ble" / "brand"

RED = (211, 47, 47)  # #D32F2F
SUPERSAMPLE = 3


def _in_heart(x: float, y: float) -> bool:
    """Return True for points inside the implicit heart curve.

    ``(x^2 + y^2 - 1)^3 - x^2 y^3 <= 0`` is the classic cardioid-like heart;
    x and y are normalised so the shape fits into [-1.18, 1.18] / [-1.1, 1.25].
    """
    left = (x * x + y * y - 1) ** 3
    return left - x * x * y**3 <= 0


def _render(size: int) -> list[list[tuple[int, int, int, int]]]:
    """Render the heart as RGBA rows."""
    rows: list[list[tuple[int, int, int, int]]] = []
    step = 1.0 / (size * SUPERSAMPLE)
    for py in range(size):
        row: list[tuple[int, int, int, int]] = []
        for px in range(size):
            hits = 0
            for sub_y in range(SUPERSAMPLE):
                for sub_x in range(SUPERSAMPLE):
                    u = (px * SUPERSAMPLE + sub_x + 0.5) * step
                    v = (py * SUPERSAMPLE + sub_y + 0.5) * step
                    # normalised, y flipped so the heart points down
                    x = (u - 0.5) * 2.6
                    y = (0.55 - v) * 2.6
                    if _in_heart(x, y):
                        hits += 1
            if hits == 0:
                row.append((0, 0, 0, 0))
                continue
            alpha = round(255 * hits / (SUPERSAMPLE * SUPERSAMPLE))
            row.append((*RED, alpha))
        rows.append(row)
    return rows


def _write_png(path: pathlib.Path, rows: list[list[tuple[int, int, int, int]]]) -> None:
    """Write RGBA rows as a non-interlaced PNG (no external dependencies)."""
    height = len(rows)
    width = len(rows[0])
    raw = bytearray()
    for row in rows:
        raw.append(0)  # filter type 0
        for r, g, b, a in row:
            raw += bytes((r, g, b, a))

    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def main() -> int:
    BRAND.mkdir(parents=True, exist_ok=True)
    for size, name in ((256, "icon.png"), (512, "icon@2x.png")):
        _write_png(BRAND / name, _render(size))
        print(f"wrote {BRAND / name} ({size}x{size})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
