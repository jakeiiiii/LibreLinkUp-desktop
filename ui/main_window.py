import logging
from datetime import datetime, timedelta

import winsound

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap, QPainter, QFont, QColor, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QMessageBox, QDialog, QDoubleSpinBox,
    QDialogButtonBox, QFormLayout,
)

from api.client import LibreLinkUpClient, LibreLinkUpError
from api.models import Connection, GraphData
from utils.version import app_title
from ui.graph_widget import GlucoseChart
from ui.logbook_dialog import LogbookDialog

logger = logging.getLogger(__name__)

# Default stale threshold (overridden by config "stale_minutes")


class MainWindow(QWidget):
    logout_requested = Signal()

    def __init__(self, client: LibreLinkUpClient, config: dict):
        super().__init__()
        self.client = client
        self.config = config
        self.connections: list[Connection] = []
        self.current_connection: Connection | None = None
        self.graph_data: GraphData | None = None
        self._recent_readings: list = []  # accumulated 1-min readings between API's 15-min points
        self._blink_visible = True
        self._is_stale = False
        self._compact = False

        self.setWindowTitle(app_title(config))
        self.resize(420, 620)
        self.setMinimumSize(360, 500)
        self._normal_size = None  # saved before going compact

        self._build_ui()
        self._setup_timer()
        self._setup_blink_timer()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Header bar ──
        self._header = QWidget()
        header = self._header
        header.setObjectName("headerBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 8, 16, 8)

        self.connection_combo = QComboBox()
        self.connection_combo.setObjectName("connectionCombo")
        self.connection_combo.currentIndexChanged.connect(self._on_connection_changed)
        header_layout.addWidget(self.connection_combo)

        header_layout.addStretch()

        title_label = QLabel("LibreLinkUp")
        title_label.setObjectName("headerTitle")
        title_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.unit_btn = QPushButton("mmol/L")
        self.unit_btn.setObjectName("unitButton")
        self.unit_btn.setFixedWidth(60)
        self.unit_btn.clicked.connect(self._toggle_unit)
        header_layout.addWidget(self.unit_btn)

        layout.addWidget(header)

        # ── Patient info bar ──
        self._info_bar = QWidget()
        info_bar = self._info_bar
        info_bar.setObjectName("infoBar")
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(16, 10, 16, 10)

        self.reading_label = QLabel("— — —")
        self.reading_label.setObjectName("currentReading")
        info_layout.addWidget(self.reading_label)

        self.trend_label = QLabel("")
        self.trend_label.setObjectName("trendArrow")
        info_layout.addWidget(self.trend_label)

        info_layout.addStretch()

        layout.addWidget(info_bar)

        # ── Compact view: glucose number + trend, click to expand ──
        self._compact_widget = QWidget()
        self._compact_widget.setObjectName("compactView")
        compact_layout = QHBoxLayout(self._compact_widget)
        compact_layout.setContentsMargins(12, 8, 12, 8)

        self._compact_reading = QLabel("--")
        self._compact_reading.setObjectName("compactReading")
        compact_layout.addWidget(self._compact_reading)

        self._compact_trend = QLabel("")
        self._compact_trend.setObjectName("compactTrend")
        compact_layout.addWidget(self._compact_trend)

        compact_layout.addStretch()

        self._expand_btn = QPushButton("expand")
        self._expand_btn.setObjectName("expandButton")
        self._expand_btn.setCursor(Qt.PointingHandCursor)
        self._expand_btn.clicked.connect(self._toggle_compact)
        compact_layout.addWidget(self._expand_btn)

        self._compact_widget.setVisible(False)
        layout.addWidget(self._compact_widget)

        # ── Glucose chart ──
        self.chart = GlucoseChart()
        self.chart.set_unit(self.config.get("unit", "mmol"))
        self.chart.set_target_range(
            self.config.get("target_low_mmol", 3.9),
            self.config.get("target_high_mmol", 10.0),
        )
        layout.addWidget(self.chart, stretch=1)

        # ── Bottom bar ──
        self._bottom = QWidget()
        bottom = self._bottom
        bottom.setObjectName("bottomBar")
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(16, 8, 16, 8)

        self.refresh_label = QLabel("")
        self.refresh_label.setObjectName("refreshLabel")
        bottom_layout.addWidget(self.refresh_label)

        bottom_layout.addStretch()

        self.beep_cb = QCheckBox("")
        self.beep_cb.setObjectName("beepCheckbox")
        self.beep_cb.setChecked(self.config.get("low_beep_enabled", True))
        self.beep_cb.toggled.connect(self._on_beep_toggled)
        bottom_layout.addWidget(self.beep_cb)

        self.beep_label = QPushButton("")
        self.beep_label.setObjectName("beepLabel")
        self.beep_label.setCursor(Qt.PointingHandCursor)
        self.beep_label.clicked.connect(self._show_beep_threshold_dialog)
        self._update_beep_label()
        bottom_layout.addWidget(self.beep_label)

        bottom_layout.addStretch()

        logbook_btn = QPushButton("Log")
        logbook_btn.setObjectName("logbookButton")
        logbook_btn.clicked.connect(self._show_logbook)
        bottom_layout.addWidget(logbook_btn)

        bottom_layout.addStretch()

        compact_btn = QPushButton("Compact")
        compact_btn.setObjectName("compactButton")
        compact_btn.clicked.connect(self._toggle_compact)
        bottom_layout.addWidget(compact_btn)

        bottom_layout.addStretch()

        logout_btn = QPushButton("Logout")
        logout_btn.setObjectName("logoutButton")
        logout_btn.clicked.connect(self.logout_requested.emit)
        bottom_layout.addWidget(logout_btn)

        layout.addWidget(bottom)

        self._update_unit_button()

    def _setup_timer(self):
        interval = self.config.get("refresh_seconds", 60) * 1000
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_data)
        self._timer.start(interval)

    def _toggle_compact(self):
        self._compact = not self._compact
        self.config["compact_view"] = self._compact
        from utils.config import save_config
        save_config(self.config)
        if self._compact:
            # Save current size, switch to compact
            self._normal_size = self.size()
            self._header.setVisible(False)
            self._info_bar.setVisible(False)
            self.chart.setVisible(False)
            self._bottom.setVisible(False)
            self._compact_widget.setVisible(True)
            self.setMinimumSize(200, 50)
            self.resize(250, 60)
        else:
            # Restore full view
            self._compact_widget.setVisible(False)
            self._header.setVisible(True)
            self._info_bar.setVisible(True)
            self.chart.setVisible(True)
            self._bottom.setVisible(True)
            self.setMinimumSize(360, 500)
            if self._normal_size:
                self.resize(self._normal_size)
            else:
                self.resize(420, 620)

    def _setup_blink_timer(self):
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._on_blink)
        # Not started yet — only runs when data is stale

    def _on_blink(self):
        self._blink_visible = not self._blink_visible
        if self._blink_visible:
            self.reading_label.setText(self._last_reading_text)
            self.trend_label.setText(self._last_trend_text)
            self._compact_reading.setText(self._last_compact_text)
            self._compact_trend.setText(self._last_compact_trend)
        else:
            self.reading_label.setText("No Recent Data")
            self.trend_label.setText("")
            self._compact_reading.setText("--")
            self._compact_trend.setText("")

    def _start_blinking(self, reading_text="--", trend_text="",
                         compact_text="--", compact_trend=""):
        self._last_reading_text = reading_text
        self._last_trend_text = trend_text
        self._last_compact_text = compact_text
        self._last_compact_trend = compact_trend
        if not self._blink_timer.isActive():
            self._blink_visible = True
            self._blink_timer.start(800)  # alternate every 800ms

    def _stop_blinking(self):
        self._blink_timer.stop()
        self._blink_visible = True

    def start(self):
        """Called after login to load initial data."""
        # Restore compact view if saved
        if self.config.get("compact_view", False):
            self._toggle_compact()
        self._load_connections()

    def _load_connections(self):
        try:
            self.connections = self.client.get_connections()
        except Exception as e:
            logger.error(f"Failed to load connections: {e}")
            QMessageBox.warning(self, "Error", f"Failed to load connections:\n{e}")
            return

        self.connection_combo.blockSignals(True)
        self.connection_combo.clear()
        for conn in self.connections:
            self.connection_combo.addItem(conn.full_name, conn.patient_id)
        self.connection_combo.blockSignals(False)

        if self.connections:
            self.current_connection = self.connections[0]
            self._refresh_data()

    def _on_connection_changed(self, index):
        if 0 <= index < len(self.connections):
            self.current_connection = self.connections[index]
            self._refresh_data()

    def _refresh_data(self):
        if not self.current_connection:
            return

        try:
            self.graph_data = self.client.get_graph(self.current_connection.patient_id)
        except Exception as e:
            logger.error(f"Refresh failed: {e}")
            self.refresh_label.setText(f"Error: {e}")
            return

        conn = self.graph_data.connection

        # Set alarm thresholds on chart
        self.chart.set_low_alarm(conn.low_alarm_mgdl)
        self.chart.set_target_range(conn.target_low_mmol, conn.target_high_mmol)

        # Update current reading display
        reading = conn.current_reading
        if reading:
            unit = self.config.get("unit", "mmol")
            val = reading.value(unit)
            unit_str = "mmol/L" if unit == "mmol" else "mg/dL"
            self.reading_label.setText(f"{val} {unit_str}")
            self.trend_label.setText(reading.trend_symbol)
            self._compact_reading.setText(str(val))
            self._compact_trend.setText(reading.trend_symbol)

            age = datetime.now() - reading.timestamp
            stale_minutes = self.config.get("stale_minutes", 15)
            self._is_stale = age > timedelta(minutes=stale_minutes)
            if self._is_stale:
                # Stale — alternate between last value and "No Recent Data"
                self.reading_label.setStyleSheet("color: #888;")
                self._compact_reading.setStyleSheet("color: #888;")
                self._start_blinking(
                    f"{val} {unit_str}", reading.trend_symbol,
                    str(val), reading.trend_symbol,
                )
            else:
                self._stop_blinking()
                self._compact_reading.setStyleSheet("color: #333;")

                # Color based on alarm state
                if reading.is_low:
                    color = "color: #cc0000;"
                elif reading.is_high:
                    color = "color: #ff8800;"
                else:
                    color = "color: #333;"
                self.reading_label.setStyleSheet(color)
                self._compact_reading.setStyleSheet(color)

                # Beep if below threshold
                self._check_low_beep(reading)
        else:
            self._is_stale = True
            self.reading_label.setStyleSheet("color: #888;")
            self._compact_reading.setStyleSheet("color: #888;")
            self.trend_label.setText("")
            self._compact_trend.setText("")
            self._start_blinking("No Recent Data", "", "--", "")

        # Accumulate current readings for higher resolution on recent data
        if conn.current_reading:
            # Add if it's a new timestamp we haven't seen
            if (not self._recent_readings
                    or conn.current_reading.timestamp > self._recent_readings[-1].timestamp):
                self._recent_readings.append(conn.current_reading)

        # Build full reading list: API graph data + our accumulated recent readings
        all_readings = list(self.graph_data.readings)
        if all_readings and self._recent_readings:
            last_graph_ts = all_readings[-1].timestamp
            # Only add recent readings that are after the last graph point
            extras = [r for r in self._recent_readings if r.timestamp > last_graph_ts]
            all_readings.extend(extras)
        elif self._recent_readings:
            all_readings.extend(self._recent_readings)

        # Prune old accumulated readings (keep last 12 hours)
        if self._recent_readings:
            cutoff = datetime.now() - timedelta(hours=12)
            self._recent_readings = [r for r in self._recent_readings if r.timestamp > cutoff]

        self.chart.update_data(all_readings, conn.current_reading)

        # Update taskbar icon — show "—" when stale/no signal
        self._update_taskbar_icon(None if self._is_stale else conn.current_reading)

        now = datetime.now().strftime("%I:%M %p")
        self.refresh_label.setText(f"Updated {now}")

    def _toggle_unit(self):
        current = self.config.get("unit", "mmol")
        new_unit = "mgdl" if current == "mmol" else "mmol"
        self.config["unit"] = new_unit
        self.chart.set_unit(new_unit)
        self._update_unit_button()
        self._update_beep_label()
        # Re-render current data
        if self.graph_data:
            conn = self.graph_data.connection
            reading = conn.current_reading
            if reading:
                val = reading.value(new_unit)
                unit_str = "mmol/L" if new_unit == "mmol" else "mg/dL"
                self.reading_label.setText(f"{val} {unit_str}")
            self.chart.update_data(self.graph_data.readings, conn.current_reading)

    def _update_taskbar_icon(self, reading=None):
        """Generate a taskbar icon showing the current glucose number."""
        size = 256
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        radius = 32  # rounded corner radius

        if reading:
            unit = self.config.get("unit", "mmol")
            val = reading.value(unit)
            text = str(val)

            # Background rounded rect color based on state
            if reading.is_low:
                bg_color = QColor("#cc0000")
            elif reading.is_high:
                bg_color = QColor("#ff8800")
            else:
                bg_color = QColor("#2ecc71")

            painter.setBrush(bg_color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(0, 0, size, size, radius, radius)

            # Text — large and bold to fill the icon
            painter.setPen(QColor("black"))
            font_size = 80 if len(text) <= 4 else 64
            font = QFont("Segoe UI", font_size, QFont.Bold)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
        else:
            painter.setBrush(QColor("#888"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(0, 0, size, size, radius, radius)
            painter.setPen(QColor("black"))
            painter.setFont(QFont("Segoe UI", 90, QFont.Bold))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "--")

        painter.end()

        icon = QIcon(pixmap)
        self.setWindowIcon(icon)
        # Also update the title so the taskbar tooltip shows the value
        if reading:
            unit = self.config.get("unit", "mmol")
            val = reading.value(unit)
            unit_str = "mmol/L" if unit == "mmol" else "mg/dL"
            self.setWindowTitle(app_title(self.config, f"— {val} {unit_str}"))
        else:
            self.setWindowTitle(app_title(self.config))

    def _update_unit_button(self):
        unit = self.config.get("unit", "mmol")
        self.unit_btn.setText("mmol/L" if unit == "mmol" else "mg/dL")

    def _update_beep_label(self):
        threshold = self.config.get("low_beep_threshold_mmol", 0)
        unit = self.config.get("unit", "mmol")
        if unit == "mgdl":
            val = round(threshold * 18.0)
            self.beep_label.setText(f"Beep < {val}")
        else:
            self.beep_label.setText(f"Beep < {threshold}")

    def _on_beep_toggled(self, checked):
        self.config["low_beep_enabled"] = checked
        from utils.config import save_config
        save_config(self.config)

    def _show_beep_threshold_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Warning Beep Threshold")
        dialog.setFixedSize(280, 120)

        form = QFormLayout(dialog)

        unit = self.config.get("unit", "mmol")
        current = self.config.get("low_beep_threshold_mmol", 4.0)

        spin = QDoubleSpinBox()
        spin.setDecimals(1)
        if unit == "mgdl":
            spin.setRange(0, 400)
            spin.setSingleStep(5)
            spin.setValue(round(current * 18.0, 1))
            spin.setSuffix(" mg/dL")
        else:
            spin.setRange(0, 22)
            spin.setSingleStep(0.5)
            spin.setValue(current)
            spin.setSuffix(" mmol/L")

        form.addRow("Beep when below:", spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() == QDialog.Accepted:
            val = spin.value()
            if unit == "mgdl":
                val = round(val / 18.0, 1)
            self.config["low_beep_threshold_mmol"] = val
            self._update_beep_label()
            from utils.config import save_config
            save_config(self.config)

    def _check_low_beep(self, reading):
        """Beep if glucose is below the configured threshold."""
        if not self.config.get("low_beep_enabled", True):
            return
        threshold = self.config.get("low_beep_threshold_mmol", 0)
        if threshold <= 0:
            return
        if reading.value_mmol < threshold:
            try:
                winsound.Beep(1000, 600)  # 1000 Hz for 600ms
            except Exception:
                pass  # winsound only works on Windows

    def _show_logbook(self):
        if not self.current_connection:
            return
        try:
            entries = self.client.get_logbook(self.current_connection.patient_id)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load logbook:\n{e}")
            return

        dialog = LogbookDialog(entries, self.config.get("unit", "mmol"), self)
        dialog.exec()

    def stop_timer(self):
        self._timer.stop()
        self._stop_blinking()
