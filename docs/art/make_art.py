"""Generate the 16-bit style pixel-art SVGs used by the README.

Run:  python docs/art/make_art.py      (standard library only)

Everything is drawn on a small grid of "logical pixels" and written as SVG
rectangles, so the images stay sharp at any size. Colors come from the
Sweetie 16 palette by GrafxKid (CC0).
"""

import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))

# Sweetie 16 palette.
INK, PLUM, RED, ORANGE, YELLOW, LIME, GREEN, TEAL = (
    "#1a1c2c", "#5d275d", "#b13e53", "#ef7d57", "#ffcd75", "#a7f070", "#38b764", "#257179")
NAVY, BLUE, SKY, CYAN, WHITE, SILVER, SLATE, DUSK = (
    "#29366f", "#3b5dc9", "#41a6f6", "#73eff7", "#f4f4f4", "#94b0c2", "#566c86", "#333c57")

# ----------------------------------------------------------------------------
# 5x7 pixel font
# ----------------------------------------------------------------------------

_GLYPHS = """
A .###. #...# #...# ##### #...# #...# #...#
B ####. #...# #...# ####. #...# #...# ####.
C .###. #...# #.... #.... #.... #...# .###.
D ####. #...# #...# #...# #...# #...# ####.
E ##### #.... #.... ####. #.... #.... #####
F ##### #.... #.... ####. #.... #.... #....
G .###. #...# #.... #.### #...# #...# .####
H #...# #...# #...# ##### #...# #...# #...#
I .###. ..#.. ..#.. ..#.. ..#.. ..#.. .###.
J ..### ...#. ...#. ...#. #..#. #..#. .##..
K #...# #..#. #.#.. ##... #.#.. #..#. #...#
L #.... #.... #.... #.... #.... #.... #####
M #...# ##.## #.#.# #.#.# #...# #...# #...#
N #...# #...# ##..# #.#.# #..## #...# #...#
O .###. #...# #...# #...# #...# #...# .###.
P ####. #...# #...# ####. #.... #.... #....
Q .###. #...# #...# #...# #.#.# #..#. .##.#
R ####. #...# #...# ####. #.#.. #..#. #...#
S .#### #.... #.... .###. ....# ....# ####.
T ##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#..
U #...# #...# #...# #...# #...# #...# .###.
V #...# #...# #...# #...# #...# .#.#. ..#..
W #...# #...# #...# #.#.# #.#.# #.#.# .#.#.
X #...# #...# .#.#. ..#.. .#.#. #...# #...#
Y #...# #...# .#.#. ..#.. ..#.. ..#.. ..#..
Z ##### ....# ...#. ..#.. .#... #.... #####
0 .###. #...# #..## #.#.# ##..# #...# .###.
1 ..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.
2 .###. #...# ....# ...#. ..#.. .#... #####
3 ####. ....# ....# .###. ....# ....# ####.
4 ...#. ..##. .#.#. #..#. ##### ...#. ...#.
5 ##### #.... ####. ....# ....# #...# .###.
6 .###. #.... #.... ####. #...# #...# .###.
7 ##### ....# ...#. ..#.. .#... .#... .#...
8 .###. #...# #...# .###. #...# #...# .###.
9 .###. #...# #...# .#### ....# ....# .###.
. ..... ..... ..... ..... ..... .##.. .##..
, ..... ..... ..... ..... .##.. ..#.. .#...
: ..... .##.. .##.. ..... .##.. .##.. .....
- ..... ..... ..... ##### ..... ..... .....
_ ..... ..... ..... ..... ..... ..... #####
/ ....# ....# ...#. ..#.. .#... #.... #....
( ...#. ..#.. .#... .#... .#... ..#.. ...#.
) .#... ..#.. ...#. ...#. ...#. ..#.. .#...
> .#... ..#.. ...#. ....# ...#. ..#.. .#...
< ...#. ..#.. .#... #.... .#... ..#.. ...#.
@ .###. #...# #.### #.#.# #.### #.... .####
! ..#.. ..#.. ..#.. ..#.. ..#.. ..... ..#..
? .###. #...# ....# ...#. ..#.. ..... ..#..
= ..... ..... ##### ..... ##### ..... .....
+ ..... ..#.. ..#.. ##### ..#.. ..#.. .....
* ..... ..#.. .###. ##### .###. ..#.. .....
{ ..##. .#... .#... #.... .#... .#... ..##.
} .##.. ...#. ...#. ....# ...#. ...#. .##..
" .#.#. .#.#. ..... ..... ..... ..... .....
' ..#.. ..#.. ..... ..... ..... ..... .....
"""
FONT = {}
for _line in _GLYPHS.strip().splitlines():
    _char, *_rows = _line.split(" ")
    FONT[_char] = _rows
FONT[" "] = ["....."] * 7


class Canvas:
    """A grid of logical pixels that becomes an SVG."""

    def __init__(self, width, height, scale):
        self.width, self.height, self.scale = width, height, scale
        self.pixels = {}
        self.under = []                 # big flat shapes, drawn below the pixels
        self.defs = {}                  # dither patterns by id
        self.extra = []                 # animated groups, added after the pixels

    def fill(self, x, y, w, h, color, dither=None):
        """A flat area (or a 50% checkerboard of two colors) below the pixels."""
        if dither:
            pid = f"d{color[1:]}{dither[1:]}"
            self.defs[pid] = (
                f'<pattern id="{pid}" width="2" height="2" patternUnits="userSpaceOnUse">'
                f'<rect width="2" height="2" fill="{color}"/><rect width="1" height="1" fill="{dither}"/>'
                f'<rect x="1" y="1" width="1" height="1" fill="{dither}"/></pattern>')
            color = f"url(#{pid})"
        self.under.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}"/>')

    def dot(self, x, y, color):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[x, y] = color

    def rect(self, x, y, w, h, color):
        for j in range(y, y + h):
            for i in range(x, x + w):
                self.dot(i, j, color)

    def frame(self, x, y, w, h, color):
        self.rect(x, y, w, 1, color)
        self.rect(x, y + h - 1, w, 1, color)
        self.rect(x, y, 1, h, color)
        self.rect(x + w - 1, y, 1, h, color)

    def text(self, x, y, text, color, size=1, shade=None, outline=None, shadow=None):
        """Draw text; `shade` colors the lower half (two-tone 16-bit letters)."""
        layers = []
        if shadow:
            layers.append((size, size, shadow, None))
        if outline:
            layers += [(dx, dy, outline, None) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
        layers.append((0, 0, color, shade))
        for dx, dy, ink, lower in layers:
            cx = x
            for char in text.upper():
                rows = FONT.get(char, FONT["?"])
                for r, row in enumerate(rows):
                    for c, bit in enumerate(row):
                        if bit == "#":
                            tint = lower if lower and r >= 4 else ink
                            self.rect(cx + c * size + dx, y + r * size + dy, size, size, tint)
                cx += 6 * size

    @staticmethod
    def text_width(text, size=1):
        return len(text) * 6 * size - size

    def sprite(self, x, y, art, colors, size=1):
        for j, row in enumerate(art):
            for i, key in enumerate(row):
                if key in colors:
                    self.rect(x + i * size, y + j * size, size, size, colors[key])

    def svg(self, title):
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
               f'width="{self.width * self.scale}" height="{self.height * self.scale}" '
               f'shape-rendering="crispEdges" role="img" aria-label="{title}">',
               f"<title>{title}</title>"]
        if self.defs:
            out.append("<defs>" + "".join(self.defs.values()) + "</defs>")
        out += self.under
        out.append(_paths(self.pixels))
        out += self.extra
        out.append("</svg>")
        return "\n".join(out) + "\n"

    def save(self, name, title):
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
            f.write(self.svg(title))


def blink(content, period="1.2s"):
    """Wrap SVG elements so they blink (SMIL works in GitHub's <img>)."""
    return (f'<g>{content}<animate attributeName="opacity" values="1;1;0;0" '
            f'keyTimes="0;0.5;0.5;1" dur="{period}" repeatCount="indefinite"/></g>')


def _paths(pixels):
    """Pixels -> one <path> per color, merging horizontal runs (small files)."""
    runs = {}
    for (x, y) in sorted(pixels, key=lambda p: (p[1], p[0])):
        color = pixels[x, y]
        row = runs.setdefault(color, [])
        if row and row[-1][1] == y and row[-1][0] + row[-1][2] == x:
            row[-1][2] += 1
        else:
            row.append([x, y, 1])
    return "".join(f'<path fill="{color}" d="' + "".join(f"M{x} {y}h{w}v1h-{w}z" for x, y, w in row) + '"/>'
                   for color, row in runs.items())


def rects(canvas_draw):
    """Draw on a scratch canvas and return its pixels as SVG paths."""
    scratch = Canvas(1000, 1000, 1)
    canvas_draw(scratch)
    return _paths(scratch.pixels)


# ----------------------------------------------------------------------------
# Sprites
# ----------------------------------------------------------------------------

SNAKE = [
    "..........KKKKK.....",
    ".........KLLGGGK....",
    "........KLGWKGGGK...",
    "........KGGGGGGGGKRR",
    "........KGGGGGGGK..R",
    ".........KKGGGKK....",
    "...........KYGK.....",
    "..KKKKK...KGYGK.....",
    ".KGLLGGK.KGYGK......",
    "KGLKKKGGKGYGGK......",
    "KGK..KGGGYGGK.......",
    "KGK...KGGGGK........",
    "KGGK...KKKK.........",
    ".KGGKKKKKKKKKK......",
    "..KGGGGYYYYGGGK.....",
    "...KKKKKKKKKKK......",
]
SNAKE_COLORS = {"K": INK, "G": GREEN, "L": LIME, "Y": YELLOW, "W": WHITE, "R": RED}


def draw_monitor(c, x, y, w=30, h=24, lines=(), cursor=True):
    """A beige 90s CRT. Returns the screen origin for extra drawing."""
    c.rect(x, y, w, h, INK)
    c.rect(x + 1, y + 1, w - 2, h - 2, SILVER)
    c.rect(x + 1, y + 1, w - 2, 1, WHITE)               # highlight
    c.rect(x + 1, y + h - 2, w - 2, 1, SLATE)           # shade
    c.rect(x + 3, y + 3, w - 6, h - 8, INK)             # screen
    c.rect(x + 4, y + 4, w - 8, h - 10, "#10141f")
    c.rect(x + w - 6, y + h - 4, 2, 1, LIME)            # power led
    c.rect(x + w // 2 - 4, y + h, 8, 2, SLATE)          # neck
    c.rect(x + w // 2 - 8, y + h + 2, 16, 2, SILVER)    # foot
    c.rect(x + w // 2 - 8, y + h + 3, 16, 1, SLATE)
    for i, line in enumerate(lines):
        c.text(x + 6, y + 6 + i * 8, line, LIME)
    return x + 6, y + 6


def draw_window(c, x, y, w, h):
    """An RPG menu window: blue fading to navy, white double border."""
    half = h // 2
    c.fill(x, y, w, half - 1, BLUE)
    c.fill(x, y + half - 1, w, 2, BLUE, dither=NAVY)
    c.fill(x, y + half + 1, w, h - half - 1, NAVY)
    c.frame(x - 2, y - 2, w + 4, h + 4, INK)
    c.frame(x - 1, y - 1, w + 2, h + 2, WHITE)
    c.frame(x, y, w, h, SILVER)


HAND = [
    ".KK.......",
    "KWWK......",
    "KWWKKKKK..",
    "KWWWWWWWK.",
    "KWWWWWWWWK",
    "KWWWWWWWK.",
    "KWWWWWWK..",
    ".KKKKKK...",
]


def sky(c, top, bottom, seed):
    """Night sky: flat bands joined by checkerboard dithering, plus stars."""
    bands = [INK, NAVY, BLUE, PLUM]
    step = (bottom - top) / len(bands)
    for i, color in enumerate(bands):
        y0, y1 = top + round(i * step), top + round((i + 1) * step)
        c.fill(0, y0, c.width, y1 - y0, color)
        if i + 1 < len(bands):
            c.fill(0, y1 - 2, c.width, 4, color, dither=bands[i + 1])
    rnd = random.Random(seed)
    for _ in range(c.width // 6):
        x, y = rnd.randrange(c.width), rnd.randrange(top, top + (bottom - top) // 2)
        c.fill(x, y, 1, 1, rnd.choice([WHITE, SILVER, CYAN]))


# ----------------------------------------------------------------------------
# Images
# ----------------------------------------------------------------------------

def banner():
    c = Canvas(320, 100, 3)
    sky(c, 0, 84, seed=16)
    c.defs["brick"] = (                                  # brick floor, as a tile
        f'<pattern id="brick" width="8" height="12" patternUnits="userSpaceOnUse">'
        f'<rect width="8" height="12" fill="{DUSK}"/>'
        f'<rect width="7" height="5" fill="{SLATE}"/><rect width="7" height="1" fill="{SILVER}"/>'
        f'<rect x="4" y="6" width="7" height="5" fill="{SLATE}"/><rect x="4" y="6" width="7" height="1" fill="{SILVER}"/>'
        f'<rect x="-4" y="6" width="7" height="5" fill="{SLATE}"/><rect x="-4" y="6" width="7" height="1" fill="{SILVER}"/>'
        f'</pattern>')
    c.under.append('<rect x="0" y="84" width="320" height="16" fill="url(#brick)"/>')

    title = "MCP MINIMAL"
    c.text((320 - c.text_width(title, 3)) // 2, 9, title, YELLOW, size=3, shade=ORANGE, outline=INK, shadow=RED)
    sub = "ONE FILE * ZERO DEPENDENCIES * PURE PYTHON"
    c.text((320 - c.text_width(sub)) // 2, 39, sub, CYAN, outline=INK)

    c.sprite(6, 52, SNAKE, SNAKE_COLORS, size=2)          # the snake...
    draw_monitor(c, 270, 52, w=38, h=26, lines=[">"])    # ...talks to the computer

    # Cable between them, with JSON packets travelling on it.
    c.rect(36, 80, 236, 1, INK)
    c.rect(36, 81, 236, 1, SLATE)
    packet = rects(lambda s: (s.rect(0, 0, 5, 4, INK), s.rect(1, 1, 3, 2, YELLOW)))
    for delay in (0, 1, 2):
        c.extra.append(
            f'<g transform="translate(40 78)"><g>{packet}'
            f'<animateTransform attributeName="transform" type="translate" from="0 0" to="224 0" '
            f'dur="3s" begin="{delay}s" repeatCount="indefinite"/></g></g>')
    cursor = rects(lambda s: s.rect(282, 64, 4, 1, LIME))
    c.extra.append(blink(cursor, "1s"))

    press = "PRESS START: COPY ONE FILE"
    press_px = rects(lambda s: s.text((320 - s.text_width(press)) // 2, 60, press, WHITE, outline=INK))
    c.extra.append(blink(press_px, "1.6s"))
    c.save("banner.svg", "MCP MINIMAL: one file, zero dependencies, pure Python")


def how_it_works():
    c = Canvas(320, 150, 3)
    sky(c, 0, 150, seed=90)
    c.text((320 - c.text_width("HOW IT WORKS", 2)) // 2, 8, "HOW IT WORKS", YELLOW,
           size=2, shade=ORANGE, outline=INK)

    # Left: the client.
    draw_window(c, 10, 34, 96, 84)
    c.text(16, 40, "CLAUDE", WHITE)
    c.text(16, 49, "DESKTOP / CODE", CYAN)
    draw_monitor(c, 41, 62, w=34, h=26, lines=[">_"])

    # Right: your script.
    draw_window(c, 214, 34, 96, 84)
    c.text(220, 40, "YOUR SERVER.PY", WHITE)
    c.text(220, 52, "@SERVER.TOOL()", LIME)
    c.text(220, 61, "DEF ADD(A, B):", CYAN)
    c.text(220, 70, "  RETURN A+B", CYAN)
    c.sprite(242, 80, SNAKE, SNAKE_COLORS, size=2)

    # Middle: the pipes.
    def pipe(y, color):
        c.rect(110, y, 100, 4, INK)
        c.rect(110, y + 1, 100, 2, color)

    pipe(60, SLATE)
    for i in range(4):                                   # arrow head right
        c.rect(206 + i, 58 + i, 1, 8 - 2 * i, INK)
    c.text(128, 50, "STDIN", WHITE, outline=INK)
    c.text(118, 68, "REQUESTS", SILVER)

    pipe(92, SLATE)
    for i in range(4):                                   # arrow head left
        c.rect(113 - i, 90 + i, 1, 8 - 2 * i, INK)
    c.text(128, 82, "STDOUT", WHITE, outline=INK)
    c.text(118, 100, "RESULTS +", SILVER)
    c.text(118, 109, "PROGRESS", SILVER)

    # Down from the server: stderr.
    c.rect(258, 120, 4, 12, INK)
    c.rect(259, 120, 2, 12, RED)
    c.text(222, 136, "STDERR = LOGS", ORANGE, outline=INK)
    c.text(10, 126, "ONE JSON MESSAGE", CYAN, outline=INK)
    c.text(10, 136, "PER LINE", CYAN, outline=INK)

    def packet(color):
        return rects(lambda s: (s.rect(0, 0, 9, 6, INK), s.rect(1, 1, 7, 4, color)))
    for delay in (0, 1.2):
        c.extra.append(
            f'<g transform="translate(112 59)"><g>{packet(YELLOW)}'
            f'<animateTransform attributeName="transform" type="translate" from="0 0" to="88 0" '
            f'dur="2.4s" begin="{delay}s" repeatCount="indefinite"/></g></g>')
        c.extra.append(
            f'<g transform="translate(200 91)"><g>{packet(LIME)}'
            f'<animateTransform attributeName="transform" type="translate" from="0 0" to="-88 0" '
            f'dur="2.4s" begin="{delay + 0.6}s" repeatCount="indefinite"/></g></g>')
    c.save("how-it-works.svg", "How it works: Claude talks to your script over stdin and stdout")


def quest_log():
    c = Canvas(320, 168, 3)
    sky(c, 0, 168, seed=42)
    title = "LIFE OF A TOOL CALL"
    c.text((320 - c.text_width(title, 2)) // 2, 8, title, YELLOW, size=2, shade=ORANGE, outline=INK)
    draw_window(c, 12, 34, 296, 124)
    steps = [
        ("1", "SERVER/DISCOVER OR INITIALIZE", "WHO ARE YOU? WHICH VERSION?"),
        ("2", "TOOLS/LIST", "WHAT CAN YOU DO?"),
        ("3", "TOOLS/CALL  ADD {A:2, B:3}", "PLEASE RUN THIS TOOL."),
        ("4", "NOTIFICATIONS/PROGRESS", "1 OF 3... 2 OF 3..."),
        ("5", "RESULT  {TEXT: \"5\"}", "DONE! (OR ISERROR: TRUE)"),
        ("X", "NOTIFICATIONS/CANCELLED", "STOP! NO ANSWER IS SENT."),
    ]
    for i, (num, method, line) in enumerate(steps):
        y = 42 + i * 19
        color = ORANGE if num == "X" else YELLOW
        c.text(34, y, num, color)
        arrow = "<" if num in "45" else ">"
        c.text(44, y, arrow + " " + method, WHITE)
        c.text(56, y + 9, line, CYAN)
    hand = rects(lambda s: s.sprite(18, 0, HAND, {"K": INK, "W": WHITE}))
    c.extra.append(
        f'<g transform="translate(0 41)"><g>{hand}'
        f'<animateTransform attributeName="transform" type="translate" '
        f'values="0 0;0 0;0 19;0 19;0 38;0 38;0 57;0 57;0 76;0 76;0 95;0 95" '
        f'keyTimes="0;0.16;0.17;0.33;0.34;0.5;0.51;0.66;0.67;0.83;0.84;1" '
        f'dur="9s" repeatCount="indefinite"/></g></g>')
    c.save("tool-call.svg", "Life of a tool call: discover or initialize, list, call, progress, result")


if __name__ == "__main__":
    banner()
    how_it_works()
    quest_log()
    print("wrote", ", ".join(sorted(f for f in os.listdir(HERE) if f.endswith(".svg"))))
