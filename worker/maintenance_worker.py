from PySide6.QtCore import QThread, Signal
import esptool.cmds
import espefuse
from utils.signal_logger import SignalLogger
from esptool.logger import log, EsptoolLogger

class MaintenanceWorker(QThread):
    log_message = Signal(str)
    status_update = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, task_type: str, params: dict):
        super().__init__()
        self.task_type = task_type
        self.params = params

    def run(self):
        # Set the custom logger to capture esptool/espefuse output.
        # Since set_logger only changes the class, we set the handler on the class.
        SignalLogger._handler = self.log_message
        log.set_logger(SignalLogger())
        
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
        finally:
            # Restore the default EsptoolLogger class
            log.__class__ = EsptoolLogger
            SignalLogger._handler = None

    def run_efuse_summary(self):
        port = self.params.get("port")
        chip = self.params.get("chip")
        if not all([port, chip]):
            raise ValueError("Port and Chip type are required for efuse_summary")
            
        self.status_update.emit("Reading eFuse Summary...")
        with espefuse.init_commands(port=port) as efuses:
            efuses.summary()

    def run_erase_flash(self):
        port = self.params.get("port")
        if not port:
            raise ValueError("Port is required for erase_flash")
        
        self.status_update.emit("Erasing Flash...")
        esp = esptool.cmds.detect_chip(port=port)
        try:
            esp.connect()
            esptool.cmds.attach_flash(esp)
            esptool.cmds.erase_flash(esp, force=True)
        finally:
            esp._port.close()

    def run_image_info(self):
        file_path = self.params.get("file_path")
        if not file_path:
            raise ValueError("File path is required for image_info")
        
        self.status_update.emit(f"Reading Image Info: {file_path}...")
        esptool.cmds.image_info(input=file_path)

    def run_read_flash(self):
        port = self.params.get("port")
        address = self.params.get("address", "0x0")
        size = self.params.get("size")
        output_path = self.params.get("output_path")
        
        if not all([port, size, output_path]):
            raise ValueError("Port, Size, and Output Path are required for read_flash")
            
        self.status_update.emit("Reading Flash...")
        
        addr_int = int(address, 0)
        size_int = int(size, 0)
        
        with esptool.cmds.detect_chip(port=port) as esp:
            esp.connect()
            esptool.cmds.attach_flash(esp)
            esptool.cmds.read_flash(esp, address=addr_int, size=size_int, output=output_path)
    