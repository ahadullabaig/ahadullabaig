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
    ".i,.m,.t,.d{{fill:none;stroke-linecap:round;stroke-linejoin:round}}"
    ".i{{stroke:{ink};stroke-width:2.2}}"
    ".m{{stroke:{muted};stroke-width:1.1}}"
    ".t{{stroke:{ink};stroke-opacity:{trace};stroke-width:1.2}}"
    ".d{{stroke:{ink};stroke-opacity:{trace};stroke-width:2.8}}"
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


def ouroboros(p, bx, by, bw, bh):
    """Snake on its grid, and the dotted BFS path it plans to the food."""
    step, cols, rows = 20, 18, 10
    ox = bx + (bw - step * (cols - 1)) / 2
    oy = by + (bh - step * (rows - 1)) / 2

    def pt(c, r):
        return ox + c * step, oy + r * step

    p.path("".join(f"M{n(x)} {n(y)}h0" for x, y in (pt(c, r) for c in range(cols) for r in range(rows))), "d")
    p.line([pt(*c) for c in [(12, 6), (15, 6), (15, 3)]], "m", "stroke-width:1.6;stroke-dasharray:0 5.5")
    body = [(1, 8), (5, 8), (5, 5), (2, 5), (2, 2), (9, 2), (9, 6), (12, 6)]
    p.line([pt(*c) for c in body], "i", "stroke-width:9")
    hx, hy = pt(12, 6)
    p.circle(hx + 1.5, hy, 6.2, "fi")
    fx, fy = pt(15, 3)
    p.circle(fx, fy, 5, "i")


def luna(p, bx, by, bw, bh):
    """Last cycle, this one split at today, the next one predicted."""
    R, cy = 52, by + bh / 2
    centres = [bx + R + 6, bx + bw / 2, bx + bw - R - 6]
    cycles, today = [29, 27, 28], 17

    def arc(cx, a0, a1, cls, style=""):
        x0, y0 = cx + R * math.cos(a0), cy + R * math.sin(a0)
        x1, y1 = cx + R * math.cos(a1), cy + R * math.sin(a1)
        large = 1 if a1 - a0 > math.pi else 0
        p.path(f"M{n(x0)} {n(y0)}A{R} {R} 0 {large} 1 {n(x1)} {n(y1)}", cls, style)

    for idx, (cx, length) in enumerate(zip(centres, cycles)):
        phases = [5, length - 21, 2, 14]
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
    """ECG with powerline hum (ghost), the cleaned trace (ink), and the spikes between."""
    rng = random.Random(3)
    base, period = by + 104, 122

    def ecg(t):
        ph = ((t + 34) % period) / period
        g = lambda mu, sig, a: a * math.exp(-0.5 * ((ph - mu) / sig) ** 2)
        return g(.2, .035, 9) - g(.37, .011, 8) + g(.41, .012, 70) - g(.45, .013, 15) + g(.7, .06, 17)

    xs = [bx + t for t in range(0, bw + 1)]
    noisy = [(x, base - ecg(x - bx) - 7 * math.sin(2 * math.pi * (x - bx) / 6.2) + rng.gauss(0, 1.1)) for x in xs]
    clean = [(x, base - ecg(x - bx)) for x in xs]
    p.line(noisy, "t", "stroke-width:1")
    p.line(clean, "i")
    ticks = []
    for row in range(3):
        y = by + 150 + row * 13
        for x in xs[::2]:
            if rng.random() < 0.012 + 0.22 * max(0, ecg(x - bx - 6 * row)) / 70:
                ticks.append(f"M{n(x)} {n(y)}v7")
    p.path("".join(ticks), "m", "stroke-width:1.4")


def bean(p, bx, by, bw, bh):
    """Messy notes in, three passes (auditor, ghostwriter, critic), a tidy report out."""
    rng = random.Random(5)
    cy = by + bh / 2
    for k in range(7):
        y0 = by + 30 + k * 22 + rng.uniform(-3, 3)
        x0, length = bx + rng.uniform(0, 14), rng.uniform(60, 128)
        tilt, wob = rng.uniform(-0.06, 0.06), rng.uniform(0, 6)
        pts = [(x0 + t, y0 + tilt * t + 1.6 * math.sin(t / 7 + wob) + rng.uniform(-0.5, 0.5))
               for t in range(0, int(length), 4)]
        p.line(pts, "t", "stroke-width:1.5")
        if k == 3:
            x, y = pts[len(pts) // 3]
            p.line([(x + i * 4, y + (-4 if i % 2 else 4)) for i in range(7)], "t", "stroke-width:1.5")
    nodes = [bx + 176, bx + 200, bx + 224]
    p.line([(bx + 150, cy), (nodes[0] - 6, cy)], "m")
    p.line([(nodes[-1] + 6, cy), (bx + 252, cy)], "m")
    arrowhead(p, (bx + 252, cy), 0, "m", 5)
    for i, x in enumerate(nodes):
        p.circle(x, cy, 6, "m")
        if i:
            p.line([(nodes[i - 1] + 6, cy), (x - 6, cy)], "m")
    rx, rw = bx + 270, bw - 270
    p.line([(rx, by + 34), (rx + 72, by + 34)], "i", "stroke-width:4.5")
    for k in range(6):
        y = by + 62 + k * 17
        p.line([(rx, y), (rx + (rw * 0.62 if k == 5 else rw), y)], "i", "stroke-width:1.4")
    p.line([(rx + rw - 22, by + 166), (rx + rw - 14, by + 174), (rx + rw, by + 156)], "i")


PROJECTS = [
    ("amaze", "Amaze", "https://github.com/ahadullabaig/Amaze",
     "a recursive backtracker carves a hex maze, then BFS, A* and DFS race through identical copies of it.", amaze),
    ("automata", "Automata-Visualis", "https://github.com/ahadullabaig/Automata-Visualis",
     "build a DFA, then watch a token step through it one input symbol at a time.", automata),
    ("ouroboros", "ouroboros", "https://github.com/ahadullabaig/ouroboros",
     "a snake AI in plain C. it chases food with BFS, but only if it can still reach its own tail.", ouroboros),
    ("luna", "Luna", "https://github.com/ahadullabaig/Luna",
     "a period tracker with no internet permission. your data has nowhere to go.", luna),
    ("neuroflux", "NeuroFlux", "https://github.com/ahadullabaig/NeuroFlux",
     "an experiment in spiking neural networks that strip powerline hum out of ECG, with no labelled data.",
     neuroflux),
    ("bean", "Bean", "https://github.com/ahadullabaig/Bean",
     "turns messy event notes into reports for the IEEE RIT-B student branch, then checks its own facts.", bean),
]

LEAD = "a few things i've made:"
EMAIL, LINKEDIN = "ahadullabaig.16@gmail.com", "in/ahadullabaig"
COLOPHON = ("every drawing on this page is generated by code in this repo. each letter of the header is one "
            "closed line through every cell of a maze grown inside it.")


def plates():
    lead = Plate("lead", 52, LEAD)
    lead.text(BOOK, LEAD, PAD, 30, 19, "fm")
    yield lead, None

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

    colophon = Plate("colophon", 92, COLOPHON)
    colophon.para(BOOK, COLOPHON, PAD, 30, 14, 21, "fm")
    yield colophon, "https://github.com/ahadullabaig/ahadullabaig/tree/main/art"


RAW = "https://raw.githubusercontent.com/ahadullabaig/ahadullabaig/main/art"


def picture(name, width, alt):
    alt = escape(alt, {'"': "&quot;"})
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="{RAW}/{name}-dark.svg">'
            f'<img src="{RAW}/{name}-light.svg" width="{width}" alt="{alt}"></picture>')


def readme(items):
    """One HTML block, so GitHub keeps each link around its picture. Two plates fill a row."""
    tiles = [picture(p.name, W, p.alt) if url is None else f'<a href="{url}">{picture(p.name, W, p.alt)}</a>'
             for p, url in items]
    rows = [picture("ahad", 2 * W, "ahad"), tiles[0] + "<br>"]
    rows += [a + b for a, b in zip(tiles[1:-1:2], tiles[2:-1:2])] + [tiles[-1]]
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
