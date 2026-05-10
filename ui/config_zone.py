from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox,
    QFileDialog, QRadioButton, QButtonGroup, QCheckBox, QFormLayout,
    QLineEdit, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt
from utils.config_manager import ConfigManager


class FlashFileEntry(QWidget):
    """A single row representing one binary file to flash with its address."""

    def __init__(self, parent=None, on_remove=None):
        super().__init__(parent)
        self._on_remove = on_remove
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        # Address field
        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText("0x0")
        self.address_edit.setFixedWidth(90)

        # File path field
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Select binary file (.bin or .hex)...")

        # Browse button
        browse_btn = QPushButton("Browse")
        browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(self._browse)

        # Remove button
        remove_btn = QPushButton("✕")
        remove_btn.setFixedWidth(30)
        remove_btn.setToolTip("Remove this entry")
        remove_btn.clicked.connect(self._remove)

        layout.addWidget(QLabel("Addr:"))
        layout.addWidget(self.address_edit)
        layout.addWidget(self.path_edit)
        layout.addWidget(browse_btn)
        layout.addWidget(remove_btn)

    def _browse(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Binary File", "", "Binary Files (*.bin *.hex)"
        )
        if file_path:
            self.path_edit.setText(file_path)

    def _remove(self):
        if self._on_remove:
            self._on_remove(self)

    def get_entry(self):
        """Returns (address_str, file_path) or None if incomplete."""
        addr = self.address_edit.text().strip()
        path = self.path_edit.text().strip()
        if not addr or not path:
            return None
        return addr, path

    def get_data(self):
        """Returns (address_str, file_path) even if incomplete."""
        return self.address_edit.text().strip(), self.path_edit.text().strip()


class FlashFilesWidget(QWidget):
    """Widget that manages a dynamic list of (address, binary file) entries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[FlashFileEntry] = []
        self._init_ui()

    def _init_ui(self):
        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("Flash Files"))
        add_btn = QPushButton("+ Add File")
        add_btn.setFixedWidth(90)
        add_btn.clicked.connect(self.add_entry)
        header.addStretch()
        header.addWidget(add_btn)
        self._outer_layout.addLayout(header)

        # Scroll area for entries
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.Shape.StyledPanel)
        self._scroll_area.setMaximumHeight(200)

        self._entries_container = QWidget()
        self._entries_layout = QVBoxLayout(self._entries_container)
        self._entries_layout.setContentsMargins(4, 4, 4, 4)
        self._entries_layout.setSpacing(2)
        self._entries_layout.addStretch()

        self._scroll_area.setWidget(self._entries_container)
        self._outer_layout.addWidget(self._scroll_area)

        # Add default common entries
        self._add_default_entries()

    def _add_default_entries(self):
        defaults = [
            ("0x0",     "Bootloader"),
            ("0x8000",  "Partition Table"),
            ("0x10000", "Application"),
        ]
        for addr, label in defaults:
            entry = self.add_entry()
            entry.address_edit.setText(addr)
            entry.path_edit.setPlaceholderText(f"Select {label} binary (.bin or .hex)...")

    def clear_entries(self):
        for entry in self._entries[:]:
            self._remove_entry(entry)

    def set_flash_files(self, files: list[tuple[str, str]]):
        """Populates the widget with the given (address, file_path) pairs."""
        if files is None:
            return
        self.clear_entries()
        for addr, path in files:
            entry = self.add_entry()
            entry.address_edit.setText(addr)
            entry.path_edit.setText(path)

    def add_entry(self) -> FlashFileEntry:
        entry = FlashFileEntry(on_remove=self._remove_entry)
        self._entries.append(entry)
        # Insert before the stretch
        self._entries_layout.insertWidget(self._entries_layout.count() - 1, entry)
        return entry

    def _remove_entry(self, entry: FlashFileEntry):
        if entry in self._entries:
            self._entries.remove(entry)
            self._entries_layout.removeWidget(entry)
            entry.deleteLater()

    def get_flash_files(self) -> list[tuple[str, str]]:
        """Returns list of (address, file_path) for all complete entries."""
        result = []
        for entry in self._entries:
            data = entry.get_entry()
            if data:
                result.append(data)
        return result

    def get_all_entries(self) -> list[tuple[str, str]]:
        """Returns list of (address, file_path) for all entries, even incomplete."""
        return [entry.get_data() for entry in self._entries]


class ConfigZone(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Configuration & Operation", parent)
        self.init_ui()
        self.load_config()

    def load_config(self):
        config = ConfigManager.get_last_config()
        if config:
            self.set_config(config)

    def set_config(self, config: dict):
        if "flash_files" in config:
            self.flash_files_widget.set_flash_files(config["flash_files"])
        
        if "is_factory_mode" in config:
            if config["is_factory_mode"]:
                self.factory_mode_rb.setChecked(True)
            else:
                self.proto_mode_rb.setChecked(True)
        
        if "use_static_key" in config:
            if config["use_static_key"]:
                self.static_key_rb.setChecked(True)
            else:
                self.auto_key_rb.setChecked(True)

        if "fe_static_key_path" in config:
            self.fe_key_path_edit.setText(config["fe_static_key_path"])
        if "sb_static_key_path" in config:
            self.sb_key_path_edit.setText(config["sb_static_key_path"])
        
        if "enable_flash_encryption" in config:
            self.enc_cb.setChecked(config["enable_flash_encryption"])
        if "enable_secure_boot" in config:
            self.sb_cb.setChecked(config["enable_secure_boot"])
        
        if "disable_jtag" in config:
            self.disable_jtag_cb.setChecked(config["disable_jtag"])
        if "disable_uart" in config:
            self.disable_uart_cb.setChecked(config["disable_uart"])

        if "skip_efuse_burning" in config:
            if config["skip_efuse_burning"]:
                self.skip_efuse_exec_rb.setChecked(True)
        
        if "virtual" in config:
            if config["virtual"]:
                self.virtual_exec_rb.setChecked(True)
            elif not config.get("skip_efuse_burning", False):
                self.normal_exec_rb.setChecked(True)

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Flash Files section
        self.flash_files_widget = FlashFilesWidget()
        layout.addWidget(self.flash_files_widget)

        # Operation Mode
        mode_group = QGroupBox("Operation Mode")
        mode_layout = QHBoxLayout(mode_group)
        self.proto_mode_rb = QRadioButton("Prototyping Mode")
        self.factory_mode_rb = QRadioButton("Factory Mode (Production)")
        self.proto_mode_rb.setChecked(True)
        mode_layout.addWidget(self.proto_mode_rb)
        mode_layout.addWidget(self.factory_mode_rb)
        layout.addWidget(mode_group)

        # Execution Mode Group
        exec_group = QGroupBox("Execution Mode")
        exec_layout = QHBoxLayout(exec_group)
        self.normal_exec_rb = QRadioButton("Normal Mode")
        self.virtual_exec_rb = QRadioButton("Virtual Mode (Simulate eFuse)")
        self.skip_efuse_exec_rb = QRadioButton("Skip eFuse Burning")
        self.normal_exec_rb.setChecked(True)
        
        exec_layout.addWidget(self.normal_exec_rb)
        exec_layout.addWidget(self.virtual_exec_rb)
        exec_layout.addWidget(self.skip_efuse_exec_rb)
        layout.addWidget(exec_group)

        # Security Toggles
        sec_layout = QHBoxLayout()
        self.enc_cb = QCheckBox("Enable Flash Encryption (Irreversible)")
        self.sb_cb = QCheckBox("Enable Secure Boot (Irreversible)")
        sec_layout.addWidget(self.enc_cb)
        sec_layout.addWidget(self.sb_cb)
        layout.addLayout(sec_layout)

        # Key Management
        self.key_group = QGroupBox("Key Management")
        key_layout = QVBoxLayout(self.key_group)
        self.auto_key_rb = QRadioButton("Auto-Generate Unique Key")
        self.static_key_rb = QRadioButton("Select Static Key")
        self.auto_key_rb.setChecked(True)
        key_layout.addWidget(self.auto_key_rb)
        key_layout.addWidget(self.static_key_rb)

        self.static_key_container = QWidget()
        self.static_key_form = QFormLayout(self.static_key_container)

        # Flash Encryption Key Input
        self.fe_key_path_edit = QLineEdit()
        self.fe_key_path_edit.setPlaceholderText("Select FE key .bin file...")
        self.fe_key_browse_btn = QPushButton("Browse")
        self.fe_key_browse_btn.clicked.connect(self.browse_fe_key)
        fe_layout = QHBoxLayout()
        fe_layout.addWidget(self.fe_key_path_edit)
        fe_layout.addWidget(self.fe_key_browse_btn)
        self.fe_row_label = QLabel("FE Key:")
        self.static_key_form.addRow(self.fe_row_label, fe_layout)

        # Secure Boot Key Input
        self.sb_key_path_edit = QLineEdit()
        self.sb_key_path_edit.setPlaceholderText("Select secure boot key .pem file...")
        self.sb_key_browse_btn = QPushButton("Browse")
        self.sb_key_browse_btn.clicked.connect(self.browse_sb_key)
        sb_layout = QHBoxLayout()
        sb_layout.addWidget(self.sb_key_path_edit)
        sb_layout.addWidget(self.sb_key_browse_btn)
        self.sb_row_label = QLabel("Secure Boot Key:")
        self.static_key_form.addRow(self.sb_row_label, sb_layout)

        key_layout.addWidget(self.static_key_container)
        layout.addWidget(self.key_group)

        # Hardware Lockdown
        self.lockdown_group = QGroupBox("Hardware Lockdown (Irreversible)")
        lockdown_layout = QVBoxLayout(self.lockdown_group)
        self.disable_jtag_cb = QCheckBox("Disable JTAG (Irreversible)")
        self.disable_uart_cb = QCheckBox("Disable UART Download Mode (Irreversible)")
        lockdown_layout.addWidget(self.disable_jtag_cb)
        lockdown_layout.addWidget(self.disable_uart_cb)
        layout.addWidget(self.lockdown_group)

        # Connections for dynamic UI
        self.static_key_rb.toggled.connect(self.update_key_ui)
        self.factory_mode_rb.toggled.connect(self.update_mode_ui)
        self.enc_cb.toggled.connect(self.update_sec_ui)
        self.sb_cb.toggled.connect(self.update_sec_ui)

        self.update_key_ui()
        self.update_mode_ui()
        self.update_sec_ui()

        # Save Button
        self.save_btn = QPushButton("Save Configuration")
        self.save_btn.clicked.connect(self.save_current_config)
        self.save_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        layout.addWidget(self.save_btn)

    def save_current_config(self):
        """Manually save the current UI state to disk."""
        full_config = {
            "flash_files": self.flash_files_widget.get_all_entries(),
            "is_factory_mode": self.factory_mode_rb.isChecked(),
            "use_static_key": self.static_key_rb.isChecked(),
            "fe_static_key_path": self.fe_key_path_edit.text(),
            "sb_static_key_path": self.sb_key_path_edit.text(),
            "enable_flash_encryption": self.enc_cb.isChecked(),
            "enable_secure_boot": self.sb_cb.isChecked(),
            "skip_efuse_burning": self.skip_efuse_exec_rb.isChecked(),
            "disable_jtag": self.disable_jtag_cb.isChecked(),
            "disable_uart": self.disable_uart_cb.isChecked(),
            "virtual": self.virtual_exec_rb.isChecked()
        }
        ConfigManager.save_last_config(full_config)

    def browse_fe_key(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Flash Encryption Key", "", "Binary Files (*.bin)")
        if file_path:
            self.fe_key_path_edit.setText(file_path)

    def browse_sb_key(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Secure Boot Key", "", "PEM Files (*.pem)")
        if file_path:
            self.sb_key_path_edit.setText(file_path)

    def update_key_ui(self):
        self.static_key_container.setVisible(self.static_key_rb.isChecked())

    def update_mode_ui(self):
        self.lockdown_group.setVisible(self.factory_mode_rb.isChecked())

    def update_sec_ui(self):
        enc_enabled = self.enc_cb.isChecked()
        sb_enabled = self.sb_cb.isChecked()

        self.key_group.setVisible(enc_enabled or sb_enabled)

        self.fe_key_path_edit.setVisible(enc_enabled)
        self.fe_key_browse_btn.setVisible(enc_enabled)
        self.fe_row_label.setVisible(enc_enabled)

        self.sb_key_path_edit.setVisible(sb_enabled)
        self.sb_key_browse_btn.setVisible(sb_enabled)
        self.sb_row_label.setVisible(sb_enabled)

    def get_config(self):
        """Returns current configuration for operation."""
        full_config = {
            "flash_files": self.flash_files_widget.get_all_entries(),
            "is_factory_mode": self.factory_mode_rb.isChecked(),
            "use_static_key": self.static_key_rb.isChecked(),
            "fe_static_key_path": self.fe_key_path_edit.text(),
            "sb_static_key_path": self.sb_key_path_edit.text(),
            "enable_flash_encryption": self.enc_cb.isChecked(),
            "enable_secure_boot": self.sb_cb.isChecked(),
            "skip_efuse_burning": self.skip_efuse_exec_rb.isChecked(),
            "disable_jtag": self.disable_jtag_cb.isChecked(),
            "disable_uart": self.disable_uart_cb.isChecked(),
            "virtual": self.virtual_exec_rb.isChecked()
        }

        # For the caller (the worker), only return complete flash file entries
        op_config = full_config.copy()
        op_config["flash_files"] = self.flash_files_widget.get_flash_files()
        return op_config