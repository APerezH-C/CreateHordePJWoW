"""Screen recognition for the WoW Forever relaunch loop.

Every check compares a small region of the live capture with the same region
of a reference screenshot stored in ``refs/`` (1920 x 1080 game captures).
Only text-like pixels are compared, so animated 3D backgrounds do not matter.

UI scale: every box and point below is measured at the default UI scale
(scale 1.0). WoW draws its glue screens larger or smaller with the game's UI
scale setting; each element then moves away from (or towards) its anchor (a
screen corner, the top/bottom center or the center): position = anchor +
scale * (position at scale 1.0 - anchor). `classify` finds the scale of a
capture (cached between frames) and the click points follow it.
"""

from pathlib import Path
import sys

from PIL import Image, ImageChops, ImageFilter


def resource_dir():
    """Folder of the bundled read-only files (``refs/``): the folder the
    PyInstaller exe unpacks to (sys._MEIPASS), else this file's folder."""
    bundle = getattr(sys, '_MEIPASS', None)
    if getattr(sys, 'frozen', False) and bundle:
        return Path(bundle)
    return Path(__file__).parent


REFS = resource_dir() / 'refs'
SIZE = (1920, 1080)

# Anchors (1920 x 1080 game coordinates) that elements keep at any UI scale.
TOP_LEFT, TOP, TOP_RIGHT, CENTER = (0, 0), (960, 0), (1920, 0), (960, 540)
BOTTOM, BOTTOM_RIGHT = (960, 1080), (1920, 1080)

# name: (reference file, box, mask kind)
TEMPLATES = {
    'charselect': ('charselect.png', (1000, 18, 1196, 44), 'light'),
    'create_button': ('charselect.png', (1570, 958, 1752, 984), 'light'),
    # "JcJ" header above the character list (absent on the Normal list).
    'pvp_list': ('charselect_connecting.png', (1700, 118, 1732, 142), 'light'),
    'ruleset': ('ruleset.png', (790, 180, 1130, 214), 'light'),
    # "Normal" card title: the dialog title leaves the screen above ~1.5x.
    'ruleset_cards': ('ruleset.png', (498, 370, 572, 396), 'light'),
    'race': ('race_troll_rogue.png', (1660, 1004, 1840, 1032), 'light'),
    'horde': ('race_troll_rogue.png', (226, 84, 320, 110), 'light'),
    'customize': ('customize_empty.png', (870, 12, 1045, 35), 'light'),
    'error': ('error.png', (725, 484, 1200, 555), 'yellow'),
}
TEMPLATE_ANCHORS = {
    'charselect': TOP, 'create_button': BOTTOM_RIGHT, 'pvp_list': TOP_RIGHT,
    'ruleset': CENTER, 'ruleset_cards': CENTER, 'race': BOTTOM_RIGHT, 'horde': TOP_LEFT,
    'customize': TOP, 'error': CENTER,
}

# Points to click, in 1920 x 1080 game coordinates.
POINTS = {
    'ruleset': (1098, 31),
    'pvp': (818, 570),
    # Right part of Seleccionar: above ~1.5x the JcJ-rol card's click area
    # covers the middle of the button (measured live at 1.62x).
    'select': (1866, 1046),
    # Left part of Crear personaje, away from the race screen's "Modelos de
    # alta definicion" checkbox that opens under the same spot.
    'create': (1630, 971),
    'troll': (274, 444),
    'rogue': (864, 996),
    'customize': (1746, 1016),
    # "Cuerpo 1" (male body), left of the two body icons at the top.
    'male': (922, 48),
    # Tabs of the customization panel (round icons above the options).
    'tab1': (1652, 208),
    'tab2': (1738, 208),
    'name_first': (789, 54),
    'name_second': (1131, 54),
    'finish': (1745, 1018),
    'accept': (960, 583),
}
# Anchor of each point; troll and rogue have their own layouts (see place()).
# Points without an anchor (customization panel) are used at scale 1.0 only.
POINT_ANCHORS = {
    'ruleset': TOP, 'pvp': CENTER, 'select': BOTTOM_RIGHT, 'create': BOTTOM_RIGHT,
    'customize': BOTTOM_RIGHT, 'male': TOP, 'name_first': TOP, 'name_second': TOP,
    'finish': BOTTOM_RIGHT, 'accept': CENTER,
}

# Red enabled-button areas.
BUTTONS = {
    'finish': (1640, 1000, 1850, 1035),
    'select': (1680, 1015, 1900, 1058),
    'create': (1566, 954, 1756, 988),
    # Red button of a centered popup over the customize screen.
    'dialog': (870, 574, 1050, 596),
}
BUTTON_ANCHORS = {'finish': BOTTOM_RIGHT, 'select': BOTTOM_RIGHT, 'create': BOTTOM_RIGHT,
                  'dialog': CENTER}

PVP_BORDER = (704, 420, 716, 700)   # centered dialog

# Icon frames on the race/class screen: (outer box, inner box). A selected
# icon gets a bright gold frame; the ring between both boxes covers it.
# Measured light-pixel ratio on refs/: selected 0.38 (troll) / 0.43 (rogue),
# unselected <= 0.014 on race screens.
FRAMES = {
    'troll': ((228, 399, 322, 493), (240, 411, 310, 481)),
    'rogue': ((822, 954, 906, 1038), (834, 966, 894, 1026)),
    # Body icons: selected 0.42, unselected <= 0.04 on every reference.
    'male': ((889, 14, 957, 80), (898, 23, 948, 71)),
}

# Race/class screen layouts measured live at UI scales 0.90-1.62 (T10):
# - Race banners: x follows the scale from the top-left corner; above
#   TROLL_CAP the icon column is squeezed so the troll icon stays at the
#   height it has at TROLL_CAP (measured 675 px at 1.62x, 444 * 1.52).
# - Class bar (bottom center): one row of 9 icons, all scaled from the
#   bottom center, until the bar gets too wide (between 1.27x and 1.34x); then
#   it wraps into 5 + 4 icons with an 86 px pitch and the rogue (4th icon,
#   first row) is centered at (960 + 86 s, 1080 - 203.2 s). The wrapped bar is
#   recognized by its top border line at 1080 - 251 s (classes_wrapped()).
TROLL_CAP = 1.51
ROGUE_CENTER = (864, 996)
WRAPPED_ROGUE = (86, 203.2)
WRAPPED_TOP = 251
# Scales tried when the cached scale does not fit (0.60 - 1.70).
SCALES = tuple(round(0.6 + 0.01 * step, 2) for step in range(111))

# Customization options: name -> (tab, selector y, number x of each list
# column, rows per column). Clicking the middle of a selector (x = 1740)
# opens its numbered list just below it; clicking the selector again closes
# it. Lists have a pure black background, item n of column c sits at
# (column x, selector y + 44 + 31 * row). Measured live (male troll):
# skin 6, face 5, hairstyle 13 (7 + 6), hair color 10, eye color 10 (5 + 5),
# tusks 5, face paint 7, paint color 10 items.
OPTIONS = {
    'skin': (1, 334, (1651,), 12),          # Color de piel
    'face': (1, 420, (1651,), 12),          # Rostro
    'hairstyle': (1, 506, (1474, 1664), 7),  # Peinado
    'hair_color': (1, 592, (1651,), 12),    # Color de pelo
    'eye_color': (1, 678, (1564, 1709), 5),  # Color de ojos
    'tusks': (2, 334, (1651,), 12),         # Colmillos
    'face_paint': (2, 420, (1651,), 12),    # Pintura facial
    'paint_color': (2, 506, (1651,), 12),   # Color de pintura facial
}
LABELS = {
    'skin': 'Color de piel', 'face': 'Rostro', 'hairstyle': 'Peinado',
    'hair_color': 'Color de pelo', 'eye_color': 'Color de ojos', 'tusks': 'Colmillos',
    'face_paint': 'Pintura facial', 'paint_color': 'Color de pintura facial',
}
SELECTOR_X = 1740
LIST_FIRST = 44     # first item below the selector center
LIST_PITCH = 31
POINTS.update({name: (SELECTOR_X, y) for name, (_, y, _, _) in OPTIONS.items()})
# Active tab icon has a yellow glow: measured 0.25-0.31, inactive 0.00.
TAB_GLOW = {1: (1620, 176, 1684, 240), 2: (1706, 176, 1770, 240)}

# Centered popups (loading, errors) have a long, thin bronze border line at
# the top and bottom. Rows are sampled across the middle of the screen.
# Measured share of bronze samples: popup border rows 1.0, any other row
# of any reference <= 0.34 (the character model's red clothes give 0.02).
POPUP_AREA = (760, 300, 1160, 780)
POPUP_SAMPLES = 50

# Name input boxes. The placeholder text is very dim; typed names are white.
NAME_BOXES = ((630, 42, 950, 68), (976, 42, 1296, 68))

_cache = {}


class Layout:
    """UI scale of the current WoW session and the class bar layout."""

    def __init__(self, scale=1.0, wrapped=False):
        self.scale, self.wrapped = scale, wrapped


_layout = Layout()


def scale():
    """UI scale of the last recognized screen (1.0 = calibration scale)."""
    return _layout.scale


def set_scale(value, wrapped=None):
    _layout.scale = value
    if wrapped is not None:
        _layout.wrapped = wrapped


def _at(point, anchor, s):
    return (anchor[0] + s * (point[0] - anchor[0]), anchor[1] + s * (point[1] - anchor[1]))


def _icon(icon, point, s, wrapped):
    """Position of a point on the troll or rogue icon at scale `s`."""
    if icon == 'troll':
        return point[0] * s, point[1] * min(s, TROLL_CAP)
    if wrapped:
        center = (960 + WRAPPED_ROGUE[0] * s, 1080 - WRAPPED_ROGUE[1] * s)
        return (center[0] + s * (point[0] - ROGUE_CENTER[0]),
                center[1] + s * (point[1] - ROGUE_CENTER[1]))
    return _at(point, BOTTOM, s)


def place(point, anchor, s=None, icon=None, wrapped=None):
    """Point at scale `s` (default: the current scale), rounded to pixels.
    At scale 1.0 every point is returned unchanged."""
    s = _layout.scale if s is None else s
    wrapped = _layout.wrapped if wrapped is None else wrapped
    if s == 1 and not (icon == 'rogue' and wrapped):
        return tuple(point)
    if icon in ('troll', 'rogue'):
        x, y = _icon(icon, point, s, wrapped)
    elif anchor is None:
        return tuple(point)
    else:
        x, y = _at(point, anchor, s)
    return round(x), round(y)


def place_box(box, anchor, s=None, icon=None, wrapped=None):
    """Box at scale `s`; icon boxes keep their size around the moved center."""
    s = _layout.scale if s is None else s
    if icon in ('troll', 'rogue'):
        center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        x, y = place(center, None, s, icon, wrapped)
        if (x, y) == center and s == 1:
            return tuple(box)
        half_w, half_h = s * (box[2] - box[0]) / 2, s * (box[3] - box[1]) / 2
        return (round(x - half_w), round(y - half_h), round(x + half_w), round(y + half_h))
    return place(box[:2], anchor, s) + place(box[2:], anchor, s)


def point(name, s=None):
    """Click point `name` at the current (or given) scale."""
    icon = name if name in ('troll', 'rogue') else None
    return place(POINTS[name], POINT_ANCHORS.get(name), s, icon)


def frame_box(icon, s=None):
    """Outer box of a race/class/body icon frame at the current scale."""
    outer = FRAMES[icon][0]
    if icon in ('troll', 'rogue'):
        return place_box(outer, None, s, icon)
    return place_box(outer, TOP, s)


def button_box(button, s=None):
    return place_box(BUTTONS[button], BUTTON_ANCHORS[button], s)


def pvp_box(s=None):
    """Area holding the JcJ card border and Seleccionar (for region grabs)."""
    border, select = place_box(PVP_BORDER, CENTER, s), button_box('select', s)
    return (min(border[0], select[0]), min(border[1], select[1]),
            max(border[2], select[2]), max(border[3], select[3]))


def region(image, box, anchor, s=None, icon=None, resample=Image.BILINEAR):
    """The capture's area of `box` at scale `s`, resized to the box's size at
    scale 1.0, so every check below uses its scale 1.0 sizes and limits."""
    s = _layout.scale if s is None else s
    area = image.crop(place_box(box, anchor, s, icon))
    size = (box[2] - box[0], box[3] - box[1])
    return area if area.size == size else area.resize(size, resample)


_LUTS = {}


def _threshold(channel, limit, above=True):
    key = (limit, above)
    if key not in _LUTS:
        _LUTS[key] = [255 if (value > limit if above else value < limit) else 0
                      for value in range(256)]
    return channel.point(_LUTS[key])


def _mask_of(area, kind):
    """255 where a pixel is text-like: light (r > 170, g > 150) or yellow."""
    red, green, blue = area.convert('RGB').split()
    if kind == 'yellow':
        mask = ImageChops.multiply(_threshold(red, 160), _threshold(green, 140))
        return ImageChops.multiply(mask, _threshold(blue, 110, above=False))
    return ImageChops.multiply(_threshold(red, 170), _threshold(green, 150))


def _mask(image, box, kind):
    return [value == 255 for value in _mask_of(image.crop(box), kind).get_flattened_data()]


# Captures under 900 px high (below the supported size, e.g. a shrunken
# screenshot) have thin, dimmed text strokes: brighten them before checking.
SMALL_HEIGHT = 900
SMALL_GAIN = 1.3


def normalize(image):
    image = image.convert('RGB')
    if image.height < SMALL_HEIGHT:
        image = image.point([min(255, round(value * SMALL_GAIN)) for value in range(256)] * 3)
    if image.size == SIZE:
        return image
    if all(abs(a - b) <= 2 for a, b in zip(image.size, SIZE)):
        canvas = Image.new('RGB', SIZE)
        canvas.paste(image, (0, 0))
        return canvas
    return image.resize(SIZE)


def reference(name):
    if name not in _cache:
        with Image.open(REFS / name) as source:
            _cache[name] = normalize(source)
    return _cache[name]


def _mask_image(image, box, kind, anchor=None, s=1, masks=None):
    """Text mask of `box`. At another scale the mask is made at the capture's
    resolution and then resized to the box (text stays sharp). `masks`: the
    whole capture's masks by kind, made once for many lookups."""
    if s == 1 or anchor is None:
        if masks:
            return masks[kind].crop(box)
        return _mask_of(image.crop(box), kind)
    scaled = place_box(box, anchor, s)
    mask = masks[kind].crop(scaled) if masks else _mask_of(image.crop(scaled), kind)
    size = (box[2] - box[0], box[3] - box[1])
    if mask.size != size:
        mask = _threshold(mask.resize(size, Image.BILINEAR), 95)
    return mask


def _count(mask):
    return mask.histogram()[255]


def score(image, template, s=None, masks=None):
    """Share of text pixels that match the reference within 1 pixel.

    The 1 pixel tolerance keeps captures from other resolutions, resized to
    1920 x 1080, recognizable (thin text moves or blurs by a pixel). At another
    UI scale the template's area is read where the scale puts it."""
    s = _layout.scale if s is None else s
    ref_name, box, kind = TEMPLATES[template]
    # At another UI scale the text may differ by one more pixel: 2 px tolerance.
    near = 3 if s == 1 else 5
    key = ('mask', template, near)
    if key not in _cache:
        expected = _mask_image(reference(ref_name), box, kind)
        _cache[key] = expected, expected.filter(ImageFilter.MaxFilter(near)), _count(expected)
    expected, expected_near, expected_count = _cache[key]
    actual = _mask_image(image, box, kind, TEMPLATE_ANCHORS[template], s, masks)
    if masks is not None and not expected_count / 3 <= _count(actual) <= expected_count * 3:
        return 0.0   # scale search shortcut: far too few or too many text pixels
    total = _count(expected) + _count(actual)
    if total < 30:
        return 0.0
    actual_near = actual.filter(ImageFilter.MaxFilter(near))
    hits = (_count(ImageChops.multiply(expected, actual_near))
            + _count(ImageChops.multiply(actual, expected_near)))
    return hits / total


# Text is drawn with whole-pixel font sizes, so at another UI scale a text
# can be a little wider or narrower than the scale says: also try nearby scales.
NEARBY = (0, -0.01, 0.01, -0.02, 0.02)


def has(image, template, threshold=0.7, s=None):
    s = _layout.scale if s is None else s
    if s == 1:
        return score(image, template, 1) >= threshold
    return any(score(image, template, round(s + step, 3)) >= threshold for step in NEARBY)


def red_ratio(image, box, anchor=None, s=1):
    area = region(image, box, anchor, s) if anchor else image.crop(box)
    red = sum(r > 60 and r > g * 2 and r > b * 2 for r, g, b in area.get_flattened_data())
    return red / (area.width * area.height)


def enabled(image, button):
    return red_ratio(image, BUTTONS[button], BUTTON_ANCHORS[button], _layout.scale) > 0.35


def pvp_selected(image):
    area = region(image, PVP_BORDER, CENTER)
    gold = sum(r > 150 and g > 120 and b < 90 for r, g, b in area.get_flattened_data())
    return gold / (area.width * area.height) > 0.25


def selected(image, icon):
    """True when the race/class icon has the bright selection frame."""
    outer, inner = FRAMES[icon]
    area = region(image, outer, TOP, icon=icon if icon != 'male' else None)
    inner = tuple(v - outer[i % 2] for i, v in enumerate(inner))
    light = sum(_mask(area, (0, 0) + area.size, 'light')) - sum(_mask(area, inner, 'light'))
    size = ((outer[2] - outer[0]) * (outer[3] - outer[1])
            - (inner[2] - inner[0]) * (inner[3] - inner[1]))
    return light / size > 0.15


def _frame_grey(pixel):
    r, g, b = pixel
    return 90 <= r <= 170 and 0.7 * r <= g <= 0.92 * r and 0.4 * r <= b <= 0.68 * r


def classes_wrapped(image, s=None):
    """True when the class bar is wrapped into two rows (large UI scales):
    its top border is a long grey-bronze line at 1080 - 251 s."""
    s = _layout.scale if s is None else s
    if s <= 1.1:
        return False
    y = round(1080 - WRAPPED_TOP * s)
    left, right = round(960 - 200 * s), round(960 + 200 * s)
    area = image.crop((left, y - 8, right, y + 9)).resize((40, 17), Image.NEAREST)
    pixels = list(area.get_flattened_data())
    return any(sum(map(_frame_grey, pixels[row * 40:(row + 1) * 40])) >= 32
               for row in range(17))


def _bronze(pixel):
    r, g, b = pixel
    return 90 <= r <= 200 and 0.55 * r <= g <= 0.75 * r and 0.25 * r <= b <= 0.5 * r


def popup_open(image):
    """True when a centered popup frame (top and bottom border) is shown."""
    left, top, right, bottom = POPUP_AREA
    height = bottom - top
    # Nearest sampling keeps whole rows apart while reading few pixels.
    area = image.crop(place_box(POPUP_AREA, CENTER))
    pixels = list(area.resize((POPUP_SAMPLES, height), Image.NEAREST).get_flattened_data())
    lines = [top + y for y in range(height)
             if sum(map(_bronze, pixels[y * POPUP_SAMPLES:(y + 1) * POPUP_SAMPLES]))
             >= POPUP_SAMPLES * 0.8]
    return bool(lines) and lines[-1] - lines[0] >= 30


def _yellow(pixel):
    r, g, b = pixel
    return r > 170 and g > 130 and b < 90


def _black(pixel):
    # Lists are exactly black; their drop shadow and the panel are not.
    return max(pixel) <= 2


def active_tab(image):
    """Return the open customization tab (1 or 2) or None."""
    for tab, box in TAB_GLOW.items():
        area = image.crop(box)
        if sum(map(_yellow, area.get_flattened_data())) > area.width * area.height * 0.12:
            return tab
    return None


def open_list(image, tab):
    """Return the option whose numbered list is open on this tab, or None."""
    for name, (option_tab, y, _, _) in OPTIONS.items():
        if option_tab != tab:
            continue
        # Strip between the list's top border and its first item. A list
        # also covers the strips of the options below it: topmost wins.
        area = image.crop((1700, y + 25, 1820, y + 32))
        if sum(map(_black, area.get_flattened_data())) >= area.width * area.height * 0.9:
            return name
    return None


def item_center(option, number):
    """Center of the number label of a list item, or None outside the layout."""
    _, y, columns, rows = OPTIONS[option]
    column, row = divmod(number - 1, rows)
    if number < 1 or column >= len(columns):
        return None
    return columns[column], y + LIST_FIRST + LIST_PITCH * row


def list_box(option):
    """Screen area covering an option's open list (for fast region grabs)."""
    _, y, columns, rows = OPTIONS[option]
    return (min(columns) - 20, y + 20, 1830, y + LIST_FIRST + LIST_PITCH * rows + 10)


def item_point(option, number):
    """Point to click to choose a list item (on its row, right of the number)."""
    x, y = item_center(option, number)
    return x + 40, y


def item_label(image, option, number):
    """None if the item's number is not shown, else 'selected' or 'item'."""
    center = item_center(option, number)
    if center is None:
        return None
    x, y = center
    left, top, right, bottom = x - 6, y - 9, x + 26, y + 10
    edges = (list(image.crop((left, top, right, top + 2)).get_flattened_data())
             + list(image.crop((left, bottom - 2, right, bottom)).get_flattened_data()))
    if sum(map(_black, edges)) < len(edges) * 0.9:
        return None  # outside the black list
    pixels = image.crop((left, top, right, bottom)).get_flattened_data()
    yellow = sum(map(_yellow, pixels))
    gray = sum(abs(r - g) < 14 and abs(g - b) < 14 and r > 70 for r, g, b in pixels)
    if yellow + gray < 10:
        return None
    # The current value has a yellow number, the others are gray.
    return 'selected' if yellow >= 10 else 'item'


def list_details(image):
    """Tab, open list, number of visible items and the selected item (0 = none).
    The customization panel is calibrated at UI scale 1.0 only."""
    if _layout.scale != 1:
        return {'tab': None, 'list': None, 'items': 0, 'selected': 0}
    tab = active_tab(image)
    option = open_list(image, tab) if tab else None
    items = selected = 0
    if option:
        while True:
            label = item_label(image, option, items + 1)
            if label is None:
                break
            items += 1
            if label == 'selected':
                selected = items
    return {'tab': tab, 'list': option, 'items': items, 'selected': selected}


def names_filled(image):
    """Return (first name typed, second name typed).

    A name is more than 40 white pixels spread over at least 8 columns: the
    blinking text cursor alone is a 1-2 column line (up to ~45 pixels when
    the UI is scaled up)."""
    filled = []
    for box in NAME_BOXES:
        area = region(image, box, TOP)
        white = [index for index, p in enumerate(area.get_flattened_data()) if min(p) > 180]
        columns = {index % area.width for index in white}
        filled.append(len(white) > 40 and len(columns) >= 8)
    return tuple(filled)


# Battle.net "Jugar": the big blue button at the bottom left of the
# Battle.net window. Measured on refs/battlenet.png (window (205, 22)-(1805,
# 1022), 1600 x 1000): button (245, 886)-(516, 941), color (0, 116, 224); the
# other blue areas are small or in the right half. Fractions of the window.
PLAY_AREA = (0.0, 0.55, 0.45, 1.0)
PLAY_CELLS = 180      # search grid columns across PLAY_AREA (4 px at 1600 px)


def _play_blue(pixel):
    r, g, b = pixel[:3]
    return b > 150 and b > r + 60 and b > g + 40


def find_play_button(image):
    """Point to click on Battle.net's blue "Jugar" button, in coordinates of
    `image` (a capture of the Battle.net window at any size), or None."""
    image = image.convert('RGB')
    width, height = image.size
    area = (round(width * PLAY_AREA[0]), round(height * PLAY_AREA[1]),
            round(width * PLAY_AREA[2]), round(height * PLAY_AREA[3]))
    if area[2] - area[0] < 10 or area[3] - area[1] < 10:
        return None
    cell = (area[2] - area[0]) / PLAY_CELLS
    rows = max(1, round((area[3] - area[1]) / cell))
    grid = image.crop(area).resize((PLAY_CELLS, rows), Image.NEAREST)
    blue = [_play_blue(p) for p in grid.get_flattened_data()]
    seen, best = set(), None
    for start, on in enumerate(blue):
        if not on or start in seen:
            continue
        seen.add(start)
        stack, cells = [start], []
        while stack:
            index = stack.pop()
            cells.append(index)
            x, y = index % PLAY_CELLS, index // PLAY_CELLS
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                near = ny * PLAY_CELLS + nx
                if 0 <= nx < PLAY_CELLS and 0 <= ny < rows and blue[near] and near not in seen:
                    seen.add(near)
                    stack.append(near)
        xs = [index % PLAY_CELLS for index in cells]
        ys = [index // PLAY_CELLS for index in cells]
        left, top, right, bottom = min(xs), min(ys), max(xs) + 1, max(ys) + 1
        box_w, box_h = (right - left) * cell, (bottom - top) * cell
        # A wide, filled button: Jugar is 0.17 x 0.055 of the window, 85 % blue.
        if (box_w >= width * 0.08 and box_h >= height * 0.025 and box_w >= 2.5 * box_h
                and len(cells) >= 0.6 * (right - left) * (bottom - top)
                and (best is None or len(cells) > best[0])):
            best = (len(cells), left, top, right, bottom)
    if best is None:
        return None
    _, left, top, right, bottom = best
    # Left of center: the right end of the button may hold a menu arrow.
    return (round(area[0] + (left + 0.4 * (right - left)) * cell),
            round(area[1] + (top + bottom) / 2 * cell))


# Templates that identify a screen, tried at every scale in SCALES when the
# cached scale shows nothing known (first screen of a session, other scale).
# The most scale-robust template of each screen (the dialog title and the
# top bar text are also checked by classify, at the found scale +- 0.02).
SCALE_PROBES = ('create_button', 'ruleset_cards', 'race', 'customize', 'error')


def estimate_scale(image):
    """UI scale (from SCALES) whose screen templates match best, or None.
    Coarse pass every 0.02, then the neighbours of the best one."""
    masks = {kind: _mask_of(image, kind) for kind in ('light', 'yellow')}
    best_score, best = 0.0, None
    for s in SCALES[::2]:
        for template in SCALE_PROBES:
            value = score(image, template, s, masks)
            if value > best_score:
                best_score, best = value, s
    if best is None or best_score < 0.5:
        return None
    for s in (round(best - 0.01, 2), round(best + 0.01, 2)):
        for template in SCALE_PROBES:
            value = score(image, template, s, masks)
            if value > best_score:
                best_score, best = value, s
    return best


def classify(image):
    """Return the screen name and a dict of details for the live capture.

    Tries the cached UI scale first; if nothing is recognized there, the
    scale is estimated again and kept when it recognizes the screen."""
    image = normalize(image)
    current = _layout.scale
    screen, details = _classify(image, current)
    if screen != 'unknown':
        return screen, details
    found = estimate_scale(image)
    if found is None or found == current:
        return screen, details
    wrapped = _layout.wrapped
    result = _classify(image, found)
    if result[0] == 'unknown':
        set_scale(current, wrapped)   # keep the session's scale
    return result


def _classify(image, s):
    set_scale(s)
    if has(image, 'error'):
        return 'error', {}
    if has(image, 'customize'):
        if enabled(image, 'dialog') and popup_open(image):
            # Red in the center alone is not enough: hair can be red.
            # A popup over the creation screen that is not the imbalance error.
            return 'dialog', {}
        return 'customize', {'names': names_filled(image),
                             'finish_enabled': enabled(image, 'finish'),
                             **list_details(image)}
    if has(image, 'ruleset') or has(image, 'ruleset_cards'):
        return 'ruleset', {'pvp': pvp_selected(image), 'select_enabled': enabled(image, 'select')}
    if has(image, 'race') and has(image, 'horde', 0.6):
        set_scale(s, classes_wrapped(image))
        return 'race', {'troll': selected(image, 'troll'), 'rogue': selected(image, 'rogue'),
                        'male': selected(image, 'male')}
    if has(image, 'charselect'):
        if popup_open(image):
            # "Accediendo a un servidor de juegos..." or another loading popup.
            return 'unknown', {}
        return 'charselect', {'create_enabled': enabled(image, 'create'),
                              'pvp_list': has(image, 'pvp_list', 0.6)}
    return 'unknown', {}
