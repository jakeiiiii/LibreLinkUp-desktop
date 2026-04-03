from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel,
)

from api.models import LogbookEntry


class LogbookDialog(QDialog):
    def __init__(self, entries: list[LogbookEntry], unit: str = "mmol", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Logbook")
        self.resize(360, 480)
        self.entries = entries
        self.unit = unit
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        if not self.entries:
            label = QLabel("No logbook entries found.")
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
            return

        unit_str = "mmol/L" if self.unit == "mmol" else "mg/dL"

        table = QTableWidget(len(self.entries), 2)
        table.setHorizontalHeaderLabels(["Date / Time", f"Glucose ({unit_str})"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)

        for row, entry in enumerate(self.entries):
            dt_str = entry.timestamp.strftime("%Y-%m-%d  %I:%M %p")
            table.setItem(row, 0, QTableWidgetItem(dt_str))

            val = entry.value(self.unit)
            val_item = QTableWidgetItem(str(val))
            val_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 1, val_item)

        layout.addWidget(table)
