#!/usr/bin/env python3

#  Python version of the KyDevTool flashing utility
#  Copyright (C) 2026 chkndrp
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

import logging
import signal
import sys

from pathlib import Path
from darkdetect import isDark

from PyQt6.QtCore import (
    QThread,
    QTimer,
    QPropertyAnimation,
    pyqtSignal,
    Qt
)

from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from PyQt6.QtGui import (
    QCloseEvent
)

from src.fastboot import (
    FASTBOOT_BIN,
    FastbootFlasher,
    FlashOptions,
    checkEnvironment,
    getFastbootDevices,
)

logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
STYLESHEET_BASE_PATH = SCRIPT_DIR / "src" / "qt.css"
STYLESHEET_DARK_PATH = SCRIPT_DIR / "src" / "qt_dark.css"
STYLESHEET_LIGHT_PATH = SCRIPT_DIR / "src" / "qt_light.css"


def loadStylesheet(is_dark: bool) -> str:
    """Load base and theme css file contents."""

    theme_path = STYLESHEET_DARK_PATH if is_dark else STYLESHEET_LIGHT_PATH
    try:
        base_css = STYLESHEET_BASE_PATH.read_text(
            encoding="utf-8"
        )
        theme_css = theme_path.read_text(
            encoding="utf-8"
        )

        return f"{base_css}\n{theme_css}"
    except OSError as e:
        logger.warning("Could not load stylesheet: %s", e)
        return ""


def getBootInfoTargets(tool_dir: Path) -> list[str]:
    """Get all bootinfo targets from the factory/ directory."""

    factory_dir = tool_dir / "factory"

    if not factory_dir.is_dir():
        return []

    return sorted(p.name for p in factory_dir.glob("bootinfo_*"))


class FlashWorker(QThread):
    """Worker thread for running fastboot operations."""

    LOG_SIGNAL = pyqtSignal(str, str)
    PROGRESS_SIGNAL = pyqtSignal(int, int)
    FINISHED_SIGNAL = pyqtSignal(bool)

    def __init__(self, options: FlashOptions):
        super().__init__()
        self.FLASHER = FastbootFlasher(options)

        options.LOG_CB, options.PROGRESS_CB = (
            self.LOG_SIGNAL.emit,
            self.PROGRESS_SIGNAL.emit,
        )

    def stop(self):
        """Stop the fastboot flashing process."""

        self.FLASHER.stop()

    def run(self):
        """Run the flash process."""

        self.FINISHED_SIGNAL.emit(self.FLASHER.flash())


class FlasherWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("KyDevTool-python")
        self.resize(620, 420)

        self.CURRENT_IS_DARK: bool | None = None
        self.applyTheme()

        self.THEME_TIMER = QTimer(self)
        self.THEME_TIMER.setInterval(2000)
        self.THEME_TIMER.timeout.connect(self.applyTheme)
        self.THEME_TIMER.start()

        self.IS_FLASHING = False
        self.WORKER: FlashWorker | None = None
        self.DEVICE_COMBO = QComboBox()
        self.REFRESH_BTN = QPushButton("Refresh")
        self.BOOTINFO_COMBO = QComboBox()
        self.IMAGE_EDIT = QLineEdit()
        self.IMAGE_BTN = QPushButton("Browse")
        self.REBOOT_CHECKBOX = QCheckBox("Reboot device after flashing")
        self.FLASH_BTN = QPushButton("Start Flashing")
        self.PROGRESS_BAR = QProgressBar()
        self.CONSOLE = QTextEdit()

        self.initUi()


    def applyTheme(self):
        """Apply stylesheet matching system theme"""

        is_dark = bool(isDark())

        if self.CURRENT_IS_DARK == is_dark:
            return

        first_run = self.CURRENT_IS_DARK is None
        self.CURRENT_IS_DARK = is_dark

        if first_run:
            self.setStyleSheet(loadStylesheet(is_dark))
            return

        old_pixmap = self.grab()
        self.setStyleSheet(loadStylesheet(is_dark))

        overlay = QLabel(self)
        overlay.setPixmap(old_pixmap)
        overlay.setGeometry(self.rect())
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        overlay.show()

        effect = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(300)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(overlay.deleteLater)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


    def initUi(self):
        """Initialize widgets and layouts."""

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(16)

        form_frame = QWidget()
        form = QFormLayout(form_frame)
        form.setSpacing(10)

        self.REFRESH_BTN.setObjectName("browseBtn")
        self.REFRESH_BTN.clicked.connect(self.refreshDevices)
        dev_layout = QHBoxLayout()
        dev_layout.addWidget(self.DEVICE_COMBO, stretch=1)
        dev_layout.addWidget(self.REFRESH_BTN)

        if targets := getBootInfoTargets(SCRIPT_DIR):
            self.BOOTINFO_COMBO.addItems(targets)
        else:
            self.BOOTINFO_COMBO.addItem("bootinfo_emmc.bin")

        self.IMAGE_BTN.setObjectName("browseBtn")
        self.IMAGE_BTN.clicked.connect(self.browseImage)
        img_layout = QHBoxLayout()
        img_layout.addWidget(self.IMAGE_EDIT)
        img_layout.addWidget(self.IMAGE_BTN)

        checkbox_layout = QHBoxLayout()
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        checkbox_layout.addWidget(
            self.REBOOT_CHECKBOX,
            alignment=Qt.AlignmentFlag.AlignVCenter
        )

        label_width = 130
        labels = [
            QLabel("Target Device"),
            QLabel("BootInfo Target"),
            QLabel("System Image"),
            QLabel("Advanced"),
        ]

        for lbl in labels:
            lbl.setFixedWidth(label_width)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        form.addRow(labels[0], dev_layout)
        form.addRow(labels[1], self.BOOTINFO_COMBO)
        form.addRow(labels[2], img_layout)
        form.addRow(labels[3], checkbox_layout)
        layout.addWidget(form_frame)

        self.FLASH_BTN.setFixedHeight(40)
        self.FLASH_BTN.clicked.connect(self.handleFlashAction)
        layout.addWidget(self.FLASH_BTN)

        self.PROGRESS_BAR.setFixedHeight(20)
        layout.addWidget(self.PROGRESS_BAR)

        self.CONSOLE.setReadOnly(True)
        layout.addWidget(self.CONSOLE)

        self.refreshDevices()


    def refreshDevices(self):
        """Refresh available fastboot devices"""

        if self.IS_FLASHING:
            return

        self.DEVICE_COMBO.clear()

        if devices := getFastbootDevices():
            self.DEVICE_COMBO.addItems(devices)
            self.FLASH_BTN.setEnabled(True)
        else:
            self.DEVICE_COMBO.addItem("No devices found")
            self.FLASH_BTN.setEnabled(False)


    def browseImage(self):
        """Open file manager dialog to select image or archive file."""

        # pylint: disable=line-too-long
        if file_path := QFileDialog.getOpenFileName(self,
            "Select System Image or Archive", 
            "", 
            "Supported Files (*.img *.bin *.tar.gz *.tgz *.zip);;Image Files (*.img *.bin);;Archives (*.tar.gz *.tgz *.zip);;All Files (*)"
        )[0]:
            self.IMAGE_EDIT.setText(file_path)


    def appendLog(self, message: str, color: str):
        """Append colored log entry to console view."""

        self.CONSOLE.append(f'<span style="color:{color};">{message}</span>')


    def updateProgress(self, current: int, total: int):
        """Update progress bar values."""

        self.PROGRESS_BAR.setMaximum(total)
        self.PROGRESS_BAR.setValue(current)


    def setUiFlashingState(self, flashing: bool):
        """Enable or disable input controls based on flashing status."""

        self.IS_FLASHING = flashing

        for widget in (
            self.DEVICE_COMBO,
            self.REFRESH_BTN,
            self.BOOTINFO_COMBO,
            self.IMAGE_EDIT,
            self.IMAGE_BTN,
            self.REBOOT_CHECKBOX,
        ):
            widget.setEnabled(not flashing)

        match flashing:
            case True:
                self.FLASH_BTN.setText("Stop Flashing")
                self.FLASH_BTN.setObjectName("stopBtn")
                self.FLASH_BTN.setEnabled(True)
            case False:
                self.FLASH_BTN.setText("Start Flashing")
                self.FLASH_BTN.setObjectName("")
                self.refreshDevices()

        self.FLASH_BTN.style().unpolish(self.FLASH_BTN)
        self.FLASH_BTN.style().polish(self.FLASH_BTN)


    def flashFinished(self, _success: bool):
        """Handle flash worker finished signal."""

        self.setUiFlashingState(False)


    def handleFlashAction(self):
        """Toggle between start and stop flash operations."""

        if self.IS_FLASHING:
            self.stopFlash()
        else:
            self.startFlash()


    def stopFlash(self):
        """Request flash worker termination."""

        reply = QMessageBox.warning(self,
            "Stop Flashing Process",
            "Are you sure you want to stop flashing?\n\n"
            + "Aborting during flash operations can write incomplete partition images",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes and self.WORKER is not None:
            self.FLASH_BTN.setEnabled(False)
            self.appendLog(
                "[Info] Stopping flashing process...",
                "#f6c177"
            )
            self.WORKER.stop()
            self.WORKER.wait()


    def startFlash(self):
        """Validate inputs and start flash worker thread."""

        device_serial = self.DEVICE_COMBO.currentText().strip()
        if not device_serial or device_serial == "No devices found":
            self.appendLog(
                "[Error] Target device is not selected.",
                "#eb6f92"
            )
            return

        image_path = Path(self.IMAGE_EDIT.text().strip())
        if not image_path.is_file():
            self.appendLog(
                "[Error] Select a valid system image file.", 
                "#eb6f92"
            )
            return

        bootinfo_path = SCRIPT_DIR / "factory" / self.BOOTINFO_COMBO.currentText()
        if not bootinfo_path.is_file():
            self.appendLog(
                "[Error] BootInfo target file does not exist.",
                "#eb6f92"
            )
            return

        self.CONSOLE.clear()
        self.PROGRESS_BAR.setValue(0)
        self.setUiFlashingState(True)

        options = FlashOptions(
            IMAGE_PATH=image_path,
            TOOL_DIR=SCRIPT_DIR,
            BOOTINFO_PATH=bootinfo_path,
            FASTBOOT_BIN=FASTBOOT_BIN,
            DEVICE_SERIAL=device_serial,
            REBOOT_AFTER_FLASH=self.REBOOT_CHECKBOX.isChecked(),
        )

        self.WORKER = FlashWorker(options)
        self.WORKER.LOG_SIGNAL.connect(self.appendLog)
        self.WORKER.PROGRESS_SIGNAL.connect(self.updateProgress)
        self.WORKER.FINISHED_SIGNAL.connect(self.flashFinished)
        self.WORKER.finished.connect(self.WORKER.deleteLater)
        self.WORKER.start()


    def closeEvent(self, event: QCloseEvent):
        """Handle window close event safely."""

        if self.IS_FLASHING:
            reply = QMessageBox.warning(
                self,
                "Flashing in Progress",
                "A flash operation is active. Do you want to abort and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes and self.WORKER is not None:
                self.WORKER.stop()
                self.WORKER.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    try:
        checkEnvironment(SCRIPT_DIR)
    except RuntimeError as e:
        logger.error(e)
        sys.exit(1)

    signal.signal(
        signal.SIGINT,
        signal.SIG_DFL
    )
    app = QApplication(sys.argv)

    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    window = FlasherWindow()
    window.show()

    sys.exit(app.exec())
