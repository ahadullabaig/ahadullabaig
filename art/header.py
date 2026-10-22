"""Draws the profile header: "ahad", each letter one closed line.

A random maze (spanning tree) is grown on a coarse grid inside each letter,
then traced around on a grid twice as fine. Tracing around a tree visits
every fine cell exactly once and ends where it started, so each letter is a
single Hamiltonian cycle.

    python3 art/header.py
"""

import math
import random
from pathlib import Path

SEED = 16
P = 10            # fine grid pitch, in viewBox units
R = 10            # bowl radius, in coarse cells
W = 5             # stroke weight, in coarse cells
ASC = 30          # ascender height, in coarse cells
STROKE = 4.4
SPEED = 5200      # viewBox units drawn per second
STAGGER = 1.1     # seconds between letters starting
BELOW = 90        # space under the baseline, so the text below can breathe
SIDE = 25.35      # side margin that lines the letters up with the plates' text

THEMES = {
    "light": {"ink": "#1f2328", "ghost": 0.13},
    "dark": {"ink": "#f0f6fc", "ghost": 0.16},
}


def ring(cx, cy, r_out, r_in, top_only=False):
    def inside(x, y):
        d = math.hypot(x - cx, y - cy)
        return r_in <= d <= r_out and (not top_only or y <= cy)
    return inside


def rect(x0, y0, x1, y1):
    return lambda x, y: x0 <= x <= x1 and y0 <= y <= y1


def letters():
    """Geometric lowercase a, h, a, d as point-in-shape tests, in coarse cells."""
    base, xh = ASC, 2 * R
    cy = base - R

    def bowl_with_stem(x, stem_top):
        return [ring(x + R, cy, R, R - W), rect(x + 2 * R - W, stem_top, x + 2 * R, base)]

    def h(x):
        return [rect(x, 0, x + W, base),
                ring(x + R, base - xh + R, R, R - W, top_only=True),
                rect(x + 2 * R - W, base - xh + R, x + 2 * R, base)]

    gaps = [6, 5, 5]  # stem to stem, stem to bowl, stem to bowl
    xs = [0]
    for g in gaps:
        xs.append(xs[-1] + 2 * R + g)
    shapes = [bowl_with_stem(xs[0], base - xh), h(xs[1]),
              bowl_with_stem(xs[2], base - xh), bowl_with_stem(xs[3], 0)]
    width = xs[-1] + 2 * R
    return shapes, width


def rasterize(parts, width):
    return {(i, j) for i in range(width) for j in range(ASC)
            if any(part(i + 0.5, j + 0.5) for part in parts)}


def grow_maze(cells, rng):
    """Recursive backtracker; returns the tree's edges."""
    start = min(cells)
    seen, stack, edges = {start}, [start], set()
    while stack:
        i, j = stack[-1]
        nxt = [(i + di, j + dj) for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1))
               if (i + di, j + dj) in cells and (i + di, j + dj) not in seen]
        if not nxt:
            stack.pop()
            continue
        n = rng.choice(nxt)
        seen.add(n)
        edges.add(frozenset(((i, j), n)))
        stack.append(n)
    assert seen == cells, "letter is not one connected piece"
    return edges


def trace(cells, edges):
    """Hamiltonian cycle on the fine grid around the coarse tree."""
    adj = {}

    def link(a, b, on=True):
        for u, v in ((a, b), (b, a)):
            adj.setdefault(u, set())
            (adj[u].add if on else adj[u].discard)(v)

    for i, j in cells:
        x, y = 2 * i, 2 * j
        tl, tr, bl, br = (x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)
        link(tl, tr), link(tr, br), link(br, bl), link(bl, tl)
    for e in edges:
        (i, j), (k, l) = sorted(e)
        x, y = 2 * i, 2 * j
        if k > i:   # right neighbour: open the shared wall, bridge across it
            link((x + 1, y), (x + 1, y + 1), False), link((x + 2, y), (x + 2, y + 1), False)
            link((x + 1, y), (x + 2, y)), link((x + 1, y + 1), (x + 2, y + 1))
        else:       # neighbour below
            link((x, y + 1), (x + 1, y + 1), False), link((x, y + 2), (x + 1, y + 2), False)
            link((x, y + 1), (x, y + 2)), link((x + 1, y + 1), (x + 1, y + 2))

    start = min(adj, key=lambda c: (c[1], -c[0]))  # top of the stem
    order, prev, cur = [start], None, start
    while True:
        a, b = adj[cur]
        prev, cur = cur, (b if a == prev else a) if prev else max(a, b, key=lambda c: c[1])
        if cur == start:
            break
        order.append(cur)
    assert len(order) == 4 * len(cells), "trace missed cells"
    return order


def to_path(order):
    """Grid cycle to an SVG path with quarter-circle corners. Returns (d, length)."""
    pts = [((x + 0.5) * P, (y + 0.5) * P) for x, y in order]
    n, r = len(pts), P / 2
    unit = lambda a, b: ((b[0] - a[0]) / P, (b[1] - a[1]) / P)
    first = ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2)
    ops, pos, length = [], first, 0.0

    def line(to):
        nonlocal pos, length
        dx, dy = to[0] - pos[0], to[1] - pos[1]
        if ops and ops[-1][0] == "l" and (ops[-1][1] * dy - ops[-1][2] * dx) == 0 \
                and ops[-1][1] * dx + ops[-1][2] * dy >= 0:
            ops[-1] = ("l", ops[-1][1] + dx, ops[-1][2] + dy)
        elif dx or dy:
            ops.append(("l", dx, dy))
        length += abs(dx) + abs(dy)
        pos = to

    for k in range(1, n + 1):
        here, din, dout = pts[k % n], unit(pts[k - 1], pts[k % n]), unit(pts[k % n], pts[(k + 1) % n])
        if din == dout:
            line(here)
            continue
        line((here[0] - din[0] * r, here[1] - din[1] * r))
        end = (here[0] + dout[0] * r, here[1] + dout[1] * r)
        sweep = 1 if din[0] * dout[1] - din[1] * dout[0] > 0 else 0
        ops.append(("a", end[0] - pos[0], end[1] - pos[1], sweep))
        length += math.pi * r / 2
        pos = end
    line(first)

    num = lambda v: f"{v:g}"
    d = [f"M{num(first[0])} {num(first[1])}"]
    for op in ops:
        if op[0] == "a":
            d.append(f"a{num(r)} {num(r)} 0 0 {op[3]} {num(op[1])} {num(op[2])}")
        elif op[2] == 0:
            d.append(f"h{num(op[1])}")
        elif op[1] == 0:
            d.append(f"v{num(op[2])}")
        else:
            d.append(f"l{num(op[1])} {num(op[2])}")
    return "".join(d) + "z", length


def svg(paths, width, height, theme):
    ink, ghost = theme["ink"], theme["ghost"]
    css, body, t = [], [], 0.3
    for idx, (d, length) in enumerate(paths):
        dur = length / SPEED
        css.append(f"#l{idx}{{stroke-dasharray:{length:.0f} {length + 20:.0f};"
                   f"stroke-dashoffset:{length + 10:.0f};animation:draw {dur:.2f}s linear {t:.2f}s forwards}}")
        body.append(f'<path d="{d}" opacity="{ghost}"/>')
        body.append(f'<path id="l{idx}" d="{d}"/>')
        t += STAGGER
    pad = STROKE
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-SIDE} {-pad} {width + 2 * SIDE} {height + 2 * pad + BELOW}" '
        f'role="img" aria-labelledby="t">\n<title id="t">ahad</title>\n'
        f"<style>path{{fill:none;stroke:{ink};stroke-width:{STROKE};stroke-linecap:round;stroke-linejoin:round}}\n"
        + "\n".join(css)
        + "\n@keyframes draw{to{stroke-dashoffset:0}}"
        "\n@media (prefers-reduced-motion:reduce){path{animation:none!important;stroke-dashoffset:0!important}}"
        "</style>\n" + "\n".join(body) + "\n</svg>\n"
    )


def main():
    rng = random.Random(SEED)
    shapes, width = letters()
    paths = []
    for parts in shapes:
        cells = rasterize(parts, width)
        paths.append(to_path(trace(cells, grow_maze(cells, rng))))
    out = Path(__file__).parent
    for name, theme in THEMES.items():
        (out / f"ahad-{name}.svg").write_text(svg(paths, width * 2 * P, ASC * 2 * P, theme))
    print(f"{len(paths)} loops, {sum(l for _, l in paths) / SPEED:.1f}s of line")


if __name__ == "__main__":
    main()
