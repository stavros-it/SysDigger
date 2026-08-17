# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for SysDigger.

Build:  pyinstaller sysdigger.spec --noconfirm --clean
Output: dist/SysDigger/SysDigger.exe  (--onedir, faster startup)

For enterprise deployment, sign the exe + all DLLs with signtool.exe
(see build.ps1).
"""

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = []

# -- pythonnet (clr) — .NET bridge for LibreHardwareMonitorLib --------------
tmp_d, tmp_b, tmp_h = collect_all("pythonnet")
datas += tmp_d; binaries += tmp_b; hiddenimports += tmp_h

# -- pywin32 / wmi / pythoncom ---------------------------------------------
tmp_d, tmp_b, tmp_h = collect_all("win32com")
datas += tmp_d; binaries += tmp_b; hiddenimports += tmp_h
hiddenimports += collect_submodules("wmi")
hiddenimports += collect_submodules("pythoncom")
hiddenimports += collect_submodules("win32evtlog")
hiddenimports += collect_submodules("win32api")

# -- PySide6 ----------------------------------------------------------------
tmp_d, tmp_b, tmp_h = collect_all("PySide6")
datas += tmp_d; binaries += tmp_b; hiddenimports += tmp_h

# -- psutil, requests, certifi ---------------------------------------------
hiddenimports += collect_submodules("psutil")
tmp_d, tmp_b, tmp_h = collect_all("certifi")
datas += tmp_d; binaries += tmp_b; hiddenimports += tmp_h

# -- Bundle read-only resources --------------------------------------------
_base = os.path.abspath(".")

# App icon
if os.path.exists(os.path.join(_base, "app.ico")):
    datas.append((os.path.join(_base, "app.ico"), "."))

# Nav + category icons
if os.path.isdir(os.path.join(_base, "icons")):
    datas.append((os.path.join(_base, "icons"), "icons"))

# PowerShell tool library
if os.path.isdir(os.path.join(_base, "tools source")):
    datas.append((os.path.join(_base, "tools source"), "tools source"))

# LHM DLLs (read-only baseline; lib/lhm_standalone/ is downloaded at runtime)
if os.path.isdir(os.path.join(_base, "lib")):
    for _f in os.listdir(os.path.join(_base, "lib")):
        _full = os.path.join(_base, "lib", _f)
        if os.path.isfile(_full) and not _f.startswith("."):
            datas.append((_full, "lib"))

# -- Analysis ---------------------------------------------------------------
a = Analysis(
    ["sysdigger.pyw"],
    pathex=[_base],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    runtime_hooks=["runtime_hook.py"],
    excludes=["tkinter", "test", "unittest", "pydoc"],
    noarchive=False,
    cipher=None,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SysDigger",
    console=False,
    icon="app.ico" if os.path.exists("app.ico") else None,
    uac_admin=True,
    version="version.txt",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="SysDigger",
    strip=False,
    upx=True,
    upx_exclude=[
        "python3*.dll",
        "pythonnet.dll",
        "clr.pyd",
        "vcruntime140.dll",
        "LibreHardwareMonitorLib.dll",
        "HidSharp.dll",
    ],
)
