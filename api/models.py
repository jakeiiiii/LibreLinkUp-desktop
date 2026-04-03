from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


TREND_ARROWS = {
    1: "↓",    # Falling quickly
    2: "↘",    # Falling
    3: "→",    # Stable
    4: "↗",    # Rising
    5: "↑",    # Rising quickly
}

MGDL_TO_MMOL = 18.0


@dataclass
class GlucoseReading:
    timestamp: datetime
    value_mgdl: float
    trend_arrow: int = 3
    measurement_color: int = 1
    is_high: bool = False
    is_low: bool = False

    @property
    def value_mmol(self) -> float:
        return round(self.value_mgdl / MGDL_TO_MMOL, 1)

    @property
    def trend_symbol(self) -> str:
        return TREND_ARROWS.get(self.trend_arrow, "?")

    def value(self, unit: str = "mmol") -> float:
        if unit == "mgdl":
            return self.value_mgdl
        return self.value_mmol

    @staticmethod
    def from_api(data: dict) -> "GlucoseReading":
        ts_str = data.get("Timestamp") or data.get("FactoryTimestamp", "")
        try:
            timestamp = datetime.strptime(ts_str, "%m/%d/%Y %I:%M:%S %p")
        except (ValueError, TypeError):
            timestamp = datetime.now()

        return GlucoseReading(
            timestamp=timestamp,
            value_mgdl=float(data.get("ValueInMgPerDl", 0)),
            trend_arrow=int(data.get("TrendArrow", 3)),
            measurement_color=int(data.get("MeasurementColor", 1)),
            is_high=bool(data.get("isHigh", False)),
            is_low=bool(data.get("isLow", False)),
        )


@dataclass
class Connection:
    patient_id: str
    first_name: str
    last_name: str
    current_reading: Optional[GlucoseReading] = None
    sensor_serial: str = ""
    target_low_mgdl: float = 70
    target_high_mgdl: float = 180
    low_alarm_mgdl: float = 70
    high_alarm_mgdl: float = 180

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def target_low_mmol(self) -> float:
        return round(self.target_low_mgdl / MGDL_TO_MMOL, 1)

    @property
    def target_high_mmol(self) -> float:
        return round(self.target_high_mgdl / MGDL_TO_MMOL, 1)

    @property
    def low_alarm_mmol(self) -> float:
        return round(self.low_alarm_mgdl / MGDL_TO_MMOL, 1)

    @property
    def high_alarm_mmol(self) -> float:
        return round(self.high_alarm_mgdl / MGDL_TO_MMOL, 1)

    @staticmethod
    def from_api(data: dict) -> "Connection":
        reading = None
        gm = data.get("glucoseMeasurement")
        if gm:
            reading = GlucoseReading.from_api(gm)

        # Target range from top-level fields
        target_low = float(data.get("targetLow", 70))
        target_high = float(data.get("targetHigh", 180))

        # Alarm thresholds from alarmRules dict: {h: {th: ...}, l: {th: ...}, ...}
        alarm_rules = data.get("alarmRules", {})
        low_alarm = target_low
        high_alarm = target_high
        if isinstance(alarm_rules, dict):
            low_data = alarm_rules.get("l", {})
            if isinstance(low_data, dict) and "th" in low_data:
                low_alarm = float(low_data["th"])
            high_data = alarm_rules.get("h", {})
            if isinstance(high_data, dict) and "th" in high_data:
                high_alarm = float(high_data["th"])

        return Connection(
            patient_id=data.get("patientId", ""),
            first_name=data.get("firstName", ""),
            last_name=data.get("lastName", ""),
            current_reading=reading,
            sensor_serial=data.get("sensor", {}).get("sn", "") if data.get("sensor") else "",
            target_low_mgdl=target_low,
            target_high_mgdl=target_high,
            low_alarm_mgdl=low_alarm,
            high_alarm_mgdl=high_alarm,
        )


@dataclass
class GraphData:
    connection: Connection
    readings: list[GlucoseReading] = field(default_factory=list)

    @staticmethod
    def from_api(data: dict) -> "GraphData":
        connection_data = data.get("connection", {})
        connection = Connection.from_api(connection_data)

        readings = []
        for item in data.get("graphData", []):
            readings.append(GlucoseReading.from_api(item))

        readings.sort(key=lambda r: r.timestamp)
        return GraphData(connection=connection, readings=readings)


@dataclass
class LogbookEntry:
    timestamp: datetime
    value_mgdl: float
    entry_type: int = 0

    @property
    def value_mmol(self) -> float:
        return round(self.value_mgdl / MGDL_TO_MMOL, 1)

    def value(self, unit: str = "mmol") -> float:
        if unit == "mgdl":
            return self.value_mgdl
        return self.value_mmol

    @staticmethod
    def from_api(data: dict) -> "LogbookEntry":
        ts_str = data.get("Timestamp") or data.get("FactoryTimestamp", "")
        try:
            timestamp = datetime.strptime(ts_str, "%m/%d/%Y %I:%M:%S %p")
        except (ValueError, TypeError):
            timestamp = datetime.now()

        return LogbookEntry(
            timestamp=timestamp,
            value_mgdl=float(data.get("ValueInMgPerDl", 0)),
            entry_type=int(data.get("type", 0)),
        )
