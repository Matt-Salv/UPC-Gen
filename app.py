import time
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QThread, Signal, QUrl, QTimer
from PySide6.QtGui import QFont, QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLabel, QLineEdit, QTextEdit, QComboBox,
    QPushButton, QProgressBar, QRadioButton, QButtonGroup,
    QFileDialog, QSizePolicy, QSpacerItem, QStackedWidget,
    QMessageBox, QDialog, QApplication, QTabWidget, QSpinBox, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
)

from constants import (APP_NAME, APP_VERSION, DEFAULT_DPI, DEFAULT_QUALITY,
                       DEFAULT_FORMAT, DEFAULT_BAR_HEIGHT, FORMAT_EXTENSIONS)


_GITHUB_REPO = "Matt-Salv/UPC-Gen"


def _version_gt(a: str, b: str) -> bool:
    try:
        return tuple(int(x) for x in a.split(".")) > tuple(int(x) for x in b.split("."))
    except (ValueError, AttributeError):
        return False


class UpdateChecker(QThread):
    update_available = Signal(str, str)  # version, release_url

    def run(self):
        import urllib.request, json
        try:
            url = f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "UPCGen-App"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            tag = data.get("tag_name", "").lstrip("v")
            html_url = data.get("html_url", "")
            if tag and _version_gt(tag, APP_VERSION):
                self.update_available.emit(tag, html_url)
        except Exception:
            pass


class SkippedUpcsDialog(QDialog):
    def __init__(self, errors: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Skipped UPCs")
        self.setMinimumWidth(580)
        self.setMinimumHeight(320)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(QLabel(
            f"{len(errors)} UPC(s) skipped — fix the issues below and re-paste to retry:"
        ))

        table = QTableWidget(len(errors), 2)
        table.setHorizontalHeaderLabels(["UPC", "Reason"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.setFont(QFont("Courier New", 9))
        for row, (upc, reason) in enumerate(errors):
            table.setItem(row, 0, QTableWidgetItem(upc))
            table.setItem(row, 1, QTableWidgetItem(reason))
        table.resizeRowsToContents()
        layout.addWidget(table)

        self._upcs = [upc for upc, _ in errors]

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Copy UPCs to Clipboard")
        copy_btn.clicked.connect(self._copy)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(copy_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _copy(self):
        QApplication.clipboard().setText("\n".join(self._upcs))


class SheetColumnLoader(QThread):
    loaded = Signal(list)   # column name list
    failed = Signal(str)    # error message

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self):
        from generator import read_spreadsheet_columns
        try:
            self.loaded.emit(read_spreadsheet_columns(self._path))
        except Exception as e:
            self.failed.emit(str(e))


class GenerateWorker(QThread):
    progress = Signal(int, int, str)               # current, total, upc
    finished = Signal(int, int, int, list)         # generated, skipped_existing, skipped_errors, errors

    def __init__(self, jobs: list[tuple[str, Path]], dpi: int = DEFAULT_DPI,
                 quality: int = DEFAULT_QUALITY, fmt: str = DEFAULT_FORMAT,
                 bar_height_pct: int = DEFAULT_BAR_HEIGHT,
                 skip_existing: bool = False, parent=None):
        super().__init__(parent)
        self._jobs = jobs
        self._dpi = dpi
        self._quality = quality
        self._fmt = fmt
        self._bar_height_pct = bar_height_pct
        self._skip_existing = skip_existing
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        from generator import generate_barcode_image, validate_upc

        generated = 0
        skipped_existing = 0
        errors: list[tuple[str, str]] = []
        total = len(self._jobs)

        for i, (raw_upc, out_path) in enumerate(self._jobs):
            if self._cancelled:
                break
            self.progress.emit(i, total, raw_upc)
            try:
                if self._skip_existing and out_path.exists():
                    skipped_existing += 1
                    continue
                upc = validate_upc(raw_upc)
                generate_barcode_image(upc, out_path, dpi=self._dpi, quality=self._quality,
                                       fmt=self._fmt, bar_height_pct=self._bar_height_pct)
                generated += 1
            except Exception as e:
                errors.append((raw_upc, str(e)))

        self.finished.emit(generated, skipped_existing, len(errors), errors)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._settings = QSettings("UPCGen", "UPCGen")
        self._worker: GenerateWorker | None = None
        self._sheet_loader: SheetColumnLoader | None = None
        self._update_checker: UpdateChecker | None = None
        self._spreadsheet_path: Path | None = None
        self._col_select_upc: str = ""
        self._update_url: str = ""
        self._setup_ui()
        self._load_settings()
        self._schedule_update_check()

    # ------------------------------------------------------------------ setup

    def _setup_ui(self):
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumWidth(520)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Update notification bar — hidden until an update is detected
        self._update_bar = QFrame()
        self._update_bar.setStyleSheet(
            "QFrame { background-color: #1a4a82; border: none; }"
        )
        bar_row = QHBoxLayout(self._update_bar)
        bar_row.setContentsMargins(12, 6, 8, 6)
        self._update_bar_label = QLabel()
        self._update_bar_label.setStyleSheet(
            "color: #ffffff; font-size: 9pt; background: transparent;"
        )
        self._update_download_btn = QPushButton("Download")
        self._update_download_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.35); "
            "color: white; padding: 2px 10px; font-size: 9pt; border-radius: 3px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.28); }"
        )
        self._update_download_btn.clicked.connect(self._on_update_download)
        _dismiss = QPushButton("✕")
        _dismiss.setFixedWidth(28)
        _dismiss.setStyleSheet(
            "QPushButton { background: transparent; border: none; "
            "color: rgba(255,255,255,0.55); font-size: 11pt; }"
            "QPushButton:hover { color: white; }"
        )
        _dismiss.clicked.connect(self._update_bar.hide)
        bar_row.addWidget(self._update_bar_label)
        bar_row.addStretch()
        bar_row.addWidget(self._update_download_btn)
        bar_row.addWidget(_dismiss)
        self._update_bar.setVisible(False)
        root.addWidget(self._update_bar)

        tabs = QTabWidget()
        tabs.addTab(self._build_generate_tab(), "Generate")
        tabs.addTab(self._build_settings_tab(), "Settings")
        root.addWidget(tabs)

    def _build_generate_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(self._build_input_group())
        layout.addWidget(self._build_output_group())
        layout.addSpacerItem(QSpacerItem(0, 4, QSizePolicy.Minimum, QSizePolicy.Fixed))
        layout.addLayout(self._build_bottom())
        return w

    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(self._render_preview)

        group = QGroupBox("Image Output")
        form = QFormLayout(group)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Format — first, because it controls what else is enabled
        self._format_combo = QComboBox()
        self._format_combo.addItem("EPS — vector (.eps)", "EPS")
        self._format_combo.addItem("JPEG (.jpg)",          "JPEG")
        self._format_combo.addItem("PNG (.png)",           "PNG")
        self._format_combo.currentIndexChanged.connect(self._on_format_changed)
        form.addRow("Format:", self._format_combo)

        # Resolution — disabled for EPS (vector is resolution-independent)
        self._dpi_combo = QComboBox()
        for lbl, val in [("72 DPI", 72), ("96 DPI", 96), ("150 DPI", 150),
                         ("200 DPI", 200), ("300 DPI (default)", 300), ("600 DPI", 600)]:
            self._dpi_combo.addItem(lbl, val)
        self._dpi_combo.setCurrentIndex(4)  # 300 DPI
        self._dpi_combo.currentIndexChanged.connect(self._on_dpi_changed)
        self._dpi_row_label = QLabel("Resolution:")
        form.addRow(self._dpi_row_label, self._dpi_combo)

        # Bar height
        self._bar_height_spin = QSpinBox()
        self._bar_height_spin.setRange(50, 200)
        self._bar_height_spin.setValue(DEFAULT_BAR_HEIGHT)
        self._bar_height_spin.setSuffix("%")
        self._bar_height_spin.setSingleStep(5)
        self._bar_height_spin.valueChanged.connect(self._update_dims_label)
        form.addRow("Bar height:", self._bar_height_spin)

        # JPEG quality — disabled for EPS and PNG
        self._quality_spin = QSpinBox()
        self._quality_spin.setRange(1, 100)
        self._quality_spin.setValue(DEFAULT_QUALITY)
        self._quality_spin.setSuffix("%")
        self._quality_row_label = QLabel("JPEG quality:")
        form.addRow(self._quality_row_label, self._quality_spin)

        # Info label
        self._dims_label = QLabel()
        self._dims_label.setStyleSheet("color: #888888; font-size: 9pt;")
        form.addRow("", self._dims_label)

        self._skip_existing_chk = QCheckBox("Skip files that already exist in the output folder")
        form.addRow("", self._skip_existing_chk)

        self._open_folder_chk = QCheckBox("Open output folder when generation finishes")
        form.addRow("", self._open_folder_chk)

        restore_btn = QPushButton("Restore Defaults")
        restore_btn.clicked.connect(self._on_restore_defaults)
        form.addRow("", restore_btn)

        self._bar_height_spin.valueChanged.connect(self._preview_timer.start)
        self._format_combo.currentIndexChanged.connect(self._preview_timer.start)
        self._dpi_combo.currentIndexChanged.connect(self._preview_timer.start)

        layout.addWidget(group)

        # Preview toggle
        preview_row = QHBoxLayout()
        self._preview_btn = QPushButton("Show Preview")
        self._preview_btn.setCheckable(True)
        self._preview_btn.setFixedWidth(140)
        self._preview_btn.toggled.connect(self._on_preview_toggled)
        preview_row.addStretch()
        preview_row.addWidget(self._preview_btn)
        preview_row.addStretch()
        layout.addLayout(preview_row)

        # Preview panel
        self._preview_panel = QWidget()
        prev_lay = QVBoxLayout(self._preview_panel)
        prev_lay.setContentsMargins(0, 4, 0, 0)
        prev_lay.setSpacing(6)

        upc_row = QHBoxLayout()
        upc_row.addWidget(QLabel("Preview UPC:"))
        self._preview_upc_edit = QLineEdit("012345678905")
        self._preview_upc_edit.setFont(QFont("Courier New", 10))
        self._preview_upc_edit.setFixedWidth(180)
        self._preview_upc_edit.textChanged.connect(self._preview_timer.start)
        upc_row.addWidget(self._preview_upc_edit)
        upc_row.addStretch()
        prev_lay.addLayout(upc_row)

        self._preview_img_label = QLabel()
        self._preview_img_label.setAlignment(Qt.AlignCenter)
        self._preview_img_label.setMinimumHeight(80)
        self._preview_img_label.setStyleSheet(
            "background-color: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 3px;"
        )
        prev_lay.addWidget(self._preview_img_label)

        self._preview_eps_note = QLabel(
            "EPS output is fully vector; this preview renders as raster."
        )
        self._preview_eps_note.setStyleSheet("color: #666666; font-size: 8pt;")
        self._preview_eps_note.setAlignment(Qt.AlignCenter)
        self._preview_eps_note.setVisible(False)
        prev_lay.addWidget(self._preview_eps_note)

        self._preview_panel.setVisible(False)
        layout.addWidget(self._preview_panel)

        layout.addStretch()

        self._update_dims_label()
        return w

    def _on_format_changed(self):
        fmt = self._format_combo.currentData()
        is_raster = fmt != "EPS"
        is_jpeg   = fmt == "JPEG"
        self._dpi_combo.setEnabled(is_raster)
        self._dpi_row_label.setEnabled(is_raster)
        self._quality_spin.setEnabled(is_jpeg)
        self._quality_row_label.setEnabled(is_jpeg)
        self._update_dims_label()

    def _on_dpi_changed(self):
        self._update_dims_label()

    def _on_restore_defaults(self):
        self._format_combo.setCurrentIndex(0)    # EPS
        self._dpi_combo.setCurrentIndex(4)       # 300 DPI
        self._bar_height_spin.setValue(DEFAULT_BAR_HEIGHT)
        self._quality_spin.setValue(DEFAULT_QUALITY)
        self._skip_existing_chk.setChecked(False)
        self._open_folder_chk.setChecked(False)

    def _update_dims_label(self):
        fmt = self._format_combo.currentData()
        if fmt == "EPS":
            self._dims_label.setText("Vector — scales to any print size  ·  .eps")
        else:
            dpi = self._dpi_combo.currentData()
            h_s = self._bar_height_spin.value() / 100
            s   = dpi / 300
            w   = round(707 * s)
            h   = round(313 * s * h_s)
            ext = FORMAT_EXTENSIONS[fmt]
            self._dims_label.setText(f"Output image: {w} × {h} px  ·  {ext}")

    def _on_preview_toggled(self, checked: bool):
        self._preview_btn.setText("Hide Preview" if checked else "Show Preview")
        self._preview_panel.setVisible(checked)
        if checked:
            self._render_preview()

    def _render_preview(self):
        if not self._preview_panel.isVisible():
            return
        import io
        from generator import render_barcode_preview, validate_upc

        raw = self._preview_upc_edit.text().strip()
        try:
            upc = validate_upc(raw)
        except ValueError:
            self._preview_img_label.setText("Invalid UPC")
            return

        fmt = self._format_combo.currentData()
        dpi = self._dpi_combo.currentData() if fmt != "EPS" else 300
        bar_h = self._bar_height_spin.value()

        try:
            img = render_barcode_preview(upc, dpi=dpi, bar_height_pct=bar_h)
        except Exception as e:
            self._preview_img_label.setText(f"Render error: {e}")
            return

        buf = io.BytesIO()
        img.save(buf, "PNG")
        buf.seek(0)

        qimg = QImage()
        qimg.loadFromData(buf.getvalue())
        pixmap = QPixmap.fromImage(qimg)

        max_w = max(self._preview_img_label.width() - 16, 460)
        if pixmap.width() > max_w:
            pixmap = pixmap.scaledToWidth(max_w, Qt.SmoothTransformation)
        self._preview_img_label.setPixmap(pixmap)

        self._preview_eps_note.setVisible(fmt == "EPS")

    def _build_input_group(self) -> QGroupBox:
        group = QGroupBox("Input")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # Mode radio buttons
        mode_row = QHBoxLayout()
        self._radio_paste = QRadioButton("Paste UPC codes")
        self._radio_sheet = QRadioButton("Load from spreadsheet")
        self._radio_paste.setChecked(True)
        mode_row.addWidget(self._radio_paste)
        mode_row.addWidget(self._radio_sheet)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        self._radio_group = QButtonGroup(self)
        self._radio_group.addButton(self._radio_paste)
        self._radio_group.addButton(self._radio_sheet)
        self._radio_group.buttonClicked.connect(self._on_mode_changed)

        # Stacked: paste view / spreadsheet view
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_paste_widget())   # index 0
        self._stack.addWidget(self._build_sheet_widget())   # index 1
        layout.addWidget(self._stack)

        return group

    def _build_paste_widget(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lbl = QLabel("One UPC code per line (11 or 12 digits):")
        self._paste_edit = QTextEdit()
        self._paste_edit.setPlaceholderText(
            "026635437769\n030625257237\n012345678905"
        )
        self._paste_edit.setMinimumHeight(140)
        self._paste_edit.setMaximumHeight(220)
        self._paste_edit.setFont(QFont("Courier New", 10))
        lay.addWidget(lbl)
        lay.addWidget(self._paste_edit)
        return w

    def _build_sheet_widget(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # File row
        file_row = QHBoxLayout()
        self._sheet_path_edit = QLineEdit()
        self._sheet_path_edit.setPlaceholderText("Select an Excel or CSV file…")
        self._sheet_path_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._on_browse_spreadsheet)
        file_row.addWidget(self._sheet_path_edit)
        file_row.addWidget(browse_btn)
        form.addRow("Spreadsheet:", file_row)

        # UPC column
        self._upc_col_combo = QComboBox()
        self._upc_col_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        form.addRow("UPC column:", self._upc_col_combo)

        return w

    def _build_output_group(self) -> QGroupBox:
        group = QGroupBox("Output")
        form = QFormLayout(group)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        folder_row = QHBoxLayout()
        self._out_folder_edit = QLineEdit()
        self._out_folder_edit.setPlaceholderText("Select output folder…")
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._on_browse_output)
        folder_row.addWidget(self._out_folder_edit)
        folder_row.addWidget(browse_btn)
        form.addRow("Folder:", folder_row)

        hint = QLabel("Files named {upc}.ext — format and resolution set in Settings")
        hint.setStyleSheet("color: #888888; font-size: 9pt;")
        form.addRow("", hint)

        return group

    def _build_bottom(self) -> QVBoxLayout:
        lay = QVBoxLayout()
        lay.setSpacing(8)

        # Generate button centered
        btn_row = QHBoxLayout()
        self._generate_btn = QPushButton("Generate Barcodes")
        self._generate_btn.setObjectName("generate_btn")
        self._generate_btn.setFixedWidth(200)
        self._generate_btn.clicked.connect(self._on_generate)
        btn_row.addStretch()
        btn_row.addWidget(self._generate_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("")
        lay.addWidget(self._progress_bar)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet("color: #888888; font-size: 9pt;")
        lay.addWidget(self._status_label)

        # Copy skipped UPCs button — hidden until a run produces errors
        self._copy_skipped_btn = QPushButton("Copy Skipped UPCs…")
        self._copy_skipped_btn.setVisible(False)
        self._copy_skipped_btn.clicked.connect(self._on_copy_skipped)
        skip_row = QHBoxLayout()
        skip_row.addStretch()
        skip_row.addWidget(self._copy_skipped_btn)
        skip_row.addStretch()
        lay.addLayout(skip_row)

        self._skipped_errors: list[tuple[str, str]] = []
        return lay

    # --------------------------------------------------------- settings persist

    def _save_settings(self):
        s = self._settings
        s.setValue("mode", "sheet" if self._radio_sheet.isChecked() else "paste")
        s.setValue("paste_text", self._paste_edit.toPlainText())
        s.setValue("sheet_path", str(self._spreadsheet_path) if self._spreadsheet_path else "")
        s.setValue("upc_col", self._upc_col_combo.currentText())
        s.setValue("out_folder", self._out_folder_edit.text())
        s.setValue("format", self._format_combo.currentData())
        s.setValue("dpi", self._dpi_combo.currentData())
        s.setValue("bar_height", self._bar_height_spin.value())
        s.setValue("quality", self._quality_spin.value())
        s.setValue("skip_existing", self._skip_existing_chk.isChecked())
        s.setValue("open_folder", self._open_folder_chk.isChecked())
        s.sync()

    def _load_settings(self):
        s = self._settings
        mode = s.value("mode", "paste")
        if mode == "sheet":
            self._radio_sheet.setChecked(True)
            self._stack.setCurrentIndex(1)
        else:
            self._radio_paste.setChecked(True)
            self._stack.setCurrentIndex(0)

        saved_paste = s.value("paste_text", "")
        if saved_paste:
            self._paste_edit.setPlainText(saved_paste)

        saved_path = s.value("sheet_path", "")
        if saved_path and Path(saved_path).is_file():
            self._spreadsheet_path = Path(saved_path)
            self._sheet_path_edit.setText(saved_path)
            self._populate_columns(s.value("upc_col", ""))

        out = s.value("out_folder", "")
        if out:
            self._out_folder_edit.setText(out)

        dpi = int(s.value("dpi", DEFAULT_DPI))
        idx = self._dpi_combo.findData(dpi)
        if idx >= 0:
            self._dpi_combo.setCurrentIndex(idx)

        fmt = s.value("format", DEFAULT_FORMAT)
        fmt_idx = self._format_combo.findData(fmt)
        if fmt_idx >= 0:
            self._format_combo.setCurrentIndex(fmt_idx)

        self._bar_height_spin.setValue(int(s.value("bar_height", DEFAULT_BAR_HEIGHT)))
        self._quality_spin.setValue(int(s.value("quality", DEFAULT_QUALITY)))
        self._skip_existing_chk.setChecked(s.value("skip_existing", False, type=bool))
        self._open_folder_chk.setChecked(s.value("open_folder", False, type=bool))

    # ------------------------------------------------------------- event handlers

    def _on_mode_changed(self):
        self._stack.setCurrentIndex(1 if self._radio_sheet.isChecked() else 0)

    def _on_browse_spreadsheet(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select spreadsheet",
            str(self._spreadsheet_path.parent) if self._spreadsheet_path else "",
            "Spreadsheets (*.xlsx *.xls *.xlsm *.csv);;All files (*)",
        )
        if not path:
            return
        self._spreadsheet_path = Path(path)
        self._sheet_path_edit.setText(path)
        self._populate_columns("")

    def _populate_columns(self, select_upc: str):
        if self._sheet_loader and self._sheet_loader.isRunning():
            self._sheet_loader.quit()
            self._sheet_loader.wait(500)

        self._col_select_upc = select_upc

        self._upc_col_combo.clear()
        self._upc_col_combo.setEnabled(False)
        self._upc_col_combo.addItem("Loading columns…")

        self._sheet_loader = SheetColumnLoader(self._spreadsheet_path, parent=self)
        self._sheet_loader.loaded.connect(self._on_columns_loaded)
        self._sheet_loader.failed.connect(self._on_columns_failed)
        self._sheet_loader.start()

    def _on_columns_loaded(self, cols: list):
        self._upc_col_combo.clear()
        for col in cols:
            self._upc_col_combo.addItem(str(col))

        select_upc = self._col_select_upc
        if select_upc:
            idx = self._upc_col_combo.findText(select_upc)
            if idx >= 0:
                self._upc_col_combo.setCurrentIndex(idx)
        else:
            upc_lower = [str(c).lower() for c in cols]
            for keyword in ("upc", "barcode", "bar code", "ean", "gtin"):
                for i, name in enumerate(upc_lower):
                    if keyword in name:
                        self._upc_col_combo.setCurrentIndex(i)
                        break
                else:
                    continue
                break

        self._upc_col_combo.setEnabled(True)

    def _on_columns_failed(self, error: str):
        self._upc_col_combo.clear()
        self._upc_col_combo.setEnabled(True)
        QMessageBox.warning(self, "Could not read spreadsheet", error)

    def _on_browse_output(self):
        start = self._out_folder_edit.text() or ""
        folder = QFileDialog.getExistingDirectory(self, "Select output folder", start)
        if folder:
            self._out_folder_edit.setText(folder)

    def _on_generate(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._generate_btn.setText("Generate Barcodes")
            self._generate_btn.setObjectName("generate_btn")
            self._status_label.setText("Cancelled.")
            return

        jobs = self._build_job_list()
        if jobs is None:
            return  # validation failed, error already shown

        self._save_settings()
        self._copy_skipped_btn.setVisible(False)
        self._generate_btn.setText("Cancel")
        self._progress_bar.setRange(0, len(jobs))
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat(f"0 / {len(jobs)}")
        self._status_label.setText("Starting…")

        self._worker = GenerateWorker(
            jobs,
            dpi=self._dpi_combo.currentData(),
            quality=self._quality_spin.value(),
            fmt=self._format_combo.currentData(),
            bar_height_pct=self._bar_height_spin.value(),
            skip_existing=self._skip_existing_chk.isChecked(),
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _build_job_list(self) -> list[tuple[str, Path]] | None:
        out_folder_str = self._out_folder_edit.text().strip()
        if not out_folder_str:
            QMessageBox.warning(self, "No output folder", "Please select an output folder.")
            return None
        out_folder = Path(out_folder_str)

        if self._radio_paste.isChecked():
            text = self._paste_edit.toPlainText()
            codes = [line.strip() for line in text.splitlines() if line.strip()]
            if not codes:
                QMessageBox.warning(self, "No codes", "Paste at least one UPC code.")
                return None
            ext = FORMAT_EXTENSIONS[self._format_combo.currentData()]
            return [(code, out_folder / f"{code}{ext}") for code in codes]

        else:
            if not self._spreadsheet_path or not self._spreadsheet_path.is_file():
                QMessageBox.warning(self, "No spreadsheet", "Please select a spreadsheet file.")
                return None
            upc_col = self._upc_col_combo.currentText().strip()
            if not upc_col:
                QMessageBox.warning(self, "No UPC column", "Please select the UPC column.")
                return None

            from generator import read_upcs_from_spreadsheet
            try:
                upcs = read_upcs_from_spreadsheet(self._spreadsheet_path, upc_col)
            except Exception as e:
                QMessageBox.critical(self, "Error reading spreadsheet", str(e))
                return None

            if not upcs:
                QMessageBox.warning(self, "No data", "No UPC codes found in the selected column.")
                return None

            ext = FORMAT_EXTENSIONS[self._format_combo.currentData()]
            return [(upc_raw, out_folder / f"{upc_raw}{ext}") for upc_raw in upcs]

    # ------------------------------------------------------------- worker signals

    def _on_progress(self, current: int, total: int, upc: str):
        self._progress_bar.setValue(current)
        self._progress_bar.setFormat(f"{current} / {total}")
        self._status_label.setText(f"Generating {upc}…")

    def _on_finished(self, generated: int, skipped_existing: int, skipped_errors: int,
                     errors: list[tuple[str, str]]):
        self._generate_btn.setText("Generate Barcodes")
        total = self._progress_bar.maximum()
        self._progress_bar.setValue(total)
        self._progress_bar.setFormat(f"{total} / {total}")

        parts = [f"{generated} generated"]
        if skipped_existing:
            parts.append(f"{skipped_existing} already existed")
        if skipped_errors:
            parts.append(f"{skipped_errors} skipped")

        if errors:
            self._skipped_errors = errors
            self._copy_skipped_btn.setVisible(True)
            self._status_label.setText("Done — " + ", ".join(parts) + ".")
            self._status_label.setStyleSheet("color: #f0a030; font-size: 9pt;")
        else:
            self._skipped_errors = []
            self._copy_skipped_btn.setVisible(False)
            self._status_label.setText("Done — " + ", ".join(parts) + ".")
            self._status_label.setStyleSheet("color: #4caf50; font-size: 9pt;")

        self._worker = None

        if self._open_folder_chk.isChecked():
            out = self._out_folder_edit.text().strip()
            if out:
                QDesktopServices.openUrl(QUrl.fromLocalFile(out))

    def _on_copy_skipped(self):
        if self._skipped_errors:
            SkippedUpcsDialog(self._skipped_errors, self).exec()

    # ----------------------------------------------------------- update checker

    def _schedule_update_check(self):
        last = self._settings.value("last_update_check", 0.0, type=float)
        if time.time() - last > 86400:
            QTimer.singleShot(3000, self._run_update_check)
        self._update_check_timer = QTimer(self)
        self._update_check_timer.setInterval(86400 * 1000)
        self._update_check_timer.timeout.connect(self._run_update_check)
        self._update_check_timer.start()

    def _run_update_check(self):
        if self._update_checker and self._update_checker.isRunning():
            return
        self._settings.setValue("last_update_check", time.time())
        self._update_checker = UpdateChecker(self)
        self._update_checker.update_available.connect(self._on_update_available)
        self._update_checker.start()

    def _on_update_available(self, version: str, url: str):
        self._update_url = url
        self._update_bar_label.setText(
            f"UPC Gen v{version} is available — you're on v{APP_VERSION}."
        )
        self._update_bar.setVisible(True)

    def _on_update_download(self):
        if self._update_url:
            QDesktopServices.openUrl(QUrl(self._update_url))

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        self._save_settings()
        super().closeEvent(event)
