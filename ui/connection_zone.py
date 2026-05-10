from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QLabel, QGroupBox, QFormLayout
)
from PySide6.QtCore import Signal, QTimer
import serial.tools.list_ports
import re
from typing import Optional
from worker.provisioning_worker import ChipInfo
import esptool.cmds
from esptool.logger import log, EsptoolLogger
from utils.signal_logger import SignalLogger

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

        output_buffer = []
        def capture_log(msg):
            output_buffer.append(msg)

        # Redirect esptool output to our local buffer
        SignalLogger._handler = capture_log
        log.set_logger(SignalLogger())

        try:
            with esptool.cmds.detect_chip(port=port) as esp:
                esp.connect()
                esptool.cmds.attach_flash(esp)
                esptool.cmds.flash_id(esp)
                esptool.cmds.read_mac(esp)
                esptool.cmds.get_security_info(esp)
                
                clean_output = "\n".join(output_buffer)
                self.log_message.emit(clean_output)
                
                flash_match = re.search(r"Detected flash size: (\d+\w+)", clean_output)
                mac_match = re.search(r"MAC:\s+([\w:]+)", clean_output)

                # Normalize chip type for esptool commands (e.g. ESP32-S3 -> esp32s3)
                chip_type_cmd = esp.CHIP_NAME.lower().replace("-", "").replace(" ", "")
                
                flash_size = flash_match.group(1).strip() if flash_match else "Unknown"
                mac_addr = mac_match.group(1).strip() if mac_match else "Unknown"

                self.chip_label.setText(esp.CHIP_NAME)
                self.flash_label.setText(flash_size)
                self.mac_label.setText(mac_addr)

                if esp.CHIP_NAME == "Unknown":
                     self.status_label_update("Partial Detection", "orange")
                else:
                     self.status_label_update("Ready", "#90EE90") # Light Green

                chip_info = ChipInfo(chip_type_cmd, flash_size, mac_addr)
                self.hardware_discovered.emit(chip_info)

        except Exception as e:
            self.status_label_update("Error", "#FF6B6B") # Light Red
            clean_output = "\n".join(output_buffer)
            if clean_output:
                self.log_message.emit("Capture before failure:\n" + clean_output)
            self.discovery_failed.emit(f"Error during discovery: {str(e)}")
        finally:
            # Restore logger
            log.__class__ = EsptoolLogger
            SignalLogger._handler = None
            self.discover_btn.setEnabled(True)

    def status_label_update(self, text: str, color: str = "white"):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
