"""Support for Pulsar meters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, translation
from homeassistant.helpers.device_registry import DeviceEntry
import homeassistant.helpers.entity_registry as er

from .const import (
    CONF_DEVICE_CONFIG,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    PLATFORMS,
)
from .coordinator import PulsarDataUpdateCoordinator
from .pulsar_manager import PulsarManager

UNSUB_LISTENER = "unsub_listener"


@dataclass
class HomeAssistantPulsarData:
    """Runtime data for Pulsar integration."""

    device_manager: PulsarManager
    coordinators: dict[str, PulsarDataUpdateCoordinator]


type PulsarConfigEntry = ConfigEntry[HomeAssistantPulsarData]


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: PulsarConfigEntry) -> bool:
    """Set up Pulsar with connection validation."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["device_translations"] = await translation.async_get_translations(
        hass, hass.config.language, "device"
    )

    device_manager = PulsarManager(hass, entry)

    # Test connection before proceeding
    try:
        await hass.async_add_executor_job(device_manager.test_connection)
    except Exception as err:
        raise ConfigEntryNotReady(f"Unable to connect to serial device: {err}") from err

    scan_interval_seconds = entry.options.get(
        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL.total_seconds()
    )
    scan_interval = timedelta(seconds=scan_interval_seconds)

    coordinators: dict[str, PulsarDataUpdateCoordinator] = {}
    devices = device_manager.get_devices(None)

    translations = hass.data[DOMAIN]["device_translations"]
    
    # Register devices in device registry
    device_registry = dr.async_get(hass)
    for device_id, device in devices.items():
        metadata = device.metadata
        model_key = f"component.{DOMAIN}.device.{metadata.type_id}.name"
        model = translations.get(model_key, metadata.model_name)
        
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, device_id)},
            manufacturer=MANUFACTURER,
            name=device.name,
            model=model,
        )

        coordinator = PulsarDataUpdateCoordinator(
            hass, device, device_id, scan_interval=scan_interval
        )
        await coordinator.async_config_entry_first_refresh()
        coordinators[device_id] = coordinator

    entry.runtime_data = HomeAssistantPulsarData(
        device_manager=device_manager, coordinators=coordinators
    )

    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_update_listener(hass: HomeAssistant, config_entry: ConfigEntry):
    """Update listener."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: PulsarConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Remove a config entry from a device."""
    dev_id = next(iter(device_entry.identifiers))[1]

    # Stop and remove coordinator if it exists
    if config_entry.runtime_data and dev_id in config_entry.runtime_data.coordinators:
        coordinator = config_entry.runtime_data.coordinators[dev_id]
        await coordinator.async_shutdown()
        config_entry.runtime_data.coordinators.pop(dev_id)

    # Remove entities
    ent_reg = er.async_get(hass)
    entities = {
        ent.unique_id: ent.entity_id
        for ent in er.async_entries_for_config_entry(ent_reg, config_entry.entry_id)
        if dev_id in ent.unique_id
    }
    for entity_id in entities.values():
        ent_reg.async_remove(entity_id)

    # Remove device from device registry
    device_registry = dr.async_get(hass)
    device_registry.async_remove_device(device_entry.id)

    # Remove device from config entry data if present
    if dev_id in config_entry.data[CONF_DEVICE_CONFIG]:
        new_data = config_entry.data.copy()
        new_data[CONF_DEVICE_CONFIG].pop(dev_id)
        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
        )
        _LOGGER.info("Device %s removed from config entry.", dev_id)
    else:
        _LOGGER.info(
            "Device %s not found in config entry: finalizing device removal", dev_id
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: PulsarConfigEntry) -> bool:
    """Unload a config entry."""
    if (
        unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    ) and entry.runtime_data:
        # Clean up coordinators
        for coordinator in entry.runtime_data.coordinators.values():
            await coordinator.async_shutdown()

        # Disconnect the connector in an executor to avoid blocking the event loop
        if entry.runtime_data.device_manager is not None:
            await hass.async_add_executor_job(
                entry.runtime_data.device_manager.disconnect
            )

    return unload_ok
