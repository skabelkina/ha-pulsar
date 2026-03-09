"""Device type metadata definitions for Pulsar meters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import enum
from typing import Any, Literal

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)

from .const import (
    FUNCTION_READ_CHANNELS,
    FUNCTION_READ_SYSTEM_TIME,
    FUNCTION_READ_PARAMETERS,
)


class DeviceType(enum.StrEnum):
    """Device type identifiers."""

    WATER_TYPE_A = "water_type_a"
    WATER_TYPE_B = "water_type_b"
    WATER_TYPE_C = "water_type_c"
    WATER_TYPE_D = "water_type_d"
    WATER_TYPE_E = "water_type_e"
    HEAT_TYPE_A = "heat_type_a"
    HEAT_TYPE_B = "heat_type_b"


@dataclass(frozen=True)
class DataSpec:
    """Unified specification for channels and parameters."""

    address: int
    function_code: int
    key: str
    data_type: Literal[
        "int32", "float32", "uint32", "uint8", "uint16", "int8", "string", "datetime"
    ]
    unit: str | None
    translation_key: str | None = None
    entity_category: EntityCategory | None = None
    icon: str | None = None
    read_only: bool = True
    scale_factor: float = 1.0
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    display_precision: int | None = None

    @property
    def payload_size(self) -> int:
        """Request payload size in bytes."""
        payload_sizes = {
            FUNCTION_READ_CHANNELS: 4,
            FUNCTION_READ_SYSTEM_TIME: 0,
            FUNCTION_READ_PARAMETERS: 2,
        }
        return payload_sizes.get(self.function_code, 2)

    @property
    def response_size(self) -> int:
        """Expected response payload size in bytes."""
        response_sizes = {
            FUNCTION_READ_CHANNELS: 4,
            FUNCTION_READ_SYSTEM_TIME: 6,
            FUNCTION_READ_PARAMETERS: 8,
        }
        return response_sizes.get(self.function_code, 8)


@dataclass(frozen=True)
class DevicePropertySpec:
    """Specification for device properties (firmware version, etc.)."""

    address: int
    function_code: int
    key: str
    data_type: Literal["uint8", "uint16", "uint32", "uint64"]

    @property
    def payload_size(self) -> int:
        """Request payload size in bytes."""
        return 2

    @property
    def response_size(self) -> int:
        """Expected response payload size in bytes."""
        return 8


def parse_firmware_info(properties: dict[str, Any]) -> dict[str, Any]:
    """Parse firmware_info and extract sw_version and hw_version.

    Structure: [fw_number(2), hw_version(2), sw_version(2), revision(1), modification(1)]
    """
    firmware_info = properties.get("firmware_info")
    if firmware_info is None:
        return {}
    return {
        "sw_version": (firmware_info >> 32) & 0xFFFF,
        "hw_version": (firmware_info >> 16) & 0xFFFF,
    }


@dataclass(frozen=True)
class DeviceTypeMetadata:
    """Complete device type specification."""

    type_id: str
    model_name: str
    data_specs: tuple[DataSpec, ...]
    property_specs: tuple[DevicePropertySpec, ...] = ()
    property_parser: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def battery_voltage_sensor(
    address: int,
    data_type: Literal["uint16", "float32"] = "uint16",
    scale_factor: float = 0.001,
) -> DataSpec:
    """Create a battery voltage DataSpec."""
    return DataSpec(
        address=address,
        function_code=FUNCTION_READ_PARAMETERS,
        key="battery_voltage",
        data_type=data_type,
        unit=UnitOfElectricPotential.VOLT,
        translation_key="battery_voltage",
        scale_factor=scale_factor,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        display_precision=1,
    )


def volume_sensor(
    address: int,
    key: str,
    data_type: Literal["int32", "float32"],
    unit: str = UnitOfVolume.LITERS,
    scale_factor: float = 1.0,
) -> DataSpec:
    """Create a volume DataSpec."""
    return DataSpec(
        address=address,
        function_code=FUNCTION_READ_CHANNELS,
        key=key,
        data_type=data_type,
        unit=unit,
        translation_key=key,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        display_precision=1,
        scale_factor=scale_factor,
    )


def temperature_sensor(
    address: int,
    key: str,
    data_type: Literal["int8", "float32", "uint8"],
    function_code: int = FUNCTION_READ_PARAMETERS,
) -> DataSpec:
    """Create a temperature DataSpec."""
    return DataSpec(
        address=address,
        function_code=function_code,
        key=key,
        data_type=data_type,
        unit=UnitOfTemperature.CELSIUS,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        display_precision=1,
    )


def flow_rate_sensor(
    address: int,
    function_code: int = FUNCTION_READ_CHANNELS,
    scale_factor: float = 1000.0,
) -> DataSpec:
    """Create a flow rate DataSpec."""
    return DataSpec(
        address=address,
        function_code=function_code,
        key="flow_rate",
        data_type="float32",
        unit=UnitOfVolumeFlowRate.LITERS_PER_HOUR,
        translation_key="flow_rate",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        display_precision=1,
        scale_factor=scale_factor,
    )


def energy_sensor(
    address: int,
    key: str,
) -> DataSpec:
    """Create an energy DataSpec."""
    return DataSpec(
        address=address,
        function_code=FUNCTION_READ_CHANNELS,
        key=key,
        data_type="float32",
        unit=UnitOfEnergy.GIGA_CALORIE,
        translation_key=key,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        display_precision=1,
    )


def pressure_sensor(
    address: int,
    key: str,
    scale_factor: float = 1.0,
    display_precision: int = 1,
) -> DataSpec:
    """Create a pressure DataSpec."""
    return DataSpec(
        address=address,
        function_code=FUNCTION_READ_CHANNELS,
        key=key,
        data_type="float32",
        unit=UnitOfPressure.KPA,
        translation_key=key,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        display_precision=display_precision,
        scale_factor=scale_factor,
    )


def power_sensor(
    address: int,
    key: str,
    scale_factor: float = 1.0,
    display_precision: int = 1,
    function_code: int = FUNCTION_READ_CHANNELS,
) -> DataSpec:
    """Create a power DataSpec."""
    return DataSpec(
        address=address,
        function_code=function_code,
        key=key,
        data_type="float32",
        unit=UnitOfPower.KILO_WATT,
        translation_key=key,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        display_precision=display_precision,
        scale_factor=scale_factor,
    )


def duration_sensor(
    address: int,
    key: str,
    function_code: int = FUNCTION_READ_PARAMETERS,
) -> DataSpec:
    """Create a duration/time DataSpec."""
    return DataSpec(
        address=address,
        function_code=function_code,
        key=key,
        data_type="uint32",
        unit=UnitOfTime.HOURS,
        translation_key=key,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        display_precision=0,
    )


def measurement_sensor(
    address: int,
    key: str,
    data_type: Literal["int8", "uint8", "uint16", "float32"],
    unit: str | None = None,
    function_code: int = FUNCTION_READ_PARAMETERS,
) -> DataSpec:
    """Create a generic measurement DataSpec."""
    return DataSpec(
        address=address,
        function_code=function_code,
        key=key,
        data_type=data_type,
        unit=unit,
        translation_key=key,
        state_class=SensorStateClass.MEASUREMENT,
        display_precision=1,
    )


def device_property_sensor(
    address: int,
    key: str,
    data_type: Literal["uint8", "uint16", "uint32", "uint64"],
    function_code: int = FUNCTION_READ_PARAMETERS,
) -> DevicePropertySpec:
    """Create a device property spec."""
    return DevicePropertySpec(
        address=address,
        function_code=function_code,
        key=key,
        data_type=data_type,
    )


def diagnostic_sensor(
    address: int,
    key: str,
    data_type: Literal["uint8", "uint16", "uint32", "float32", "datetime", "int8"],
    function_code: int = FUNCTION_READ_PARAMETERS,
    unit: str | None = None,
    scale_factor: float = 1.0,
) -> DataSpec:
    """Create a diagnostic DataSpec."""
    return DataSpec(
        address=address,
        function_code=function_code,
        key=key,
        data_type=data_type,
        unit=unit,
        translation_key=key,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:information-outline",
        device_class=None,
        display_precision=None,
        scale_factor=scale_factor,
    )


WATER_TYPE_A_METADATA = DeviceTypeMetadata(
    type_id=DeviceType.WATER_TYPE_A,
    model_name="Water meter: Pulse Module",
    data_specs=(
        volume_sensor(0x01, "volume", "int32"),
        battery_voltage_sensor(0x0041),
        temperature_sensor(0x0040, "temperature", "int8"),
        diagnostic_sensor(0x0007, "error_flags", "uint16"),
        diagnostic_sensor(
            0x0000, "device_date_time", "datetime", FUNCTION_READ_SYSTEM_TIME
        ),
    ),
    property_specs=(device_property_sensor(0x0002, "firmware_info", "uint64"),),
    property_parser=parse_firmware_info,
)

WATER_TYPE_B_METADATA = DeviceTypeMetadata(
    type_id=DeviceType.WATER_TYPE_B,
    model_name="Water meter: Ultrasonic",
    data_specs=(
        volume_sensor(0x01, "volume", "float32", scale_factor=1000.0),
        volume_sensor(0x02, "volume_reverse", "float32", scale_factor=1000.0),
        flow_rate_sensor(0x0100, FUNCTION_READ_PARAMETERS, scale_factor=1000.0),
        volume_sensor(0x100, "pulse_input_1", "float32", scale_factor=1000.0),
        volume_sensor(0x200, "pulse_input_2", "float32", scale_factor=1000.0),
        volume_sensor(0x400, "pulse_input_3", "float32", scale_factor=1000.0),
        volume_sensor(0x800, "pulse_input_4", "float32", scale_factor=1000.0),
        battery_voltage_sensor(0x0040),
        duration_sensor(0x000A, "operating_time"),
        diagnostic_sensor(0x80, "error_flags", "uint32", FUNCTION_READ_CHANNELS),
        diagnostic_sensor(
            0x0000, "device_date_time", "datetime", FUNCTION_READ_SYSTEM_TIME
        ),
    ),
    property_specs=(device_property_sensor(0x0002, "firmware_info", "uint64"),),
    property_parser=parse_firmware_info,
)

WATER_TYPE_C_METADATA = DeviceTypeMetadata(
    type_id=DeviceType.WATER_TYPE_C,
    model_name="Water meter: Electronic (Type 1)",
    data_specs=(
        volume_sensor(0x01, "volume", "float32", scale_factor=1000.0),
        flow_rate_sensor(0x02, scale_factor=1000.0),
        battery_voltage_sensor(0x0040),
        diagnostic_sensor(0x0010, "error_flags", "uint16"),
        diagnostic_sensor(
            0x0125,
            "flow_threshold_min",
            "float32",
            unit=UnitOfVolumeFlowRate.LITERS_PER_HOUR,
            scale_factor=1000.0,
        ),
        diagnostic_sensor(
            0x0126,
            "flow_threshold_max",
            "float32",
            unit=UnitOfVolumeFlowRate.LITERS_PER_HOUR,
            scale_factor=1000.0,
        ),
        diagnostic_sensor(
            0x0000, "device_date_time", "datetime", FUNCTION_READ_SYSTEM_TIME
        ),
    ),
    property_specs=(device_property_sensor(0x0002, "firmware_info", "uint64"),),
    property_parser=parse_firmware_info,
)

WATER_TYPE_D_METADATA = DeviceTypeMetadata(
    type_id=DeviceType.WATER_TYPE_D,
    model_name="Water meter: Electronic (Type 2)",
    data_specs=(
        volume_sensor(0x01, "volume", "float32", scale_factor=1000.0),
        flow_rate_sensor(0x0100, FUNCTION_READ_PARAMETERS, scale_factor=1000.0),
        battery_voltage_sensor(0x0040),
        diagnostic_sensor(0x80, "error_flags", "uint32"),
        diagnostic_sensor(
            0x0000, "device_date_time", "datetime", FUNCTION_READ_SYSTEM_TIME
        ),
    ),
    property_specs=(device_property_sensor(0x0002, "firmware_info", "uint64"),),
    property_parser=parse_firmware_info,
)

WATER_TYPE_E_METADATA = DeviceTypeMetadata(
    type_id=DeviceType.WATER_TYPE_E,
    model_name="Water meter: Two-Tariff",
    data_specs=(
        temperature_sensor(0x04, "temperature", "float32", FUNCTION_READ_CHANNELS),
        volume_sensor(0x20, "volume_total", "float32", scale_factor=1000.0),
        volume_sensor(0x40, "volume_cold", "float32", scale_factor=1000.0),
        volume_sensor(0x80, "volume_hot", "float32", scale_factor=1000.0),
        flow_rate_sensor(0x100, FUNCTION_READ_CHANNELS, scale_factor=1000.0),
        volume_sensor(0x200, "pulse_input_1", "float32", scale_factor=1000.0),
        volume_sensor(0x400, "pulse_input_2", "float32", scale_factor=1000.0),
        volume_sensor(0x800, "pulse_input_3", "float32", scale_factor=1000.0),
        volume_sensor(0x1000, "pulse_input_4", "float32", scale_factor=1000.0),
        battery_voltage_sensor(0x000A),
        diagnostic_sensor(0x0008, "device_status", "uint8"),
        duration_sensor(0x000C, "operating_time"),
        diagnostic_sensor(0x0006, "error_flags", "uint32"),
        diagnostic_sensor(
            0x0000, "device_date_time", "datetime", FUNCTION_READ_SYSTEM_TIME
        ),
    ),
    property_specs=(device_property_sensor(0x0002, "firmware_info", "uint64"),),
    property_parser=parse_firmware_info,
)

HEAT_TYPE_A_METADATA = DeviceTypeMetadata(
    type_id=DeviceType.HEAT_TYPE_A,
    model_name="Heat Meter Apartment",
    data_specs=(
        volume_sensor(0x01, "volume_supply", "float32", scale_factor=1000.0),
        volume_sensor(0x02, "volume_return", "float32", scale_factor=1000.0),
        temperature_sensor(0x04, "temp_supply", "float32", FUNCTION_READ_CHANNELS),
        temperature_sensor(0x08, "temp_return", "float32", FUNCTION_READ_CHANNELS),
        energy_sensor(0x10, "energy_heat"),
        energy_sensor(0x20, "energy_cooling"),
        duration_sensor(0x40, "operating_time", FUNCTION_READ_CHANNELS),
        diagnostic_sensor(0x80, "error_flags", "uint32", FUNCTION_READ_CHANNELS),
        battery_voltage_sensor(0x0040, "uint16"),
        flow_rate_sensor(0x0100, FUNCTION_READ_PARAMETERS, scale_factor=1000.0),
        volume_sensor(0x100, "pulse_input_1", "float32", scale_factor=1000.0),
        volume_sensor(0x200, "pulse_input_2", "float32", scale_factor=1000.0),
        volume_sensor(0x400, "pulse_input_3", "float32", scale_factor=1000.0),
        volume_sensor(0x800, "pulse_input_4", "float32", scale_factor=1000.0),
        temperature_sensor(0x0130, "temp_diff", "float32", FUNCTION_READ_PARAMETERS),
        temperature_sensor(
            0x0131, "environment_temp", "int8", FUNCTION_READ_PARAMETERS
        ),
        power_sensor(
            0x0170,
            "power_heat",
            scale_factor=1163.0,
            function_code=FUNCTION_READ_PARAMETERS,
        ),
        diagnostic_sensor(
            0x0000, "device_date_time", "datetime", FUNCTION_READ_SYSTEM_TIME
        ),
        pressure_sensor(0x1000, "pressure_supply", scale_factor=1000.0),
        pressure_sensor(0x2000, "pressure_return", scale_factor=1000.0),
    ),
    property_specs=(device_property_sensor(0x0002, "firmware_info", "uint64"),),
    property_parser=parse_firmware_info,
)

HEAT_TYPE_B_METADATA = DeviceTypeMetadata(
    type_id=DeviceType.HEAT_TYPE_B,
    model_name="Heat Meter Apartment (Legacy)",
    data_specs=(
        temperature_sensor(0x04, "temp_supply", "float32", FUNCTION_READ_CHANNELS),
        temperature_sensor(0x08, "temp_return", "float32", FUNCTION_READ_CHANNELS),
        temperature_sensor(0x10, "temp_diff", "float32", FUNCTION_READ_CHANNELS),
        power_sensor(0x20, "power_heat", scale_factor=1163.0),
        energy_sensor(0x40, "energy_heat"),
        energy_sensor(0x100000, "energy_cooling"),
        volume_sensor(0x80, "volume", "float32", scale_factor=1000.0),
        flow_rate_sensor(0x100, FUNCTION_READ_CHANNELS, scale_factor=1000.0),
        volume_sensor(0x200, "pulse_input_1", "float32", scale_factor=1000.0),
        volume_sensor(0x400, "pulse_input_2", "float32", scale_factor=1000.0),
        volume_sensor(0x800, "pulse_input_3", "float32", scale_factor=1000.0),
        volume_sensor(0x1000, "pulse_input_4", "float32", scale_factor=1000.0),
        duration_sensor(0x80000, "operating_time", FUNCTION_READ_CHANNELS),
        pressure_sensor(0x200000, "pressure_supply", scale_factor=1000.0),
        pressure_sensor(0x400000, "pressure_return", scale_factor=1000.0),
        diagnostic_sensor(0x10000000, "error_flags", "uint32", FUNCTION_READ_CHANNELS),
        diagnostic_sensor(
            0x0000, "device_date_time", "datetime", FUNCTION_READ_SYSTEM_TIME
        ),
        battery_voltage_sensor(0x000A),
    ),
    property_specs=(device_property_sensor(0x0002, "firmware_info", "uint64"),),
    property_parser=parse_firmware_info,
)

DEVICE_TYPE_REGISTRY: dict[str, DeviceTypeMetadata] = {
    DeviceType.WATER_TYPE_A: WATER_TYPE_A_METADATA,
    DeviceType.WATER_TYPE_B: WATER_TYPE_B_METADATA,
    DeviceType.WATER_TYPE_C: WATER_TYPE_C_METADATA,
    DeviceType.WATER_TYPE_D: WATER_TYPE_D_METADATA,
    DeviceType.WATER_TYPE_E: WATER_TYPE_E_METADATA,
    DeviceType.HEAT_TYPE_A: HEAT_TYPE_A_METADATA,
    DeviceType.HEAT_TYPE_B: HEAT_TYPE_B_METADATA,
}
