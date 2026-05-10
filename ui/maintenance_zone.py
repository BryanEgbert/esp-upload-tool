from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QGroupBox,
    QLineEdit, QFileDialog, QFormLayout
)
from PySide6.QtCore import Signal


class MaintenanceZone(QGroupBox):
    run_maintenance = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__("Maintenance & Tools", parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Erase Flash
        self.erase_btn = QPushButton("ERASE FLASH")
        self.erase_btn.setStyleSheet("background-color: #f44336; color: white;")
        self.erase_btn.clicked.connect(lambda: self.run_maintenance.emit("erase_flash", {}))
        layout.addWidget(self.erase_btn)

        # eFuse Summary
        self.summary_btn = QPushButton("VIEW EFUSE SUMMARY")
        self.summary_btn.clicked.connect(lambda: self.run_maintenance.emit("efuse_summary", {}))
        layout.addWidget(self.summary_btn)

        # Image Info
        info_group = QGroupBox("Image Info")
        info_layout = QHBoxLayout(info_group)
        self.image_info_path_edit = QLineEdit()
        self.image_info_path_edit.setPlaceholderText("Select a .bin or .hex file to inspect...")
        self.image_info_browse_btn = QPushButton("Browse")
        self.image_info_browse_btn.setFixedWidth(70)
        self.image_info_browse_btn.clicked.connect(self.browse_image_info_file)
        self.image_info_run_btn = QPushButton("VIEW IMAGE INFO")
        self.image_info_run_btn.clicked.connect(self.on_image_info)
        info_layout.addWidget(self.image_info_path_edit)
        info_layout.addWidget(self.image_info_browse_btn)
        info_layout.addWidget(self.image_info_run_btn)
        layout.addWidget(info_group)

        # Read Flash
        read_group = QGroupBox("Read Flash Contents")
        read_layout = QFormLayout(read_group)
        self.read_addr_edit = QLineEdit("0x0")
        self.read_size_edit = QLineEdit("0x100000")
        self.read_output_btn = QPushButton("READ FLASH TO FILE")
        self.read_output_btn.clicked.connect(self.on_read_flash)
        read_layout.addRow("Address:", self.read_addr_edit)
        read_layout.addRow("Size:", self.read_size_edit)
        read_layout.addRow(self.read_output_btn)
        layout.addWidget(read_group)

    def browse_image_info_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Binary File", "", "Binary Files (*.bin *.hex)"
        )
        if file_path:
            self.image_info_path_edit.setText(file_path)

    def on_image_info(self):
        file_path = self.image_info_path_edit.text().strip()
        if not file_path:
            # Prompt if nothing was pre-selected
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select Binary File", "", "Binary Files (*.bin *.hex)"
            )
            if not file_path:
                return
            self.image_info_path_edit.setText(file_path)
        self.run_maintenance.emit("image_info", {"file_path": file_path})

    def on_read_flash(self):
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Save Flash Content", "", "Binary Files (*.bin)"
        )
        if output_path:
            params = {
                "address": self.read_addr_edit.text(),
                "size": self.read_size_edit.text(),
                "output_path": output_path
            }
            self.run_maintenance.emit("read_flash", params)


# ---------------------------------------------------------------------------

from PySide6.QtCore import QThread, Signal
from utils.subprocess_runner import SubprocessRunner


class MaintenanceWorker(QThread):
    log_message = Signal(str)
    status_update = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, task_type: str, params: dict):
        super().__init__()
        self.task_type = task_type
        self.params = params

    def run(self):
        try:
            if self.task_type == "erase_flash":
                self.run_erase_flash()
            elif self.task_type == "image_info":
                self.run_image_info()
            elif self.task_type == "read_flash":
                self.run_read_flash()
            elif self.task_type == "efuse_summary":
                self.run_efuse_summary()
            else:
                raise ValueError(f"Unknown maintenance task: {self.task_type}")
            self.finished.emit(True, f"Task '{self.task_type}' completed successfully.")
        except Exception as e:
            self.finished.emit(False, str(e))

    def run_efuse_summary(self):
        port = self.params.get("port")
        chip = self.params.get("chip")
        if not all([port, chip]):
            raise ValueError("Port and Chip type are required for efuse_summary")
        self.status_update.emit("Reading eFuse Summary...")
        cmd = ["espefuse", "--chip", chip, "--port", port, "summary"]
        if SubprocessRunner.run_command(cmd, self.log_message.emit) != 0:
            raise RuntimeError("eFuse summary failed")

    def run_erase_flash(self):
        port = self.params.get("port")
        if not port:
            raise ValueError("Port is required for erase_flash")
        self.status_update.emit("Erasing Flash...")
        cmd = ["esptool", "--port", port, "erase-flash"]
        if SubprocessRunner.run_command(cmd, self.log_message.emit) != 0:
            raise RuntimeError("Erase flash failed")

    def run_image_info(self):
        file_path = self.params.get("file_path")
        if not file_path:
            raise ValueError("File path is required for image_info")
        self.status_update.emit(f"Reading Image Info: {file_path}...")
        cmd = ["esptool", "image-info", file_path]
        if SubprocessRunner.run_command(cmd, self.log_message.emit) != 0:
            raise RuntimeError("Image info retrieval failed")

    def run_read_flash(self):
        port = self.params.get("port")
        chip = self.params.get("chip")
        address = self.params.get("address", "0x0")
        size = self.params.get("size")
        output_path = self.params.get("output_path")
        if not all([port, size, output_path]):
            raise ValueError("Port, Size, and Output Path are required for read_flash")
        self.status_update.emit("Reading Flash...")
        cmd = ["esptool", "--port", port]
        if chip:
            cmd.extend(["--chip", chip, "-b", "115200"])
        cmd.extend(["read-flash", address, size, output_path])
        if SubprocessRunner.run_command(cmd, self.log_message.emit) != 0:
            raise RuntimeError("Read flash failed")