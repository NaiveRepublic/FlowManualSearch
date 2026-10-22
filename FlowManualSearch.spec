# PyInstaller recipe for Flow Manual Search  ->  dist\FlowManualSearch.exe
# Build with:  pyinstaller --noconfirm --clean FlowManualSearch.spec

a = Analysis(
    ["app/main.py"],
    pathex=["app"],
    datas=[
        ("app/data", "data"),          # index, page previews, manual PDF
        ("app/ui", "ui"),              # the search window
        ("app/synonyms.json", "."),    # built-in synonym list
    ],
    hiddenimports=["search_engine"],
    excludes=["tkinter", "matplotlib", "PIL", "pymupdf", "fitz", "wordllama",
              "safetensors", "torch", "pandas", "scipy", "IPython"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="FlowManualSearch",
    icon="app/icon.ico",
    console=False,      # no black console window
    upx=False,          # UPX compression triggers antivirus false alarms
)
