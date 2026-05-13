from PySide6.QtCore import QThread, Signal
from dataclasses import dataclass, field
import os
import traceback
from typing import Optional
import esptool.cmds
import espefuse
import espsecure
from esptool.logger import log, EsptoolLogger
from utils.signal_logger import SignalLogger
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
        # Set the custom logger to capture esptool/espefuse/espsecure output
        SignalLogger._handler = self.log_message
        log.set_logger(SignalLogger())
        
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
            error_msg = str(e)
            error_traceback = traceback.format_exc()
            self.finished.emit(False, f"{error_msg}\n\nTraceback:\n{error_traceback}")
        finally:
            # Restore the default EsptoolLogger class
            log.__class__ = EsptoolLogger
            SignalLogger._handler = None

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

        with open(self.fe_key_path, "wb") as f:
            # espsecure.generate_flash_encryption_key()
            f.write(os.urandom(key_size // 8))

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
        espsecure.generate_signing_key("2", None, self.sb_key_path)

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
        chip = self.chip_info.chip_type.lower()
        
        with espefuse.init_commands(port=self.port, chip=chip, virt=self.virtual, do_not_confirm=True) as efuses:
            with open(key_path, "rb") as f:
                if chip == "esp32":
                    # Legacy ESP32: uses BLOCK1, signature: burn_key(blocks, keyfiles)
                    efuses.burn_key(["BLOCK1"], [f])
                else:
                    # Newer chips (S2, S3, C3, etc.): uses BLOCK_KEY0, needs key purpose
                    # Determine key type based on key file size (64 bytes = 512 bits)
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    f.seek(0)
                    key_type = "XTS_AES_256_KEY" if size == 64 else "XTS_AES_128_KEY"
                    efuses.burn_key(["BLOCK_KEY0"], [f], [key_type])

    def enable_flash_encryption_efuse(self):
        self.status_update.emit("Enabling Flash Encryption eFuse...")
        chip = self.chip_info.chip_type.lower()
        with espefuse.init_commands(port=self.port, chip=chip, virt=self.virtual, do_not_confirm=True) as efuses:
            if chip == "esp32":
                efuses.burn_efuse({"FLASH_CRYPT_CNT": "1"})
            else:
                efuses.burn_efuse({"SPI_BOOT_CRYPT_CNT": "1"})

    def setup_secure_boot(self, key_path: str):
        self.status_update.emit("Setting up Secure Boot...")
        chip = self.chip_info.chip_type.lower()
        
        with espefuse.init_commands(port=self.port, chip=chip, virt=self.virtual, do_not_confirm=True) as efuses:
            with open(key_path, "rb") as f:
                if chip == "esp32":
                    # Legacy ESP32: signature: burn_key_digest(keyfile)
                    efuses.burn_key_digest(f)
                    efuses.burn_efuse({"ABS_DONE_1": "1"})
                else:
                    # Newer chips: use BLOCK_KEY2 (standard choice) with digest purpose
                    efuses.burn_key_digest(["BLOCK_KEY2"], [f], ["SECURE_BOOT_DIGEST0"])
                    efuses.burn_efuse({"SECURE_BOOT_EN": "1"})

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
                
                with open(sb_key, "rb") as kf, open(current, "rb") as df:
                    espsecure.sign_data(
                        version="2",
                        keyfile=[kf],
                        output=signed_path,
                        append_signatures=False,
                        hsm=False,
                        hsm_config=None,
                        pub_key=[],
                        signature=[],
                        datafile=df
                    )
                    self.log_message.emit("  Verifying signature...")
                    try:
                        espsecure.verify_signature(
                            version=2,
                            hsm=False,
                            hsm_config=None,
                            keyfile=kf,
                            datafile=open(signed_path, "rb")
                        )
                    except Exception as e:
                        self.log_message.emit(f"  Signature verification failed: {e}")
                        raise
                    self.log_message.emit("  Signature verified successfully.")
                current = signed_path

            # -- Encrypt --
            if self.enable_flash_encryption and fe_key:
                encrypted_path = os.path.join(self.work_dir, f"{base_name}_enc.bin")
                self._temp_files.append(encrypted_path)
                self.log_message.emit(f"  Encrypting {os.path.basename(current)} at {address}...")
                
                with open(fe_key, "rb") as kf, open(current, "rb") as pf, open(encrypted_path, "wb") as of:
                    espsecure.encrypt_flash_data(
                        keyfile=kf,
                        output=of,
                        address=int(address, 0),
                        flash_crypt_conf=0xF,
                        aes_xts=True,
                        plaintext_file=pf
                    )
                current = encrypted_path

            processed.append((address, current))

        # -- Single write-flash call with all files --
        self.status_update.emit("Flashing all files...")
        
        with esptool.cmds.detect_chip(port=self.port, baud=115200) as esp:

            addr_data = []
            open_files = []
            for addr, path in processed:
                f = open(path, "rb")
                open_files.append(f)
                addr_data.append((int(addr, 0), f))
            
            try:
                esp.connect()
                esptool.cmds.attach_flash(esp)
                esptool.cmds.write_flash(
                    esp,
                    addr_data,
                    compress=False,
                    flash_mode="keep",
                    flash_freq="keep",
                    flash_size="detect"
                )
                esptool.cmds.verify_flash(esp, addr_data)
                esptool.cmds.reset_chip(esp)
            finally:
                for f in open_files:
                    f.close()

    # -------------------------------------------------------------------------
    # Hardware Lockdown
    # -------------------------------------------------------------------------

    def hardware_lockdown(self):
        with espefuse.init_commands(port=self.port, virt=self.virtual, do_not_confirm=True) as efuses:
            if self.disable_jtag:
                self.status_update.emit("Disabling JTAG...")
                efuses.burn_efuse({
                    "DIS_PAD_JTAG": "1",
                    "DIS_USB_SERIAL_JTAG_ROM_PRINT": "1"
                })

            if self.disable_uart_boot:
                self.status_update.emit("Disabling UART Download Mode...")
                efuses.burn_efuse({"DIS_DOWNLOAD_MODE": "1"})

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
 
 