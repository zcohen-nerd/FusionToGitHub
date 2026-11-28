#!/usr/bin/env python3
"""Generate the add-in's icons from one vector definition (standard library only).

    python scripts/make_icons.py          # write every icon
    python scripts/make_icons.py --check  # exit 1 if a committed icon differs

The artwork redraws the approved master (``Assets/Branding/Icon-Master.png``,
kept by the maintainer outside the repository) as clean geometry: a
sharp-edged isometric cube with three blue faces on a navy square, and an
orange three-node branch on its right face. See ``branding/README.md``.

Two drawings share the same colours and layout:

* ``full`` — the master's proportions, for 64 px and larger and for the SVGs;
* ``small`` — a larger cube and a bolder branch without the white node
  centres, so the shape still reads at 16 and 32 px.

PNGs are rendered here with a small supersampling rasteriser (no Pillow,
no Inkscape), so the output is the same on every machine and CI can check
that the committed files match this script.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
VIEW = 512  # the drawings' coordinate space

NAVY = (0x07, 0x1B, 0x41)
TOP = (0x5B, 0xC9, 0xF2)
LEFT = (0x1F, 0x8B, 0xC2)
RIGHT = (0x02, 0x3F, 0x65)
ORANGE = (0xFD, 0x98, 0x15)
WHITE = (0xFF, 0xFF, 0xFF)

Point = Tuple[float, float]


def _cubic(p0: Point, p1: Point, p2: Point, p3: Point, steps: int = 24) -> List[Point]:
    points = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        points.append((
            u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
            u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1],
        ))
    return points


def drawing(variant: str) -> List[dict]:
    """The shapes of one drawing, bottom first, in the 512 x 512 space."""
    scale = 1.0 if variant == "full" else 1.16
    cx, cy = 252.0, 253.0

    def p(x: float, y: float) -> Point:
        return (cx + (x - cx) * scale, cy + (y - cy) * scale)

    # The cube: C is where the three faces meet.
    T, LT, RT, C = p(256, 70), p(96, 154), p(408, 154), p(248, 238)
    LB, B, RB = p(96, 352), p(248, 436), p(408, 352)
    shapes: List[dict] = [
        {"kind": "rect", "color": NAVY},
        {"kind": "poly", "color": TOP, "points": [T, RT, C, LT]},
        {"kind": "poly", "color": LEFT, "points": [LT, C, B, LB]},
        {"kind": "poly", "color": RIGHT, "points": [C, RT, RB, B]},
    ]
    # The branch on the right face: a trunk from the top node to the bottom
    # node, and a curve from the right-hand node joining the trunk.
    if variant == "full":
        n1, n2, n3 = p(308, 246), p(375, 281), p(308, 371)
        width, ring, hole = 18 * scale, 26 * scale, 13 * scale
        join, c1, c2 = p(308, 348), p(370, 318), p(310, 316)
    else:
        n1, n2, n3 = p(304, 248), p(376, 282), p(304, 370)
        width, ring, hole = 24 * scale, 29 * scale, 0.0
        join, c1, c2 = p(304, 346), p(374, 320), p(306, 312)
    shapes.append({"kind": "stroke", "color": ORANGE, "width": width, "points": [n1, n3]})
    shapes.append({"kind": "stroke", "color": ORANGE, "width": width,
                   "points": _cubic(n2, c1, c2, join), "curve": (n2, c1, c2, join)})
    for node in (n1, n2, n3):
        shapes.append({"kind": "circle", "color": ORANGE, "center": node, "r": ring})
        if hole:
            shapes.append({"kind": "circle", "color": WHITE, "center": node, "r": hole})
    return shapes


# -- SVG ----------------------------------------------------------------------


def _hex(color: Sequence[int]) -> str:
    return "#%02X%02X%02X" % tuple(color)


def _n(value: float) -> str:
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def svg(variant: str = "full") -> str:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW} {VIEW}" width="{VIEW}" height="{VIEW}">',
        "  <title>Push to GitHub</title>",
    ]
    for shape in drawing(variant):
        color = _hex(shape["color"])
        if shape["kind"] == "rect":
            parts.append(f'  <rect width="{VIEW}" height="{VIEW}" fill="{color}"/>')
        elif shape["kind"] == "poly":
            pts = " ".join(f"{_n(x)},{_n(y)}" for x, y in shape["points"])
            parts.append(f'  <polygon points="{pts}" fill="{color}"/>')
        elif shape["kind"] == "circle":
            x, y = shape["center"]
            parts.append(f'  <circle cx="{_n(x)}" cy="{_n(y)}" r="{_n(shape["r"])}" fill="{color}"/>')
        elif shape["kind"] == "stroke":
            if "curve" in shape:
                a, b, c, d = shape["curve"]
                path = (f"M{_n(a[0])} {_n(a[1])} C{_n(b[0])} {_n(b[1])} {_n(c[0])} {_n(c[1])} "
                        f"{_n(d[0])} {_n(d[1])}")
            else:
                path = "M" + " L".join(f"{_n(x)} {_n(y)}" for x, y in shape["points"])
            parts.append(f'  <path d="{path}" fill="none" stroke="{color}" '
                         f'stroke-width="{_n(shape["width"])}" stroke-linecap="round"/>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


# -- PNG ----------------------------------------------------------------------


def _inside(shape: dict, x: float, y: float) -> bool:
    kind = shape["kind"]
    if kind == "rect":
        return True
    if kind == "circle":
        cx, cy = shape["center"]
        return (x - cx) ** 2 + (y - cy) ** 2 <= shape["r"] ** 2
    if kind == "poly":
        pts = shape["points"]
        sign = 0
        for i in range(len(pts)):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % len(pts)]
            cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
            if cross:
                if sign == 0:
                    sign = 1 if cross > 0 else -1
                elif (cross > 0) != (sign > 0):
                    return False
        return True
    half = shape["width"] / 2
    pts = shape["points"]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        dx, dy = x2 - x1, y2 - y1
        length = dx * dx + dy * dy
        t = 0.0 if not length else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length))
        if (x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2 <= half * half:
            return True
    return False


def _bounds(shape: dict) -> Tuple[float, float, float, float]:
    if shape["kind"] == "rect":
        return (0, 0, VIEW, VIEW)
    if shape["kind"] == "circle":
        (x, y), r = shape["center"], shape["r"]
        return (x - r, y - r, x + r, y + r)
    pad = shape.get("width", 0) / 2
    xs = [x for x, _ in shape["points"]]
    ys = [y for _, y in shape["points"]]
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def render(size: int, variant: str, samples: int = 4) -> bytes:
    """RGB pixels (row-major) of the drawing at *size* x *size*, with samples x samples per pixel."""
    shapes = list(reversed(drawing(variant)))  # topmost first
    bounds = [_bounds(s) for s in shapes]
    unit = VIEW / size
    out = bytearray()
    offsets = [(i + 0.5) / samples for i in range(samples)]
    total = samples * samples
    for py in range(size):
        for px in range(size):
            r = g = b = 0
            for oy in offsets:
                y = (py + oy) * unit
                for ox in offsets:
                    x = (px + ox) * unit
                    for shape, (x0, y0, x1, y1) in zip(shapes, bounds):
                        if x0 <= x <= x1 and y0 <= y <= y1 and _inside(shape, x, y):
                            cr, cg, cb = shape["color"]
                            r += cr
                            g += cg
                            b += cb
                            break
            out += bytes((round(r / total), round(g / total), round(b / total)))
    return bytes(out)


def png(size: int, pixels: bytes) -> bytes:
    """A PNG file (8-bit RGB, no metadata, so the bytes depend only on the pixels)."""
    stride = size * 3
    raw = b"".join(b"\x00" + pixels[y * stride:(y + 1) * stride] for y in range(size))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


# -- outputs ------------------------------------------------------------------

# path in the repository -> (size or "svg", drawing)
OUTPUTS: Dict[str, Tuple[object, str]] = {
    "branding/icon.svg": ("svg", "full"),
    "branding/icon-small.svg": ("svg", "small"),
    "src/AddInIcon.svg": ("svg", "full"),
    # The toolbar button (Push_To_GitHub.RESOURCE_FOLDER). The Community
    # Store also reads resources/32x32@2x.png as the add-in's icon.
    "src/resources/16x16.png": (16, "small"),
    "src/resources/16x16@2x.png": (32, "small"),
    "src/resources/32x32.png": (32, "small"),
    "src/resources/32x32@2x.png": (64, "full"),
    # Store listings and documentation.
    "branding/png/icon-120.png": (120, "full"),
    "branding/png/icon-256.png": (256, "full"),
    "branding/png/icon-512.png": (512, "full"),
}


def build(path: str) -> bytes:
    size, variant = OUTPUTS[path]
    if size == "svg":
        return svg(variant).encode("utf-8")
    return png(int(size), render(int(size), variant))


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    parser.add_argument("--only", nargs="*", help="only these outputs")
    args = parser.parse_args(list(argv))
    stale = []
    for path in args.only or OUTPUTS:
        data = build(path)
        target = ROOT / path
        if args.check:
            current = target.read_bytes() if target.is_file() else None
            if current is not None and path.endswith(".svg"):
                current = current.replace(b"\r\n", b"\n")  # a Windows checkout may convert text files
            if current != data:
                stale.append(path)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            print(f"wrote {path} ({len(data)} bytes)")
    if stale:
        print("These icons don't match scripts/make_icons.py; run it and commit the result:")
        for path in stale:
            print(f"  {path}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


__all__ = ["OUTPUTS", "build", "drawing", "png", "render", "svg"]
