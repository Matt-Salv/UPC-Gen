import sys


def _smoke_test():
    """
    Headless verification run in CI after a PyInstaller build.
    Exercises the full barcode pipeline without launching the GUI.
    Exits 0 on success, 1 on any failure.
    """
    import traceback
    try:
        # Core dependencies
        from constants import APP_VERSION, BARCODE_FONT_PATH_PRIMARY
        from generator import validate_upc, render_barcode_preview, _generate_eps
        from pathlib import Path
        import tempfile, os

        # Font must be resolvable
        assert os.path.isfile(BARCODE_FONT_PATH_PRIMARY), \
            f"Font not found: {BARCODE_FONT_PATH_PRIMARY}"

        # Raster pipeline
        upc = validate_upc("012345678905")
        img = render_barcode_preview(upc, dpi=300, bar_height_pct=100)
        assert img.size == (707, 313), f"Unexpected image size: {img.size}"

        # EPS pipeline
        with tempfile.NamedTemporaryFile(suffix=".eps", delete=False) as f:
            tmp = Path(f.name)
        try:
            _generate_eps(upc, tmp, bar_height_pct=100)
            assert tmp.stat().st_size > 500, "EPS file suspiciously small"
        finally:
            tmp.unlink(missing_ok=True)

        # Verify bundled dependencies are importable
        import importlib
        for mod in ("pandas", "openpyxl", "PySide6.QtWidgets"):
            importlib.import_module(mod)

        print(f"UPC Gen v{APP_VERSION} smoke test passed")
        sys.exit(0)

    except Exception:
        traceback.print_exc()
        sys.exit(1)


def _app_icon():
    import os
    from PySide6.QtGui import QIcon
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, 'assets', 'icon.png')
    return QIcon(path) if os.path.isfile(path) else QIcon()


def main():
    if "--smoke-test" in sys.argv:
        _smoke_test()

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from constants import APP_STYLESHEET
    from app import MainWindow

    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app.setWindowIcon(_app_icon())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
