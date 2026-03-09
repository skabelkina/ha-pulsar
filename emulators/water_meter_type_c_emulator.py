"""Pulsar Water Meter Type C Emulator - RS485 Meters.

Returns Float32 volume values with minimal diagnostics.
"""

from __future__ import annotations

from datetime import datetime

from base_emulator import BaseEmulator
from config_loader import load_config, get_device_config


class WaterMeterTypeCEmulator(BaseEmulator):
    """Type C: RS485 Meters emulator (Float32 format, minimal diagnostics)."""

    def __init__(self, port: int | None = None, config_path: str | None = None):
        """Initialize Type C water meter emulator.

        Args:
            port: TCP port to listen on. If None, uses config value.
            config_path: Path to config file. If None, uses default.
        """
        # Load configuration
        config = load_config(config_path)
        device_config = get_device_config(config, "water_meter_type_c")

        # Extract configuration values
        self.device_id = device_config["device_id"]
        self.device_address = device_config["address"]
        self.port = port if port is not None else device_config["port"]

        # Channel data (Float32, m³)
        self.channel_1_volume = device_config["channels"]["volume"]

        # Parameters
        params = device_config["parameters"]
        self.reed_switch = params["reed_switch"]  # UINT8

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
        """Get channel data for Type C water meter.

        Type C has only Channel 1 (Volume) as Float32 (4 bytes, IEEE 754).

        Args:
            channel_mask: Bitmask of channels to read.

        Returns:
            Channel data bytes or None if invalid.
        """
        if channel_mask == 0:
            return None

        channel_data = bytearray()

        # Channel 1: Volume (Float32, 4 bytes, IEEE 754, little-endian)
        if channel_mask & 0x01:
            channel_data.extend(self.encode_float32(self.channel_1_volume))

        # Type C only has 1 channel, reject other channel requests
        if channel_mask & ~0x01:
            return None

        return bytes(channel_data)

    def get_parameter(self, param_index: int) -> bytes | None:
        """Get parameter value for Type C water meter.

        Note: Battery/Temp registers are not available in standard protocol.

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

        elif param_index == 0x001C:
            # Protective Reed Switch (UINT8)
            result[0] = self.reed_switch

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
        """Get archive data for Type C water meter (Float32 format).

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

        # Generate archive records (Float32 format)
        if archive_type == 1:
            num_records = min(
                24, int((date_end - date_start).total_seconds() / 3600) + 1
            )
            base_value = self.channel_1_volume
            for i in range(num_records):
                value = base_value + (i * 0.5)  # 0.5 m³ per hour
                response.extend(self.encode_float32(value))

        elif archive_type == 2:
            num_records = min(7, (date_end - date_start).days + 1)
            base_value = self.channel_1_volume
            for i in range(num_records):
                value = base_value + (i * 12.0)  # 12.0 m³ per day
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
            base_value = self.channel_1_volume
            for i in range(num_records):
                value = base_value + (i * 360.0)  # 360.0 m³ per month
                response.extend(self.encode_float32(value))

        return bytes(response)


def main():
    """Run the Type C water meter emulator."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Pulsar Water Meter Type C Emulator (RS485 Meters)"
    )
    parser.add_argument(
        "--port", type=int, default=9603, help="TCP port to listen on (default: 9603)"
    )
    args = parser.parse_args()

    emulator = WaterMeterTypeCEmulator(port=args.port)
    try:
        emulator.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        emulator.stop()


if __name__ == "__main__":
    main()
