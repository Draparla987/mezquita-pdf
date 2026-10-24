# -*- mode: python ; coding: utf-8 -*-
# Construcción con PyInstaller:
#   macOS:   ./construir_app.sh            → dist/Mezquita PDF.app
#   Windows: pyinstaller MezquitaPDF.spec  → dist/Mezquita PDF/ (y el instalador con Inno Setup)
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ES_MAC = sys.platform == "darwin"
datos = (collect_data_files("pyhanko") + collect_data_files("pyhanko_certvalidator")
         + collect_data_files("qtawesome"))
ocultos = (collect_submodules("pyhanko") + collect_submodules("pyhanko_certvalidator") + ["qtawesome"]
           + (["AppKit", "Foundation", "Security", "objc"] if ES_MAC else []))

a = Analysis(
    ["main.py"],
    datas=datos,
    hiddenimports=ocultos,
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia"],
)
pyz = PYZ(a.pure)

if not ES_MAC:
    # Windows: la app (sin consola) y «mezquita-mcp.exe», el mismo programa con consola para que la
    # app de Claude pueda hablar con él por su entrada y salida estándar (--mcp).
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Mezquita PDF", console=False,
              icon="recursos/icono.ico")
    exe_mcp = EXE(pyz, a.scripts, [], exclude_binaries=True, name="mezquita-mcp", console=True,
                  icon="recursos/icono.ico")
    coll = COLLECT(exe, exe_mcp, a.binaries, a.datas, name="Mezquita PDF")
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Mezquita PDF",
              console=False, argv_emulation=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="Mezquita PDF")
    app = BUNDLE(
        coll,
        name="Mezquita PDF.app",
        icon="recursos/icono.icns",
        bundle_identifier="local.mezquitapdf.app",
        info_plist={
            "CFBundleDisplayName": "Mezquita PDF",
            "CFBundleShortVersionString": "2.10.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
            "LSMinimumSystemVersion": "11.0",
            "NSAppleEventsUsageDescription": "Mezquita PDF usa Mail u Outlook para crear un mensaje con el PDF adjunto.",
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Documento PDF",
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Default",
                "LSItemContentTypes": ["com.adobe.pdf"],
            }],
        },
    )
