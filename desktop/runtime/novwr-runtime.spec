from importlib.util import find_spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path(SPECPATH).resolve().parents[1]
STATE_PROTO_SPEC = find_spec("_novwr_state_proto")
if STATE_PROTO_SPEC is None or STATE_PROTO_SPEC.origin is None:
    raise RuntimeError("_novwr_state_proto must be installed before packaging")

datas = [
    (str(ROOT / "alembic.ini"), "."),
    (str(ROOT / "alembic"), "alembic"),
    (str(ROOT / "web/dist"), "static"),
    (str(ROOT / "data/common_words"), "data/common_words"),
    (str(ROOT / "data/demo"), "data/demo"),
    (str(ROOT / "data/worldpacks"), "data/worldpacks"),
    (
        str(ROOT / "app/core/indexing/data"),
        "app/core/indexing/data",
    ),
]

analysis = Analysis(
    [str(ROOT / "app/desktop_runtime.py")],
    pathex=[str(ROOT)],
    binaries=[(STATE_PROTO_SPEC.origin, ".")],
    datas=datas,
    hiddenimports=[*collect_submodules("app"), "_novwr_state_proto"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="novwr-runtime",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    contents_directory="_internal",
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="novwr-runtime",
)
