"""
sketch.py
---------
A small hand-drawn drawing kit for the insight deck: wobbly double-stroke lines, boxes with hachure fill, sticky
notes, curved arrows and handwritten labels (Kalam, SIL Open Font License, in pipeline/assets/fonts). Everything is
drawn with matplotlib on a canvas measured in inches (origin top-left, y down) and saved as a transparent PNG, so a
drawing drops onto a slide at exactly the size it was designed for.

Randomness is seeded per canvas, so the same data always gives the same drawing.
"""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

FONTS = Path(__file__).resolve().parent / "assets" / "fonts"
HAND = {w: FontProperties(fname=str(FONTS / f"Kalam-{w}.ttf")) for w in ("Light", "Regular", "Bold")}

INK, GREY, PURPLE, RED, GREEN = "#1E2A3A", "#6B7383", "#6A2BC2", "#D9472F", "#13866F"
LAVENDER, YELLOW, YELLOW_EDGE, PAPER, SOFTRED = "#E6DAFA", "#FFE89A", "#E9C84A", "#FFFFFF", "#F8D9D3"


class Sketch:
    def __init__(self, w: float, h: float, seed: int = 7, dpi: int = 220):
        self.w, self.h, self.dpi = w, h, dpi
        self.rng = np.random.default_rng(seed)
        self.fig = plt.figure(figsize=(w, h), dpi=dpi)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, w)
        self.ax.set_ylim(h, 0)
        self.ax.axis("off")
        self.fig.patch.set_alpha(0)
        self.ax.patch.set_alpha(0)

    # ── primitives ───────────────────────────────────────────────────────────
    def _stroke(self, x1, y1, x2, y2, rough):
        length = math.hypot(x2 - x1, y2 - y1)
        j = min(0.035, 0.012 + length * 0.006) * rough
        a = (x1 + self.rng.normal(0, j), y1 + self.rng.normal(0, j))
        b = (x2 + self.rng.normal(0, j), y2 + self.rng.normal(0, j))
        # bowed middle, perpendicular to the line
        nx, ny = (-(y2 - y1) / length, (x2 - x1) / length) if length else (0, 0)
        bow = self.rng.normal(0, min(0.03, length * 0.012)) * rough
        mx, my = (a[0] + b[0]) / 2 + nx * bow, (a[1] + b[1]) / 2 + ny * bow
        t = np.linspace(0, 1, max(8, int(length * 18)))
        xs = (1 - t) ** 2 * a[0] + 2 * (1 - t) * t * mx + t ** 2 * b[0]
        ys = (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * my + t ** 2 * b[1]
        return xs, ys

    def line(self, x1, y1, x2, y2, color=INK, lw=1.6, rough=1.0, passes=2, dash=None, alpha=1.0):
        for k in range(passes):
            xs, ys = self._stroke(x1, y1, x2, y2, rough * (1 if k == 0 else 0.8))
            self.ax.plot(xs, ys, color=color, lw=lw * (1 if k == 0 else 0.75), solid_capstyle="round",
                         linestyle=(0, dash) if dash else "-", alpha=alpha * (1 if k == 0 else 0.8))

    def _hachure(self, x, y, w, h, color, gap=0.075, angle=-41, lw=0.9, alpha=0.9):
        """Parallel strokes clipped to an axis-aligned rectangle."""
        th = math.radians(angle)
        dx, dy = math.cos(th), math.sin(th)
        nx, ny = -dy, dx
        corners = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
        proj = [cx * nx + cy * ny for cx, cy in corners]
        c = min(proj)
        while c <= max(proj):
            pts = []
            # intersect the line {p : p·n = c} with each rectangle edge
            for (ax_, ay_), (bx_, by_) in [((x, y), (x + w, y)), ((x + w, y), (x + w, y + h)),
                                            ((x + w, y + h), (x, y + h)), ((x, y + h), (x, y))]:
                pa, pb = ax_ * nx + ay_ * ny - c, bx_ * nx + by_ * ny - c
                if pa == pb:
                    continue
                t = pa / (pa - pb)
                if 0 <= t <= 1:
                    pts.append((ax_ + t * (bx_ - ax_), ay_ + t * (by_ - ay_)))
            if len(pts) >= 2:
                (p1x, p1y), (p2x, p2y) = pts[0], pts[-1]
                if math.hypot(p2x - p1x, p2y - p1y) > 0.02:
                    self.line(p1x, p1y, p2x, p2y, color=color, lw=lw, rough=0.35, passes=1, alpha=alpha)
            c += gap

    def box(self, x, y, w, h, stroke=INK, lw=1.7, fill=None, hachure=None, gap=0.075, rough=1.0, shadow=False):
        """Rectangle: optional solid fill and/or hachure fill, wobbly double outline."""
        if shadow:
            self._poly(x + 0.05, y + 0.06, w, h, "#00000018")
        if fill:
            self._poly(x, y, w, h, fill)
        if hachure:
            self._hachure(x + 0.02, y + 0.02, w - 0.04, h - 0.04, hachure, gap=gap)
        if stroke:
            for (a, b, c_, d) in [(x, y, x + w, y), (x + w, y, x + w, y + h), (x + w, y + h, x, y + h), (x, y + h, x, y)]:
                self.line(a, b, c_, d, color=stroke, lw=lw, rough=rough)

    def _poly(self, x, y, w, h, color, wobble=0.02):
        j = lambda: self.rng.normal(0, wobble)  # noqa: E731
        pts = [(x + j(), y + j()), (x + w + j(), y + j()), (x + w + j(), y + h + j()), (x + j(), y + h + j())]
        self.ax.add_patch(Polygon(pts, closed=True, facecolor=color, edgecolor="none"))

    def sticky(self, x, y, w, h, color=YELLOW):
        self._poly(x + 0.04, y + 0.05, w, h, "#0000001A", wobble=0.01)
        self._poly(x, y, w, h, color, wobble=0.012)
        self.line(x, y + h, x + w, y + h, color=YELLOW_EDGE, lw=1.2, rough=0.5, passes=1)

    def ellipse(self, cx, cy, rx, ry, color=RED, lw=1.8, start=None):
        """Hand-drawn loop around something (overshoots its start like a pen would)."""
        s = self.rng.uniform(0, 2 * math.pi) if start is None else start
        t = np.linspace(s, s + 2 * math.pi * 1.08, 120)
        wob = 1 + 0.03 * np.sin(3 * t + self.rng.uniform(0, 6))
        self.ax.plot(cx + rx * wob * np.cos(t), cy + ry * wob * np.sin(t), color=color, lw=lw, solid_capstyle="round")

    def arrow(self, x1, y1, x2, y2, color=GREY, lw=1.6, bend=0.18, head=0.13):
        """Curved arrow; bend is the sideways bulge as a share of the length (negative bends the other way)."""
        length = math.hypot(x2 - x1, y2 - y1)
        nx, ny = -(y2 - y1) / length, (x2 - x1) / length
        mx, my = (x1 + x2) / 2 + nx * bend * length, (y1 + y2) / 2 + ny * bend * length
        t = np.linspace(0, 1, 60)
        xs = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * mx + t ** 2 * x2
        ys = (1 - t) ** 2 * y1 + 2 * (1 - t) * t * my + t ** 2 * y2
        self.ax.plot(xs, ys, color=color, lw=lw, solid_capstyle="round")
        ang = math.atan2(ys[-1] - ys[-4], xs[-1] - xs[-4])
        for d in (2.6, -2.6):
            self.line(x2, y2, x2 - head * math.cos(ang + d / 6), y2 - head * math.sin(ang + d / 6), color=color,
                      lw=lw, rough=0.3, passes=1)

    def cross(self, x, y, s=0.13, color=RED, lw=2.0):
        self.line(x - s, y - s, x + s, y + s, color=color, lw=lw, rough=0.4, passes=1)
        self.line(x - s, y + s, x + s, y - s, color=color, lw=lw, rough=0.4, passes=1)

    def tick(self, x, y, s=0.13, color=GREEN, lw=2.2):
        self.line(x - s, y, x - s * 0.3, y + s * 0.8, color=color, lw=lw, rough=0.3, passes=1)
        self.line(x - s * 0.3, y + s * 0.8, x + s * 1.2, y - s, color=color, lw=lw, rough=0.3, passes=1)

    def underline(self, x1, x2, y, color=YELLOW_EDGE, lw=2.0):
        self.line(x1, y, x2, y, color=color, lw=lw, rough=0.6, passes=1)

    def text(self, x, y, s, size=14, color=INK, weight="Regular", ha="left", va="baseline", rotation=0, alpha=1.0,
             linespacing=1.15):
        return self.ax.text(x, y, s, fontproperties=HAND[weight], fontsize=size, color=color, ha=ha, va=va,
                            rotation=rotation, alpha=alpha, linespacing=linespacing)

    @staticmethod
    def width(s: str, size: float, weight: str = "Regular") -> float:
        """Width of handwritten text in inches (widest line)."""
        from matplotlib.textpath import TextPath
        return max(TextPath((0, 0), line or " ", prop=HAND[weight], size=size).get_extents().width / 72
                   for line in s.split("\n"))

    def num_circle(self, cx, cy, label, r=0.17, color=INK, size=12, fill=None):
        if fill:
            t = np.linspace(0, 2 * math.pi, 60)
            self.ax.fill(cx + r * np.cos(t), cy + r * np.sin(t), color=fill)
        self.ellipse(cx, cy, r, r, color=color, lw=1.5)
        self.text(cx, cy + 0.01, label, size=size, color=color, weight="Bold", ha="center", va="center")

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fig.savefig(path, dpi=self.dpi, transparent=True)
        plt.close(self.fig)
        return path


def background(path: Path, dark: bool = False, w: int = 2000, h: int = 1125) -> Path:
    """Slide background: white with a faint dot grid (light slides) or deep navy with faint dots (dark slides)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), "#1C2433" if dark else "#FFFFFF")
    d = ImageDraw.Draw(im)
    dot = "#28324A" if dark else "#E3E6EC"
    step = 30
    for yy in range(step // 2, h, step):
        for xx in range(step // 2, w, step):
            d.ellipse([xx - 1.4, yy - 1.4, xx + 1.4, yy + 1.4], fill=dot)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)
    return path
