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
        
        ret = SubprocessRunner.run_command(cmd, self.log_message.emit)
        if ret != 0: raise RuntimeError("eFuse summary failed")

    def run_erase_flash(self):
        port = self.params.get("port")
        chip = self.params.get("chip")
        if not port: raise ValueError("Port is required for erase_flash")
        
        self.status_update.emit("Erasing Flash...")
        cmd = ["esptool", "--port", port]
        # if chip: cmd.extend(["--chip", chip])
        cmd.append("erase-flash")
        
        ret = SubprocessRunner.run_command(cmd, self.log_message.emit)
        if ret != 0: raise RuntimeError("Erase flash failed")

    def run_image_info(self):
        file_path = self.params.get("file_path")
        if not file_path: raise ValueError("File path is required for image_info")
        
        self.status_update.emit("Reading Image Info...")
        cmd = ["esptool", "image-info", file_path]
        
        ret = SubprocessRunner.run_command(cmd, self.log_message.emit)
        if ret != 0: raise RuntimeError("Image info retrieval failed")

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
        if chip: cmd.extend(["--chip", chip, "-b", "115200"])
        cmd.extend(["read-flash", address, size, output_path])
        
        ret = SubprocessRunner.run_command(cmd, self.log_message.emit)
        if ret != 0: raise RuntimeError("Read flash failed")
