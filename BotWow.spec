# PyInstaller spec: one windowed file, dist\BotWow.exe. Build with build.bat.
import sys
from pathlib import Path

sys.path.insert(0, SPECPATH)
import screens  # noqa: E402  (only to list the reference screenshots it reads)

HERE = Path(SPECPATH)
# The reference screenshots the recognition reads (screens.TEMPLATES).
# In the exe they load from sys._MEIPASS/refs.
REFS = sorted({ref for ref, _, _ in screens.TEMPLATES.values()})
DATAS = [(str(HERE / 'refs' / name), 'refs') for name in REFS]

# Modules the bot never imports (keeps the exe small).
EXCLUDES = [
    'numpy', 'unittest', 'doctest', 'pydoc', 'pydoc_data', 'lib2to3', 'test',
    'setuptools', 'pkg_resources', 'distutils', 'pip', 'sqlite3', 'xmlrpc',
    'PIL.ImageQt', 'PIL.ImageTk', 'PIL.ImageShow',
    # AVIF/WebP codecs (refs are PNG) and OpenSSL (no network): Pillow,
    # urllib and hashlib work without them.
    'PIL._avif', 'PIL._webp', 'ssl', '_ssl', '_hashlib',
]
# Tcl/Tk files the window does not need (time zones, translations, demos).
DROP = ('_tcl_data/tzdata/', '_tcl_data/msgs/', '_tk_data/demos/', '_tk_data/images/',
        '_tk_data/msgs/')

a = Analysis(
    [str(HERE / 'loop.py')],
    pathex=[str(HERE)],
    datas=DATAS,
    excludes=EXCLUDES,
    noarchive=False,
)
a.datas = [entry for entry in a.datas
           if not Path(entry[0]).as_posix().startswith(DROP)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BotWow',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    runtime_tmpdir=None,
)
