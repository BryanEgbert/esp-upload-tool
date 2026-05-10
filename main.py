import sys
import subprocess
from PySide6.QtWidgets import QApplication, QMessageBox
from ui.main_window import MainWindow

def check_dependencies():
    deps = ["esptool", "espefuse.py", "espsecure.py"]
    missing = []
    for dep in deps:
        try:
            subprocess.run([dep, "--version"], capture_output=True, text=True)
        except FileNotFoundError:
            missing.append(dep)
    return missing

def main():
    app = QApplication(sys.argv)
    
    missing_deps = check_dependencies()
    if missing_deps:
        QMessageBox.critical(
            None, 
            "Missing Dependencies", 
            f"The following required tools were not found in PATH:\n{', '.join(missing_deps)}\n\n"
            "Please ensure esptool is installed and accessible."
        )
        sys.exit(1)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
