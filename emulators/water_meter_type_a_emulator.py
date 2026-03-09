"""Pulsar Water Meter Type A Emulator - Pulse Modules (IoT/Mini).

Returns Int32 volume values with modern IoT/Mini parameter map.
"""

from __future__ import annotations

from datetime import datetime

from base_emulator import BaseEmulator
from config_loader import load_config, get_device_config


class WaterMeterTypeAEmulator(BaseEmulator):
    """Type A: Pulse Modules emulator (Int32 format, modern parameters)."""

    def __init__(self, port: int | None = None, config_path: str | None = None):
        """Initialize Type A water meter emulator.

        Args:
            port: TCP port to listen on. If None, uses config value.
            config_path: Path to config file. If None, uses default.
        """
        # Load configuration
        config = load_config(config_path)
        device_config = get_device_config(config, "water_meter_type_a")

        # Extract configuration values
        self.device_id = device_config["device_id"]
        self.device_address = device_config["address"]
        self.port = port if port is not None else device_config["port"]

        # Channel data (Int32, liters)
        self.channel_1_volume = int(device_config["channels"]["volume"])

        # Parameters
        params = device_config["parameters"]
        self.battery_voltage = params["battery_voltage"]  # mV (UINT16)
        self.environment_temp = params["environment_temp"]  # °C (INT8)
        self.current_errors = params["current_errors"]  # UINT16
        self.last_rssi = params["last_rssi"]  # dBm (INT8)
        self.last_rf_error = params["last_rf_error"]  # UINT8

        # Firmware version
        fw = device_config["firmware"]
        self.fw_number = fw["fw_number"]
        self.hw_version = fw["hw_version"]
        self.sw_version = fw["sw_version"]
        self.revision = fw["revision"]
        self.modification = fw["modification"]

        super().__init__(
            device_address=self.device_address,
            device_id=self.device_id,
            port=self.port,
        )

    def get_channel_data(self, channel_mask: int) -> bytes | None:
        """Get channel data for Type A water meter.

        Type A has only Channel 1 (Volume) as Int32 (signed, 4 bytes).

        Args:
            channel_mask: Bitmask of channels to read.

        Returns:
            Channel data bytes or None if invalid.
        """
        if channel_mask == 0:
            return None

        channel_data = bytearray()

        # Channel 1: Volume (Int32, 4 bytes, signed, little-endian)
        if channel_mask & 0x01:
            channel_data.extend(self.encode_int32(self.channel_1_volume))

        # Type A only has 1 channel, reject other channel requests
        if channel_mask & ~0x01:
            return None

        return bytes(channel_data)

    def get_parameter(self, param_index: int) -> bytes | None:
        """Get parameter value for Type A water meter.

        Args:
            param_index: Parameter index.

        Returns:
            Parameter value (8 bytes) or None if not found.
        """
        result = bytearray(8)

        if param_index == 0x0000:
            # Device ID (UINT16)
            result[0:2] = self.encode_uint(self.device_id, 2)

        elif param_index == 0x0001:
            # Network Address (UINT32)
            result[0:4] = self.encode_uint(self.device_address, 4)

        elif param_index == 0x0002:
            # Firmware Version (UINT64)
            result[0:2] = self.encode_uint(self.fw_number, 2)
            result[2:4] = self.encode_uint(self.hw_version, 2)
            result[4:6] = self.encode_uint(self.sw_version, 2)
            result[6] = self.revision
            result[7] = self.modification

        elif param_index == 0x0041:
            # Battery Voltage (UINT16, mV)
            result[0:2] = self.encode_uint(self.battery_voltage, 2)

        elif param_index == 0x0040:
            # Temperature (INT8, °C)
            result[0] = self.environment_temp & 0xFF

        elif param_index == 0x0007:
            # Current Errors (UINT16, bitmask)
            result[0:2] = self.encode_uint(self.current_errors, 2)

        elif param_index == 0x000E:
            # Last Packet RSSI (INT8, dBm)
            # Convert signed int to byte
            rssi_byte = self.last_rssi & 0xFF
            if self.last_rssi < 0:
                rssi_byte = (self.last_rssi + 256) & 0xFF
            result[0] = rssi_byte

        elif param_index == 0x0049:
            # Last RF Error (UINT8, code)
            result[0] = self.last_rf_error

        else:
            return None

        return bytes(result)

    def get_archive_data(
        self,
        channel_mask: int,
        archive_type: int,
        date_start: datetime,
        date_end: datetime,
    ) -> bytes | None:
        """Get archive data for Type A water meter (Int32 format).

        Args:
            channel_mask: Single channel mask (must be 0x01).
            archive_type: Archive type (1=hourly, 2=daily, 3=monthly).
            date_start: Start datetime.
            date_end: End datetime.

        Returns:
            Archive data or None if invalid.
        """
        if channel_mask != 0x01:
            return None

        if archive_type not in [1, 2, 3]:
            return None

        response = bytearray()
        response.extend(self.encode_uint(channel_mask, 4))
        response.extend(self.encode_datetime(date_start))

        # Generate archive records (Int32 format)
        if archive_type == 1:
            num_records = min(
                24, int((date_end - date_start).total_seconds() / 3600) + 1
            )
            base_value = self.channel_1_volume
            for i in range(num_records):
                value = base_value + (i * 500)  # 500 liters per hour
                response.extend(self.encode_int32(value))

        elif archive_type == 2:
            num_records = min(7, (date_end - date_start).days + 1)
            base_value = self.channel_1_volume
            for i in range(num_records):
                value = base_value + (i * 12000)  # 12000 liters per day
                response.extend(self.encode_int32(value))

        elif archive_type == 3:
            num_records = min(
                3,
                (
                    (date_end.year - date_start.year) * 12
                    + date_end.month
                    - date_start.month
                )
                + 1,
            )
            base_value = self.channel_1_volume
            for i in range(num_records):
                value = base_value + (i * 360000)  # 360000 liters per month
                response.extend(self.encode_int32(value))

        return bytes(response)


def main():
    """Run the Type A water meter emulator."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Pulsar Water Meter Type A Emulator (Pulse Modules)"
    )
    parser.add_argument(
        "--port", type=int, default=9601, help="TCP port to listen on (default: 9601)"
    )
    args = parser.parse_args()

    emulator = WaterMeterTypeAEmulator(port=args.port)
    try:
        emulator.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        emulator.stop()


if __name__ == "__main__":
    main()
