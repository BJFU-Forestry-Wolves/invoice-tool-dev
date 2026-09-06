from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata


datas = collect_data_files("paddleocr") + collect_data_files("paddlex")
for distribution in (
    "paddleocr",
    "paddlepaddle",
    "paddlex",
    "Pillow",
    "imagesize",
    "opencv-contrib-python",
    "pyclipper",
    "pypdfium2",
    "python-bidi",
    "shapely",
    "psutil",
):
    datas += copy_metadata(distribution, recursive=True)

datas += [
    ("models/manifest.json", "models"),
    ("config/release.json", "config"),
    ("order_date/rules", "order_date/rules"),
]
binaries = collect_dynamic_libs("paddle")
hiddenimports = [
    "paddleocr._pipelines.ocr",
    "paddlex.inference.pipelines.ocr",
    "paddlex.inference.pipelines.doc_preprocessor",
    "paddlex.inference.models.image_classification",
    "paddlex.inference.models.text_detection",
    "paddlex.inference.models.text_recognition",
    "paddlex.inference.models.runners.paddle_static",
    "paddlex.inference.models.engines.paddle",
]

a = Analysis(
    ["invoice_attachment_gui.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    runtime_hooks=["p0/paddlex_runtime_hook.py"],
    excludes=[
        "IPython",
        "matplotlib",
        "modelscope",
        "notebook",
        "paddle.jit.sot",
        "paddle.tensorrt",
        "pytest",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="invoice_attachment_tool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    manifest="app.manifest",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="invoice_attachment_tool",
)
