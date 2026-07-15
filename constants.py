APP_NAME = "UPC Gen"
APP_VERSION = "1.0.0"

DEFAULT_DPI        = 300    # default raster resolution — 707×313 px, matches tec-it.com output
DEFAULT_QUALITY    = 95     # default JPEG quality
DEFAULT_FORMAT     = "EPS"  # "EPS", "JPEG", or "PNG"
DEFAULT_BAR_HEIGHT = 100    # bar height as a percentage of the standard UPC-A height

FORMAT_EXTENSIONS = {"EPS": ".eps", "JPEG": ".jpg", "PNG": ".png"}

# Regular Arial matches the website's digit style (regular width, not narrow).
def _find_arial() -> str:
    import sys as _sys, os as _os
    base = _sys._MEIPASS if getattr(_sys, 'frozen', False) else _os.path.dirname(_os.path.abspath(__file__))
    bundled = _os.path.join(base, 'fonts', 'arial.ttf')
    if _os.path.isfile(bundled):
        return bundled
    for p in (
        r'C:\Windows\Fonts\arial.ttf',
        '/Library/Fonts/Arial.ttf',
        '/System/Library/Fonts/Supplemental/Arial.ttf',
    ):
        if _os.path.isfile(p):
            return p
    return bundled  # will produce a clear FileNotFoundError at render time

BARCODE_FONT_PATH_PRIMARY  = _find_arial()
BARCODE_FONT_PATH_FALLBACK = BARCODE_FONT_PATH_PRIMARY

APP_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #2b2b2b;
}
QWidget {
    background-color: #2b2b2b;
    color: #e0e0e0;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
}
QGroupBox {
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 10px;
    font-size: 10pt;
    font-weight: bold;
    color: #aaaaaa;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
}
QLabel {
    border: none;
    background: transparent;
    font-size: 10pt;
    font-weight: normal;
    color: #e0e0e0;
}
QLineEdit, QTextEdit {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    border-radius: 3px;
    padding: 4px 6px;
    color: #e0e0e0;
    font-size: 10pt;
}
QLineEdit:focus, QTextEdit:focus {
    border: 1px solid #4a9eff;
}
QComboBox {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    border-radius: 3px;
    padding: 4px 6px;
    color: #e0e0e0;
    font-size: 10pt;
}
QComboBox:focus {
    border: 1px solid #4a9eff;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    selection-background-color: #1e6fb5;
    color: #e0e0e0;
    outline: none;
}
QPushButton {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    border-radius: 3px;
    padding: 5px 14px;
    font-size: 10pt;
    color: #e0e0e0;
}
QPushButton:hover {
    background-color: #4a4a4a;
    border-color: #6a6a6a;
}
QPushButton:pressed {
    background-color: #252525;
}
QPushButton#generate_btn {
    background-color: #1e6fb5;
    border-color: #2583cc;
    font-size: 11pt;
    font-weight: bold;
    padding: 8px 28px;
    color: white;
}
QPushButton#generate_btn:hover {
    background-color: #2583cc;
}
QPushButton#generate_btn:disabled {
    background-color: #383838;
    border-color: #4a4a4a;
    color: #606060;
}
QRadioButton {
    font-size: 10pt;
    font-weight: normal;
    spacing: 6px;
    color: #e0e0e0;
    background: transparent;
}
QRadioButton::indicator {
    width: 14px;
    height: 14px;
}
QProgressBar {
    border: 1px solid #4a4a4a;
    border-radius: 3px;
    background-color: #3c3c3c;
    text-align: center;
    font-size: 9pt;
    color: #e0e0e0;
    min-height: 18px;
    max-height: 18px;
}
QProgressBar::chunk {
    background-color: #1e6fb5;
    border-radius: 2px;
}
QScrollBar:vertical {
    background-color: #2b2b2b;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #555555;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background-color: #2b2b2b;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background-color: #555555;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
"""
