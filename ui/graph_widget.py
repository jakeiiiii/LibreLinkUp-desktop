from datetime import datetime

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from api.models import GlucoseReading, MGDL_TO_MMOL


class TimeAxisItem(pg.AxisItem):
    """Custom axis that displays timestamps as human-readable times."""

    def tickStrings(self, values, scale, spacing):
        result = []
        for v in values:
            try:
                dt = datetime.fromtimestamp(v)
                result.append(dt.strftime("%I%p").lstrip("0"))
            except (OSError, ValueError, OverflowError):
                result.append("")
        return result


class GlucoseChart(pg.PlotWidget):
    def __init__(self, parent=None):
        time_axis = TimeAxisItem(orientation="bottom")
        super().__init__(
            parent=parent,
            axisItems={"bottom": time_axis},
            background="w",
        )

        self._unit = "mmol"
        self._target_low = 3.9
        self._target_high = 10.0
        self._low_alarm = None

        self._setup_plot()

    def _setup_plot(self):
        self.setMouseEnabled(x=True, y=False)
        self.showGrid(x=False, y=True, alpha=0.15)

        # Y axis label
        self.setLabel("left", "mmol/L")

        plot_item = self.getPlotItem()
        plot_item.getAxis("left").setWidth(40)
        plot_item.getAxis("bottom").setHeight(30)

        # Target range band (green shaded region)
        self._target_region = pg.LinearRegionItem(
            values=[0, 0],
            orientation="horizontal",
            brush=QColor(144, 238, 144, 50),
            pen=pg.mkPen(None),
            movable=False,
        )
        self.addItem(self._target_region)

        # Low alarm line (red dashed)
        self._low_line = pg.InfiniteLine(
            pos=0, angle=0,
            pen=pg.mkPen(color="r", width=1, style=Qt.DashLine),
        )
        self.addItem(self._low_line)

        # High alarm line (orange dashed)
        self._high_line = pg.InfiniteLine(
            pos=0, angle=0,
            pen=pg.mkPen(color=(255, 165, 0), width=1, style=Qt.DashLine),
        )
        self.addItem(self._high_line)

        # Glucose data line
        self._curve = self.plot(
            [], [],
            pen=pg.mkPen(color="k", width=2),
            symbol=None,
        )

        # Current reading marker
        self._current_dot = pg.ScatterPlotItem(
            size=10,
            brush=pg.mkBrush(200, 50, 50),
            pen=pg.mkPen(None),
        )
        self.addItem(self._current_dot)

        self._update_thresholds()

    def set_unit(self, unit: str):
        self._unit = unit
        label = "mmol/L" if unit == "mmol" else "mg/dL"
        self.setLabel("left", label)
        self._update_thresholds()

    def set_target_range(self, low_mmol: float, high_mmol: float):
        self._target_low = low_mmol
        self._target_high = high_mmol
        self._update_thresholds()

    def set_low_alarm(self, value_mgdl: float):
        self._low_alarm = value_mgdl
        self._update_thresholds()

    def _convert(self, mmol_val: float) -> float:
        if self._unit == "mgdl":
            return mmol_val * MGDL_TO_MMOL
        return mmol_val

    def _update_thresholds(self):
        low = self._convert(self._target_low)
        high = self._convert(self._target_high)
        self._target_region.setRegion([low, high])
        self._high_line.setPos(high)

        if self._low_alarm is not None:
            alarm_val = self._low_alarm / MGDL_TO_MMOL if self._unit == "mmol" else self._low_alarm
            self._low_line.setPos(alarm_val)
            self._low_line.setVisible(True)
        else:
            self._low_line.setPos(low)
            self._low_line.setVisible(True)

    def update_data(self, readings: list[GlucoseReading], current: GlucoseReading = None):
        if not readings:
            self._curve.setData([], [])
            self._current_dot.setData([], [])
            return

        timestamps = []
        values = []
        for r in readings:
            ts = r.timestamp.timestamp()
            val = r.value(self._unit)
            timestamps.append(ts)
            values.append(val)

        self._curve.setData(timestamps, values)

        # Show current reading dot
        if current:
            ct = current.timestamp.timestamp()
            cv = current.value(self._unit)
            self._current_dot.setData([ct], [cv])
        elif timestamps:
            self._current_dot.setData([timestamps[-1]], [values[-1]])

        # Auto-range X to show all data, Y with some padding
        if values:
            y_min = min(values) - 1
            y_max = max(values) + 1
            self.setYRange(max(0, y_min), y_max, padding=0)
            self.setXRange(timestamps[0], timestamps[-1], padding=0.02)
