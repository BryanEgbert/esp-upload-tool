from PySide6.QtCore import QThread, Signal
import esptool.cmds
import re
from utils.signal_logger import SignalLogger
from esptool.logger import log, EsptoolLogger
from worker.provisioning_worker import ChipInfo


class DiscoveryWorker(QThread):
    log_message = Signal(str)
    finished = Signal(bool, ChipInfo, str)  # success, chip_info, error_message

    def __init__(self, port: str):
        super().__init__()
        self.port = port
        self.output_buffer = []

    def run(self):
        # Set the custom logger to capture esptool output
        self.output_buffer = []
        SignalLogger._handler = self._capture_log
        log.set_logger(SignalLogger())

        try:
            with esptool.cmds.detect_chip(port=self.port) as esp:
                esp.connect()
                esptool.cmds.attach_flash(esp)
                esptool.cmds.flash_id(esp)
                esptool.cmds.read_mac(esp)
                esptool.cmds.get_security_info(esp)

                # Parse the captured output for flash size and MAC
                clean_output = "\n".join(self.output_buffer)
                flash_match = re.search(r"Detected flash size: (\d+\w+)", clean_output)
                mac_match = re.search(r"MAC:\s+([\w:]+)", clean_output)

                # Normalize chip type for esptool commands (e.g. ESP32-S3 -> esp32s3)
                chip_type_cmd = esp.CHIP_NAME.lower().replace("-", "").replace(" ", "")

                flash_size = flash_match.group(1).strip() if flash_match else "Unknown"
                mac_addr = mac_match.group(1).strip() if mac_match else "Unknown"

                chip_info = ChipInfo(chip_type_cmd, flash_size, mac_addr)
                self.finished.emit(True, chip_info, "")

        except Exception as e:
            clean_output = "\n".join(self.output_buffer)
            if clean_output:
                self.log_message.emit("Capture before failure:\n" + clean_output)
            self.finished.emit(False, None, str(e))
        finally:
            # Restore logger
            log.__class__ = EsptoolLogger
            SignalLogger._handler = None

    def _capture_log(self, msg):
        """Capture log messages to buffer and also emit them."""
        self.output_buffer.append(msg)
        self.log_message.emit(msg)
