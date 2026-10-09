# PyInstaller recipe for oktoboot.app (Apple Silicon).
#
# Build:  .venv/bin/python -m PyInstaller oktoboot.spec --noconfirm
# Result: dist/oktoboot.app — see scripts/build_app.sh, which also zips it.
#
# Needs the generated data first (scripts/build_frequencies.py,
# scripts/build_doda.py): the databases and fonts aren't in git.

from pathlib import Path

from oktoboot import __version__

ROOT = Path(SPECPATH)
DATA = ROOT / "data"

for needed in ("doda.db", "frequencies.db", "fonts/Amiri-Regular.ttf", "icon.icns"):
    if not (DATA / needed).exists():
        raise SystemExit(f"missing data/{needed} — run the scripts/build_*.py first")

datas = [
    (str(DATA / "doda.db"), "data"),
    (str(DATA / "frequencies.db"), "data"),
    (str(DATA / "icon.icns"), "data"),
    (str(DATA / "fonts"), "data/fonts"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "NOTICE"), "."),
]

a = Analysis(
    [str(ROOT / "src" / "oktoboot" / "main.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=["AppKit", "Foundation"],
    # Qt parts the app never uses — keeps the download small.
    excludes=[
        "tkinter",
        "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtMultimedia", "PySide6.Qt3DCore", "PySide6.QtCharts",
        "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtOpenGL",
    ],
    noarchive=False,
)

# Qt plugins drag in whole frameworks the app never uses: the on-screen
# virtual keyboard plugin pulls QML/Quick, the PDF image plugin pulls QtPdf.
# Dropping them (and what only they need) saves ~25 MB.
_UNUSED_QT = (
    "QtQml", "QtQuick", "QtPdf", "QtVirtualKeyboard", "QtNetwork",
    "libqtvirtualkeyboardplugin", "libqpdf",
)
a.binaries = [b for b in a.binaries if not any(u in b[0] for u in _UNUSED_QT)]
a.datas = [d for d in a.datas if not any(u in d[0] for u in _UNUSED_QT)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="oktoboot",
    console=False,
    target_arch="arm64",
)
coll = COLLECT(exe, a.binaries, a.datas, name="oktoboot")

app = BUNDLE(
    coll,
    name="oktoboot.app",
    icon=str(DATA / "icon.icns"),
    bundle_identifier="com.oktoboot.oktoboot",
    version=__version__,
    info_plist={
        "CFBundleDisplayName": "oktoboot",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "© 2026 Sawt Dakhili — AGPL-3.0",
        "LSApplicationCategoryType": "public.app-category.productivity",
        # Python (Homebrew) and the PySide6 wheels inside are built for 15+.
        "LSMinimumSystemVersion": "15.0",
    },
)
