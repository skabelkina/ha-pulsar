"""Pulsar Water Meter Type D Emulator - Two-Tariff Meters.

Returns Float32 volume values with multiple channels (two-tariff).
"""

from __future__ import annotations

from datetime import datetime

from base_emulator import BaseEmulator
from config_loader import load_config, get_device_config


class WaterMeterTypeDEmulator(BaseEmulator):
    """Type D: Two-Tariff Meters emulator (Float32 format, multi-channel)."""

    def __init__(self, port: int | None = None, config_path: str | None = None):
        """Initialize Type D water meter emulator.

        Args:
            port: TCP port to listen on. If None, uses config value.
            config_path: Path to config file. If None, uses default.
        """
        # Load configuration
        config = load_config(config_path)
        device_config = get_device_config(config, "water_meter_type_d")

        # Extract configuration values
        self.device_id = device_config["device_id"]
        self.device_address = device_config["address"]
        self.port = port if port is not None else device_config["port"]

        # Channel data (Float32)
        channels = device_config["channels"]
        self.channel_3_temp = channels["temp"]
        self.channel_6_volume_total = channels["volume_total"]
        self.channel_7_volume_cold = channels["volume_cold"]
        self.channel_8_volume_hot = channels["volume_hot"]
        self.channel_9_flow_rate = channels.get("flow_rate", 0.0)  # m³/h (Float32)

        # Parameters
        params = device_config["parameters"]
        self.battery_voltage = params["battery_voltage"]  # mV (UINT16)
        self.environment_temp = params["environment_temp"]  # °C (UINT8)
        self.device_status = params["device_status"]  # UINT8
        self.current_errors = params["current_errors"]  # UINT32
        self.operating_time = params.get("operating_time", 0)  # hours (UINT32)

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
        """Get channel data for Type D water meter.

        Type D has multiple channels (3, 6, 7, 8, 9) as Float32.

        Args:
            channel_mask: Bitmask of channels to read.

        Returns:
            Channel data bytes or None if invalid.

        """
        if channel_mask == 0:
            return None

        channel_data = bytearray()

        # Define channels with their data (sorted by channel index)
        channels = [
            (0x04, self.encode_float32(self.channel_3_temp)),  # Ch 3: Temp
            (0x20, self.encode_float32(self.channel_6_volume_total)),  # Ch 6: Vol Total
            (0x40, self.encode_float32(self.channel_7_volume_cold)),  # Ch 7: Vol Cold
            (0x80, self.encode_float32(self.channel_8_volume_hot)),  # Ch 8: Vol Hot
            (0x100, self.encode_float32(self.channel_9_flow_rate)),  # Ch 9: Flow Rate
        ]

        # Add requested channels in order
        for mask_bit, data in channels:
            if channel_mask & mask_bit:
                channel_data.extend(data)

        # Reject if requesting non-existent channels
        if (
            channel_mask & ~0x1E4
        ):  # Only bits 2, 5, 6, 7, 8 are valid (0x04, 0x20, 0x40, 0x80, 0x100)
            return None

        return bytes(channel_data) if len(channel_data) > 0 else None

    def get_parameter(self, param_index: int) -> bytes | None:
        """Get parameter value for Type D water meter.

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

        elif param_index == 0x000A:
            # Battery Voltage (UINT16, mV)
            result[0:2] = self.encode_uint(self.battery_voltage, 2)

        elif param_index == 0x000B:
            # Temperature (UINT8, °C)
            result[0] = self.environment_temp & 0xFF

        elif param_index == 0x0008:
            # Device Status (UINT8, bitmask)
            result[0] = self.device_status

        elif param_index == 0x0006:
            # Error Flags (UINT32, bitmask)
            result[0:4] = self.encode_uint(self.current_errors, 4)

        elif param_index == 0x000C:
            # Operating Time (UINT32, hours)
            result[0:4] = self.encode_uint(self.operating_time, 4)

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
        """Get archive data for Type D water meter (Float32 format).

        Args:
            channel_mask: Single channel mask (must be one of 0x04, 0x20, 0x40, 0x80, 0x100).
            archive_type: Archive type (1=hourly, 2=daily, 3=monthly).
            date_start: Start datetime.
            date_end: End datetime.

        Returns:
            Archive data or None if invalid.

        """
        # Validate that only one channel is requested
        if channel_mask == 0 or (channel_mask & (channel_mask - 1)) != 0:
            return None

        if archive_type not in [1, 2, 3]:
            return None

        # Determine which channel was requested
        channel_values = {
            0x04: self.channel_3_temp,
            0x20: self.channel_6_volume_total,
            0x40: self.channel_7_volume_cold,
            0x80: self.channel_8_volume_hot,
            0x100: self.channel_9_flow_rate,
        }

        if channel_mask not in channel_values:
            return None

        base_value = channel_values[channel_mask]

        response = bytearray()
        response.extend(self.encode_uint(channel_mask, 4))
        response.extend(self.encode_datetime(date_start))

        # Generate archive records (Float32 format)
        if archive_type == 1:
            num_records = min(
                24, int((date_end - date_start).total_seconds() / 3600) + 1
            )
            increment = 0.5  # Temp or volume increment
            for i in range(num_records):
                value = base_value + (i * increment)
                response.extend(self.encode_float32(value))

        elif archive_type == 2:
            num_records = min(7, (date_end - date_start).days + 1)
            increment = 0.1 if channel_mask == 0x04 else 12.0
            for i in range(num_records):
                value = base_value + (i * increment)
                response.extend(self.encode_float32(value))

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
            increment = 1.0 if channel_mask == 0x04 else 360.0
            for i in range(num_records):
                value = base_value + (i * increment)
                response.extend(self.encode_float32(value))

        return bytes(response)


def main():
    """Run the Type D water meter emulator."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Pulsar Water Meter Type D Emulator (Two-Tariff Meters)"
    )
    parser.add_argument(
        "--port", type=int, default=9604, help="TCP port to listen on (default: 9604)"
    )
    args = parser.parse_args()

    emulator = WaterMeterTypeDEmulator(port=args.port)
    try:
        emulator.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        emulator.stop()


if __name__ == "__main__":
    main()
