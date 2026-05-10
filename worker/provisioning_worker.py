from PySide6.QtCore import QThread, Signal
from dataclasses import dataclass, field
import os
from typing import Optional
from utils.subprocess_runner import SubprocessRunner
from utils.config_manager import ConfigManager


@dataclass
class ChipInfo:
    chip_type: str  # e.g., "esp32s3", "esp32c3"
    flash_size: str
    mac_address: str


class ProvisioningWorker(QThread):
    log_message = Signal(str)
    progress_update = Signal(int)
    status_update = Signal(str)
    finished = Signal(bool, str)

    def __init__(
        self,
        port: str,
        flash_files: list[tuple[str, str]],  # list of (address, file_path)
        is_factory_mode: bool,
        use_static_key: bool,
        fe_static_key_path: Optional[str] = None,
        sb_static_key_path: Optional[str] = None,
        enable_flash_encryption: bool = False,
        enable_secure_boot: bool = False,
        skip_efuse_burning: bool = False,
        disable_jtag: bool = False,
        disable_uart_boot: bool = False,
        chip_info: ChipInfo = None,
        virtual: bool = False,
        **kwargs
    ):
        super().__init__()
        self.port = port
        self.flash_files = flash_files  # [(addr, path), ...]
        self.is_factory_mode = is_factory_mode
        self.use_static_key = use_static_key
        self.fe_static_key_path = fe_static_key_path
        self.sb_static_key_path = sb_static_key_path
        self.enable_flash_encryption = enable_flash_encryption
        self.enable_secure_boot = enable_secure_boot
        self.skip_efuse_burning = skip_efuse_burning
        self.disable_jtag = disable_jtag
        self.disable_uart_boot = disable_uart_boot
        self.chip_info = chip_info
        self.virtual = virtual

        self.work_dir = "build"
        self.fe_key_path = os.path.join(self.work_dir, "temp_fe_key.bin")
        self.sb_key_path = os.path.join(self.work_dir, "temp_sb_key.pem")

        # Tracks all temp files created during processing for cleanup
        self._temp_files: list[str] = []

    def run(self):
        try:
            os.makedirs(self.work_dir, exist_ok=True)

            if not self.flash_files:
                raise ValueError("No flash files provided.")

            if self.virtual:
                self.status_update.emit("Starting Virtual Provisioning (Simulation)...")
            else:
                self.status_update.emit("Starting Provisioning...")

            # Step 1: Key Management
            active_fe_key = self.manage_flash_encryption_key()
            active_sb_key = self.manage_secure_boot_key()

            if not self.skip_efuse_burning:
                # Step 2: Burn Encryption Key
                if self.enable_flash_encryption:
                    self.burn_encryption_key(active_fe_key)

                # Step 3: Enable Flash Encryption eFuse
                if self.enable_flash_encryption:
                    self.enable_flash_encryption_efuse()

                # Step 4: Setup Secure Boot
                if self.enable_secure_boot:
                    self.setup_secure_boot(active_sb_key)
            else:
                self.log_message.emit("Skipping eFuse burning steps.")

            # Step 5: Sign + Encrypt each file individually, then flash all
            if not self.virtual:
                self.flash_all_files(active_fe_key, active_sb_key)

            # Step 6: Hardware Lockdown
            if self.is_factory_mode and not self.skip_efuse_burning:
                self.hardware_lockdown()

            self.cleanup()

            if self.virtual:
                self.finished.emit(True, "Virtual Provisioning Completed Successfully (No hardware changes)")
            else:
                self.finished.emit(True, "Provisioning Completed Successfully")

        except Exception as e:
            self.finished.emit(False, str(e))

    # -------------------------------------------------------------------------
    # Key Management
    # -------------------------------------------------------------------------

    def manage_flash_encryption_key(self) -> Optional[str]:
        if not self.enable_flash_encryption:
            return None

        if self.use_static_key:
            if not self.fe_static_key_path or not os.path.exists(self.fe_static_key_path):
                raise ValueError("Static Flash Encryption key path is invalid or does not exist")
            return self.fe_static_key_path

        if not self.is_factory_mode:
            persistent_path = ConfigManager.get_persistent_key_path(self.chip_info.chip_type, "flash_encryption")
            if persistent_path and os.path.exists(persistent_path):
                self.log_message.emit(f"Reusing persistent Flash Encryption key: {persistent_path}")
                return persistent_path

        self.log_message.emit("Generating new Flash Encryption key...")
        key_size = 512 if "s3" in self.chip_info.chip_type.lower() else 256
        cmd = ["espsecure", "generate-flash-encryption-key", "--keylen", str(key_size), self.fe_key_path]
        if SubprocessRunner.run_command(cmd, self.log_message.emit) != 0:
            raise RuntimeError("Failed to generate flash encryption key")

        if not self.is_factory_mode:
            perm_path = os.path.join(self.work_dir, f"proto_fe_key_{self.chip_info.chip_type}.bin")
            if os.path.exists(self.fe_key_path):
                os.replace(self.fe_key_path, perm_path)
            ConfigManager.set_persistent_key_path(self.chip_info.chip_type, "flash_encryption", perm_path)
            return perm_path

        return self.fe_key_path

    def manage_secure_boot_key(self) -> Optional[str]:
        if not self.enable_secure_boot:
            return None

        if self.use_static_key:
            if not self.sb_static_key_path or not os.path.exists(self.sb_static_key_path):
                raise ValueError("Static Secure Boot signing key path is invalid or does not exist")
            return self.sb_static_key_path

        if not self.is_factory_mode:
            persistent_path = ConfigManager.get_persistent_key_path(self.chip_info.chip_type, "secure_boot")
            if persistent_path and os.path.exists(persistent_path):
                self.log_message.emit(f"Reusing persistent Secure Boot key: {persistent_path}")
                return persistent_path

        self.log_message.emit("Generating new Secure Boot signing key...")
        cmd = ["espsecure", "generate-signing-key", "--version", "2", self.sb_key_path]
        if SubprocessRunner.run_command(cmd, self.log_message.emit) != 0:
            raise RuntimeError("Failed to generate secure boot signing key")

        if not self.is_factory_mode:
            perm_path = os.path.join(self.work_dir, f"proto_sb_key_{self.chip_info.chip_type}.pem")
            if os.path.exists(self.sb_key_path):
                os.replace(self.sb_key_path, perm_path)
            ConfigManager.set_persistent_key_path(self.chip_info.chip_type, "secure_boot", perm_path)
            return perm_path

        return self.sb_key_path

    # -------------------------------------------------------------------------
    # eFuse Operations
    # -------------------------------------------------------------------------

    def burn_encryption_key(self, key_path: str):
        self.status_update.emit("Burning Encryption Key...")
        key_size = 512 if "s3" in self.chip_info.chip_type.lower() else 256
        key_type = "XTS_AES_256_KEY" if key_size == 512 else "XTS_AES_128_KEY"
        cmd = [
            "espefuse", "--chip", self.chip_info.chip_type, "--port", self.port,
            "--do-not-confirm", "burn-key", "BLOCK_KEY0", key_path, key_type
        ]
        if self.virtual:
            cmd.insert(1, "--virt")
        if SubprocessRunner.run_command(cmd, self.log_message.emit) != 0:
            raise RuntimeError("Failed to burn encryption key")

    def enable_flash_encryption_efuse(self):
        self.status_update.emit("Enabling Flash Encryption eFuse...")
        cmd = [
            "espefuse", "--chip", self.chip_info.chip_type, "--port", self.port,
            "--do-not-confirm", "burn-efuse", "SPI_BOOT_CRYPT_CNT", "1"
        ]
        if self.virtual:
            cmd.insert(1, "--virt")
        if SubprocessRunner.run_command(cmd, self.log_message.emit) != 0:
            raise RuntimeError("Failed to enable flash encryption eFuse")

    def setup_secure_boot(self, key_path: str):
        self.status_update.emit("Setting up Secure Boot...")
        cmd = [
            "espefuse", "--chip", self.chip_info.chip_type, "--port", self.port,
            "--do-not-confirm", "burn-key-digest", "BLOCK_KEY2", key_path, "SECURE_BOOT_DIGEST0"
        ]
        if self.virtual:
            cmd.insert(1, "--virt")
        if SubprocessRunner.run_command(cmd, self.log_message.emit) != 0:
            raise RuntimeError("Failed to burn secure boot key digest")

        cmd = [
            "espefuse", "--chip", self.chip_info.chip_type, "--port", self.port,
            "--do-not-confirm", "burn-efuse", "SECURE_BOOT_EN"
        ]
        if self.virtual:
            cmd.insert(1, "--virt")
        if SubprocessRunner.run_command(cmd, self.log_message.emit) != 0:
            raise RuntimeError("Failed to enable secure boot eFuse")

    # -------------------------------------------------------------------------
    # Per-file Sign + Encrypt + Flash
    # -------------------------------------------------------------------------

    def flash_all_files(self, fe_key: Optional[str], sb_key: Optional[str]):
        """
        For each (address, file) pair:
          1. Sign the file (if secure boot enabled)
          2. Encrypt the file at its specific address (if flash encryption enabled)
          3. Collect all processed (address, processed_file) pairs
          4. Issue a single write-flash command with all of them
        """
        processed: list[tuple[str, str]] = []  # (address, final_bin_path)

        total = len(self.flash_files)
        for idx, (address, file_path) in enumerate(self.flash_files):
            self.status_update.emit(f"Processing file {idx + 1}/{total}: {os.path.basename(file_path)} @ {address}")
            current = file_path
            base_name = os.path.splitext(os.path.basename(file_path))[0]

            # -- Sign --
            if self.enable_secure_boot and sb_key:
                signed_path = os.path.join(self.work_dir, f"{base_name}_signed.bin")
                self._temp_files.append(signed_path)
                self.log_message.emit(f"  Signing {os.path.basename(current)}...")
                cmd = [
                    "espsecure", "sign-data", "--version", "2",
                    "--keyfile", sb_key,
                    "--output", signed_path,
                    current
                ]
                if SubprocessRunner.run_command(cmd, self.log_message.emit) != 0:
                    raise RuntimeError(f"Failed to sign {file_path}")
                current = signed_path

            # -- Encrypt --
            if self.enable_flash_encryption and fe_key:
                encrypted_path = os.path.join(self.work_dir, f"{base_name}_enc.bin")
                self._temp_files.append(encrypted_path)
                self.log_message.emit(f"  Encrypting {os.path.basename(current)} at {address}...")
                cmd = [
                    "espsecure", "encrypt-flash-data", "--aes-xts",
                    "--keyfile", fe_key,
                    "--address", address,
                    "--output", encrypted_path,
                    current
                ]
                if SubprocessRunner.run_command(cmd, self.log_message.emit) != 0:
                    raise RuntimeError(f"Failed to encrypt {file_path}")
                current = encrypted_path

            processed.append((address, current))

        # -- Single write-flash call with all files --
        self.status_update.emit("Flashing all files...")
        cmd = [
            "esptool",
            "--before", "default-reset",
            "--after", "hard-reset",
            "--no-stub",
            "--chip", self.chip_info.chip_type,
            "--port", self.port,
            "--baud", "115200",
            "write-flash",
            "-u",
            "--flash-mode", "keep",
            "--flash-freq", "keep",
            "--flash-size", "detect",
        ]

        # Append all (address, file) pairs
        for address, file_path in processed:
            cmd.append(address)
            cmd.append(file_path)

        if SubprocessRunner.run_command(cmd, self.log_message.emit) != 0:
            raise RuntimeError("Failed to flash binaries")

    # -------------------------------------------------------------------------
    # Hardware Lockdown
    # -------------------------------------------------------------------------

    def hardware_lockdown(self):
        if self.disable_jtag:
            self.status_update.emit("Disabling JTAG...")
            for efuse in ["DIS_PAD_JTAG", "DIS_USB_SERIAL_JTAG_ROM_PRINT"]:
                cmd = [
                    "espefuse", "--chip", self.chip_info.chip_type, "--port", self.port,
                    "--do-not-confirm", "burn-efuse", efuse
                ]
                if self.virtual:
                    cmd.insert(1, "--virt")
                SubprocessRunner.run_command(cmd, self.log_message.emit)

        if self.disable_uart_boot:
            self.status_update.emit("Disabling UART Download Mode...")
            cmd = [
                "espefuse", "--chip", self.chip_info.chip_type, "--port", self.port,
                "--do-not-confirm", "burn-efuse", "DIS_DOWNLOAD_MODE"
            ]
            if self.virtual:
                cmd.insert(1, "--virt")
            SubprocessRunner.run_command(cmd, self.log_message.emit)

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    def cleanup(self):
        self.status_update.emit("Cleaning up temporary keys...")

        for path in self._temp_files:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    self.log_message.emit(f"Removed temp file: {path}")
                except OSError as e:
                    self.log_message.emit(f"Warning: Could not remove {path}: {e}")
        
        if self.is_factory_mode:
            for path in [self.fe_key_path, self.sb_key_path]:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                        self.log_message.emit(f"Removed temp key: {path}")
                    except OSError as e:
                        self.log_message.emit(f"Warning: Could not remove {path}: {e}")
 
 