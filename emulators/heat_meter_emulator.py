"""PulsarM Heat Meter Emulator.

Provides static data for testing the Home Assistant integration.
"""

from __future__ import annotations

import struct
from datetime import datetime

from base_emulator import BaseEmulator
from config_loader import load_config, get_device_config


class HeatMeterEmulator(BaseEmulator):
    """Heat meter emulator with static data."""

    def __init__(self, port: int | None = None, config_path: str | None = None):
        """Initialize heat meter emulator.

        Args:
            port: TCP port to listen on. If None, uses config value.
            config_path: Path to config file. If None, uses default.
        """
        # Load configuration
        config = load_config(config_path)
        device_config = get_device_config(config, "heat_meter")

        # Extract configuration values
        self.device_id = device_config["device_id"]
        self.device_address = device_config["address"]
        self.port = port if port is not None else device_config["port"]

        # Channel data (FLOAT32 except Ch7 which is UINT32, Ch8 is UINT32)
        channels = device_config["channels"]
        self.channel_1_volume_supply = channels["volume_supply"]
        self.channel_2_volume_return = channels["volume_return"]
        self.channel_3_temp_supply = channels["temp_supply"]
        self.channel_4_temp_return = channels["temp_return"]
        self.channel_5_energy_heat = channels["energy_heat"]
        self.channel_6_energy_cooling = channels["energy_cooling"]
        self.channel_7_operation_time = channels["operating_time"]  # UINT32
        self.channel_8_error_flags = channels.get("error_flags", 0x0000)  # UINT32
        self.channel_9_pulse_input_1 = channels["pulse_input_1"]
        self.channel_10_pulse_input_2 = channels["pulse_input_2"]
        self.channel_11_pulse_input_3 = channels["pulse_input_3"]
        self.channel_12_pulse_input_4 = channels["pulse_input_4"]
        self.channel_13_pressure_supply = channels["pressure_supply"]
        self.channel_14_pressure_return = channels["pressure_return"]

        # Parameters
        params = device_config["parameters"]
        self.factory_number = params.get("factory_number", "HM123456")  # 8 bytes ASCII
        self.battery_voltage = params["battery_voltage"]  # mV
        self.pulse_in_1_weight = params.get("pulse_in_1_weight", 0.1)  # m³/imp
        self.flow_rate = params.get("flow_rate", 0.5)  # m³/h
        self.temp_diff = params.get("temp_diff", 30.3)  # °C
        self.environment_temp = params.get("environment_temp", 20)  # °C (int8)
        self.power_heat = params.get("power_heat", 0.5)  # Gcal/h
        self.last_rssi = params.get("last_rssi", -70)  # dBm (int8)

        # Firmware version
        fw = device_config["firmware"]
        self.fw_number = fw["fw_number"]
        self.hw_version = fw["hw_version"]
        self.sw_version = fw["sw_version"]
        self.revision = fw["revision"]
        self.modification = fw["modification"]

        # Default values for parameters not in config
        self.operating_time = self.channel_7_operation_time  # hours

        super().__init__(
            device_address=self.device_address,
            device_id=self.device_id,
            port=self.port,
        )

    def get_channel_data(self, channel_mask: int) -> bytes | None:
        """Get channel data for heat meter.

        Heat meter has 13 channels, most are FLOAT32 except Ch7 (UINT32).

        Args:
            channel_mask: Bitmask of channels to read.

        Returns:
            Channel data bytes or None if invalid.
        """
        if channel_mask == 0:
            return None

        channel_data = bytearray()

        # Define channels with their data
        channels = [
            (0x01, self.encode_float32(self.channel_1_volume_supply)),
            (0x02, self.encode_float32(self.channel_2_volume_return)),
            (0x04, self.encode_float32(self.channel_3_temp_supply)),
            (0x08, self.encode_float32(self.channel_4_temp_return)),
            (0x10, self.encode_float32(self.channel_5_energy_heat)),
            (0x20, self.encode_float32(self.channel_6_energy_cooling)),
            (0x40, self.encode_uint(self.channel_7_operation_time, 4)),  # UINT32
            (0x80, self.encode_uint(self.channel_8_error_flags, 4)),  # UINT32
            (0x100, self.encode_float32(self.channel_9_pulse_input_1)),
            (0x200, self.encode_float32(self.channel_10_pulse_input_2)),
            (0x400, self.encode_float32(self.channel_11_pulse_input_3)),
            (0x800, self.encode_float32(self.channel_12_pulse_input_4)),
            (0x1000, self.encode_float32(self.channel_13_pressure_supply)),
            (0x2000, self.encode_float32(self.channel_14_pressure_return)),
        ]

        # Add requested channels in order
        for mask_bit, data in channels:
            if channel_mask & mask_bit:
                channel_data.extend(data)

        # Reject if requesting non-existent channels (bits 14-31, except valid ones)
        if channel_mask & ~0x3FFF:
            return None

        return bytes(channel_data) if len(channel_data) > 0 else None

    def get_parameter(self, param_index: int) -> bytes | None:
        """Get parameter value for heat meter.

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
            # Byte 0-1: FW Number
            result[0:2] = self.encode_uint(self.fw_number, 2)
            # Byte 2-3: HW Version
            result[2:4] = self.encode_uint(self.hw_version, 2)
            # Byte 4-5: SW Version
            result[4:6] = self.encode_uint(self.sw_version, 2)
            # Byte 6: Revision
            result[6] = self.revision
            # Byte 7: Modification
            result[7] = self.modification

        elif param_index == 0x0005:
            # Factory Number (STRING, 8 bytes ASCII)
            factory_bytes = self.factory_number.encode("ascii")
            result[0 : len(factory_bytes)] = factory_bytes

        elif param_index == 0x0100:
            # Flow Rate (FLOAT32) - m³/h
            result[0:4] = self.encode_float32(self.flow_rate)

        elif param_index == 0x0130:
            # Temperature Difference (FLOAT32) - °C
            result[0:4] = self.encode_float32(self.temp_diff)

        elif param_index == 0x0131:
            # Environment Temperature (INT8) - °C
            result[0] = struct.pack("b", self.environment_temp)[0]

        elif param_index == 0x0170:
            # Power Heat (FLOAT32) - Gcal/h
            result[0:4] = self.encode_float32(self.power_heat)

        elif param_index == 0x0402:
            # Last RSSI (INT8) - dBm
            result[0] = struct.pack("b", self.last_rssi)[0]

        elif param_index == 0x0012:
            # Operating Time (UINT32)
            result[0:4] = self.encode_uint(self.operating_time, 4)

        elif param_index == 0x0020:
            # Pulse Out 1 Mode (UINT8)
            result[0] = 0x00  # Default mode

        elif param_index == 0x0040:
            # Battery Voltage (UINT16)
            result[0:2] = self.encode_uint(self.battery_voltage, 2)

        elif param_index == 0x0041:
            # Pulse Out Weight (FLOAT32)
            result[0:4] = self.encode_float32(1.0)

        elif param_index == 0x000C:
            # Pulse In 1 Weight (FLOAT32)
            result[0:4] = self.encode_float32(self.pulse_in_1_weight)

        elif param_index == 0x000D:
            # Pulse In 1 Initial (FLOAT32)
            result[0:4] = self.encode_float32(0.0)

        elif param_index == 0x1100:
            # LoRa Device EUI (8 bytes)
            # Return a dummy EUI
            result = bytearray([0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07])

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
        """Get archive data for heat meter.

        Generates synthetic archive records for testing.

        Args:
            channel_mask: Single channel mask.
            archive_type: Archive type (1=hourly, 2=daily, 3=monthly).
            date_start: Start datetime.
            date_end: End datetime.

        Returns:
            Archive data or None if invalid.
        """
        # Validate that only one channel is requested
        if channel_mask == 0 or (channel_mask & (channel_mask - 1)) != 0:
            return None

        # Validate archive type
        if archive_type not in [1, 2, 3]:
            return None

        # Determine which channel was requested
        channel_num = 0
        temp_mask = channel_mask
        while temp_mask > 1:
            temp_mask >>= 1
            channel_num += 1
        channel_num += 1  # Convert to 1-based

        # Build response header
        response = bytearray()

        # Echo back mask
        response.extend(self.encode_uint(channel_mask, 4))

        # Echo back start date
        response.extend(self.encode_datetime(date_start))

        # Determine base value for this channel
        base_values = {
            1: self.channel_1_volume_supply,
            2: self.channel_2_volume_return,
            3: self.channel_3_temp_supply,
            4: self.channel_4_temp_return,
            5: self.channel_5_energy_heat,
            6: self.channel_6_energy_cooling,
            9: self.channel_9_pulse_input_1,
            10: self.channel_10_pulse_input_2,
            11: self.channel_11_pulse_input_3,
            12: self.channel_12_pulse_input_4,
            13: self.channel_13_pressure_supply,
            14: self.channel_14_pressure_return,
        }

        # Generate archive records based on type
        if archive_type == 1:
            # Hourly archive - generate up to 24 records
            num_records = min(
                24, int((date_end - date_start).total_seconds() / 3600) + 1
            )
        elif archive_type == 2:
            # Daily archive - generate up to 7 records
            num_records = min(7, (date_end - date_start).days + 1)
        else:  # archive_type == 3
            # Monthly archive - generate up to 3 records
            num_records = min(
                3,
                (
                    (date_end.year - date_start.year) * 12
                    + date_end.month
                    - date_start.month
                )
                + 1,
            )

        # Generate records
        if channel_num == 7:
            # Channel 7 is UINT32
            base_value = self.channel_7_operation_time
            for i in range(num_records):
                value = base_value + (i * 100)
                response.extend(self.encode_uint(value, 4))
        elif channel_num in base_values:
            # Other channels are FLOAT32
            base_value = base_values[channel_num]
            increment = base_value * 0.01  # 1% increment per record
            for i in range(num_records):
                value = base_value + (i * increment)
                response.extend(self.encode_float32(value))
        else:
            return None

        return bytes(response)


def main():
    """Run the heat meter emulator."""
    import argparse

    parser = argparse.ArgumentParser(description="PulsarM Heat Meter Emulator")
    parser.add_argument(
        "--port", type=int, default=9602, help="TCP port to listen on (default: 9602)"
    )
    args = parser.parse_args()

    emulator = HeatMeterEmulator(port=args.port)
    try:
        emulator.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        emulator.stop()


if __name__ == "__main__":
    main()
