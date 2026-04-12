import ctypes
import ctypes.wintypes
import logging
from datetime import datetime, timedelta

import winsound

from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import QPixmap, QPainter, QFont, QColor, QIcon, QImage
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QMessageBox, QDialog, QDoubleSpinBox,
    QDialogButtonBox, QFormLayout, QMenu, QSystemTrayIcon,
)

from api.client import LibreLinkUpClient, LibreLinkUpError
from api.models import Connection, GraphData
from utils.version import app_title
from ui.graph_widget import GlucoseChart
from ui.logbook_dialog import LogbookDialog

logger = logging.getLogger(__name__)


class _UpdateChecker(QThread):
    """Background thread that checks GitHub for a newer release."""
    update_available = Signal(str, str)  # (new_version, download_url)

    def run(self):
        from utils.updater import check_for_update
        result = check_for_update()
        if result:
            self.update_available.emit(*result)


# ── Win32 helpers for dynamic taskbar icon ──

class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.wintypes.DWORD),
        ("biWidth", ctypes.wintypes.LONG),
        ("biHeight", ctypes.wintypes.LONG),
        ("biPlanes", ctypes.wintypes.WORD),
        ("biBitCount", ctypes.wintypes.WORD),
        ("biCompression", ctypes.wintypes.DWORD),
        ("biSizeImage", ctypes.wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.wintypes.LONG),
        ("biYPelsPerMeter", ctypes.wintypes.LONG),
        ("biClrUsed", ctypes.wintypes.DWORD),
        ("biClrImportant", ctypes.wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER)]


class _ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", ctypes.wintypes.BOOL),
        ("xHotspot", ctypes.wintypes.DWORD),
        ("yHotspot", ctypes.wintypes.DWORD),
        ("hbmMask", ctypes.c_void_p),
        ("hbmColor", ctypes.c_void_p),
    ]


_WM_SETICON = 0x0080
_ICON_BIG = 1
_ICON_SMALL = 0


def _hicon_from_pixmap(pixmap: QPixmap):
    """Create a native Windows HICON from a QPixmap."""
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    width, height = image.width(), image.height()

    # Create a color DIB section
    hdc = ctypes.windll.user32.GetDC(0)
    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bits_ptr = ctypes.c_void_p()
    hbm_color = ctypes.windll.gdi32.CreateDIBSection(
        hdc, ctypes.byref(bmi), 0, ctypes.byref(bits_ptr), None, 0,
    )
    # Copy pixel data
    data = bytes(image.constBits())
    ctypes.memmove(bits_ptr, data, len(data))

    # Monochrome mask (all zeros → fully opaque via alpha channel)
    hbm_mask = ctypes.windll.gdi32.CreateBitmap(width, height, 1, 1, None)

    ii = _ICONINFO()
    ii.fIcon = True
    ii.hbmMask = hbm_mask
    ii.hbmColor = hbm_color
    hicon = ctypes.windll.user32.CreateIconIndirect(ctypes.byref(ii))

    ctypes.windll.gdi32.DeleteObject(hbm_color)
    ctypes.windll.gdi32.DeleteObject(hbm_mask)
    ctypes.windll.user32.ReleaseDC(0, hdc)
    return hicon


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
        self._last_icon: QIcon | None = None
        self._last_hicon = None
        self._tray_icon = QSystemTrayIcon(self)
        self._tray_icon.activated.connect(self._on_tray_activated)

        self.setWindowFlags(
            Qt.Window | Qt.WindowCloseButtonHint
            | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
        )
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

        logbook_btn = QPushButton("Log")
        logbook_btn.setObjectName("logbookButton")
        logbook_btn.clicked.connect(self._show_logbook)
        bottom_layout.addWidget(logbook_btn)

        bottom_layout.addStretch()

        gear_btn = QPushButton("\u2699")
        gear_btn.setObjectName("gearButton")
        gear_btn.setCursor(Qt.PointingHandCursor)
        gear_btn.clicked.connect(self._show_gear_menu)
        bottom_layout.addWidget(gear_btn)

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
            # Save current size, switch to compact (keep position)
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
            # Center on screen when expanding to full view
            self._center_on_screen()

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
        # Restore saved position or center on screen
        self._restore_position()
        # Restore compact view if saved
        if self.config.get("compact_view", False):
            self._toggle_compact()
        # Restore always-on-top if saved
        if self.config.get("always_on_top", False):
            self._apply_always_on_top()
        self._load_connections()
        # Check for updates in background
        self._start_update_check()

    def _restore_position(self):
        x = self.config.get("window_x")
        y = self.config.get("window_y")
        if x is not None and y is not None:
            self.move(x, y)
        else:
            self._center_on_screen()

    def _center_on_screen(self):
        screen = self.screen().availableGeometry()
        x = screen.x() + (screen.width() - self.width()) // 2
        y = screen.y() + (screen.height() - self.height()) // 2
        self.move(x, y)

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

                # Color based on mmol/L ranges
                mmol_val = reading.value_mmol
                if mmol_val < 4:
                    color = "color: #cc0000;"
                elif mmol_val <= 10:
                    color = "color: #333;"
                elif mmol_val <= 14.9:
                    color = "color: #cc8800;"
                else:
                    color = "color: #6b1010;"
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

        radius = 20  # rounded corner radius

        if reading:
            unit = self.config.get("unit", "mmol")
            val = reading.value(unit)
            text = str(val)

            # Background and text color based on mmol/L ranges
            mmol_val = reading.value_mmol
            if mmol_val < 4:
                bg_color = QColor("#cc0000")       # red
                fg_color = QColor("#ffdd00")        # yellow
            elif mmol_val <= 10:
                bg_color = QColor("#2ecc71")        # light green
                fg_color = QColor("black")
            elif mmol_val <= 14.9:
                bg_color = QColor("#f0c800")        # yellow
                fg_color = QColor("black")
            else:
                bg_color = QColor("#6b1010")        # bloody/dark red
                fg_color = QColor("white")

            painter.setBrush(bg_color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(0, 0, size, size, radius, radius)

            # Text — large and bold to fill the icon
            painter.setPen(fg_color)
            font_size = 120 if len(text) <= 3 else (100 if len(text) <= 4 else 80)
            font = QFont("Segoe UI", font_size, QFont.Bold)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
        else:
            painter.setBrush(QColor("#888"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(0, 0, size, size, radius, radius)
            painter.setPen(QColor("white"))
            painter.setFont(QFont("Segoe UI", 120, QFont.Bold))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "--")

        painter.end()

        icon = QIcon(pixmap)
        self._last_icon = icon
        self.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)

        # Force-set via Win32 API so pinned taskbar icons update
        self._set_native_icon(pixmap)

        # Update system tray icon
        if reading:
            unit = self.config.get("unit", "mmol")
            val = reading.value(unit)
            unit_str = "mmol/L" if unit == "mmol" else "mg/dL"
            self._tray_icon.setIcon(icon)
            self._tray_icon.setToolTip(f"LibreLinkUp — {val} {unit_str}")
            if not self._tray_icon.isVisible():
                self._tray_icon.show()
            self.setWindowTitle(app_title(self.config, f"— {val} {unit_str}"))
        else:
            self._tray_icon.setIcon(icon)
            self._tray_icon.setToolTip("LibreLinkUp — No Recent Data")
            if not self._tray_icon.isVisible():
                self._tray_icon.show()
            self.setWindowTitle(app_title(self.config))

    def _set_native_icon(self, pixmap: QPixmap):
        """Force-set the taskbar icon via Win32 SendMessage(WM_SETICON)."""
        try:
            hwnd = int(self.winId())
            hicon = _hicon_from_pixmap(pixmap)
            if hicon:
                if self._last_hicon:
                    ctypes.windll.user32.DestroyIcon(self._last_hicon)
                self._last_hicon = hicon
                ctypes.windll.user32.SendMessageW(hwnd, _WM_SETICON, _ICON_BIG, hicon)
                ctypes.windll.user32.SendMessageW(hwnd, _WM_SETICON, _ICON_SMALL, hicon)
        except Exception:
            pass  # fall back to Qt icon silently

    def _update_unit_button(self):
        unit = self.config.get("unit", "mmol")
        self.unit_btn.setText("mmol/L" if unit == "mmol" else "mg/dL")

    def _show_gear_menu(self):
        menu = QMenu(self)
        menu.setObjectName("gearMenu")

        # Compact / Full view
        compact_action = menu.addAction("Compact View" if not self._compact else "Full View")
        compact_action.triggered.connect(self._toggle_compact)

        # Keep on top
        on_top_action = menu.addAction("Keep on Top")
        on_top_action.setCheckable(True)
        on_top_action.setChecked(self.config.get("always_on_top", False))
        on_top_action.triggered.connect(self._toggle_always_on_top)

        menu.addSeparator()

        # Beep toggle with threshold display
        threshold = self.config.get("low_beep_threshold_mmol", 4.0)
        unit = self.config.get("unit", "mmol")
        if unit == "mgdl":
            val = round(threshold * 18.0)
            unit_str = "mg/dL"
        else:
            val = threshold
            unit_str = "mmol/L"
        beep_action = menu.addAction(f"Beep < {val} {unit_str}")
        beep_action.setCheckable(True)
        beep_action.setChecked(self.config.get("low_beep_enabled", True))
        beep_action.triggered.connect(self._on_beep_toggled)

        # Set threshold
        threshold_action = menu.addAction("Set Beep Threshold...")
        threshold_action.triggered.connect(self._show_beep_threshold_dialog)

        menu.addSeparator()

        # Check for updates
        update_action = menu.addAction("Check for Updates...")
        update_action.triggered.connect(self._check_for_updates)

        menu.addSeparator()

        # Logout
        logout_action = menu.addAction("Logout")
        logout_action.triggered.connect(self._do_logout)

        # Show menu above the gear button
        gear_btn = self.sender()
        pos = gear_btn.mapToGlobal(gear_btn.rect().topLeft())
        menu.exec(pos)

    def _toggle_always_on_top(self, checked):
        self.config["always_on_top"] = checked
        self._apply_always_on_top()
        from utils.config import save_config
        save_config(self.config)

    def _apply_always_on_top(self):
        on_top = self.config.get("always_on_top", False)
        was_visible = self.isVisible()
        base_flags = (
            Qt.Window | Qt.WindowCloseButtonHint
            | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
        )
        if on_top:
            self.setWindowFlags(base_flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(base_flags)
        # setWindowFlags destroys the native window — re-apply icon and show
        if self._last_icon:
            self.setWindowIcon(self._last_icon)
            QApplication.instance().setWindowIcon(self._last_icon)
        if was_visible:
            self.show()
        # Re-apply native icon after new HWND is created
        if self._last_hicon:
            try:
                hwnd = int(self.winId())
                ctypes.windll.user32.SendMessageW(hwnd, _WM_SETICON, _ICON_BIG, self._last_hicon)
                ctypes.windll.user32.SendMessageW(hwnd, _WM_SETICON, _ICON_SMALL, self._last_hicon)
            except Exception:
                pass

    def _do_logout(self):
        # Clear cached credentials
        self.config["remember_credentials"] = False
        self.config["email"] = ""
        self.config["password"] = ""
        from utils.config import save_config
        save_config(self.config)
        self.logout_requested.emit()

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

    def _on_tray_activated(self, reason):
        """Clicking the tray icon brings the window to the front."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.showNormal()
            self.activateWindow()
            self.raise_()

    def closeEvent(self, event):
        self._save_position()
        self._tray_icon.hide()
        self.stop_timer()
        super().closeEvent(event)

    def _save_position(self):
        pos = self.pos()
        self.config["window_x"] = pos.x()
        self.config["window_y"] = pos.y()
        from utils.config import save_config
        save_config(self.config)

    def _start_update_check(self):
        """Run a background update check on startup."""
        self._update_thread = _UpdateChecker()
        self._update_thread.update_available.connect(self._on_update_available)
        self._update_thread.start()

    def _on_update_available(self, new_version: str, download_url: str):
        """Called from background thread when an update is found — auto-applies."""
        from utils.updater import download_and_apply

        logger.info("Auto-updating to v%s", new_version)
        download_and_apply(download_url)

    def _check_for_updates(self):
        """Check GitHub for a newer release and offer to install it."""
        from utils.updater import check_for_update, download_and_apply

        result = check_for_update()
        if result is None:
            QMessageBox.information(self, "Up to Date", "You are running the latest version.")
            return

        new_version, download_url = result
        reply = QMessageBox.question(
            self,
            "Update Available",
            f"Version {new_version} is available (you have {self._current_version()}).\n\n"
            "Download and install now? The app will restart.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            download_and_apply(download_url)

    @staticmethod
    def _current_version() -> str:
        from utils.version import __version__
        return __version__

    def stop_timer(self):
        self._timer.stop()
        self._stop_blinking()
