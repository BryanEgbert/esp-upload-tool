from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPlainTextEdit, QProgressBar, QLabel, QGroupBox
)
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import Qt

class LogZone(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Logs", parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        # Use monospace font for logs
        font = self.log_edit.font()
        font.setFamily("Courier New")
        self.log_edit.setFont(font)
        layout.addWidget(self.log_edit)

    def append_log(self, message: str):
        self.log_edit.appendPlainText(message)
        self.log_edit.moveCursor(QTextCursor.End)

    def set_status(self, status: str):
        self.status_label.setText(status)

    def clear_logs(self):
        self.log_edit.clear()
