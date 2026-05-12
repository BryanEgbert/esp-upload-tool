import sys
from PySide6.QtWidgets import QApplication, QMessageBox
import espefuse
import esptool
from ui.main_window import MainWindow
import bitstring
import bitstring.bitstream
import bitarray

def main():
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
