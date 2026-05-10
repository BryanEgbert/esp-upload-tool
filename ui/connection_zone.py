from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QLabel, QGroupBox, QFormLayout
)
from PySide6.QtCore import Signal, QTimer
import serial.tools.list_ports
import subprocess
import re
from typing import Optional
from worker.provisioning_worker import ChipInfo

class ConnectionZone(QGroupBox):
    hardware_discovered = Signal(ChipInfo)
    discovery_failed = Signal(str)
    discovery_started = Signal()
    log_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Connection & Discovery", parent)
        self.init_ui()
        self.refresh_ports()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Port selection
        port_layout = QHBoxLayout()
        self.port_combo = QComboBox()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_ports)
        port_layout.addWidget(QLabel("COM Port:"))
        port_layout.addWidget(self.port_combo, 1)
        port_layout.addWidget(self.refresh_btn)
        layout.addLayout(port_layout)

        # Discovery button & Status
        discover_layout = QHBoxLayout()
        self.discover_btn = QPushButton("Discover Hardware")
        self.discover_btn.clicked.connect(self.discover_hardware)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-weight: bold;")
        discover_layout.addWidget(self.discover_btn)
        discover_layout.addWidget(self.status_label, 1)
        layout.addLayout(discover_layout)

        # Info display
        info_layout = QFormLayout()
        self.chip_label = QLabel("Unknown")
        self.flash_label = QLabel("Unknown")
        self.mac_label = QLabel("Unknown")
        info_layout.addRow("Detected Chip:", self.chip_label)
        info_layout.addRow("Flash Size:", self.flash_label)
        info_layout.addRow("MAC Address:", self.mac_label)
        layout.addLayout(info_layout)

        # Connect port change to auto-discovery
        self.port_combo.currentIndexChanged.connect(self.on_port_changed)

    def refresh_ports(self):
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(f"{port.device} ({port.description})", port.device)
        
        # Auto-select known ESP32 interfaces if possible
        for i in range(self.port_combo.count()):
            desc = self.port_combo.itemText(i).lower()
            if any(x in desc for x in ["cp210", "ch340", "usb-to-uart", "bridge", "jtag", "serial"]):
                self.port_combo.setCurrentIndex(i)
                # discovery will be triggered by currentIndexChanged
                return
        
        # If no auto-match but list is not empty, select first and discover
        if self.port_combo.count() > 0:
            self.port_combo.setCurrentIndex(0)

        self.port_combo.blockSignals(False)
    
    def start_initial_discovery(self):
        """Call this after all signals are connected in MainWindow."""
        if self.port_combo.count() > 0:
            self.chip_label.setText("Detecting...")
            self.flash_label.setText("Detecting...")
            self.mac_label.setText("Detecting...")
            QTimer.singleShot(0, self.discover_hardware)

    def on_port_changed(self):
        if self.port_combo.currentIndex() >= 0:
            # Clear old info while discovering
            self.chip_label.setText("Detecting...")
            self.flash_label.setText("Detecting...")
            self.mac_label.setText("Detecting...")
            self.discover_hardware()

    def get_selected_port(self) -> str:
        return self.port_combo.currentData()

    def discover_hardware(self):
        self.discovery_started.emit()
        port = self.get_selected_port()
        if not port:
            self.discovery_failed.emit("No COM port selected")
            return

        self.discover_btn.setEnabled(False)
        self.status_label_update("Discovering...", "cyan")

        try:
            # Run esptool flash-id (modern command)
            cmd = ["esptool", "--port", port, "flash-id"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                self.status_label_update("Discovery Failed", "#FF6B6B") # Light Red
                self.discovery_failed.emit(f"Discovery failed: {result.stderr}")
                return

            output = result.stdout
            # Strip ANSI escape sequences before logging
            ansi_escape = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
            clean_output = ansi_escape.sub('', output)
            self.log_message.emit(clean_output)
            
            # Regex patterns (made more robust)
            chip_match = re.search(r"(?:Detecting chip type\.\.\. |Chip is |Connected to )([\w-]+)", clean_output)
            flash_match = re.search(r"Detected flash size: (\d+\w+)", clean_output)
            mac_match = re.search(r"MAC:\s+([\w:]+)", clean_output)

            chip_type = chip_match.group(1).strip() if chip_match else "Unknown"
            # Normalize chip type for esptool commands (e.g. ESP32-S3 -> esp32s3)
            chip_type_cmd = chip_type.lower().replace("-", "").replace(" ", "")
            
            flash_size = flash_match.group(1).strip() if flash_match else "Unknown"
            mac_addr = mac_match.group(1).strip() if mac_match else "Unknown"

            self.chip_label.setText(chip_type)
            self.flash_label.setText(flash_size)
            self.mac_label.setText(mac_addr)

            if chip_type == "Unknown":
                 self.status_label_update("Partial Detection", "orange")
            else:
                 self.status_label_update("Ready", "#90EE90") # Light Green

            chip_info = ChipInfo(chip_type_cmd, flash_size, mac_addr)
            self.hardware_discovered.emit(chip_info)

        except Exception as e:
            self.status_label_update("Error", "#FF6B6B") # Light Red
            self.discovery_failed.emit(f"Error during discovery: {str(e)}")
        finally:
            self.discover_btn.setEnabled(True)

    def status_label_update(self, text: str, color: str = "white"):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
