from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QGroupBox,
    QLineEdit, QFileDialog, QFormLayout
)
from PySide6.QtCore import Signal


class MaintenanceZone(QGroupBox):
    run_maintenance = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__("Tools", parent)
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

