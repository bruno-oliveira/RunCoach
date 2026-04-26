"""FIT workout file generation for Garmin devices with pace targets.

Encodes FIT binary directly to match the format produced by the official
Garmin FIT SDK tools (big-endian, 14-byte header with CRC, profile 21.201).

FIT Protocol Scale Factors:
- Speed: m/s * 1000 (stored as mm/s)
- Distance: m * 100 (stored as cm)
- Time: s * 1000 (stored as ms)
"""

import datetime
import struct
from typing import Any

SPEED_SCALE = 1000
DISTANCE_SCALE = 100
TIME_SCALE = 1000

_CRC_TABLE = [
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
]


def _crc16(data: bytes, crc: int = 0) -> int:
    for byte in data:
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[byte & 0xF]
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[(byte >> 4) & 0xF]
    return crc


def _pace_min_km_to_speed_raw(pace_min_km: float) -> int:
    if pace_min_km <= 0:
        return 0
    speed_ms = 1000.0 / (pace_min_km * 60.0)
    return int(round(speed_ms * SPEED_SCALE))


def _encode_string(value: str, size: int) -> bytes:
    encoded = value.encode("utf-8") + b"\x00"
    return encoded.ljust(size, b"\x00")[:size]


class _FITWriter:
    """Minimal FIT binary writer matching Garmin SDK output format."""

    PROTOCOL_VERSION = 0x20  # 2.0
    PROFILE_VERSION = 21201  # 21.201

    def __init__(self):
        self._records = bytearray()
        self._local_counter = 0

    def _write_definition(self, local_id: int, global_id: int, fields: list[tuple[int, int, int]]) -> None:
        buf = struct.pack(">BBBHB", 0x40 | local_id, 0x00, 0x01, global_id, len(fields))
        for field_num, size, base_type in fields:
            buf += struct.pack("BBB", field_num, size, base_type)
        self._records.extend(buf)

    def _write_data(self, local_id: int, payload: bytes) -> None:
        self._records.append(local_id)
        self._records.extend(payload)

    def write_file_id(self, time_created: int, serial_number: int) -> None:
        fields = [
            (0, 1, 0x00),   # type: ENUM
            (1, 2, 0x84),   # manufacturer: UINT16
            (2, 2, 0x84),   # product: UINT16
            (3, 4, 0x8C),   # serial_number: UINT32Z
            (4, 4, 0x86),   # time_created: UINT32
        ]
        self._write_definition(0, 0, fields)
        payload = struct.pack(">BHHII", 5, 255, 0, serial_number, time_created)
        self._write_data(0, payload)

    def write_workout(self, name: str, num_steps: int, string_size: int = 50) -> None:
        fields = [
            (4, 1, 0x00),           # sport: ENUM
            (6, 2, 0x84),           # num_valid_steps: UINT16
            (8, string_size, 0x07), # wkt_name: STRING
        ]
        self._write_definition(0, 26, fields)
        payload = struct.pack(">BH", 1, num_steps) + _encode_string(name, string_size)
        self._write_data(0, payload)

    def write_workout_steps(self, steps: list[dict], string_size: int = 50) -> None:
        fields = [
            (254, 2, 0x84),          # message_index: UINT16
            (0, string_size, 0x07),  # wkt_step_name: STRING
            (1, 1, 0x00),            # duration_type: ENUM
            (2, 4, 0x86),            # duration_value: UINT32
            (3, 1, 0x00),            # target_type: ENUM
            (4, 4, 0x86),            # target_value: UINT32
            (5, 4, 0x86),            # custom_target_value_low: UINT32
            (6, 4, 0x86),            # custom_target_value_high: UINT32
            (7, 1, 0x00),            # intensity: ENUM
        ]
        self._write_definition(0, 27, fields)

        for step in steps:
            payload = struct.pack(">H", step["message_index"])
            payload += _encode_string(step["name"], string_size)
            payload += struct.pack(
                ">BIBIIIB",
                step["duration_type"],
                step["duration_value"],
                step["target_type"],
                step["target_value"],
                step["custom_target_low"],
                step["custom_target_high"],
                step["intensity"],
            )
            self._write_data(0, payload)

    def build(self) -> bytes:
        data_size = len(self._records)
        header = struct.pack("<BbHI4s", 14, self.PROTOCOL_VERSION, self.PROFILE_VERSION, data_size, b".FIT")
        header_crc = _crc16(header)
        header += struct.pack("<H", header_crc)

        file_crc = _crc16(header)
        file_crc = _crc16(bytes(self._records), file_crc)
        return header + bytes(self._records) + struct.pack("<H", file_crc)


class FITService:
    """Generate Garmin-compatible FIT workout files with per-km pace targets."""

    @staticmethod
    def generate_race_workout(
        segments: list[dict[str, Any]],
        target_time_seconds: int,
        target_time_str: str,
        race_name: str = "RunCoach Race Plan",
    ) -> bytes:
        """Create a FIT workout file with distance-based pace targets per km."""
        now = datetime.datetime.now(datetime.timezone.utc)
        garmin_epoch = datetime.datetime(1989, 12, 31, tzinfo=datetime.timezone.utc)
        time_created = int((now - garmin_epoch).total_seconds())

        writer = _FITWriter()
        writer.write_file_id(time_created=time_created, serial_number=0x12345678)

        workout_name = f"{race_name} - {target_time_str}"
        writer.write_workout(name=workout_name, num_steps=len(segments))

        steps = []
        for idx, seg in enumerate(segments):
            seg_distance_m = (seg["end_km"] - seg["start_km"]) * 1000.0
            pace = seg["target_pace_min_km"]

            speed_low = _pace_min_km_to_speed_raw(pace + (5.0 / 60.0))
            speed_high = _pace_min_km_to_speed_raw(max(0.1, pace - (5.0 / 60.0)))

            km_label = f"KM {seg['start_km']:.0f}-{seg['end_km']:.0f}"
            if seg.get("grade_pct", 0) > 0.5:
                km_label += " (uphill)"
            elif seg.get("grade_pct", 0) < -0.5:
                km_label += " (downhill)"

            steps.append({
                "message_index": idx,
                "name": km_label,
                "duration_type": 1,      # DISTANCE
                "duration_value": int(seg_distance_m * DISTANCE_SCALE),
                "target_type": 0,        # SPEED
                "target_value": 0,       # custom range
                "custom_target_low": max(500, speed_low),
                "custom_target_high": max(500, speed_high),
                "intensity": 0,          # ACTIVE
            })

        writer.write_workout_steps(steps)
        return writer.build()
