from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QPushButton, QMessageBox, QTabWidget, QScrollArea, QSplitter
)
from PySide6.QtCore import Qt
from ui.connection_zone import ConnectionZone
from ui.config_zone import ConfigZone
from ui.log_zone import LogZone
from ui.maintenance_zone import MaintenanceZone
from worker.provisioning_worker import ProvisioningWorker, ChipInfo
from worker.maintenance_worker import MaintenanceWorker
from typing import Optional

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ESP32 Secure Factory Provisioning Tool")
        self.setMinimumSize(800, 900)
        
        self.chip_info: Optional[ChipInfo] = None
        self.worker: Optional[ProvisioningWorker] = None
        self.m_worker: Optional[MaintenanceWorker] = None

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 1. Connection Zone - Top (Persistent)
        self.conn_zone = ConnectionZone()
        main_layout.addWidget(self.conn_zone)

        # 2. Splitter for Top (Tabs) and Bottom (Logs)
        self.splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(self.splitter)

        # --- Top Half: Tabs ---
        self.tabs = QTabWidget()
        
        # Provisioning Tab (Scrollable)
        provision_scroll = QScrollArea()
        provision_scroll.setWidgetResizable(True)
        provision_content = QWidget()
        provision_layout = QVBoxLayout(provision_content)
        
        self.config_zone = ConfigZone()
        provision_layout.addWidget(self.config_zone)
        
        self.flash_btn = QPushButton("PROVISION & FLASH")
        self.flash_btn.setFixedHeight(60)
        self.flash_btn.setStyleSheet("font-weight: bold; font-size: 18px; background-color: #4CAF50; color: white;")
        self.flash_btn.clicked.connect(self.start_provisioning)
        provision_layout.addWidget(self.flash_btn)
        provision_layout.addStretch()
        
        provision_scroll.setWidget(provision_content)

        # Maintenance Tab (Scrollable)
        maintenance_scroll = QScrollArea()
        maintenance_scroll.setWidgetResizable(True)
        maintenance_content = QWidget()
        maintenance_layout = QVBoxLayout(maintenance_content)
        
        self.m_zone = MaintenanceZone()
        maintenance_layout.addWidget(self.m_zone)
        maintenance_layout.addStretch()
        
        maintenance_scroll.setWidget(maintenance_content)

        self.tabs.addTab(provision_scroll, "Provisioning")
        self.tabs.addTab(maintenance_scroll, "Maintenance & Tools")
        
        self.splitter.addWidget(self.tabs)

        # --- Bottom Half: Logs ---
        self.log_zone = LogZone()
        self.splitter.addWidget(self.log_zone)

        # Set initial splitter sizes (50/50 split)
        self.splitter.setSizes([450, 450])

        # Signals
        self.conn_zone.discovery_started.connect(self.on_discovery_started)
        self.conn_zone.hardware_discovered.connect(self.on_hardware_discovered)
        self.conn_zone.discovery_failed.connect(self.on_discovery_failed)
        self.conn_zone.log_message.connect(self.log_zone.append_log)
        self.m_zone.run_maintenance.connect(self.start_maintenance)

        self.conn_zone.start_initial_discovery()

    def on_discovery_started(self):
        self.chip_info = None
        self.log_zone.set_status("Detecting Hardware...")

    def on_hardware_discovered(self, info: ChipInfo):
        self.chip_info = info

    def on_discovery_failed(self, error: str):
        self.chip_info = None
        QMessageBox.warning(self, "Discovery Failed", error)
        self.log_zone.append_log(f"Discovery Error: {error}")

    def start_provisioning(self):
        if not self.chip_info:
            QMessageBox.warning(self, "Missing Hardware", "Please discover hardware first.")
            return

        config = self.config_zone.get_config()
        if not config["flash_files"]:
            QMessageBox.warning(self, "Missing Files", "Please add at least one flash file with an address.")
            return
        
        seen = {}
        for addr_str, file_path in config["flash_files"]:
            try:
                addr_int = int(addr_str, 0)
            except ValueError:
                QMessageBox.warning(
                    self, "Invalid Address",
                    f"Address '{addr_str}' for file '{file_path}' is not a valid number."
                )
                return
            if addr_int in seen:
                QMessageBox.warning(
                    self, "Duplicate Address",
                    f"Address {addr_str} is used by both:\n"
                    f"  • {seen[addr_int]}\n"
                    f"  • {file_path}\n\n"
                    f"Each file must have a unique flash address."
                )
                return

            seen[addr_int] = file_path


        port = self.conn_zone.get_selected_port()
        if not port:
            QMessageBox.warning(self, "Missing Port", "Please select a COM port.")
            return

        irreversible_opts = []
        if not config.get("skip_efuse_burning", False):
            if config["enable_flash_encryption"]: irreversible_opts.append("Flash Encryption")
            if config["enable_secure_boot"]: irreversible_opts.append("Secure Boot")
            if config["is_factory_mode"]:
                if config["disable_jtag"]: irreversible_opts.append("Disable JTAG")
                if config["disable_uart"]: irreversible_opts.append("Disable UART Download Mode")

        if irreversible_opts:
            msg = "The following operations are IRREVERSIBLE and will permanently change the hardware:\n\n"
            msg += "\n".join([f"• {opt}" for opt in irreversible_opts])
            msg += "\n\nAre you absolutely sure you want to proceed?"
            
            reply = QMessageBox.question(
                self, "Confirm Irreversible Operations", msg,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        self.log_zone.clear_logs()
        self.set_ui_enabled(False)

        self.worker = ProvisioningWorker(
            port=port,
            chip_info=self.chip_info,
            **config
        )
        
        self.worker.log_message.connect(self.log_zone.append_log)
        self.worker.status_update.connect(self.log_zone.set_status)
        self.worker.finished.connect(self.on_provisioning_finished)
        
        self.worker.start()

    def on_provisioning_finished(self, success: bool, message: str):
        self.set_ui_enabled(True)
        if success:
            QMessageBox.information(self, "Success", message)
            self.log_zone.set_status("Provisioning Successful")
        else:
            QMessageBox.critical(self, "Error", f"Provisioning Failed: {message}")
            self.log_zone.set_status("Provisioning Failed")

    def start_maintenance(self, task_type: str, params: dict):
        port = self.conn_zone.get_selected_port()
        
        if task_type in ["erase_flash", "read_flash", "efuse_summary"]:
            if not port:
                QMessageBox.warning(self, "Missing Port", "Please select a COM port.")
                return
            params["port"] = port
            
            if task_type == "efuse_summary" and not self.chip_info:
                QMessageBox.warning(self, "Missing Chip Info", "Please discover hardware first to view eFuse summary.")
                return
                
            if self.chip_info:
                params["chip"] = self.chip_info.chip_type

        if task_type == "image_info" and not params.get("file_path"):
            return

        if task_type == "erase_flash":
            reply = QMessageBox.question(
                self, "Confirm Erase", "Are you sure you want to ERASE the entire flash?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                return


        self.log_zone.clear_logs()
        self.set_ui_enabled(False)

        self.m_worker = MaintenanceWorker(task_type, params)
        self.m_worker.log_message.connect(self.log_zone.append_log)
        self.m_worker.status_update.connect(self.log_zone.set_status)
        self.m_worker.finished.connect(self.on_maintenance_finished)
        self.m_worker.start()

    def on_maintenance_finished(self, success: bool, message: str):
        self.set_ui_enabled(True)
        if success:
            QMessageBox.information(self, "Success", message)
            self.log_zone.set_status("Task Completed")
        else:
            QMessageBox.critical(self, "Error", message)
            self.log_zone.set_status("Task Failed")

    def set_ui_enabled(self, enabled: bool):
        self.conn_zone.setEnabled(enabled)
        self.config_zone.setEnabled(enabled)
        self.m_zone.setEnabled(enabled)
        self.flash_btn.setEnabled(enabled)

    def closeEvent(self, event):
        """Save configuration on exit."""
        self.config_zone.get_config()
        super().closeEvent(event)
