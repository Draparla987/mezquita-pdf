# -*- mode: python ; coding: utf-8 -*-
# Construcción de "Mezquita PDF.app" con PyInstaller:  ./construir_app.sh
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datos = (collect_data_files("pyhanko") + collect_data_files("pyhanko_certvalidator")
         + collect_data_files("qtawesome"))
ocultos = (collect_submodules("pyhanko") + collect_submodules("pyhanko_certvalidator")
           + ["AppKit", "Foundation", "Security", "objc", "qtawesome"])

a = Analysis(
    ["main.py"],
    datas=datos,
    hiddenimports=ocultos,
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia"],
)
pyz = PYZ(a.pure)
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
        "CFBundleShortVersionString": "2.1.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "LSMinimumSystemVersion": "11.0",
        "NSAppleEventsUsageDescription": "Mezquita PDF usa Mail u Outlook para crear un mensaje con el PDF adjunto.",
        "CFBundleDocumentTypes": [{
            "CFBundleTypeName": "Documento PDF",
            "CFBundleTypeRole": "Editor",
            "LSHandlerRank": "Alternate",
            "LSItemContentTypes": ["com.adobe.pdf"],
        }],
    },
)
