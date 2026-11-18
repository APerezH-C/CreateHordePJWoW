"""Unattended WoW Forever relaunch loop.

Battle.net "Jugar" -> character list -> ruleset JcJ -> Horde troll rogue,
male body -> customization -> name -> Terminar. The faction imbalance error closes WoW and starts again.
Anything else after Terminar stops the loop and leaves WoW open for you.

Every step reacts to what is on screen; there are no fixed waits between
screens. The only timers are retry and give-up limits.

F9 stops at once (global hotkey, every driver step checks it), F8 starts.
All points are in 1920 x 1080 game space and scaled to the WoW window; the
game's UI scale is found from the screen (screens.classify) and applied too.

Packaged as the windowed single-file BotWow.exe (BotWow.spec, build.bat): it
starts at once unless run with --no-autostart, writes loop.log and captures/
next to the exe and shows startup errors in a message box.
"""

import ctypes
from ctypes import wintypes
from datetime import datetime
import os
from pathlib import Path
import queue
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import traceback
import webbrowser

from PIL import Image, ImageGrab

import screens

# ---- Settings -------------------------------------------------------------
# Character name: None = a new random name every time the bot starts.
# A developer can pin a name here (letters A-Z only), e.g. FIRST_NAME = 'Example'.
FIRST_NAME = None
SECOND_NAME = None
# Character look, set every session before the name (the game picks random
# values). Numbers are the 1-based items of each option's list, applied in
# this order. The body is always "Cuerpo 1" (male).
# Look calibrated earlier (male troll rogue). Not used: the character keeps
# the game's random look. Use CUSTOMIZATION = SAVED_LOOK to apply it again.
SAVED_LOOK = (
    # First tab
    ('skin', 1),          # Color de piel
    ('face', 4),          # Rostro
    ('hairstyle', 13),    # Peinado
    ('hair_color', 10),   # Color de pelo
    ('eye_color', 2),     # Color de ojos
    # Second tab
    ('tusks', 4),         # Colmillos
    ('face_paint', 6),    # Pintura facial
    ('paint_color', 9),   # Color de pintura facial (after Pintura facial)
)
CUSTOMIZATION = ()   # no customization: name + Terminar only
# Terminar presses per WoW session before closing it (1 = your strategy:
# Terminar, close, relaunch). Higher values accept the error and retry.
ATTEMPTS_PER_SESSION = 1
POLL = 0.15            # seconds between screen checks
STABLE = 0.35          # a screen must stay unchanged this long before acting
RETRY = 3.0            # repeat an action if the screen did not react
MAX_REPEATS = 6        # same action on the same screen -> restart WoW
LAUNCH_LIMIT = 120     # Battle.net click without a WoW window -> click again
UNKNOWN_LIMIT = 300    # unrecognized screen (login queue, loading) -> restart
SUBMITTED_LIMIT = 30   # no error this long after Terminar -> stop for you
MAX_UNKNOWN_DIALOGS = 20  # then stop: something other than the imbalance error
DIALOG_STABLE = 1.5    # an unknown popup must stay this long to count
BURST_TIMEOUT = 1.5    # one list must open/close within this time
AFTER_SELECT_STABLE = 2.0  # character list must stay this long after JcJ
KILL_RETRY = 15        # WoW still open this long after closing -> close again
SESSION_LIMIT = 300    # a WoW session without reaching Terminar -> restart
STOP_CHECK = 0.05      # longest sleep between two checks of the stop request
# ---------------------------------------------------------------------------

# --dry-run: do everything except pressing Terminar (safe test on an
# account that would really create the character).
DRY_RUN = '--dry-run' in sys.argv

APP_NAME = 'BotWow'


def frozen():
    """True inside the PyInstaller exe."""
    return bool(getattr(sys, 'frozen', False))


def app_dir():
    """Folder of BotWow.exe when frozen, else the folder of this file."""
    if frozen():
        return Path(sys.executable).parent
    return Path(__file__).parent


def writable(folder):
    """True when a file can really be created in `folder` (os.access does not
    see Windows permissions). The probe file is deleted at once."""
    try:
        with tempfile.TemporaryFile(dir=folder):
            return True
    except OSError:
        return False


def data_dir():
    """Folder for loop.log and captures/: next to the exe (or loop.py); if
    that folder is not writable, %LOCALAPPDATA%\\BotWow."""
    folder = app_dir()
    if writable(folder):
        return folder
    local = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData' / 'Local')
    folder = Path(local) / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# Donation page shown on every start (Ko-fi, PayPal...). Empty = button off.
# Donation buttons (label, url). An empty url shows the button disabled.
DONATE_LINKS = (
    ('Ko-fi ☕', 'https://ko-fi.com/pereziam'),
    ('PayPal ❤', 'https://paypal.me/pereziam'),
)
DONATE_TEXT = ('BotWow is free.\n\n'
               'If it saves you time and you want to support the project, you can '
               'donate whatever you like. It is optional: the bot works the same.')


def open_donation(url):
    if url:
        webbrowser.open(url)
    return bool(url)


def autostart(argv):
    """The exe starts the loop at once; the script only with --autostart.
    --no-autostart always wins."""
    if '--no-autostart' in argv:
        return False
    return frozen() or '--autostart' in argv


def write_log(path, message):
    line = f'{datetime.now():%Y-%m-%d %H:%M:%S.%f}'[:-3] + f' {message}'
    with Path(path).open('a', encoding='utf-8') as file:
        file.write(line + '\n')

# Random names: syllables give 6-10 letter names from ~10^9 combinations per
# name (two names per character), so an existing name is practically never hit.
NAME_ONSETS = ('b', 'c', 'd', 'f', 'g', 'j', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't',
               'v', 'z', 'br', 'dr', 'gr', 'kr', 'tr', 'th', 'st', 'ch', 'sh', 'gl',
               'fl', 'pr')
NAME_VOWELS = ('a', 'e', 'i', 'o', 'u', 'a', 'e', 'o', 'ai', 'ei', 'ia', 'ou')
NAME_CODAS = ('', '', '', '', 'n', 'r', 'l', 's', 'm', 'th', 'k', 'x')
NAME_LENGTH = (6, 10)
NAME_BLOCKLIST = (
    'puta', 'puto', 'mierd', 'polla', 'culo', 'caca', 'pene', 'nazi', 'hitler',
    'fuck', 'shit', 'cunt', 'dick', 'cock', 'fag', 'nig', 'negr', 'rape', 'sex',
    'porn', 'anal', 'marica', 'verga', 'pija', 'teta', 'zorra', 'cabron', 'mamon',
    'joto', 'follar', 'kkk', 'gay', 'jew', 'isis', 'coca', 'pedo', 'violad',
)

# WoW Forever settings file (language and UI scale checks at start).
PRODUCT_DB = Path(os.environ.get('ProgramData', 'C:/ProgramData'), 'Battle.net', 'Agent',
                  'product.db')
DEFAULT_INSTALLS = ('C:/Program Files (x86)/World of Warcraft',
                    'C:/Program Files/World of Warcraft')
CONFIG_FILE = Path('_forever_', 'WTF', 'Config.wtf')

VK_F8, VK_F9 = 0x77, 0x78
HOTKEYS = {1: (VK_F8, 'start'), 2: (VK_F9, 'stop')}   # id: (key, command)
WM_HOTKEY, WM_QUIT, MOD_NOREPEAT = 0x0312, 0x0012, 0x4000


class Stopped(Exception):
    """Raised inside driver steps once a stop (F9, Stop, closing) is requested."""


class Brain:
    """Pure decision logic: (time, game state, screen) -> one action."""

    def __init__(self, attempts_per_session=ATTEMPTS_PER_SESSION,
                 customization=CUSTOMIZATION, dry_run=False):
        self.dry_run = dry_run
        self.pvp_chosen = False    # JcJ selected in this WoW session
        self.per_session = attempts_per_session
        self.customization = tuple(customization)
        self.customized = set()    # options set in this WoW session
        self.attempts = 0
        self.session_attempts = 0
        self.submitted = None      # time Terminar was pressed, or None
        self.killing = False
        self.killed_at = None
        self.session_at = None
        self.launched_at = None
        self.view = None
        self.view_since = 0
        self.last = None           # (action, view, time)
        self.repeats = 0
        self.unknown_dialogs = 0   # unrecognized popups after Terminar in a row

    def _act(self, now, action):
        if self.last and self.last[0] == action and self.last[1] == self.view:
            if now - self.last[2] < RETRY:
                return ('wait',)
            self.repeats += 1
            if self.repeats >= MAX_REPEATS:
                return self._restart(f'no reaction to {action}', now)
        else:
            self.repeats = 0
        self.last = (action, self.view, now)
        return action

    def _restart(self, reason, now=None):
        if self.submitted is not None:
            return ('stop', f'{reason} after Terminar')
        self.killing = True
        self.killed_at = now
        return ('kill', reason)

    def step(self, now, running, screen='unknown', details=None):
        view = (screen, tuple(sorted((details or {}).items())))
        if view != self.view:
            self.view, self.view_since = view, now

        if not running:
            self.pvp_chosen = False
            self.submitted = None
            self.session_attempts = 0
            self.last = None
            self.session_at = None
            self.customized.clear()
            if self.killing:
                self.killing = False
                self.launched_at = None
            if self.launched_at is None or now - self.launched_at >= LAUNCH_LIMIT:
                self.launched_at = now
                return ('launch',)
            return ('wait',)
        if self.killing:
            if self.killed_at is not None and now - self.killed_at >= KILL_RETRY:
                self.killed_at = now
                return ('kill', 'WoW still open')
            return ('wait',)
        self.launched_at = None
        if self.session_at is None:
            self.session_at = now
        if self.submitted is None and now - self.session_at >= SESSION_LIMIT:
            return self._restart(f'no Terminar within {SESSION_LIMIT} s', now)

        if screen == 'error':
            if self.submitted is not None:
                self.submitted = None
                self.unknown_dialogs = 0
                self.attempts += 1
                self.session_attempts += 1
            if self.session_attempts >= self.per_session:
                self.killing = True
                self.killed_at = now
                return ('kill', 'imbalance error')
            if now - self.view_since < STABLE:
                return ('wait',)
            return self._act(now, ('click', 'accept'))
        if self.submitted is not None:
            if screen == 'charselect':
                return ('stop', 'character list after Terminar: character probably created')
            if screen == 'dialog' and now - self.view_since >= DIALOG_STABLE:
                # Camera moves can flash red in the center; real popups stay.
                # A popup after Terminar means the character was NOT created
                # (success returns to the character list), so retrying is
                # safe. It is usually the imbalance error not recognized at
                # this UI scale; a rejected name gets a new one on relaunch.
                self.submitted = None
                self.unknown_dialogs += 1
                if self.unknown_dialogs > MAX_UNKNOWN_DIALOGS:
                    return ('stop', f'{self.unknown_dialogs} unrecognized messages after '
                                    'Terminar in a row')
                self.attempts += 1
                self.killing = True
                self.killed_at = now
                return ('kill', 'unrecognized message after Terminar')
            if now - self.submitted >= SUBMITTED_LIMIT:
                return ('stop', f'no imbalance error {SUBMITTED_LIMIT} s after Terminar')
        if screen == 'unknown' or screen == 'dialog':
            if now - self.view_since >= UNKNOWN_LIMIT:
                return self._restart(f'{screen} screen for {UNKNOWN_LIMIT} s', now)
            return ('wait',)
        if now - self.view_since < STABLE:
            return ('wait',)

        details = details or {}
        if screen == 'charselect':
            if (self.last and self.last[0] == ('pvp',)
                    and now - self.view_since < AFTER_SELECT_STABLE):
                # Right after choosing JcJ the old list flashes between popups.
                return ('wait',)
            if self.pvp_chosen and details.get('pvp_list') and details.get('create_enabled'):
                # Account already has JcJ characters: the JcJ list shows up
                # instead of the creation screen. Press "Crear personaje".
                return self._act(now, ('click', 'create'))
            return self._act(now, ('click', 'ruleset'))
        if screen == 'ruleset':
            if not details.get('pvp') or details.get('select_enabled'):
                # Driver clicks JcJ (if needed), waits for it, then Seleccionar.
                self.pvp_chosen = True
                return self._act(now, ('pvp',))
            return ('wait',)
        if screen == 'race':
            missing = tuple(icon for icon in ('troll', 'rogue', 'male')
                            if not details.get(icon))
            if missing:
                return self._act(now, ('icons', missing))
            return self._act(now, ('click', 'customize'))
        if screen == 'customize':
            action = self._customize(now, details)
            if action:
                return action
            names = details.get('names', (False, False))
            missing = tuple(index for index, typed in enumerate(names) if not typed)
            if missing:
                return self._act(now, ('type', missing))
            if details.get('finish_enabled'):
                if self.dry_run:
                    return ('stop', 'dry run: everything ready, Terminar NOT pressed')
                action = self._act(now, ('click', 'finish'))
                if action == ('click', 'finish') and self.submitted is None:
                    self.submitted = now
                return action
            return ('wait',)
        return ('wait',)

    def _customize(self, now, details):
        """Next customization action, or None when every option is set."""
        shown = details.get('list')
        if self.last and self.last[0][0] == 'pick' and shown != self.last[0][1]:
            # The list closed after choosing the item: that option is done.
            self.customized.add(self.last[0][1])
        pending = [(name, number) for name, number in self.customization
                   if name not in self.customized]
        if shown:
            number = dict(pending).get(shown)
            if number is None:
                return self._act(now, ('click', shown))  # close it again
            if details.get('items', 0) < number:
                return ('stop', f'{screens.LABELS[shown]} list shows {details.get("items", 0)} '
                                f'items, setting asks for {number}')
            return self._act(now, ('pick', shown, number))
        if not pending:
            return None
        # All pending options in one fast burst; the driver verifies every
        # list opening and closing and reports which options it set.
        return self._act(now, ('burst', tuple(pending)))


def valid_name(name):
    """WoW name rules: letters only, capital first letter, 3-12 letters,
    no three equal letters in a row, nothing from the blocklist."""
    lower = name.lower()
    return (re.fullmatch(r'[A-Z][a-z]{2,11}', name) is not None
            and re.search(r'(.)\1\1', lower) is None
            and not any(bad in lower for bad in NAME_BLOCKLIST))


def random_name(rng):
    """A pronounceable name of NAME_LENGTH letters that follows valid_name."""
    while True:
        name = ''.join(rng.choice(NAME_ONSETS) + rng.choice(NAME_VOWELS) + rng.choice(NAME_CODAS)
                       for _ in range(rng.randint(2, 4))).capitalize()
        if NAME_LENGTH[0] <= len(name) <= NAME_LENGTH[1] and valid_name(name):
            return name


def make_names(rng=None):
    """(first, second) name: the pinned constants, or new random ones."""
    rng = rng or random.SystemRandom()
    return tuple(pinned or random_name(rng) for pinned in (FIRST_NAME, SECOND_NAME))


def to_screen(bounds, point):
    """Screen pixel of a 1920 x 1080 game point inside the WoW client `bounds`."""
    x, y, right, bottom = bounds
    return (round(x + point[0] * (right - x) / screens.SIZE[0]),
            round(y + point[1] * (bottom - y) / screens.SIZE[1]))


def fit_rect(bounds, monitor):
    """Monitor rectangle to move WoW's window to, or None.

    WoW sometimes opens its borderless window slightly larger than the
    monitor (e.g. 1936 x 1100), which shifts and scales the UI. Only that
    case is fixed; a smaller (windowed) client is left alone."""
    size = bounds[2] - bounds[0], bounds[3] - bounds[1]
    screen = monitor[2] - monitor[0], monitor[3] - monitor[1]
    if size == screen:
        return None
    if all(screen[i] <= size[i] < screen[i] * 1.05 for i in (0, 1)):
        return tuple(monitor)
    return None


def window_warning(bounds):
    """Warning for a WoW window size the bot is not calibrated for."""
    width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
    if abs(width / height - 16 / 9) > 16 / 9 * 0.03:
        return (f'Warning: the WoW window is {width}x{height}, which is not 16:9. The bot is '
                'calibrated for 16:9 screens (for example 1920x1080); it may fail.')
    if height < 900:
        return (f'Warning: the WoW window is {width}x{height}. Below 1600x900 '
                'screen recognition may fail.')
    return None


def install_paths(data):
    """Install folders listed in Battle.net's product.db (protobuf strings)."""
    paths = []
    for match in re.finditer(rb'\n', data):  # length-delimited field 1
        index, length, shift = match.end(), 0, 0
        while index < len(data) and shift < 35:
            byte = data[index]
            index += 1
            length |= (byte & 0x7F) << shift
            shift += 7
            if byte < 0x80:
                break
        raw = data[index:index + length]
        if len(raw) == length and re.fullmatch(rb'[A-Za-z]:[/\\][^\x00-\x1f]*', raw):
            try:
                paths.append(raw.decode('utf-8'))
            except UnicodeDecodeError:
                pass
    return paths


def find_config(product_db=PRODUCT_DB, defaults=DEFAULT_INSTALLS):
    """WoW Forever's Config.wtf, or None."""
    try:
        data = Path(product_db).read_bytes()
    except OSError:
        data = b''
    for folder in install_paths(data) + list(defaults):
        path = Path(folder) / CONFIG_FILE
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def read_config(path):
    """CVars of a Config.wtf file: lowercase name -> value."""
    values = {}
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        match = re.match(r'\s*SET\s+(\S+)\s+"([^"]*)"', line, re.IGNORECASE)
        if match:
            values[match.group(1).lower()] = match.group(2)
    return values


def setup_warnings(config=None, product_db=PRODUCT_DB, defaults=DEFAULT_INSTALLS):
    """Spanish warnings for client settings the bot is not calibrated for.
    Never fails: a missing or unreadable file gives no warnings."""
    try:
        config = config or find_config(product_db, defaults)
        if config is None:
            return []
        values = read_config(config)
    except Exception:
        return []
    warnings = []
    locale = values.get('textlocale')
    if locale and locale.lower() != 'eses':
        warnings.append(f'Warning: the game language is "{locale}". The bot only recognizes the '
                        'Spanish client (esES); it will not work properly in other languages.')
    # Any WoW UI scale is supported (screens.estimate_scale), so no warning.
    return warnings


class MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


class Hotkeys:
    """Global F8/F9 in a background thread, also while WoW has the focus.

    Uses RegisterHotKey (Windows queues every press, even a quick tap while
    the bot is busy). If another program owns a key, polls the keyboard
    every 20 ms instead. `on_key` gets 'start' or 'stop' on this thread."""

    def __init__(self, user, on_key, poll=0.02):
        self.user, self.on_key, self.poll = user, on_key, poll
        self.closed = threading.Event()
        self.thread_id = None
        self.mode = None   # 'hotkey' or 'poll' once running
        self.thread = threading.Thread(target=self.run, name='hotkeys', daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.closed.set()
        if self.thread_id and self.mode == 'hotkey':
            self.user.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)

    def run(self):
        self.thread_id = threading.get_native_id()
        registered = [key_id for key_id, (vk, _) in HOTKEYS.items()
                      if self.user.RegisterHotKey(None, key_id, MOD_NOREPEAT, vk)]
        if len(registered) == len(HOTKEYS):
            self.mode = 'hotkey'
            try:
                self._messages()
            finally:
                for key_id in registered:
                    self.user.UnregisterHotKey(None, key_id)
        else:
            for key_id in registered:
                self.user.UnregisterHotKey(None, key_id)
        if not self.closed.is_set():
            self.mode = 'poll'
            self._poll()

    def _messages(self):
        msg = wintypes.MSG()
        while not self.closed.is_set():
            if self.user.GetMessageW(ctypes.byref(msg), None, 0, 0) <= 0:
                return  # WM_QUIT from close(), or an error: poll instead
            if msg.message == WM_HOTKEY and msg.wParam in HOTKEYS:
                self.on_key(HOTKEYS[msg.wParam][1])

    def _poll(self):
        down = set()
        while not self.closed.is_set():
            # 0x8000: held now; 0x0001: pressed since the previous check.
            pressed = {vk for vk, _ in HOTKEYS.values()
                       if self.user.GetAsyncKeyState(vk) & 0x8001}
            for vk, command in HOTKEYS.values():
                if vk in pressed and vk not in down:
                    self.on_key(command)
            down = pressed
            self.closed.wait(self.poll)


class Windows:
    """Thin Win32 driver: find windows, capture, click, type, launch, kill.

    Every step checks `halt` and raises Stopped once it is set, so F9 also
    interrupts a burst, a wait or the typing within STOP_CHECK seconds."""

    def __init__(self, user=None):
        self.halt = threading.Event()
        if user is not None:   # tests
            self.user = user
            return
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.user.GetForegroundWindow.restype = wintypes.HWND
        self.user.FindWindowW.restype = wintypes.HWND
        self.user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        self.user.GetAsyncKeyState.restype = ctypes.c_short
        self.user.MonitorFromWindow.restype = wintypes.HMONITOR
        self.user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        self.user.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
        self.user.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT,
                                             wintypes.UINT]
        self.user.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                          wintypes.UINT, wintypes.UINT]
        self.user.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                                 wintypes.WPARAM, wintypes.LPARAM]

    def check(self):
        if self.halt.is_set():
            raise Stopped()

    def sleep(self, seconds):
        """Sleep, checking the stop request at least every STOP_CHECK s."""
        self.check()
        while seconds > 0:
            step = min(STOP_CHECK, seconds)
            time.sleep(step)
            seconds -= step
            self.check()

    def wow(self):
        handle = self.user.FindWindowW('waApplication Window', None)
        return handle if handle and self.user.IsWindowVisible(handle) else None

    def running(self):
        if self.wow():
            return True
        # No console in the exe: no window and no inherited standard input.
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Wow.exe', '/NH'],
                             capture_output=True, text=True, stdin=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout
        return 'wow.exe' in out.lower()

    def focus(self, handle):
        self.check()
        if self.user.GetForegroundWindow() == handle:
            return
        if self.user.IsIconic(handle):
            self.user.ShowWindow(handle, 9)
        # Windows blocks background processes from taking the foreground.
        # Try, in order: Alt press, input attach to the current foreground
        # thread, SwitchToThisWindow. Check the result after each one.
        kernel = ctypes.windll.kernel32
        for attempt in range(3):
            if attempt == 0:
                self.user.keybd_event(0x12, 0, 0, 0)
                self.user.SetForegroundWindow(handle)
                self.user.keybd_event(0x12, 0, 2, 0)
            elif attempt == 1:
                foreground = self.user.GetForegroundWindow()
                theirs = self.user.GetWindowThreadProcessId(foreground, None)
                mine = kernel.GetCurrentThreadId()
                self.user.AttachThreadInput(mine, theirs, True)
                try:
                    self.user.BringWindowToTop(handle)
                    self.user.SetForegroundWindow(handle)
                finally:
                    self.user.AttachThreadInput(mine, theirs, False)
            else:
                self.user.SwitchToThisWindow(handle, True)
            self.sleep(0.1)
            if self.user.GetForegroundWindow() == handle:
                return

    def bounds(self, handle):
        rect, origin = wintypes.RECT(), wintypes.POINT()
        self.user.GetClientRect(handle, ctypes.byref(rect))
        self.user.ClientToScreen(handle, ctypes.byref(origin))
        return origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom

    def monitor(self, handle):
        """Rectangle of the monitor that shows `handle` (or the nearest one)."""
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        found = self.user.MonitorFromWindow(handle, 2)  # MONITOR_DEFAULTTONEAREST
        if found and self.user.GetMonitorInfoW(found, ctypes.byref(info)):
            rect = info.rcMonitor
            return rect.left, rect.top, rect.right, rect.bottom
        return 0, 0, self.user.GetSystemMetrics(0), self.user.GetSystemMetrics(1)

    def capture(self):
        """Return (screenshot, bounds) of the WoW client area, or None."""
        self.check()
        handle = self.wow()
        if not handle:
            return None
        self.focus(handle)
        bounds = self.bounds(handle)
        target = fit_rect(bounds, self.monitor(handle))
        if target:
            self.user.SetWindowPos(handle, 0, target[0], target[1], target[2] - target[0],
                                   target[3] - target[1], 0x0014)
            self.sleep(0.3)
            bounds = self.bounds(handle)
        if bounds[2] - bounds[0] < 640 or bounds[3] - bounds[1] < 360:
            return None
        return ImageGrab.grab(bbox=bounds, all_screens=True), bounds

    def click_screen(self, x, y, settle=0.08, hold=0.1):
        self.check()
        self.user.SetCursorPos(x, y)
        self.sleep(settle)
        self.user.mouse_event(0x0002, 0, 0, 0, 0)
        try:
            time.sleep(hold)
        finally:
            self.user.mouse_event(0x0004, 0, 0, 0, 0)

    def grab_region(self, bounds, box):
        """Capture only `box` (game coordinates) on a blank full-size canvas,
        so the normal screen checks work on it at a fraction of the cost.
        The grabbed pixels are scaled to game space like the full capture."""
        left, top = to_screen(bounds, box[:2])
        right, bottom = to_screen(bounds, box[2:])
        size = box[2] - box[0], box[3] - box[1]
        region = ImageGrab.grab(bbox=(left, top, max(right, left + 1), max(bottom, top + 1)),
                                all_screens=True).convert('RGB')
        if region.size != size:
            region = region.resize(size)
        canvas = Image.new('RGB', screens.SIZE, (128, 128, 128))  # not black: lists are black
        canvas.paste(region, box[:2])
        return canvas

    def wait_for(self, bounds, box, check, timeout=BURST_TIMEOUT):
        end = time.monotonic() + timeout
        while True:
            self.check()
            image = self.grab_region(bounds, box)
            if check(image):
                return image
            if time.monotonic() >= end:
                return None
            self.sleep(0.01)

    def fast_click(self, bounds, point):
        self.click_screen(*to_screen(bounds, point), settle=0.015, hold=0.03)

    def pick_icons(self, bounds, icons):
        """Click race/class/body icons, each verified by its selection frame."""
        done = []
        for icon in icons:
            self.fast_click(bounds, screens.point(icon))
            if not self.wait_for(bounds, screens.frame_box(icon),
                                 lambda im, icon=icon: screens.selected(im, icon)):
                break
            done.append(icon)
        return done

    def pick_pvp(self, bounds):
        """Choose JcJ, wait until it is highlighted and Seleccionar is enabled,
        then press Seleccionar. Returns True when Seleccionar was pressed."""
        box = screens.pvp_box()

        def ready(image):
            return screens.pvp_selected(image) and screens.enabled(image, 'select')
        if not self.wait_for(bounds, box, ready, 0):
            self.fast_click(bounds, screens.point('pvp'))
            if not self.wait_for(bounds, box, ready):
                return False
        self.fast_click(bounds, screens.point('select'))
        return True

    def type_names(self, bounds, fields, names):
        for index in fields:
            self.fast_click(bounds, screens.point(('name_first', 'name_second')[index]))
            self.sleep(0.03)
            self.type_text(names[index])

    def burst(self, bounds, steps):
        """Set customization options as fast as the game reacts.

        For each (option, number): switch tab if needed, open the list, wait
        until it is open and item `number` is shown, click it, wait until the
        list closes. Returns the options set; stops at the first failure."""
        def fast(point):
            self.fast_click(bounds, point)

        done = []
        tab_box = (1600, 170, 1800, 250)
        for name, number in steps:
            tab, y = screens.OPTIONS[name][:2]
            if not self.wait_for(bounds, tab_box, lambda im: screens.active_tab(im) == tab, 0):
                fast(screens.POINTS[f'tab{tab}'])
                if not self.wait_for(bounds, tab_box, lambda im: screens.active_tab(im) == tab):
                    break
            list_box = screens.list_box(name)
            fast(screens.POINTS[name])
            shown = self.wait_for(bounds, list_box, lambda im: screens.open_list(im, tab) == name
                                  and screens.item_label(im, name, number) is not None)
            if shown is None:
                break
            fast(screens.item_point(name, number))
            if not self.wait_for(bounds, list_box, lambda im: screens.open_list(im, tab) != name):
                break
            done.append(name)
        return done

    def click(self, bounds, point):
        self.click_screen(*to_screen(bounds, point))

    def type_text(self, text):
        for char in text:
            self.check()
            shift = char.isupper()
            key = ord(char.upper())
            if shift:
                self.user.keybd_event(0x10, 0, 0, 0)
            try:
                self.user.keybd_event(key, 0, 0, 0)
                time.sleep(0.01)
                self.user.keybd_event(key, 0, 2, 0)
            finally:
                if shift:
                    self.user.keybd_event(0x10, 0, 2, 0)
            self.sleep(0.02)

    def find_play(self, rect):
        """Screen point of Battle.net's "Jugar" in the window `rect`, or None."""
        image = ImageGrab.grab(bbox=rect, all_screens=True).convert('RGB')
        found = screens.find_play_button(image)
        if found:
            return rect[0] + found[0], rect[1] + found[1]
        # Fallback: the old fixed offset from the bottom-left corner, used only
        # when that pixel has the button's blue.
        x, y = 155, image.height - 108
        if 0 <= x < image.width and 0 <= y < image.height:
            r, g, b = image.getpixel((x, y))
            if b > 150 and b > r + 60:
                return rect[0] + x, rect[1] + y
        return None

    def launch(self):
        """Click "Jugar" in Battle.net. Returns an error text or None."""
        self.check()
        handle = self.user.FindWindowW('Chrome_WidgetWin_0', 'Battle.net')
        if not handle:
            return 'Battle.net window not found'
        if self.user.IsIconic(handle):
            self.user.ShowWindow(handle, 9)
            self.sleep(0.5)
        self.focus(handle)
        if self.user.GetForegroundWindow() != handle:
            return 'Battle.net could not be brought to the front'
        rect = wintypes.RECT()
        self.user.GetWindowRect(handle, ctypes.byref(rect))
        point = self.find_play((rect.left, rect.top, rect.right, rect.bottom))
        if point is None:
            return 'Battle.net "Jugar" button is not ready'
        self.click_screen(*point)
        return None

    def kill(self):
        self.check()
        subprocess.run(['taskkill', '/IM', 'Wow.exe', '/F'], capture_output=True,
                       stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)


def check_names():
    for name in (FIRST_NAME, SECOND_NAME):
        if name is not None and (not name.isascii() or not name.isalpha()):
            raise SystemExit('Names may only use the letters A-Z.')
    for name, number in CUSTOMIZATION:
        if name not in screens.OPTIONS or screens.item_center(name, number) is None:
            raise SystemExit(f'CUSTOMIZATION: unknown option or item {name} {number}.')


STOP_MESSAGE = 'Stopped with F9. Press F8 (or Start) to continue.'


class App:
    def __init__(self, root, warnings=None, folder=None):
        check_names()
        self.accepted = False      # set by the donation screen's Continuar
        self.root = root
        self.folder = Path(folder) if folder is not None else data_dir()
        self.log(f'program start ({"exe" if frozen() else "script"}'
                 f'{", dry run" if DRY_RUN else ""}), files in {self.folder}')
        self.win = Windows()
        self.win.halt.set()   # stopped: no driver step runs until F8 / Start
        self.commands = queue.SimpleQueue()
        self.brain = None
        self.names = None
        self.started = None
        self.screen = None
        self.screen_at = time.monotonic()
        self.warnings = list(setup_warnings() if warnings is None else warnings)
        root.title('WoW Forever relaunch loop')
        root.geometry('620x300')
        tk.Label(root, text='F9 = stop     F8 = start',
                 font=('Segoe UI', 16, 'bold')).pack(pady=(10, 4))
        self.status = tk.StringVar(value='Stopped. Open Battle.net and press F8 (or Start).')
        tk.Label(root, textvariable=self.status, wraplength=590, justify='left').pack(pady=4)
        self.name_text = tk.StringVar(value='Name: random on start')
        tk.Label(root, textvariable=self.name_text, font=('Segoe UI', 11)).pack()
        self.warning_text = tk.StringVar(value='\n'.join(self.warnings))
        tk.Label(root, textvariable=self.warning_text, fg='#b00000', wraplength=590,
                 justify='left').pack(pady=4)
        frame = tk.Frame(root)
        frame.pack(pady=6)
        tk.Button(frame, text='Start (F8)', command=self.start).pack(side='left', padx=6)
        tk.Button(frame, text='Stop (F9)', command=lambda: self.pause('Stopped.')).pack(side='left')
        for warning in self.warnings:
            self.log(f'warning: {warning}')
        self.hotkeys = Hotkeys(self.win.user, self.hotkey)
        self.hotkeys.start()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.tick)

    @property
    def log_path(self):
        return self.folder / 'loop.log'

    def log(self, message):
        write_log(self.log_path, message)

    def hotkey(self, command):
        """Hotkey thread: F9 stops the driver at once; the tick does the rest."""
        if command == 'stop':
            self.win.halt.set()
        self.commands.put(command)

    def warn(self, warning):
        if warning and warning not in self.warnings:
            self.warnings.append(warning)
            self.warning_text.set('\n'.join(self.warnings))
            self.log(f'warning: {warning}')

    def start(self):
        if not self.accepted:
            return  # the donation screen must be closed with "Continuar"
        if self.brain is None:
            self.names = make_names()
            self.brain = Brain(dry_run=DRY_RUN)
            self.started = time.monotonic()
            self.win.halt.clear()
            self.log(f'start, name {self.names[0]} {self.names[1]}')
            self.name_text.set(f'Name: {self.names[0]} {self.names[1]}')
            self.status.set('Running.')

    def pause(self, message):
        self.win.halt.set()
        if self.brain is not None:
            self.log(f'pause: {message}')
        self.brain = None
        self.status.set(message)

    def close(self):
        """Window closed: stop every driver step and end the program."""
        self.win.halt.set()
        if self.brain is not None:
            self.log('pause: window closed')
        self.brain = None
        self.hotkeys.close()
        self.root.destroy()

    def save_capture(self, image, label):
        folder = self.folder / 'captures'
        folder.mkdir(exist_ok=True)
        path = folder / f'{datetime.now():%Y%m%d-%H%M%S}-{label}.png'
        image.save(path)
        return path

    def handle_commands(self):
        """Apply the hotkey presses since the last tick, in order."""
        while True:
            try:
                command = self.commands.get_nowait()
            except queue.Empty:
                return
            if command == 'stop':
                self.pause(STOP_MESSAGE)
            elif command == 'start':
                self.start()

    def tick(self):
        delay = POLL
        try:
            self.handle_commands()
            if self.brain is not None:
                delay = self.run_once()
        except Stopped:
            self.pause(STOP_MESSAGE)
        except Exception as error:  # keep the GUI alive and show the problem
            self.pause(f'Paused by error: {error}')
        self.root.after(int(delay * 1000), self.tick)

    def run_once(self):
        now = time.monotonic()
        shot = self.win.capture()
        running = shot is not None or self.win.running()
        screen, details = ('unknown', {})
        if shot:
            screen, details = screens.classify(shot[0])
            self.warn(window_warning(shot[1]))
        if screen != self.screen:
            if shot or self.screen is not None:
                self.log(f'screen {screen} {details} (previous lasted {now - self.screen_at:.1f} s)')
            self.screen, self.screen_at = screen, now
        if shot and screen != 'unknown' and screens.scale() != getattr(self, 'scale', 1.0):
            self.scale = screens.scale()
            self.log(f'UI scale {self.scale:.2f}')
        action = self.brain.step(now, running, screen, details)
        kind = action[0]
        if kind != 'wait':
            self.log(f'action {action}')
        if kind == 'launch':
            if self.brain.unknown_dialogs:
                # The last popup may have been a rejected name: try a new one.
                self.names = make_names()
                self.name_text.set(f'Name: {self.names[0]} {self.names[1]}')
                self.log(f'new name {self.names[0]} {self.names[1]}')
            problem = self.win.launch()
            if problem:
                self.brain.launched_at = None  # try again on the next poll
                self.status.set(f'Waiting: {problem}')
                return 2.0
        elif kind == 'kill':
            if shot and action[1] != 'imbalance error':
                self.log(f'capture {self.save_capture(shot[0], "restart")}')
            self.win.kill()
        elif kind == 'click':
            self.win.click(shot[1], screens.point(action[1]))
        elif kind == 'burst':
            started = time.monotonic()
            done = self.win.burst(shot[1], action[1])
            self.brain.customized.update(done)
            self.log(f'burst set {len(done)}/{len(action[1])} in {time.monotonic() - started:.2f} s')
        elif kind == 'pick':
            self.win.click(shot[1], screens.item_point(action[1], action[2]))
        elif kind == 'type':
            self.win.type_names(shot[1], action[1], self.names)
        elif kind == 'icons':
            done = self.win.pick_icons(shot[1], action[1])
            self.log(f'icons set {len(done)}/{len(action[1])}')
        elif kind == 'pvp':
            self.log(f'pvp selected: {self.win.pick_pvp(shot[1])}')
        elif kind == 'stop':
            path = self.save_capture(shot[0], 'stop') if shot else None
            self.pause(f'STOPPED: {action[1]}. Check the game. Capture: {path}')
            for _ in range(3):
                ctypes.windll.user32.MessageBeep(0x30)
            return POLL
        elapsed = int(now - self.started)
        self.status.set(f'Running {elapsed // 3600}h{elapsed // 60 % 60:02d}m - '
                        f'attempts: {self.brain.attempts} - screen: {screen} - '
                        f'last: {action}\nF9 = stop')
        return POLL


def dpi_aware():
    ctypes.windll.user32.SetProcessDPIAware()


def message_box(text, title=APP_NAME):
    """Windows error box (works without Tk and without a console)."""
    # MB_ICONERROR | MB_TOPMOST | MB_SETFOREGROUND
    ctypes.windll.user32.MessageBoxW(None, text, title, 0x10 | 0x40000 | 0x10000)


def report_error(title, exc_info, folder=None):
    """Write the traceback to loop.log and show the error in a message box.
    The exe has no console, so nothing may only go to stderr."""
    details = ''.join(traceback.format_exception(*exc_info)).rstrip()
    try:
        log_file = Path(folder if folder is not None else data_dir()) / 'loop.log'
        write_log(log_file, f'{title}:\n{details}')
        where = f'Details in {log_file}'
    except Exception:
        where = 'Could not write loop.log.'
    error = exc_info[1]
    message = str(error) or type(error).__name__
    try:
        message_box(f'{title}:\n\n{message}\n\n{where}')
    except Exception:
        pass


def show_donation(root, app, start_after):
    """Donation screen on every start. The bot only runs after the user
    presses "Continuar"; closing this screen closes the program."""
    root.withdraw()
    dialog = tk.Toplevel(root)
    dialog.title('BotWow')
    dialog.resizable(False, False)
    dialog.attributes('-topmost', True)
    tk.Label(dialog, text='☕ Support BotWow', font=('Segoe UI', 16, 'bold')).pack(padx=30, pady=(20, 8))
    tk.Label(dialog, text=DONATE_TEXT, wraplength=380, justify='center',
             font=('Segoe UI', 10)).pack(padx=30)
    buttons = tk.Frame(dialog)
    buttons.pack(pady=20)

    def proceed():
        app.accepted = True
        app.log('donation screen: continue')
        dialog.destroy()
        root.deiconify()
        if start_after:
            app.start()

    def donate(url):
        app.log(f'donation screen: donate pressed ({url})')
        open_donation(url)

    for label, url in DONATE_LINKS:
        tk.Button(buttons, text=label, width=12, command=lambda url=url: donate(url),
                  state='normal' if url else 'disabled').pack(side='left', padx=6)
    tk.Button(buttons, text='Continue ▶', width=12, command=proceed,
              default='active').pack(side='left', padx=(18, 6))
    dialog.protocol('WM_DELETE_WINDOW', root.destroy)
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() - dialog.winfo_reqwidth()) // 2
    y = (dialog.winfo_screenheight() - dialog.winfo_reqheight()) // 3
    dialog.geometry(f'+{x}+{y}')
    dialog.focus_force()
    return dialog, proceed, donate


def main(argv=None):
    """Start the GUI. Returns the exit code; errors never get lost: they go
    to loop.log and a message box."""
    argv = sys.argv if argv is None else argv
    folder = app = None
    try:
        folder = data_dir()
        dpi_aware()
        root = tk.Tk()
        root.report_callback_exception = lambda *exc: report_error(
            'BotWow ran into an error', exc, folder)
        app = App(root, folder=folder)
        threading.excepthook = lambda args: report_error(
            'BotWow ran into an error', (args.exc_type, args.exc_value, args.exc_traceback),
            folder)
        show_donation(root, app, autostart(argv))
        root.mainloop()
    except SystemExit as error:
        if error.code in (None, 0):
            return 0
        report_error('BotWow could not start', sys.exc_info(), folder)
        return 1
    except Exception:
        report_error('BotWow could not start' if app is None else
                     'BotWow ran into an error', sys.exc_info(), folder)
        return 1
    finally:
        if app is not None:
            app.win.halt.set()
            app.hotkeys.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
