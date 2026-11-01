"""Draws everything under the header: the intro, one plate per project, and
the contact lines.

Each project is a small drawing of its own algorithm, in the header's rule:
ghost marks are what the algorithm could have done, ink is what it did.
Text is set in Jost and outlined, so it looks the same everywhere.

    pip install fonttools uharfbuzz
    python3 art/plates.py
"""

import heapq
import io
import math
import random
from pathlib import Path
from xml.sax.saxutils import escape

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

HERE = Path(__file__).parent
W, PAD = 420, 12          # two plates fill the 840px column; text sits 12px in
INNER = W - 2 * PAD
ART = 196                 # height of a project drawing

THEMES = {
    "light": {"ink": "#1f2328", "muted": "#59636e", "ghost": 0.13, "trace": 0.3},
    "dark": {"ink": "#f0f6fc", "muted": "#9198a1", "ghost": 0.16, "trace": 0.36},
}

STYLE = (
    ".i,.m,.t{{fill:none;stroke-linecap:round;stroke-linejoin:round}}"
    ".i{{stroke:{ink};stroke-width:2.2}}"
    ".m{{stroke:{muted};stroke-width:1.1}}"
    ".t{{stroke:{ink};stroke-opacity:{trace};stroke-width:1.2}}"
    ".g{{fill:{ink};fill-opacity:{ghost}}}"
    ".fi{{fill:{ink}}}.fm{{fill:{muted}}}"
)


def n(v):
    return f"{round(v, 1):g}"


class Face:
    def __init__(self, file, weight, key):
        font = instantiateVariableFont(TTFont(HERE / "fonts" / file), {"wght": weight})
        buf = io.BytesIO()
        font.save(buf)
        self.hb = hb.Font(hb.Face(buf.getvalue()))
        self.glyphs = font.getGlyphSet()
        self.names = font.getGlyphOrder()
        self.upm = font["head"].unitsPerEm
        self.key = key

    def shape(self, text):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb, buf, {"kern": True, "liga": True, "ss01": True})  # ss01: single-storey a, like the header
        x, out = 0, []
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            out.append((info.codepoint, x + pos.x_offset, pos.y_offset))
            x += pos.x_advance
        return out, x

    def width(self, text, size):
        return self.shape(text)[1] * size / self.upm

    def outline(self, gid):
        pen = SVGPathPen(self.glyphs)
        self.glyphs[self.names[gid]].draw(pen)
        return pen.getCommands()


BOOK = Face("Jost[wght].ttf", 400, "b")
MEDIUM = Face("Jost[wght].ttf", 500, "m")
ITALIC = Face("Jost-Italic[wght].ttf", 400, "i")


class Plate:
    def __init__(self, name, height, alt):
        self.name, self.h, self.alt = name, height, alt
        self.parts, self.defs = [], {}

    def path(self, d, cls, style=""):
        self.parts.append(f'<path class="{cls}" d="{d}"{f" style={chr(34)}{style}{chr(34)}" if style else ""}/>')

    def line(self, pts, cls, style=""):
        self.path("M" + "L".join(f"{n(x)} {n(y)}" for x, y in pts), cls, style)

    def circle(self, x, y, r, cls):
        self.parts.append(f'<circle class="{cls}" cx="{n(x)}" cy="{n(y)}" r="{n(r)}"/>')

    def text(self, face, s, x, y, size, cls):
        glyphs, _ = face.shape(s)
        k = size / face.upm
        uses = []
        for gid, gx, gy in glyphs:
            key = f"{face.key}{gid}"
            if key not in self.defs:
                self.defs[key] = face.outline(gid)
            if self.defs[key]:
                uses.append(f'<use href="#{key}" x="{gx}"{f" y={chr(34)}{gy}{chr(34)}" if gy else ""}/>')
        self.parts.append(f'<g class="{cls}" transform="translate({n(x)} {n(y)}) scale({k:.5f} {-k:.5f})">'
                          + "".join(uses) + "</g>")

    def para(self, face, s, x, y, size, lead, cls, width=INNER):
        lines, cur = [], ""
        for word in s.split():
            trial = f"{cur} {word}".strip()
            if cur and face.width(trial, size) > width:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        lines.append(cur)
        for i, l in enumerate(lines):
            self.text(face, l, x, y + i * lead, size, cls)
        return len(lines)

    def render(self, theme):
        defs = "".join(f'<path id="{k}" d="{d}"/>' for k, d in self.defs.items() if d)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {self.h}" width="{W}" '
                f'height="{self.h}" role="img" aria-labelledby="t"><title id="t">{escape(self.alt)}</title>'
                f"<style>{STYLE.format(**theme)}</style><defs>{defs}</defs>\n"
                + "\n".join(self.parts) + "\n</svg>\n")


def arrowhead(p, tip, angle, cls, size=7):
    a = [angle + math.pi - 0.45, angle + math.pi + 0.45]
    p.line([(tip[0] + size * math.cos(a[0]), tip[1] + size * math.sin(a[0])), tip,
            (tip[0] + size * math.cos(a[1]), tip[1] + size * math.sin(a[1]))], cls)


def centered(p, face, s, x, y, size, cls):
    p.text(face, s, x - face.width(s, size) / 2, y, size, cls)


# Drawings. Each gets a box (x, y, w, h) to fill.

def amaze(p, bx, by, bw, bh):
    """Hex maze from a recursive backtracker. Ghost: cells A* looked at. Ink: its path."""
    rng = random.Random(7)
    s = 10.5
    hw = math.sqrt(3) * s
    cols, rows = 21, 12
    ox = bx + (bw - hw * (cols + 0.5)) / 2 + hw / 2
    oy = by + (bh - s * (1.5 * (rows - 1) + 2)) / 2 + s

    def centre(c):
        return ox + hw * (c[0] + 0.5 * (c[1] & 1)), oy + 1.5 * s * c[1]

    def corner(c, k):
        x, y = centre(c)
        a = math.radians(60 * k - 30)
        return x + s * math.cos(a), y + s * math.sin(a)

    def nbrs(c):
        odd = [(1, 0), (1, 1), (0, 1), (-1, 0), (0, -1), (1, -1)]
        even = [(1, 0), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1)]
        for e, (dc, dr) in enumerate(odd if c[1] & 1 else even):
            yield e, (c[0] + dc, c[1] + dr)

    cells = {(c, r) for c in range(cols) for r in range(rows)}
    passages, seen, stack = set(), {(0, 0)}, [(0, 0)]
    while stack:
        options = [m for _, m in nbrs(stack[-1]) if m in cells and m not in seen]
        if not options:
            stack.pop()
            continue
        m = rng.choice(options)
        passages.add(frozenset((stack[-1], m)))
        seen.add(m)
        stack.append(m)

    entry, goal = (0, 2), (cols - 1, rows - 3)
    dist = lambda a: math.dist(centre(a), centre(goal)) / hw
    best, came, looked, queue = {entry: 0}, {}, [], [(dist(entry), 0, entry)]
    while queue:
        _, g, c = heapq.heappop(queue)
        if c in looked:
            continue
        looked.append(c)
        if c == goal:
            break
        for _, m in nbrs(c):
            if frozenset((c, m)) in passages and g + 1 < best.get(m, 1e9):
                best[m], came[m] = g + 1, c
                heapq.heappush(queue, (g + 1 + dist(m), g + 1, m))
    route = [goal]
    while route[-1] != entry:
        route.append(came[route[-1]])

    p.path("".join("M" + "L".join(f"{n(x)} {n(y)}" for x, y in (corner(c, k) for k in range(6))) + "Z"
                   for c in looked), "g")
    walls = []
    for c in cells:
        for e, m in nbrs(c):
            if (c, e) in ((entry, 3), (goal, 0)):
                continue
            if m not in cells or (frozenset((c, m)) not in passages and m > c):
                (x0, y0), (x1, y1) = corner(c, e), corner(c, e + 1)
                walls.append(f"M{n(x0)} {n(y0)}L{n(x1)} {n(y1)}")
    p.path("".join(walls), "m")
    pts = [centre(c) for c in reversed(route)]
    p.line([(max(bx, pts[0][0] - hw * 0.8), pts[0][1])] + pts + [(min(bx + bw, pts[-1][0] + hw * 0.8), pts[-1][1])], "i")


def automata(p, bx, by, bw, bh):
    """The 'ends in 01' DFA. Ink: the transitions the input 1001 takes."""
    r, cy = 21, by + 84
    xs = [bx + 62, bx + 210, bx + 356]

    def on(i, deg):
        a = math.radians(deg)
        return xs[i] + r * math.cos(a), cy + r * math.sin(a)

    def loop(i, label, cls):
        a0, a1 = math.radians(-122), math.radians(-58)
        p0, p3 = on(i, -122), on(i, -58)
        c1 = (xs[i] + 2.7 * r * math.cos(a0 - 0.18), cy + 2.7 * r * math.sin(a0 - 0.18))
        c2 = (xs[i] + 2.7 * r * math.cos(a1 + 0.18), cy + 2.7 * r * math.sin(a1 + 0.18))
        p.path(f"M{n(p0[0])} {n(p0[1])}C{n(c1[0])} {n(c1[1])} {n(c2[0])} {n(c2[1])} {n(p3[0])} {n(p3[1])}", cls)
        arrowhead(p, p3, math.atan2(p3[1] - c2[1], p3[0] - c2[0]), cls)
        centered(p, ITALIC, label, xs[i], cy - 2.45 * r - 5, 15, "fm")

    def straight(i, j, label, cls):
        a, b = (xs[i] + r, cy), (xs[j] - r, cy)
        p.line([a, b], cls)
        arrowhead(p, b, 0, cls)
        centered(p, ITALIC, label, (a[0] + b[0]) / 2, cy - 8, 15, "fm")

    def under(i, j, depth, d0, d1, label, cls):
        a, b = on(i, d0), on(j, d1)
        c = ((a[0] + b[0]) / 2, cy + depth)
        p.path(f"M{n(a[0])} {n(a[1])}Q{n(c[0])} {n(c[1])} {n(b[0])} {n(b[1])}", cls)
        arrowhead(p, b, math.atan2(b[1] - c[1], b[0] - c[0]), cls)
        centered(p, ITALIC, label, c[0], (a[1] + 2 * c[1] + b[1]) / 4 + 17, 15, "fm")

    p.line([(bx + 4, cy), (xs[0] - r, cy)], "i")
    arrowhead(p, (xs[0] - r, cy), 0, "i")
    loop(0, "1", "i")
    straight(0, 1, "0", "i")
    loop(1, "0", "i")
    straight(1, 2, "1", "i")
    under(2, 1, 56, 118, 62, "0", "m")
    under(2, 0, 150, 98, 82, "1", "m")
    for i, x in enumerate(xs):
        p.circle(x, cy, r, "i")
        p.text(ITALIC, "q", x - 7, cy + 4, 18, "fi")
        p.text(BOOK, str(i), x + 2.5, cy + 8, 11, "fi")
    p.circle(xs[2], cy, r - 4.5, "i")
    tape = "1001"
    tx = xs[2] - 2 * 16
    for k, ch in enumerate(tape):
        p.path(f"M{n(tx + k * 16)} {n(by + 4)}h16v16h-16Z", "m")
        centered(p, BOOK, ch, tx + k * 16 + 8, by + 16.5, 12, "fi")


def luna(p, bx, by, bw, bh):
    """Last cycle, this one split at today, the next one predicted.
    Phases as the app counts them: a 3-day ovulation window centred on day length - 14."""
    R, cy = 52, by + bh / 2
    centres = [bx + R + 6, bx + bw / 2, bx + bw - R - 6]
    cycles, today = [29, 27, 28], 17

    def arc(cx, a0, a1, cls, style=""):
        x0, y0 = cx + R * math.cos(a0), cy + R * math.sin(a0)
        x1, y1 = cx + R * math.cos(a1), cy + R * math.sin(a1)
        large = 1 if a1 - a0 > math.pi else 0
        p.path(f"M{n(x0)} {n(y0)}A{R} {R} 0 {large} 1 {n(x1)} {n(y1)}", cls, style)

    for idx, (cx, length) in enumerate(zip(centres, cycles)):
        phases = [5, length - 21, 3, 13]  # menstrual, follicular, ovulation, luteal
        split = [length, today, 0][idx]
        day, gap = 0, math.radians(2.2)
        for span in phases:
            a = lambda d: -math.pi / 2 + 2 * math.pi * d / length
            start, end = a(day) + gap, a(day + span) - gap
            cut = min(max(a(split), start), end)
            if cut > start:
                arc(cx, start, cut, "i", "stroke-width:5;stroke-linecap:butt")
            if end > cut:
                arc(cx, cut, end, "m")
            day += span


def neuroflux(p, bx, by, bw, bh):
    """The paper's fidelity ceiling. Output S/N follows input S/N, then levels off where
    the cascade law 1/R_out = 1/R_in + 1/C puts it. Ghost: perfect fidelity. Ink: the law,
    with measured runs sitting on it."""
    lo, hi, ceiling = -15.0, 45.0, 1.92  # input range in dB; MIT-BIH ceiling in dB
    x0, x1, base = bx + 6, bx + bw, by + bh - 22
    k = (x1 - x0) / (hi - lo)            # px per dB, the same on both axes
    X = lambda db: x0 + (db - lo) * k
    Y = lambda db: base - (db - lo) * k
    law = lambda r: -10 * math.log10(10 ** (-r / 10) + 10 ** (-ceiling / 10))

    p.line([(x0, by + 4), (x0, base), (x1, base)], "m")
    p.line([(X(lo), Y(lo)), (X(lo + (base - by) / k), by)], "t")
    p.line([(x0, Y(ceiling)), (x1, Y(ceiling))], "m", "stroke-dasharray:2 4")
    p.line([(X(r / 2), Y(law(r / 2))) for r in range(int(2 * lo), int(2 * hi) + 1)], "i")
    for r in (-10, -5, 0, 5, 10, 20, 30, 40):
        p.circle(X(r), Y(law(r)), 2.6, "fi")
    p.text(ITALIC, "output S/N", x0 + 9, by + 13, 12.5, "fm")
    p.text(ITALIC, "input S/N", x1 - ITALIC.width("input S/N", 12.5), base + 17, 12.5, "fm")
    p.text(ITALIC, "ceiling", x1 - ITALIC.width("ceiling", 12.5), Y(ceiling) - 8, 12.5, "fm")


PROJECTS = [
    ("neuroflux", "NeuroFlux", "https://github.com/ahadullabaig/NeuroFlux",
     "spiking networks hit a fidelity ceiling, and a Friis-type cascade law predicts it. our IEEE ICEE 2026 paper.",
     neuroflux),
    ("luna", "Luna", "https://github.com/ahadullabaig/Luna",
     "a period tracker with no internet permission, so your cycle never leaves your phone.", luna),
    ("automata", "Automata-Visualis", "https://github.com/ahadullabaig/Automata-Visualis",
     "build a DFA, then watch a token step through it one input symbol at a time.", automata),
    ("amaze", "Amaze", "https://github.com/ahadullabaig/Amaze",
     "a recursive backtracker carves a hex maze, then BFS, A* and DFS race through identical copies of it.", amaze),
]

EMAIL, LINKEDIN = "ahadullabaig.16@gmail.com", "in/ahadullabaig"


def plates():
    for slug, name, url, desc, draw in PROJECTS:
        p = Plate(slug, 326, f"{name}: {desc}")
        draw(p, PAD, PAD, INNER, ART)
        p.text(MEDIUM, name, PAD, PAD + ART + 40, 23, "fi")
        assert p.para(BOOK, desc, PAD, PAD + ART + 66, 15.5, 22, "fm") <= 2, f"{slug} description is too long"
        yield p, url

    for slug, lead, value, url in (("email", "say hi at", EMAIL, f"mailto:{EMAIL}"),
                                   ("linkedin", "or on linkedin,", LINKEDIN, f"https://www.linkedin.com/{LINKEDIN}/")):
        p = Plate(slug, 64, f"{lead} {value}")
        p.text(BOOK, lead, PAD, 38, 19, "fm")
        p.text(BOOK, value, PAD + BOOK.width(lead + " ", 19), 38, 19, "fi")
        yield p, url


RAW = "https://raw.githubusercontent.com/ahadullabaig/ahadullabaig/main/art"


def picture(name, width, alt):
    alt = escape(alt, {'"': "&quot;"})
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="{RAW}/{name}-dark.svg">'
            f'<img src="{RAW}/{name}-light.svg" width="{width}" alt="{alt}"></picture>')


def readme(items):
    """One HTML block, so GitHub keeps each link around its picture. Two plates fill a row."""
    tiles = [f'<a href="{url}">{picture(p.name, W, p.alt)}</a>' for p, url in items]
    rows = [picture("ahad", 2 * W, "ahad")] + [a + b for a, b in zip(tiles[::2], tiles[1::2])]
    return ("<!-- generated by art/plates.py: change the words there, then run it -->\n<p>\n"
            + "\n".join(rows) + "\n</p>\n")


def main():
    items = list(plates())
    for plate, _ in items:
        for name, theme in THEMES.items():
            (HERE / f"{plate.name}-{name}.svg").write_text(plate.render(theme))
    (HERE.parent / "README.md").write_text(readme(items))
    print(f"{len(items)} plates and README.md")


if __name__ == "__main__":
    main()
