import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from constants import APP_STYLESHEET
from app import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
