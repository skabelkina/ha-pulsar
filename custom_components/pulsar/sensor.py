"""Support for Pulsar devices."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HomeAssistantPulsarData, PulsarConfigEntry
from .const import DOMAIN, MANUFACTURER
from .coordinator import PulsarDataUpdateCoordinator
from .device_specs import DeviceTypeMetadata


def create_sensor_descriptions(
    metadata: DeviceTypeMetadata,
) -> tuple[SensorEntityDescription, ...]:
    """Create sensor descriptions from device metadata."""
    return tuple(
        SensorEntityDescription(
            key=data_spec.key,
            translation_key=data_spec.translation_key or data_spec.key,
            device_class=data_spec.device_class,
            state_class=data_spec.state_class,
            native_unit_of_measurement=data_spec.unit,
            suggested_display_precision=data_spec.display_precision,
            entity_category=data_spec.entity_category,
            icon=data_spec.icon,
            has_entity_name=True,
        )
        for data_spec in metadata.data_specs
    )


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: PulsarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Pulsar sensor dynamically."""
    hass_data: HomeAssistantPulsarData = entry.runtime_data

    @callback
    def async_discover_device(device_ids: list[str]) -> None:
        """Discover and add a discovered Pulsar sensor."""
        entities: list[PulsarSensorEntity] = []
        for device_id in device_ids:
            coordinator = hass_data.coordinators.get(device_id)
            if coordinator is None:
                continue
            device = coordinator.device
            metadata = device.metadata
            descriptions = create_sensor_descriptions(metadata)
            entities.extend(
                PulsarSensorEntity(coordinator, device_id, description)
                for description in descriptions
            )

        async_add_entities(entities)

    async_discover_device([*hass_data.coordinators.keys()])


class PulsarSensorEntity(CoordinatorEntity[PulsarDataUpdateCoordinator], SensorEntity):
    """Pulsar Sensor Entity using coordinator."""

    def __init__(
        self,
        coordinator: PulsarDataUpdateCoordinator,
        device_id: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize Pulsar sensor entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_id = device_id
        self._attr_unique_id = f"pulsar.{device_id}.{description.key}"

    @property
    def available(self) -> bool:  # type: ignore[override]
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self.entity_description.key in self.coordinator.data
        )

    @property
    def native_value(self) -> StateType:  # type: ignore[override]
        """Return the value reported by the sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.key)

    @property
    def device_info(self) -> DeviceInfo:  # type: ignore[override]
        """Return device information."""
        device = self.coordinator.device
        sw_version = self.coordinator.sw_version
        hw_version = self.coordinator.hw_version

        metadata = device.metadata

        translations = self.hass.data.get(DOMAIN, {}).get("device_translations", {})
        model_key = f"component.{DOMAIN}.device.{metadata.type_id}.name"
        model = translations.get(model_key, metadata.model_name)

        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer=MANUFACTURER,
            model=model,
            name=device.name,
            sw_version=str(sw_version) if sw_version is not None else None,
            hw_version=str(hw_version) if hw_version is not None else None,
            serial_number=str(device.serial_number),
        )
